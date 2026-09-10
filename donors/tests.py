import datetime
from decimal import Decimal

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from accounts.models import Role, User
from hospitals.models import Hospital, StaffProfile
from inventory.models import BloodBag, Donation

from . import services
from .models import Appointment, Donor, RegistrationStatus  # noqa: F401  (RegistrationStatus used by callers)

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


class DonationSitesTests(TestCase):
    """The donor-facing hospital directory: visibility, stock counts, ranking."""

    def setUp(self):
        self.donor = make_donor("sitesdonor", blood_group="O-", city="Nairobi")
        self.client.force_login(self.donor.user)
        self.local = Hospital.objects.create(name="Alpha", city="Nairobi", address="a", phone="p")
        self.far = Hospital.objects.create(name="Beta", city="Mombasa", address="b", phone="q")
        # The far hospital is short on the donor's own group.
        today = timezone.localdate()
        BloodBag.objects.create(
            hospital=self.far, blood_group="O-", collected_date=today,
            expiry_date=today + datetime.timedelta(days=30),
        )
        # Hidden and pending hospitals must not appear to donors.
        Hospital.objects.create(name="Ghost", city="Nairobi", address="g", phone="h", is_hidden=True)
        Hospital.objects.create(
            name="Waiting", city="Nairobi", address="w", phone="i",
            approval_status="PENDING",
        )

    def _bags(self, hospital, group, n):
        today = timezone.localdate()
        for _ in range(n):
            BloodBag.objects.create(
                hospital=hospital, blood_group=group, collected_date=today,
                expiry_date=today + datetime.timedelta(days=30),
            )

    def test_only_approved_visible_hospitals_listed(self):
        r = self.client.get("/donors/sites/")
        self.assertContains(r, "Alpha")
        self.assertContains(r, "Beta")
        self.assertNotContains(r, "Ghost")

    def test_stock_counts_render_per_group(self):
        self._bags(self.local, "O-", 4)
        r = self.client.get("/donors/sites/")
        self.assertContains(r, "O-: 4")

    def test_low_stock_group_is_flagged(self):
        self._bags(self.local, "A+", 2)  # below LOW_STOCK_THRESHOLD = 3
        r = self.client.get("/donors/sites/")
        self.assertContains(r, "Urgently needs: A+")

    def test_own_city_ranks_first(self):
        r = self.client.get("/donors/sites/")
        body = r.content.decode()
        self.assertLess(body.index("Alpha"), body.index("Beta"))

    def test_shortage_of_own_group_ranks_first_within_city(self):
        self._bags(self.local, "O-", 5)  # local is well stocked
        # Beta (Mombasa) stays short on O-, but is not the donor's city.
        r = self.client.get("/donors/sites/")
        body = r.content.decode()
        self.assertLess(body.index("Alpha"), body.index("Beta"))

    def test_needs_mine_badge_when_own_group_is_low(self):
        # Far hospital is short on O- (1 bag) while the donor is O-.
        r = self.client.get("/donors/sites/")
        self.assertContains(r, "Needs O-")

    def test_other_roles_are_refused(self):
        self.client.logout()
        staff = User.objects.create_user(username="sitestaff", password="x", role=Role.HOSPITAL_STAFF)
        self.client.force_login(staff)
        self.assertEqual(self.client.get("/donors/sites/").status_code, 403)

    def test_anonymous_is_redirected_to_login(self):
        self.client.logout()
        r = self.client.get("/donors/sites/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r.url)


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


class AppointmentTests(TestCase):
    """Booking from the directory, staff decisions, and access control."""

    def setUp(self):
        self.donor = make_donor("bookdonor")  # APPROVED by default
        self.client.force_login(self.donor.user)
        self.hospital = Hospital.objects.create(name="Booking General", city="Nairobi", address="a", phone="p")
        self.hidden = Hospital.objects.create(name="Hidden Gen", city="Nairobi", address="h", phone="q", is_hidden=True)
        staff = User.objects.create_user(username="bookstaff", password="x", role=Role.HOSPITAL_STAFF)
        StaffProfile.objects.create(user=staff, hospital=self.hospital)

    def _post_book(self, hospital, day=None, note="See you there"):
        day = day or timezone.localdate() + datetime.timedelta(days=3)
        return self.client.post(
            f"/donors/sites/{hospital.pk}/book/",
            {"requested_for": day.isoformat(), "donor_note": note},
        )

    def test_booking_creates_appointment_and_notifies_staff(self):
        from notifications.models import Notification

        r = self._post_book(self.hospital)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, "/donors/appointments/")
        appt = Appointment.objects.get()
        self.assertEqual(appt.status, "PENDING")
        self.assertEqual(appt.donor, self.donor)
        self.assertTrue(Notification.objects.filter(user__username="bookstaff").exists())

    def test_pending_donor_cannot_book(self):
        pending = make_donor("pendingbook", status="PENDING")
        self.client.force_login(pending.user)
        r = self._post_book(self.hospital)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Appointment.objects.count(), 0)

    def test_unapproved_donor_cannot_book(self):
        rejected = make_donor("rejectedbook", status="REJECTED")
        self.client.force_login(rejected.user)
        r = self._post_book(self.hospital)
        self.assertEqual(Appointment.objects.count(), 0)

    def test_cannot_book_hidden_hospital(self):
        r = self._post_book(self.hidden)
        self.assertEqual(r.status_code, 404)
        self.assertEqual(Appointment.objects.count(), 0)

    def test_duplicate_pending_booking_redirects(self):
        self._post_book(self.hospital)
        r = self._post_book(self.hospital)
        self.assertEqual(r.url, "/donors/appointments/")
        self.assertEqual(Appointment.objects.count(), 1)

    def test_past_date_is_rejected(self):
        yesterday = timezone.localdate() - datetime.timedelta(days=1)
        r = self._post_book(self.hospital, day=yesterday)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Pick today or a future date")
        self.assertEqual(Appointment.objects.count(), 0)

    def test_far_future_date_is_rejected(self):
        far = timezone.localdate() + datetime.timedelta(days=61)
        r = self._post_book(self.hospital, day=far)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "at most 60 days ahead")

    def test_donor_can_cancel_pending_appointment(self):
        self._post_book(self.hospital)
        appt = Appointment.objects.get()
        r = self.client.post(f"/donors/appointments/{appt.pk}/cancel/")
        self.assertEqual(r.status_code, 302)
        appt.refresh_from_db()
        self.assertEqual(appt.status, "DECLINED")
        self.assertEqual(appt.staff_note, "Cancelled by the donor.")

    def test_donor_cannot_cancel_others_appointment(self):
        other = make_donor("otherdonor")
        appt = Appointment.objects.create(
            donor=other, hospital=self.hospital, requested_for=timezone.localdate() + datetime.timedelta(days=1)
        )
        r = self.client.post(f"/donors/appointments/{appt.pk}/cancel/")
        self.assertEqual(r.status_code, 404)
        appt.refresh_from_db()
        self.assertEqual(appt.status, "PENDING")

    def test_staff_confirms_and_donor_is_notified(self):
        from notifications.models import Notification

        appt = Appointment.objects.create(
            donor=self.donor, hospital=self.hospital,
            requested_for=timezone.localdate() + datetime.timedelta(days=1),
        )
        staff = User.objects.create_user(username="apptstaff", password="x", role=Role.HOSPITAL_STAFF)
        StaffProfile.objects.create(user=staff, hospital=self.hospital)
        self.client.force_login(staff)
        r = self.client.post(f"/donors/appointments/inbox/{appt.pk}/decide/", {"action": "confirm"})
        self.assertEqual(r.status_code, 302)
        appt.refresh_from_db()
        self.assertEqual(appt.status, "CONFIRMED")
        self.assertIsNotNone(appt.decided_at)
        self.assertTrue(Notification.objects.filter(user=self.donor.user, subject__icontains="confirmed").exists())

    def test_staff_declines_with_note(self):
        appt = Appointment.objects.create(
            donor=self.donor, hospital=self.hospital,
            requested_for=timezone.localdate() + datetime.timedelta(days=1),
        )
        staff = User.objects.create_user(username="apptstaff2", password="x", role=Role.HOSPITAL_STAFF)
        StaffProfile.objects.create(user=staff, hospital=self.hospital)
        self.client.force_login(staff)
        r = self.client.post(
            f"/donors/appointments/inbox/{appt.pk}/decide/",
            {"action": "decline", "staff_note": "Closed for maintenance"},
        )
        appt.refresh_from_db()
        self.assertEqual(appt.status, "DECLINED")
        self.assertEqual(appt.staff_note, "Closed for maintenance")

    def test_staff_of_other_hospital_cannot_decide(self):
        appt = Appointment.objects.create(
            donor=self.donor, hospital=self.hospital,
            requested_for=timezone.localdate() + datetime.timedelta(days=1),
        )
        other_hospital = Hospital.objects.create(name="Elsewhere", city="Accra", address="o", phone="1")
        staff = User.objects.create_user(username="apptstaff3", password="x", role=Role.HOSPITAL_STAFF)
        StaffProfile.objects.create(user=staff, hospital=other_hospital)
        self.client.force_login(staff)
        r = self.client.post(f"/donors/appointments/inbox/{appt.pk}/decide/", {"action": "confirm"})
        self.assertEqual(r.status_code, 404)
        appt.refresh_from_db()
        self.assertEqual(appt.status, "PENDING")

    def test_directory_shows_urgent_book_cta_and_pending_state(self):
        today = timezone.localdate()
        BloodBag.objects.create(
            hospital=self.hospital, blood_group="O+", collected_date=today,
            expiry_date=today + datetime.timedelta(days=30),
        )
        r = self.client.get("/donors/sites/")
        self.assertContains(r, "Book now")

        # After booking, the card offers the status page instead of a second slot.
        self._post_book(self.hospital)
        r = self.client.get("/donors/sites/")
        self.assertContains(r, "Appointment pending")
        self.assertNotContains(r, "Book now")

    def test_other_roles_cannot_reach_booking(self):
        self.client.logout()
        staff = User.objects.create_user(username="apptstaff4", password="x", role=Role.HOSPITAL_STAFF)
        self.client.force_login(staff)
        r = self.client.get(f"/donors/sites/{self.hospital.pk}/book/")
        self.assertEqual(r.status_code, 403)

    def test_anonymous_is_redirected_to_login(self):
        self.client.logout()
        r = self.client.get(f"/donors/sites/{self.hospital.pk}/book/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r.url)

