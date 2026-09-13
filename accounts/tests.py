"""Privacy-partition tests: role gates and per-hospital data isolation."""
import datetime
import email.message
import io
import json
import re
from unittest import mock

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.email import (
    MARKER, RESET_LINK, BrevoAPIError, LoggingConsoleEmailBackend,
)
from accounts.forms import RegisterForm
from cbods.validators import (
    detect_ghana_network,
    normalize_ghana_phone_number,
    validate_ghana_phone_number,
)

from accounts.models import Role, User
from donors.tests import make_donor
from hospitals.models import Hospital, StaffProfile
from inventory.models import BagStatus, BloodBag
from organs.models import OrganDonationRequest
from requests_app.models import BloodRequest


class PrivacyPartitionTests(TestCase):
    def setUp(self):
        self.h1 = Hospital.objects.create(name="Alpha", city="Nairobi", address="a", phone="1")
        self.h2 = Hospital.objects.create(name="Beta", city="Mombasa", address="b", phone="2")
        self.hidden = Hospital.objects.create(name="Ghost", city="Kisumu", address="c", phone="3", is_hidden=True)

        self.staff1 = User.objects.create_user(username="s1", password="x", role=Role.HOSPITAL_STAFF)
        StaffProfile.objects.create(user=self.staff1, hospital=self.h1)
        self.staff2 = User.objects.create_user(username="s2", password="x", role=Role.HOSPITAL_STAFF)
        StaffProfile.objects.create(user=self.staff2, hospital=self.h2)

        self.donor = make_donor("privdonor", city="Nairobi")
        self.patient = User.objects.create_user(username="privpat", password="x", role=Role.PATIENT)
        self.admin = User.objects.create_user(username="privadmin", password="x", role=Role.ADMIN)

        today = timezone.localdate()
        BloodBag.objects.create(
            hospital=self.h2, blood_group="O+", collected_date=today,
            expiry_date=today + datetime.timedelta(days=30),
            status=BagStatus.AVAILABLE,
        )
        self.req_h2 = BloodRequest.objects.create(
            patient=self.patient, hospital=self.h2, blood_group="O+", units_requested=1
        )
        self.organ_h2 = OrganDonationRequest.objects.create(
            donor=self.donor, hospital=self.h2, organ_type="KIDNEY"
        )

    def test_donor_cannot_load_staff_urls(self):
        self.client.force_login(self.donor.user)
        for url in ["/inventory/stock/", "/inventory/donate/", "/inventory/tti/",
                    "/requests/inbox/", "/donors/screening/", "/organs/review/",
                    "/donors/search/", "/requests/match/"]:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_patient_cannot_see_donors(self):
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get("/donors/search/").status_code, 403)
        self.assertEqual(self.client.get("/donors/approvals/").status_code, 403)
        self.assertEqual(self.client.get("/organs/review/").status_code, 403)

    def test_staff_cannot_see_other_hospitals_data(self):
        self.client.force_login(self.staff1)
        # inventory page never shows h2 bags
        r = self.client.get("/inventory/stock/")
        self.assertEqual(r.context["hospital"], self.h1)
        # h2's blood request invisible in inbox and unreachable by action
        r = self.client.get("/requests/inbox/")
        self.assertNotIn(self.req_h2, r.context["reqs"])
        r = self.client.post(f"/requests/action/{self.req_h2.pk}/", {"action": "accept"})
        self.assertEqual(r.status_code, 404)
        # h2's organ request invisible and unreachable
        r = self.client.get("/organs/review/")
        self.assertNotIn(self.organ_h2, r.context["reqs"])
        r = self.client.post(f"/organs/review/{self.organ_h2.pk}/", {"status": "APPROVED"})
        self.assertEqual(r.status_code, 404)

    def test_hidden_hospital_invisible_to_patient(self):
        self.client.force_login(self.patient)
        r = self.client.get("/requests/hospitals/")
        self.assertNotContains(r, "Ghost")
        self.assertEqual(self.client.get(f"/requests/new/{self.hidden.pk}/").status_code, 404)

    def test_hidden_hospital_visible_to_admin(self):
        self.assertIn(self.hidden, Hospital.objects.visible_to(self.admin))

    def test_unapproved_donor_not_in_search(self):
        pending = make_donor("pending2", status="PENDING")
        unavailable = make_donor("unavail", status="APPROVED")
        unavailable.is_available = False
        unavailable.save()
        self.client.force_login(self.staff1)
        r = self.client.get("/donors/search/")
        self.assertNotContains(r, "Donor pending2")
        self.assertNotContains(r, "Donor unavail")
        self.assertContains(r, "Donor privdonor")


class DuplicateEmailRegistrationTests(TestCase):
    """Signup refuses an email an active account already uses.

    Django's password reset sends one mail per matching active account, so a
    duplicated address meant password-reset emails arrived twice, each with
    a different account's link. This guard keeps one address = one account.
    """

    def setUp(self):
        self.existing = User.objects.create_user(
            username="firstowner",
            email="taken@example.com",
            password="FirstPass!2468",
        )

    def signup(self, email, **overrides):
        data = {
            "username": "secondcomer",
            "email": email,
            "phone": "241234567",
            "role": "DONOR",
            "password1": "Tumbleweed-Cortex-71",
            "password2": "Tumbleweed-Cortex-71",
            **overrides,
        }
        return self.client.post("/accounts/register/", data)

    def test_signup_with_a_taken_email_is_rejected(self):
        response = self.signup("taken@example.com")
        self.assertEqual(response.status_code, 200)  # form redisplayed
        self.assertContains(response, "already registered with this email")
        self.assertFalse(User.objects.filter(username="secondcomer").exists())

    def test_the_check_is_case_insensitive(self):
        """The reset lookup treats addresses case-insensitively, so the guard
        must too — otherwise Mixed@Case.com sneaks past."""
        response = self.signup("TAKEN@EXAMPLE.COM")
        self.assertContains(response, "already registered with this email")
        self.assertFalse(User.objects.filter(username="secondcomer").exists())

    def test_deactivated_account_releases_the_email(self):
        """Only active accounts hold the claim: staff can deactivate an old
        account and its address becomes signable again."""
        self.existing.is_active = False
        self.existing.save(update_fields=["is_active"])
        response = self.signup("taken@example.com", username="freecomers")
        self.assertEqual(response.status_code, 302)  # registered
        self.assertTrue(User.objects.filter(username="freecomers").exists())

    def test_a_fresh_email_still_registers(self):
        response = self.signup("brandnew@example.com", username="freshface")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="freshface").exists())


class WelcomeNotificationTests(TestCase):
    """Successful registration greets the new account by email and SMS.

    Email: in-app row + mail, through notifications.notify. SMS: through
    accounts.sms with the console provider the test runner keeps, so the
    send is observable without a gateway. Neither channel may break signup.
    """

    def register(self, **overrides):
        data = {
            "username": "newcomer",
            "email": "newcomer@example.com",
            "phone": "241234567",
            "role": "DONOR",
            "password1": "Tumbleweed-Cortex-71",
            "password2": "Tumbleweed-Cortex-71",
            **overrides,
        }
        return self.client.post("/accounts/register/", data)

    def test_registration_sends_welcome_email(self):
        mail.outbox = []
        self.register()
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Welcome to CBODS")
        self.assertEqual(message.to, ["newcomer@example.com"])
        self.assertIn("newcomer", message.body)

    def test_registration_logs_the_welcome_sms(self):
        with self.assertLogs("cbods.sms", level="WARNING") as captured:
            self.register()
        joined = "\n".join(captured.output)
        self.assertIn("CBODS-RESET-SMS", joined)
        self.assertIn("+233241234567", joined)
        self.assertIn("Welcome", joined)

    def test_account_without_phone_skips_sms_but_still_emails(self):
        """The signup form requires a phone, but accounts can exist without one
        (seeded or admin-created): the helper must not blow up on them."""
        from accounts.views import _send_welcome_notifications

        user = User.objects.create_user(
            username="nophonewelcome", email="nophone@example.com", password="x"
        )
        mail.outbox = []
        with self.assertNoLogs("cbods.sms", level="WARNING"):
            _send_welcome_notifications(user)
        self.assertEqual(len(mail.outbox), 1)

    def test_sms_failure_does_not_break_registration(self):
        with mock.patch(
            "accounts.sms.send_sms", side_effect=Exception("gateway down")
        ):
            response = self.register()
        self.assertEqual(response.status_code, 302)  # registered and logged in
        self.assertTrue(User.objects.filter(username="newcomer").exists())

    def test_welcome_email_failure_does_not_break_registration(self):
        with mock.patch(
            "notifications.services.send_mail", side_effect=Exception("relay down")
        ):
            response = self.register()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="newcomer").exists())


class LoginUsernamePersistenceTests(TestCase):
    """A failed login keeps the submitted username in the input.

    The username input is hand-written in login.html, so without an explicit
    value attribute Django's re-render dropped what the user typed — leaving
    them unsure whether the username or the password was the problem.
    """

    def setUp(self):
        User.objects.create_user(
            username="keptname", email="kept@example.com", password="RightPass!2468"
        )

    def username_input_value(self, response):
        """The value attribute of the username input, wherever it sits in the page."""
        match = re.search(
            r'id="id_username".*?value="([^"]*)"',
            response.content.decode(),
            re.DOTALL,
        )
        self.assertIsNotNone(match, "username input not rendered")
        return match.group(1)

    def test_failed_login_keeps_the_submitted_username(self):
        r = self.client.post(
            "/accounts/login/", {"username": "keptname", "password": "wrong"}
        )
        self.assertEqual(self.username_input_value(r), "keptname")

    def test_first_load_shows_an_empty_username_field(self):
        r = self.client.get("/accounts/login/")
        self.assertEqual(self.username_input_value(r), "")

    def test_forgot_password_link_carries_the_submitted_username(self):
        r = self.client.post(
            "/accounts/login/", {"username": "kept name", "password": "wrong"}
        )
        self.assertContains(r, "username=kept%20name")

    def test_reset_form_shows_the_carried_username(self):
        r = self.client.get("/accounts/password-reset/", {"username": "keptname"})
        self.assertContains(r, "Resetting the password for account:")
        self.assertContains(r, "<strong>keptname</strong>")

    def test_reset_form_renders_an_empty_page_without_the_param(self):
        r = self.client.get("/accounts/password-reset/")
        self.assertNotContains(r, "Resetting the password for account:")

    def test_reset_form_escapes_the_carried_username(self):
        """The reminder echoes user-typed text, so it must not execute it."""
        r = self.client.get(
            "/accounts/password-reset/", {"username": "<script>alert(1)</script>"}
        )
        self.assertNotContains(r, "<script>alert(1)</script>")
        self.assertContains(r, "&lt;script&gt;")


class PasswordResetFlowTests(TestCase):
    """Django's token-link reset, wired to this project's templates."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="resetme", email="resetme@example.com", password="OldPass!2468", role=Role.PATIENT
        )
        mail.outbox = []

    def request_reset(self, email):
        return self.client.post("/accounts/password-reset/", {"email": email})

    def link_from_email(self):
        """The confirm URL as the recipient would follow it."""
        body = mail.outbox[0].body
        match = re.search(r"/accounts/reset/[^/]+/[^/\s]+/", body)
        self.assertIsNotNone(match, f"no reset link in email:\n{body}")
        return match.group(0)

    def test_login_page_offers_the_link(self):
        self.assertContains(self.client.get("/accounts/login/"), "Forgot password?")

    def test_known_address_is_sent_a_link(self):
        response = self.request_reset("resetme@example.com")
        self.assertRedirects(response, "/accounts/password-reset/sent/")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Reset your CBODS password")
        self.assertIn("resetme", mail.outbox[0].body)

    def test_unknown_address_reveals_nothing(self):
        """Same page, no email. Confirming which addresses are registered would
        leak who is a donor or patient."""
        response = self.request_reset("nobody@example.com")
        self.assertRedirects(response, "/accounts/password-reset/sent/")
        self.assertEqual(len(mail.outbox), 0)
        page = self.client.get("/accounts/password-reset/sent/")
        self.assertContains(page, "If an account exists")

    def test_reset_link_scheme_matches_the_request_scheme(self):
        """An HTTP-served app emails http:// links; a TLS-served one https://.

        The form used to hardcode https, which produced links no browser could
        open on a local HTTP server (ERR_SSL_PROTOCOL_ERROR).
        """
        self.request_reset("resetme@example.com")
        self.assertIn("http://testserver/accounts/reset/", mail.outbox[0].body)

        from django.test import RequestFactory
        from accounts.urls import HttpsPasswordResetForm

        rf = RequestFactory()
        form = HttpsPasswordResetForm({"email": "resetme@example.com"})
        self.assertTrue(form.is_valid())
        mail.outbox = []
        form.save(request=rf.get("/", secure=True))
        self.assertIn("https://testserver/accounts/reset/", mail.outbox[0].body)

    def test_address_on_two_accounts_sends_two_links(self):
        """Django's reset matches by email, one mail per matching active
        account. A shared inbox therefore gets one mail per account — each
        body names its own username, so recipients can tell them apart."""
        User.objects.create_user(
            username="secondacct", email="resetme@example.com", password="x"
        )
        self.request_reset("resetme@example.com")
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            sorted(m.body.count("/accounts/reset/") for m in mail.outbox), [1, 1]
        )

    def test_link_sets_a_new_password_and_old_one_stops_working(self):
        self.request_reset("resetme@example.com")
        # Django redirects the token URL to a session-backed one before showing
        # the form, so follow it rather than posting to the emailed address.
        form_url = self.client.get(self.link_from_email(), follow=True).redirect_chain[-1][0]
        response = self.client.post(
            form_url, {"new_password1": "Fresh-Pass-9182", "new_password2": "Fresh-Pass-9182"}
        )
        self.assertRedirects(response, "/accounts/reset/done/")

        self.assertFalse(self.client.login(username="resetme", password="OldPass!2468"))
        self.assertTrue(self.client.login(username="resetme", password="Fresh-Pass-9182"))

    def test_link_cannot_be_used_twice(self):
        self.request_reset("resetme@example.com")
        link = self.link_from_email()
        form_url = self.client.get(link, follow=True).redirect_chain[-1][0]
        self.client.post(form_url, {"new_password1": "Fresh-Pass-9182", "new_password2": "Fresh-Pass-9182"})

        replayed = self.client.get(link, follow=True)
        self.assertContains(replayed, "no longer valid")

    def test_new_password_must_satisfy_the_validators(self):
        self.request_reset("resetme@example.com")
        form_url = self.client.get(self.link_from_email(), follow=True).redirect_chain[-1][0]
        response = self.client.post(form_url, {"new_password1": "123456", "new_password2": "123456"})
        self.assertEqual(response.status_code, 200)  # redisplayed, not accepted
        self.assertTrue(self.client.login(username="resetme", password="OldPass!2468"))


class ResetEmailRoutingTests(TestCase):
    """Reset emails go to the address on the account — and only that address.

    Complement to PasswordResetFlowTests: those check the flow end to end, these
    pin down the recipient so the address shown on the account is the one that
    receives the link, and an unregistered address receives nothing at all.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="routed", email="routed@example.com",
            password="OldPass!2468", role=Role.PATIENT,
        )
        mail.outbox = []

    def test_email_is_addressed_to_the_account_address(self):
        self.client.post("/accounts/password-reset/", {"email": self.user.email})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_only_the_matching_account_receives_a_link(self):
        other = User.objects.create_user(
            username="routedother", email="other@example.com",
            password="OldPass!2468",
        )
        self.client.post("/accounts/password-reset/", {"email": self.user.email})
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn(other.email, mail.outbox[0].to)
        # A reset for the other address reaches only that account.
        self.client.post("/accounts/password-reset/", {"email": other.email})
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[1].to, [other.email])

    def test_unregistered_address_produces_no_email_at_all(self):
        self.client.post("/accounts/password-reset/", {"email": "ghost@example.com"})
        self.assertEqual(len(mail.outbox), 0)


class ResetLinkExpiryWordingTests(TestCase):
    """Everything that states the link's lifetime agrees with the setting.

    PASSWORD_RESET_TIMEOUT and the human-facing wording (email body, done
    page, invalid-link page) live in different files; the settings comment
    requires them to move together. These tests fail if one changes without
    the other — e.g. wording says 12 hours while links actually last 24.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="expirywording", email="expiry@example.com", password="OldPass!2468"
        )
        mail.outbox = []

    def stated_hours(self):
        self.assertEqual(settings.PASSWORD_RESET_TIMEOUT % 3600, 0)
        return settings.PASSWORD_RESET_TIMEOUT // 3600

    def test_email_states_the_configured_expiry(self):
        self.client.post("/accounts/password-reset/", {"email": self.user.email})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(
            f"This link expires in {self.stated_hours()} hours.",
            mail.outbox[0].body,
        )

    def test_done_page_states_the_configured_expiry(self):
        self.assertContains(
            self.client.get("/accounts/password-reset/sent/"),
            f"expires in {self.stated_hours()} hours",
        )

    def test_invalid_link_page_states_the_configured_expiry(self):
        # Any uid/token pair shows the "no longer valid" page, which repeats
        # the expiry figure next to the request-a-new-link button.
        self.assertContains(
            self.client.get("/accounts/reset/Mg/stale-token/"),
            f"expire after {self.stated_hours()} hours",
        )


class ResetLinkLoggingTests(TestCase):
    """The email backend flags reset links so they can be found in a busy log.

    Exercised directly: the test runner substitutes the locmem backend, so the
    configured one never runs during the view tests above.
    """

    def send(self, body, to="someone@example.com"):
        backend = LoggingConsoleEmailBackend(stream=io.StringIO())
        message = EmailMessage(
            subject="Reset your CBODS password", body=body,
            from_email="noreply@cbods.local", to=[to],
        )
        message.connection = backend
        return backend.send_messages([message])

    def test_reset_link_is_logged_behind_the_marker(self):
        link = "http://localhost:8000/accounts/reset/Mg/abc123-def456/"
        with self.assertLogs("cbods.email", level="WARNING") as captured:
            sent = self.send(f"Open this link:\n\n{link}\n\nIt expires in 12 hours.")
        self.assertEqual(sent, 1)
        line = captured.output[0]
        self.assertIn(MARKER, line)
        self.assertIn(link, line)
        self.assertIn("someone@example.com", line)

    def test_other_mail_is_not_flagged(self):
        """Notifications go through the same backend and must stay quiet."""
        with self.assertNoLogs("cbods.email", level="WARNING"):
            sent = self.send("Your blood request at Demo Accra Central was accepted.")
        self.assertEqual(sent, 1)

    def test_marker_matches_the_real_email_template(self):
        """Guards the regex against a change in how the link is rendered."""
        user = User.objects.create_user(
            username="markertest", email="marker@example.com", password="OldPass!2468"
        )
        self.client.post("/accounts/password-reset/", {"email": user.email})
        self.assertEqual(len(mail.outbox), 1)
        self.assertRegex(mail.outbox[0].body, RESET_LINK)


class RetryingSMTPBackendTests(TestCase):
    """The connect-stall retry loop behind live password-reset delivery.

    This network's link to the relay drops a large share of plain SMTP
    connects (the banner never arrives; smtplib times out). Django's reset
    views send with fail_silently=True, so without a retry a stalled connect
    silently loses the email while the user sees "check your inbox". These
    tests run against a stubbed superclass so no network is touched.
    """

    def make_backend(self):
        from accounts.email import RetryingSMTPBackend

        return RetryingSMTPBackend(host="smtp-relay.example.com", port=587)

    def stub_open(self, outcomes):
        """Replace SMTPEmailBackend.open with a callable yielding outcomes.

        Each outcome is either an exception instance (raised) or a return
        value; the list is consumed left to right, the last value repeats.
        """
        calls = []

        def fake_open(inner_self):
            calls.append(1)
            outcome = outcomes[min(len(calls), len(outcomes)) - 1]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        return mock.patch(
            "django.core.mail.backends.smtp.EmailBackend.open",
            autospec=True,
            side_effect=fake_open,
        ), calls

    def test_success_on_first_attempt_makes_one_connection(self):
        patcher, calls = self.stub_open([True])
        with patcher:
            self.assertTrue(self.make_backend().open())
        self.assertEqual(len(calls), 1)

    def test_stalled_connect_is_retried_until_it_succeeds(self):
        import smtplib

        stall = smtplib.SMTPServerDisconnected(
            "Connection unexpectedly closed: timed out"
        )
        patcher, calls = self.stub_open([stall, stall, True])
        with patcher, mock.patch("accounts.email.time.sleep"):
            self.assertTrue(self.make_backend().open())
        self.assertEqual(len(calls), 3)

    def test_gives_up_after_four_attempts_and_reraises(self):
        import smtplib

        stall = smtplib.SMTPServerDisconnected(
            "Connection unexpectedly closed: timed out"
        )
        patcher, calls = self.stub_open([stall])
        backend = self.make_backend()
        with patcher, mock.patch("accounts.email.time.sleep"):
            with self.assertRaises(smtplib.SMTPServerDisconnected):
                backend.open()
        self.assertEqual(backend.MAX_ATTEMPTS, 4)
        self.assertEqual(len(calls), 4)

    def test_auth_rejection_is_not_retried(self):
        """SMTPAuthenticationError is an SMTPException (an OSError), but a bad
        password stays bad no matter how often you reconnect — it must
        propagate on the first attempt."""
        from smtplib import SMTPAuthenticationError

        auth_fail = SMTPAuthenticationError(535, b"5.7.8 Authentication failed")
        patcher, calls = self.stub_open([auth_fail])
        with patcher, mock.patch("accounts.email.time.sleep"):
            with self.assertRaises(SMTPAuthenticationError):
                self.make_backend().open()
        self.assertEqual(len(calls), 1)

    def test_each_attempt_logs_and_the_last_reraises_loudly(self):
        import smtplib

        stall = smtplib.SMTPServerDisconnected("Connection unexpectedly closed")
        patcher, calls = self.stub_open([stall])
        backend = self.make_backend()
        with patcher, mock.patch("accounts.email.time.sleep"):
            with self.assertLogs("cbods.email", level="WARNING") as captured:
                with self.assertRaises(smtplib.SMTPServerDisconnected):
                    backend.open()
        # One line per failed attempt: 3 retries + the final raise.
        self.assertEqual(len(captured.output), backend.MAX_ATTEMPTS)
        self.assertIn("attempt 1/4", captured.output[0])
        self.assertIn("retrying", captured.output[0])
        self.assertIn("failed after 4 attempts", captured.output[-1])

    def test_retry_cleans_up_the_partial_connection(self):
        """Django's open() leaves _partial_connection behind on failure; the
        retry must drop it before reconnecting."""
        import smtplib

        stall = smtplib.SMTPServerDisconnected("Connection unexpectedly closed")
        patcher, calls = self.stub_open([stall, True])
        backend = self.make_backend()
        # Pre-place the kind of leftover Django's failed open() leaves behind.
        leftover = mock.Mock()
        backend._partial_connection = leftover

        with patcher, mock.patch("accounts.email.time.sleep"):
            self.assertTrue(backend.open())
        self.assertEqual(len(calls), 2)
        self.assertIsNone(backend._partial_connection)
        leftover.quit.assert_called_once()


class BrevoHTTPSBackendTests(TestCase):
    """The Brevo HTTPS-API backend: payload shape, success verdict, and the
    bounded retry over the transient family (unreachable, 429, 5xx).

    urlopen is stubbed, so no network is touched and status codes are
    simulated with real HTTPError objects. A timeout must map to a retryable
    failure because that is exactly what a stalled port-587 network does to
    an HTTPS call too.
    """

    def make_backend(self, **kwargs):
        from accounts.email import BrevoHTTPSBackend

        return BrevoHTTPSBackend(api_key="xkeysib-test", **kwargs)

    def send(self, backend, **msg_kwargs):
        message = EmailMessage(
            subject=msg_kwargs.pop("subject", "Reset your CBODS password"),
            body=msg_kwargs.pop("body", "Open http://localhost:8000/accounts/reset/Mg/tok/"),
            from_email=msg_kwargs.pop("from_email", "noreply@cbods.local"),
            **msg_kwargs,
        )
        message.encoding = "utf-8"
        return backend.send_messages([message])

    def urlopen_stub(self, responses):
        """Replace accounts.email.urllib.request.urlopen with a callable
        yielding responses left to right (the last repeats). An HTTPError
        instance is raised; anything else is the context-manager value."""
        calls = []

        class FakeResponse:
            status = 201

            def read(self):
                return json.dumps({"messageIds": ["mid-1"]}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(request, timeout=None):
            calls.append(json.loads(request.data.decode()))
            # urllib capitalizes header names when storing them.
            self.assertEqual(request.get_header("Api-key"), "xkeysib-test")
            outcome = responses[min(len(calls), len(responses)) - 1]
            if isinstance(outcome, Exception):
                raise outcome
            # None means "a 201 with messageIds".
            return outcome if outcome is not None else FakeResponse()

        return (
            mock.patch(
                "accounts.email.urllib.request.urlopen", side_effect=fake_urlopen
            ),
            calls,
        )

    def http_error(self, code):
        import urllib.error

        return urllib.error.HTTPError(
            url="https://api.brevo.com/v3/smtp/email",
            code=code,
            msg="Error",
            hdrs=email.message.Message(),
            fp=io.BytesIO(b'{"code":"error","message":"nope"}'),
        )

    def test_payload_carries_the_api_contract(self):
        patcher, calls = self.urlopen_stub([None])
        backend = self.make_backend()
        with patcher:
            self.assertEqual(self.send(backend, to=["staff@example.com"]), 1)
        payload = calls[0]
        self.assertEqual(payload["sender"]["email"], "noreply@cbods.local")
        self.assertEqual(payload["to"], [{"email": "staff@example.com", "name": None}])
        self.assertEqual(payload["subject"], "Reset your CBODS password")
        self.assertIn("/accounts/reset/", payload["textContent"])

    def test_display_name_is_parsed_out_of_the_from_header(self):
        patcher, calls = self.urlopen_stub([None])
        backend = self.make_backend()
        with patcher:
            self.send(backend, to=["a@example.com"], from_email="CBODS <noreply@cbods.local>")
        self.assertEqual(
            calls[0]["sender"], {"email": "noreply@cbods.local", "name": "CBODS"}
        )

    def test_cc_bcc_and_reply_to_are_forwarded(self):
        patcher, calls = self.urlopen_stub([None])
        backend = self.make_backend()
        with patcher:
            self.send(
                backend,
                to=["a@example.com"],
                cc=["b@example.com"],
                bcc=["c@example.com"],
                reply_to=["help@example.com"],
            )
        payload = calls[0]
        self.assertEqual(payload["cc"], [{"email": "b@example.com", "name": None}])
        self.assertEqual(payload["bcc"], [{"email": "c@example.com", "name": None}])
        self.assertEqual(payload["replyTo"], [{"email": "help@example.com", "name": None}])

    def test_bcc_only_message_falls_back_to_sender_in_to(self):
        """Brevo requires a 'to' entry; the sender stands in for one."""
        patcher, calls = self.urlopen_stub([None])
        backend = self.make_backend()
        with patcher:
            self.send(backend, to=[], bcc=["hidden@example.com"])
        self.assertEqual(calls[0]["to"], [{"email": "noreply@cbods.local", "name": None}])
        self.assertEqual(calls[0]["bcc"], [{"email": "hidden@example.com", "name": None}])

    def test_attachment_message_wraps_the_body_in_html_content(self):
        patcher, calls = self.urlopen_stub([None])
        backend = self.make_backend()
        with patcher:
            self.send(
                backend, to=["a@example.com"],
                body="Blood drive <this> Saturday",
                attachments=[("roster.csv", b"x,y", "text/csv")],
            )
        self.assertNotIn("textContent", calls[0])
        self.assertIn("htmlContent", calls[0])
        self.assertIn("Blood drive &lt;this&gt; Saturday", calls[0]["htmlContent"])

    def test_success_on_first_attempt_makes_one_request(self):
        patcher, calls = self.urlopen_stub([None])
        with patcher:
            self.assertEqual(self.send(self.make_backend(), to=["a@example.com"]), 1)
        self.assertEqual(len(calls), 1)

    def test_unreachable_and_5xx_are_retried_until_success(self):
        import urllib.error

        unreachable = urllib.error.URLError(OSError("timed out"))
        patcher, calls = self.urlopen_stub(
            [unreachable, self.http_error(503), None]
        )
        backend = self.make_backend()
        with patcher, mock.patch("accounts.email.time.sleep") as sleeps:
            self.assertEqual(self.send(backend, to=["a@example.com"]), 1)
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(sleeps.call_args_list), 2)

    def test_gives_up_after_four_attempts_and_raises(self):
        import urllib.error

        unreachable = urllib.error.URLError(OSError("connection reset"))
        patcher, calls = self.urlopen_stub([unreachable])
        backend = self.make_backend()
        with patcher, mock.patch("accounts.email.time.sleep"):
            with self.assertRaises(BrevoAPIError):
                self.send(backend, to=["a@example.com"])
        self.assertEqual(backend.MAX_ATTEMPTS, 4)
        self.assertEqual(len(calls), 4)

    def test_timeout_maps_to_a_retryable_failure(self):
        patcher, calls = self.urlopen_stub([TimeoutError("read timed out"), None])
        with patcher, mock.patch("accounts.email.time.sleep"):
            self.assertEqual(self.send(self.make_backend(), to=["a@example.com"]), 1)
        self.assertEqual(len(calls), 2)

    def test_auth_and_budget_and_payload_errors_are_not_retried(self):
        for code in (400, 401, 402, 403):
            with self.subTest(code=code):
                patcher, calls = self.urlopen_stub([self.http_error(code)])
                backend = self.make_backend()
                with patcher, mock.patch("accounts.email.time.sleep"):
                    with self.assertRaises(BrevoAPIError) as caught:
                        self.send(backend, to=["a@example.com"])
                self.assertEqual(len(calls), 1)
                self.assertFalse(caught.exception.retryable)

    def test_429_is_retried(self):
        patcher, calls = self.urlopen_stub([self.http_error(429), None])
        with patcher, mock.patch("accounts.email.time.sleep"):
            self.assertEqual(self.send(self.make_backend(), to=["a@example.com"]), 1)
        self.assertEqual(len(calls), 2)

    def test_fail_silently_returns_zero_and_logs(self):
        import urllib.error

        unreachable = urllib.error.URLError(OSError("no route to host"))
        patcher, _ = self.urlopen_stub([unreachable])
        backend = self.make_backend(fail_silently=True)
        with patcher, mock.patch("accounts.email.time.sleep"):
            with self.assertLogs("cbods.email", level="WARNING") as captured:
                self.assertEqual(self.send(backend, to=["a@example.com"]), 0)
        self.assertIn("Brevo send to a@example.com failed", captured.output[-1])

    def test_each_attempt_logs_and_the_last_raises_loudly(self):
        import urllib.error

        unreachable = urllib.error.URLError(OSError("timed out"))
        patcher, calls = self.urlopen_stub([unreachable])
        backend = self.make_backend()
        with patcher, mock.patch("accounts.email.time.sleep"):
            with self.assertLogs("cbods.email", level="WARNING") as captured:
                with self.assertRaises(BrevoAPIError):
                    self.send(backend, to=["a@example.com"])
        self.assertEqual(len(captured.output), backend.MAX_ATTEMPTS)
        self.assertIn("attempt 1/4", captured.output[0])
        self.assertIn("retrying", captured.output[0])
        self.assertIn("failed after 4 attempt(s)", captured.output[-1])

    def test_send_to_every_failing_recipient_reports_zero(self):
        import urllib.error

        unreachable = urllib.error.URLError(OSError("timed out"))
        patcher, calls = self.urlopen_stub([unreachable])
        backend = self.make_backend(fail_silently=True)
        with patcher, mock.patch("accounts.email.time.sleep"):
            sent = backend.send_messages(
                [EmailMessage("Hi", "x", "noreply@cbods.local", to=[f"u{i}@example.com"]) for i in range(3)]
            )
        self.assertEqual(sent, 0)
        self.assertEqual(len(calls), 12)  # 4 attempts x 3 messages

    def test_fail_silently_batch_survives_one_dead_message(self):
        """fail_silently continues a batch past a failed message: HTTP
        failures are per-request, unlike SMTP where one dead connection
        would take the rest of the batch down with it."""
        import urllib.error

        unreachable = urllib.error.URLError(OSError("timed out"))
        # Four unreachable outcomes burn the bad message's whole retry
        # budget (the single-outcome list repeats, so four entries are
        # needed); the Nones are the two good messages' first attempts.
        patcher, calls = self.urlopen_stub(
            [unreachable, unreachable, unreachable, unreachable, None, None]
        )
        backend = self.make_backend(fail_silently=True)
        messages = [
            EmailMessage("Hi", "x", "noreply@cbods.local", to=["bad@example.com"]),
            EmailMessage("Hi", "x", "noreply@cbods.local", to=["good1@example.com"]),
            EmailMessage("Hi", "x", "noreply@cbods.local", to=["good2@example.com"]),
        ]
        with patcher, mock.patch("accounts.email.time.sleep"):
            self.assertEqual(backend.send_messages(messages), 2)
        self.assertEqual(len(calls), 6)  # 4 attempts for the bad one, 1 each

    def test_unsilent_failure_aborts_the_batch_by_raising(self):
        """Without fail_silently a dead message raises — the caller decides
        what happens next, as with Django's own backends."""
        import urllib.error

        unreachable = urllib.error.URLError(OSError("timed out"))
        patcher, calls = self.urlopen_stub([unreachable])
        backend = self.make_backend()
        messages = [
            EmailMessage("Hi", "x", "noreply@cbods.local", to=["bad@example.com"]),
            EmailMessage("Hi", "x", "noreply@cbods.local", to=["good@example.com"]),
        ]
        with patcher, mock.patch("accounts.email.time.sleep"):
            with self.assertRaises(BrevoAPIError):
                backend.send_messages(messages)
        self.assertEqual(len(calls), 4)  # bad message's whole budget
        self.assertEqual(calls[0]["to"], [{"email": "bad@example.com", "name": None}])

    def test_empty_recipient_list_is_rejected_before_any_request(self):
        patcher, calls = self.urlopen_stub([None])
        backend = self.make_backend()
        with patcher:
            with self.assertRaises(BrevoAPIError):
                self.send(backend, to=[])
        self.assertEqual(calls, [])

    def test_response_without_message_ids_is_accepted_but_logged(self):
        class BareResponse:
            def read(self):
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        patcher, calls = self.urlopen_stub([BareResponse()])
        with patcher, self.assertLogs("cbods.email", level="WARNING") as captured:
            self.assertEqual(self.send(self.make_backend(), to=["a@example.com"]), 1)
        self.assertIn("messageIds", captured.output[0])


class PasswordRuleFeedbackTests(TestCase):
    """The register page checklist must agree with AUTH_PASSWORD_VALIDATORS."""

    url = "/accounts/password-rules/"

    def post(self, password, **extra):
        r = self.client.post(self.url, {"password": password, **extra})
        self.assertEqual(r.status_code, 200)
        return r.json()["results"]

    def test_blank_password_reports_every_rule_unmet(self):
        # Only the length validator rejects "" on its own, but a pristine form
        # must not show green ticks.
        results = self.post("")
        self.assertTrue(results)
        self.assertFalse(any(results.values()))

    def test_short_common_numeric_password_fails_those_rules(self):
        results = self.post("123456")
        self.assertFalse(results["MinimumLengthValidator"])
        self.assertFalse(results["CommonPasswordValidator"])
        self.assertFalse(results["NumericPasswordValidator"])

    def test_length_rule_passes_once_long_enough(self):
        self.assertTrue(self.post("9182736455")["MinimumLengthValidator"])

    def test_similarity_rule_uses_the_unsubmitted_username(self):
        # The probe user is unsaved, so this works before registration.
        results = self.post("elkanah43", username="elkanah43")
        self.assertFalse(results["UserAttributeSimilarityValidator"])
        self.assertTrue(self.post("elkanah43")["UserAttributeSimilarityValidator"])

    def test_strong_password_meets_every_rule(self):
        results = self.post("Tumbleweed-Cortex-71", username="elkanah43", email="e@example.com")
        self.assertTrue(all(results.values()), results)

    def test_endpoint_rejects_get(self):
        # Keeps the password out of query strings and access logs.
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_register_page_renders_a_rule_per_validator(self):
        r = self.client.get("/accounts/register/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            [rule["id"] for rule in r.context["password_rules"]],
            ["UserAttributeSimilarityValidator", "MinimumLengthValidator",
             "CommonPasswordValidator", "NumericPasswordValidator"],
        )
        self.assertContains(r, 'data-rule="MinimumLengthValidator"')

    def test_verdicts_match_the_real_registration_form(self):
        from accounts.forms import RegisterForm

        for password in ["123456", "elkanah43", "Tumbleweed-Cortex-71"]:
            with self.subTest(password=password):
                form = RegisterForm({
                    "username": "elkanah43", "email": "e@example.com", "phone": "241234567",
                    "role": "DONOR", "password1": password, "password2": password,
                })
                accepted = all(self.post(password, username="elkanah43", email="e@example.com").values())
                self.assertEqual(form.is_valid(), accepted, form.errors)
class EmailTldValidationTests(TestCase):
    """Signup must reject addresses whose domain ending isn't a real TLD.

    Django's EmailField accepts any syntactically valid domain, so
    ``kwame@ghana.con`` and ``kofiaddo@ghana.gor`` previously registered
    fine. These pin the IANA-root-zone check onto the signup forms.
    """

    def valid_data(self, email, **overrides):
        # Phone is required on the signup form, so the happy-path data must
        # carry a valid one; these tests pin the email rules, not the phone.
        return {
            "username": "tldcheck",
            "email": email,
            "phone": "241234567",
            "role": "DONOR",
            "password1": "Tumbleweed-Cortex-71",
            "password2": "Tumbleweed-Cortex-71",
            **overrides,
        }

    def form_for(self, email, **overrides):
        from accounts.forms import RegisterForm

        return RegisterForm(self.valid_data(email, **overrides))

    def test_fake_tlds_are_rejected(self):
        for email in ["kwame@ghana.con", "kofiaddo@ghana.gor", "nurse@corp.qrs"]:
            with self.subTest(email=email):
                form = self.form_for(email)
                self.assertFalse(form.is_valid(), form.errors)
                self.assertIn("not a recognized top-level domain", form.errors["email"][0])

    def test_real_tlds_are_accepted(self):
        for email in [
            "kwame@ghana.com", "kofiaddo@ghana.gov.gh", "nurse@korlebu.org",
            "donor@mail.co.ke", "someone@GHANA.COM", "user@example.xn--fiqs8s",
        ]:
            with self.subTest(email=email):
                form = self.form_for(email)
                self.assertTrue(form.is_valid(), form.errors)

    def test_typo_suggestion_names_the_real_tld(self):
        self.assertIn("Did you mean 'com'?", self.form_for("kwame@ghana.con").errors["email"][0])
        self.assertIn("Did you mean 'gov'?", self.form_for("kofiaddo@ghana.gor").errors["email"][0])

    def test_obscure_fake_tld_gets_no_suggestion(self):
        error = self.form_for("nurse@corp.qrs").errors["email"][0]
        self.assertNotIn("Did you mean", error)

    def test_register_page_rejects_a_fake_tld_end_to_end(self):
        response = self.client.post("/accounts/register/", self.valid_data("kwame@ghana.con"))
        self.assertEqual(response.status_code, 200)  # redisplayed, nothing created
        self.assertContains(response, "not a recognized top-level domain")
        self.assertFalse(User.objects.filter(username="tldcheck").exists())

    def test_hospital_register_form_rejects_a_fake_tld(self):
        from hospitals.forms import HospitalRegisterForm

        data = {
            "username": "hosp-tld", "email": "admin@korle.gor", "phone": "241234567",
            "password1": "Tumbleweed-Cortex-71", "password2": "Tumbleweed-Cortex-71",
            "hospital_name": "Korle Testing", "city": "Accra", "address": "1 High St",
            "hospital_phone": "240222444", "services_offered": "", "organ_requirements": "",
        }
        form = HospitalRegisterForm(data)
        self.assertFalse(form.is_valid(), form.errors)
        self.assertIn("not a recognized top-level domain", form.errors["email"][0])


class ContactValidationTests(TestCase):
    """Email and phone rules on the registration form: no phone numbers in the
    email box, and phone numbers are Ghanaian mobiles — exactly 9 digits, a
    valid network prefix, stored as +233XXXXXXXXX."""

    def _form(self, email="donor@example.com", phone="241234567"):
        return RegisterForm({
            "username": "valdonor", "email": email, "phone": phone,
            "role": "DONOR", "password1": "Tumbleweed-Cortex-71",
            "password2": "Tumbleweed-Cortex-71",
        })

    def test_email_rejects_a_phone_number(self):
        form = self._form(email="0241234567")
        self.assertFalse(form.is_valid())
        self.assertIn("phone number", " ".join(form.errors["email"]).lower())

    def test_email_rejects_malformed_addresses(self):
        form = self._form(email="not-an-email")
        self.assertFalse(form.is_valid())
        self.assertIn("valid email", " ".join(form.errors["email"]).lower())

    def test_email_with_digits_inside_is_accepted(self):
        form = self._form(email="john2@gmail.com")
        self.assertTrue(form.is_valid(), form.errors)

    def test_phone_is_required(self):
        form = self._form(phone="")
        self.assertFalse(form.is_valid())
        self.assertIn("phone number is required", " ".join(form.errors["phone"]).lower())

    def test_phone_more_than_nine_digits_is_rejected(self):
        form = self._form(phone="2412345678")
        self.assertFalse(form.is_valid())
        self.assertIn("exactly 9 digits", " ".join(form.errors["phone"]).lower())

    def test_phone_leading_zero_form_is_rejected(self):
        """0241234567 is the old 10-digit form; the field asks for 9 digits."""
        form = self._form(phone="0241234567")
        self.assertFalse(form.is_valid())

    def test_phone_with_letters_is_rejected(self):
        form = self._form(phone="24abcdef7")
        self.assertFalse(form.is_valid())
        self.assertIn("numbers only", " ".join(form.errors["phone"]).lower())

    def test_phone_with_invalid_prefix_is_rejected(self):
        form = self._form(phone="301234567")  # 030/031 are fixed lines
        self.assertFalse(form.is_valid())
        self.assertIn("prefix", " ".join(form.errors["phone"]).lower())

    def test_formatted_phone_is_accepted_and_normalized(self):
        form = self._form(phone="24 123-4567")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["phone"], "+233241234567")

    def test_international_form_is_accepted_and_normalized(self):
        """The field asks for 9 digits, but the backend safely normalises a
        pasted or API-supplied +233 form as well."""
        form = self._form(phone="+233241234567")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["phone"], "+233241234567")

    def test_model_fields_enforce_the_same_rules(self):
        """The admin and any ModelForm get the rules from the model fields."""
        with self.assertRaises(ValidationError):
            User(username="valmodel", email="0241234567", phone="2412345678").full_clean()


class GhanaPhoneNumberTests(TestCase):
    """The shared validator/normaliser behind every phone field: the full
    Ghanaian prefix matrix, the invalid-input list, and normalisation to the
    canonical +233XXXXXXXXX form."""

    VALID = {
        "MTN Ghana": ["241234567", "251234567", "531234567", "541234567",
                      "551234567", "591234567"],
        "Telecel Ghana": ["201234567", "501234567"],
        "AirtelTigo Ghana": ["261234567", "271234567", "561234567", "571234567"],
    }
    INVALID = ["0241234567", "+2332412345670", "24123456", "2412345678",
               "123456789", "031234567", "abc123456", "24abcdef7", "24@1234567"]

    def _register_form(self, **overrides):
        data = {
            "username": "ghdonor", "email": "gh@example.com", "phone": "241234567",
            "role": "DONOR", "password1": "Tumbleweed-Cortex-71",
            "password2": "Tumbleweed-Cortex-71",
        }
        data.update(overrides)
        return RegisterForm(data)

    def test_every_valid_prefix_is_accepted_and_detects_its_network(self):
        for network, numbers in self.VALID.items():
            for number in numbers:
                with self.subTest(network=network, number=number):
                    self.assertEqual(
                        normalize_ghana_phone_number(number), "+233" + number
                    )
                    self.assertEqual(detect_ghana_network(number), network)

    def test_invalid_numbers_are_rejected(self):
        for number in self.INVALID:
            with self.subTest(number=number):
                with self.assertRaises(ValidationError):
                    normalize_ghana_phone_number(number)

    def test_international_forms_normalize_to_canonical_form(self):
        self.assertEqual(normalize_ghana_phone_number("+233241234567"), "+233241234567")
        self.assertEqual(normalize_ghana_phone_number("233241234567"), "+233241234567")

    def test_spaces_dashes_and_parentheses_are_tolerated(self):
        self.assertEqual(normalize_ghana_phone_number("24 123 4567"), "+233241234567")
        self.assertEqual(normalize_ghana_phone_number("24-123-4567"), "+233241234567")
        self.assertEqual(normalize_ghana_phone_number("+233 24 123 4567"), "+233241234567")

    def test_empty_value_is_rejected_by_the_normalizer(self):
        with self.assertRaises(ValidationError):
            normalize_ghana_phone_number("")

    def test_model_validator_allows_blank(self):
        """Blank means "no phone yet" at the model level; the registration
        forms decide that a phone is required."""
        validate_ghana_phone_number("")
        validate_ghana_phone_number(None)

    def test_duplicate_phone_is_rejected_by_the_form(self):
        User.objects.create_user(
            username="taken", password="x", role=Role.DONOR, phone="+233241234567"
        )
        form = self._register_form(phone="241234567")
        self.assertFalse(form.is_valid())
        self.assertIn("already exists", " ".join(form.errors["phone"]).lower())

    def _register_post(self, phone):
        return self.client.post("/accounts/register/", {
            "username": "ghdonor", "email": "gh@example.com", "phone": phone,
            "role": "DONOR", "password1": "Tumbleweed-Cortex-71",
            "password2": "Tumbleweed-Cortex-71",
        })

    def test_http_request_bypassing_frontend_is_rejected(self):
        """A hand-crafted request with letters in the number never reaches the
        database — Django validates the phone server-side."""
        r = self._register_post("abc123456")
        self.assertEqual(r.status_code, 200)  # form re-rendered with errors
        self.assertContains(r, "numbers only")
        self.assertEqual(User.objects.count(), 0)

    def test_http_request_with_legacy_leading_zero_is_rejected(self):
        r = self._register_post("0241234567")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "exactly 9 digits")
        self.assertEqual(User.objects.count(), 0)

    def test_registration_stores_the_normalized_number(self):
        r = self._register_post("24 123-4567")
        self.assertEqual(r.status_code, 302)
        user = User.objects.get(username="ghdonor")
        self.assertEqual(user.phone, "+233241234567")

    def test_same_phone_number_cannot_be_registered_twice(self):
        self._register_post("241234567")
        # Registration logs the client in, so sign out before the second
        # attempt and use a fresh username — the phone is what must collide.
        self.client.logout()
        r = self.client.post("/accounts/register/", {
            "username": "ghdonor2", "email": "gh2@example.com", "phone": "+233241234567",
            "role": "DONOR", "password1": "Tumbleweed-Cortex-71",
            "password2": "Tumbleweed-Cortex-71",
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "already exists")
        self.assertEqual(User.objects.count(), 1)


class SessionTimeoutTests(TestCase):
    """Idle session timeout (SESSION_COOKIE_AGE + SESSION_SAVE_EVERY_REQUEST):
    the deadline renders on authenticated pages, the cookie carries the idle
    window and rolls with activity, and a session past its deadline is treated
    as logged out."""

    def setUp(self):
        self.user = User.objects.create_user(username="timeout", password="x", role=Role.ADMIN)
        self.dashboard = reverse("dashboard")

    def test_deadline_renders_on_authenticated_pages(self):
        self.client.force_login(self.user)
        response = self.client.get(self.dashboard)
        self.assertEqual(response.status_code, 200)
        match = re.search(r'data-session-deadline="(\d+)"', response.content.decode())
        self.assertIsNotNone(
            match, "authenticated pages must carry the server-computed deadline"
        )
        # Epoch seconds, now + SESSION_COOKIE_AGE, within a second of rendering.
        rendered = int(match.group(1))
        self.assertAlmostEqual(
            rendered, timezone.now().timestamp() + settings.SESSION_COOKIE_AGE, delta=5
        )
        # The countdown script is only served to authenticated pages too.
        self.assertContains(response, "session-timeout.js")

    def test_deadline_absent_and_script_not_loaded_when_anonymous(self):
        response = self.client.get(reverse("login"))
        self.assertNotContains(response, "data-session-deadline")
        self.assertNotContains(response, "session-timeout.js")

    def test_cookie_max_age_is_the_idle_window_and_rolls_with_activity(self):
        # A real login, so the session is created the way a browser's would be.
        self.assertTrue(self.client.login(username="timeout", password="x"))
        first = self.client.get(self.dashboard)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(
            int(first.cookies["sessionid"]["max-age"]), settings.SESSION_COOKIE_AGE
        )

        # SESSION_SAVE_EVERY_REQUEST: any later request re-issues the cookie
        # with a fresh Max-Age, so the window is idle-based, not from login.
        last = self.client.get(self.dashboard)
        self.assertEqual(
            int(last.cookies["sessionid"]["max-age"]), settings.SESSION_COOKIE_AGE
        )

    def test_session_past_its_deadline_is_treated_as_logged_out(self):
        self.assertTrue(self.client.login(username="timeout", password="x"))
        self.assertEqual(self.client.get(self.dashboard).status_code, 200)

        # No requests for SESSION_COOKIE_AGE: push the row's deadline into the
        # past the way time passing would, then the next request is anonymous.
        session_key = self.client.session.session_key
        Session.objects.filter(session_key=session_key).update(
            expire_date=timezone.now() - datetime.timedelta(seconds=1)
        )

        response = self.client.get(self.dashboard)
        self.assertEqual(response.status_code, 302)  # login_required bounce
        self.assertIn(reverse("login"), response.url)
