"""Privacy-partition tests: role gates and per-hospital data isolation."""
import datetime
import io
import re

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.email import MARKER, RESET_LINK, LoggingConsoleEmailBackend
from accounts.forms import RegisterForm
from cbods.validators import (
    detect_ghana_network,
    normalize_ghana_phone_number,
    validate_ghana_phone_number,
)

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
        return {
            "username": "tldcheck",
            "email": email,
            "phone": "",
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
            "username": "hosp-tld", "email": "admin@korle.gor", "phone": "",
            "password1": "Tumbleweed-Cortex-71", "password2": "Tumbleweed-Cortex-71",
            "hospital_name": "Korle Testing", "city": "Accra", "address": "1 High St",
            "hospital_phone": "024-000-0000", "services_offered": "", "organ_requirements": "",
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
