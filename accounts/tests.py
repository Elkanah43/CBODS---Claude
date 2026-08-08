"""Privacy-partition tests: role gates and per-hospital data isolation."""
import datetime
import io
import re

from django.core import mail
from django.core.mail import EmailMessage
from django.test import TestCase

from accounts.email import MARKER, RESET_LINK, LoggingConsoleEmailBackend
from django.utils import timezone

from accounts.models import Role, User
from donors.tests import make_donor
from hospitals.models import Hospital, StaffProfile
from inventory.models import BloodBag
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
        )
        self.req_h2 = BloodRequest.objects.create(
            patient=self.patient, hospital=self.h2, blood_group="O+", units_requested=1
        )
        self.organ_h2 = OrganDonationRequest.objects.create(
            donor=self.donor, hospital=self.h2, organ_type="KIDNEY"
        )

    def test_donor_cannot_load_staff_urls(self):
        self.client.force_login(self.donor.user)
        for url in ["/inventory/stock/", "/inventory/donate/", "/requests/inbox/",
                    "/donors/screening/", "/organs/review/", "/donors/search/",
                    "/requests/match/"]:
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


class LoginFlowTests(TestCase):
    """Failed logins use Post/Redirect/Get so the error clears on refresh."""

    def test_failed_login_shows_error_once_then_clears_on_refresh(self):
        r = self.client.post("/accounts/login/", {"username": "nobody", "password": "wrong"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, "/accounts/login/")

        # The follow-up GET carries the one-shot message...
        page = self.client.get("/accounts/login/")
        self.assertContains(page, "Invalid username or password.")

        # ...and a refresh (another plain GET) no longer shows it.
        refreshed = self.client.get("/accounts/login/")
        self.assertNotContains(refreshed, "Invalid username or password.")

    def test_failed_login_preserves_the_next_target(self):
        r = self.client.post(
            "/accounts/login/?next=/requests/hospitals/",
            {"username": "nobody", "password": "wrong"},
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn("next=%2Frequests%2Fhospitals%2F", r.url)

    def test_successful_login_redirects_to_dashboard(self):
        User.objects.create_user(username="loginer", password="Good-Pass-1234", role=Role.PATIENT)
        r = self.client.post(
            "/accounts/login/", {"username": "loginer", "password": "Good-Pass-1234"}
        )
        self.assertRedirects(r, "/accounts/dashboard/", fetch_redirect_response=False)

    def test_login_page_embeds_the_dismiss_on_typing_script(self):
        self.assertContains(self.client.get("/accounts/login/"), "id_username, #id_password")


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
            sent = self.send(f"Open this link:\n\n{link}\n\nIt expires in 24 hours.")
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
                    "username": "elkanah43", "email": "e@example.com", "phone": "",
                    "role": "DONOR", "password1": password, "password2": password,
                })
                accepted = all(self.post(password, username="elkanah43", email="e@example.com").values())
                self.assertEqual(form.is_valid(), accepted, form.errors)
