import datetime
from decimal import Decimal

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from accounts.models import Role, User
from hospitals.models import Hospital
from inventory.models import Donation

from . import services
from .models import Donor, RegistrationStatus  # noqa: F401  (RegistrationStatus used by callers)

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d4944415478da63fcff9fa10e0002d40197ec1f83660000000049454e44ae426082"
)


def make_donor(username="donor1", *, age_years=30, weight="70.0", blood_group="O+", city="Nairobi",
               status="APPROVED"):
    user = User.objects.create_user(username=username, password="x", role=Role.DONOR)
    today = timezone.localdate()
    dob = today.replace(year=today.year - age_years)
    return Donor.objects.create(
        user=user, full_name=f"Donor {username}", date_of_birth=dob, sex="M",
        blood_group=blood_group, weight_kg=Decimal(weight), city=city, contact_phone="0700",
        id_document=SimpleUploadedFile(f"{username}.png", PNG, content_type="image/png"),
        registration_status=status,
    )


class Stage1BoundaryTests(TestCase):
    def test_age_17_fails_18_passes(self):
        d17 = make_donor("d17", age_years=17)
        passed, reasons, permanent = services.run_stage1(d17)
        self.assertFalse(passed)
        self.assertFalse(permanent)

        d18 = make_donor("d18", age_years=18)
        passed, reasons, _ = services.run_stage1(d18)
        self.assertTrue(passed, reasons)

    def test_age_61_permanent_ineligible(self):
        d61 = make_donor("d61", age_years=61)
        passed, reasons, permanent = services.run_stage1(d61)
        self.assertFalse(passed)
        self.assertTrue(permanent)

    def test_weight_49_9_fails_50_passes(self):
        light = make_donor("light", weight="49.9")
        passed, _, _ = services.run_stage1(light)
        self.assertFalse(passed)

        ok = make_donor("okw", weight="50.0")
        passed, reasons, _ = services.run_stage1(ok)
        self.assertTrue(passed, reasons)

    def test_day_89_fails_day_90_passes(self):
        donor = make_donor("interval")
        hospital = Hospital.objects.create(name="H", city="Nairobi", address="a", phone="p")
        donation = Donation.objects.create(
            donor=donor, hospital=hospital,
            donated_at=timezone.now() - datetime.timedelta(days=89), volume_ml=450,
        )
        passed, _, _ = services.run_stage1(donor)
        self.assertFalse(passed)

        donation.donated_at = timezone.now() - datetime.timedelta(days=90)
        donation.save()
        passed, reasons, _ = services.run_stage1(donor)
        self.assertTrue(passed, reasons)


class Stage2BoundaryTests(TestCase):
    def test_hemoglobin_12_4_fails_12_5_passes(self):
        ok, reasons = services.run_stage2(12.4, 120, 80)
        self.assertFalse(ok)
        ok, reasons = services.run_stage2(12.5, 120, 80)
        self.assertTrue(ok, reasons)

    def test_bp_bounds(self):
        self.assertFalse(services.run_stage2(13.0, 89, 80)[0])
        self.assertTrue(services.run_stage2(13.0, 90, 80)[0])
        self.assertFalse(services.run_stage2(13.0, 181, 80)[0])
        self.assertTrue(services.run_stage2(13.0, 180, 80)[0])
        self.assertFalse(services.run_stage2(13.0, 120, 59)[0])
        self.assertTrue(services.run_stage2(13.0, 120, 60)[0])
        self.assertFalse(services.run_stage2(13.0, 120, 101)[0])
        self.assertTrue(services.run_stage2(13.0, 120, 100)[0])


class DonationBlockingTests(TestCase):
    def setUp(self):
        self.donor = make_donor("blocked")
        self.hospital = Hospital.objects.create(name="H", city="Nairobi", address="a", phone="p")
        self.staff = User.objects.create_user(username="staff", password="x", role=Role.HOSPITAL_STAFF)

    def test_no_screening_blocks(self):
        ok, why = services.can_donate(self.donor)
        self.assertFalse(ok)

    def test_deferred_screening_blocks(self):
        services.screen_donor(self.donor, 11.0, 120, 80)
        ok, why = services.can_donate(self.donor)
        self.assertFalse(ok)

    def test_eligible_screening_allows(self):
        services.screen_donor(self.donor, 13.5, 120, 80)
        ok, why = services.can_donate(self.donor)
        self.assertTrue(ok, why)

    def test_unapproved_donor_blocks(self):
        pending = make_donor("pending", status="PENDING")
        services.screen_donor(pending, 13.5, 120, 80)
        ok, _ = services.can_donate(pending)
        self.assertFalse(ok)

    def test_record_donation_service_blocks_ineligible(self):
        from inventory.services import record_donation

        with self.assertRaises(ValueError):
            record_donation(self.staff, self.donor, self.hospital)


class IdDocumentPrivacyTests(TestCase):
    """Government-ID scans must be reachable only through the admin-only view."""

    def setUp(self):
        self.donor = make_donor("iddonor")
        self.admin = User.objects.create_user(username="idadmin", password="x", role=Role.ADMIN)
        self.url = f"/donors/approvals/{self.donor.pk}/id-document/"

    def test_admin_can_read_the_document(self):
        self.client.force_login(self.admin)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content), PNG)

    def test_every_other_role_is_refused(self):
        staff = User.objects.create_user(username="idstaff", password="x", role=Role.HOSPITAL_STAFF)
        patient = User.objects.create_user(username="idpatient", password="x", role=Role.PATIENT)
        for user in [staff, patient, self.donor.user]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 403, user.username)

    def test_anonymous_is_redirected_to_login(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r.url)

    def test_media_is_not_served_by_url(self):
        """The raw upload path must not resolve — no unauthenticated media route."""
        self.client.force_login(self.admin)
        r = self.client.get(f"/media/{self.donor.id_document.name}")
        self.assertEqual(r.status_code, 404)


class IdDocumentValidationTests(TestCase):
    def _post(self, upload):
        return self.client.post(
            "/donors/profile/",
            {
                "full_name": "Upload Test", "date_of_birth": "1995-01-01", "sex": "F",
                "blood_group": "O+", "weight_kg": "61.0", "city": "Accra",
                "contact_phone": "024-000-0000", "medical_history": "",
                "id_document": upload,
            },
        )

    def setUp(self):
        user = User.objects.create_user(username="uploader", password="x", role=Role.DONOR)
        self.client.force_login(user)

    def test_executable_is_rejected(self):
        r = self._post(SimpleUploadedFile("payload.exe", b"MZ\x00\x00", content_type="application/octet-stream"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "JPG, PNG or PDF")
        self.assertEqual(Donor.objects.count(), 0)

    def test_oversized_file_is_rejected(self):
        big = SimpleUploadedFile("huge.png", b"\x00" * (settings.ID_DOCUMENT_MAX_BYTES + 1), content_type="image/png")
        r = self._post(big)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "must be smaller than")
        self.assertEqual(Donor.objects.count(), 0)

    def test_valid_png_is_accepted(self):
        r = self._post(SimpleUploadedFile("id.png", PNG, content_type="image/png"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Donor.objects.count(), 1)


class DonorSelfServiceTests(TestCase):
    def test_rejected_donor_can_resubmit(self):
        donor = make_donor("rejected1", status="REJECTED")
        donor.rejection_reason = "ID unreadable"
        donor.save()
        self.client.force_login(donor.user)

        r = self.client.get("/donors/profile/")
        self.assertContains(r, "Resubmit donor registration")
        self.assertContains(r, "ID unreadable")

        r = self.client.post(
            "/donors/profile/",
            {
                "full_name": "Corrected Name", "date_of_birth": "1995-01-01", "sex": "F",
                "blood_group": "O+", "weight_kg": "61.0", "city": "Accra",
                "contact_phone": "024-000-0000", "medical_history": "",
                "id_document": SimpleUploadedFile("new_id.png", PNG, content_type="image/png"),
            },
        )
        self.assertEqual(r.status_code, 302)
        donor.refresh_from_db()
        self.assertEqual(donor.registration_status, "PENDING")
        self.assertIsNone(donor.rejection_reason)
        self.assertEqual(donor.full_name, "Corrected Name")

    def test_approved_donor_profile_is_not_editable(self):
        donor = make_donor("approved1")
        self.client.force_login(donor.user)
        r = self.client.get("/donors/profile/")
        self.assertNotContains(r, "Resubmit donor registration")

