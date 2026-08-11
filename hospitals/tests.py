from django.test import TestCase
from django.utils import timezone

from accounts.models import Role, User
from donors.tests import make_donor
from inventory.models import BloodBag, Donation
from requests_app.models import BloodRequest

from .models import Hospital, HospitalApprovalStatus, StaffProfile


def register_hospital(client, username="hsptl1", name="Ridge Clinic"):
    """POST the hospital self-service registration form."""
    return client.post(
        "/hospitals/register/",
        {
            "username": username, "email": f"{username}@example.com", "phone": "024-111-2222",
            "password1": "Hospital-Pass-1", "password2": "Hospital-Pass-1",
            "hospital_name": name, "city": "Accra", "address": "1 Ridge Rd",
            "hospital_phone": "030-222-4444", "services_offered": "Blood bank, transfusion",
            "organ_requirements": "Kidney, cornea",
        },
    )


class HospitalRegistrationTests(TestCase):
    def test_register_creates_account_pending_hospital_and_profile(self):
        response = register_hospital(self.client)
        self.assertEqual(response.status_code, 302)

        user = User.objects.get(username="hsptl1")
        self.assertEqual(user.role, Role.HOSPITAL)
        hospital = user.staff_profile.hospital
        self.assertEqual(hospital.name, "Ridge Clinic")
        self.assertEqual(hospital.approval_status, HospitalApprovalStatus.PENDING)
        # Logged straight in: the dashboard explains the pending state.
        page = self.client.get("/accounts/dashboard/")
        self.assertContains(page, "pending review")

    def test_duplicate_hospital_name_is_rejected(self):
        Hospital.objects.create(name="Ridge Clinic", city="Accra", address="a", phone="p")
        response = register_hospital(self.client)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already registered")
        self.assertEqual(Hospital.objects.filter(name="Ridge Clinic").count(), 1)

    def test_pending_hospital_cannot_use_features(self):
        register_hospital(self.client)
        for url in ["/inventory/stock/", "/requests/inbox/", "/donors/search/",
                    "/organs/review/", "/requests/match/", "/hospitals/staff/"]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertIn("/accounts/dashboard/", response.url, url)

    def test_pending_hospital_invisible_to_patients(self):
        register_hospital(self.client)
        patient = User.objects.create_user(username="pat", password="x", role=Role.PATIENT)
        self.client.force_login(patient)
        self.assertNotContains(self.client.get("/requests/hospitals/"), "Ridge Clinic")

    def test_rejected_hospital_resubmits_from_profile_while_logged_in(self):
        """The primary resubmit path: correct the profile (no logout needed),
        mirroring the donor resubmit flow."""
        register_hospital(self.client)
        hospital = User.objects.get(username="hsptl1").staff_profile.hospital
        hospital.approval_status = HospitalApprovalStatus.REJECTED
        hospital.rejection_reason = "Incomplete licence"
        hospital.save()

        response = self.client.post(
            "/hospitals/profile/",
            {
                "name": "Ridge Clinic", "city": "Accra",
                "address": "2 Ridge Rd (corrected)", "phone": "030-222-4444",
                "services_offered": "Blood bank", "organ_requirements": "Kidney",
            },
        )
        self.assertRedirects(response, "/hospitals/profile/")
        hospital.refresh_from_db()
        self.assertEqual(hospital.approval_status, HospitalApprovalStatus.PENDING)
        self.assertIsNone(hospital.rejection_reason)
        self.assertEqual(hospital.address, "2 Ridge Rd (corrected)")

    def test_rejected_hospital_can_register_again_under_same_name(self):
        register_hospital(self.client)
        hospital = User.objects.get(username="hsptl1").staff_profile.hospital
        hospital.approval_status = HospitalApprovalStatus.REJECTED
        hospital.rejection_reason = "Incomplete licence"
        hospital.save()

        # Log out of the first account and register again under the same name.
        self.client.logout()
        response = register_hospital(self.client, username="hsptl2")
        self.assertEqual(response.status_code, 302)
        hospital.refresh_from_db()
        self.assertEqual(hospital.approval_status, HospitalApprovalStatus.PENDING)
        self.assertIsNone(hospital.rejection_reason)
        self.assertEqual(Hospital.objects.filter(name="Ridge Clinic").count(), 1)


class HospitalApprovalTests(TestCase):
    def setUp(self):
        register_hospital(self.client)
        self.user = User.objects.get(username="hsptl1")
        self.hospital = self.user.staff_profile.hospital
        self.admin = User.objects.create_user(username="hadmin", password="x", role=Role.ADMIN)

    def test_approve_unlocks_features_and_notifies(self):
        self.client.logout()
        self.client.force_login(self.admin)
        response = self.client.post(f"/hospitals/approvals/{self.hospital.pk}/", {"action": "approve"})
        self.assertRedirects(response, "/hospitals/approvals/")
        self.hospital.refresh_from_db()
        self.assertEqual(self.hospital.approval_status, HospitalApprovalStatus.APPROVED)
        self.assertTrue(
            self.user.notifications.filter(subject="Hospital registration approved").exists()
        )

        self.client.logout()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/inventory/stock/").status_code, 200)

    def test_reject_requires_a_reason(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            f"/hospitals/approvals/{self.hospital.pk}/", {"action": "reject"}, follow=True
        )
        self.assertContains(response, "rejection reason is required")
        self.hospital.refresh_from_db()
        self.assertEqual(self.hospital.approval_status, HospitalApprovalStatus.PENDING)

    def test_reject_records_reason_and_notifies(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            f"/hospitals/approvals/{self.hospital.pk}/",
            {"action": "reject", "rejection_reason": "No operating licence on file"},
        )
        self.assertRedirects(response, "/hospitals/approvals/")
        self.hospital.refresh_from_db()
        self.assertEqual(self.hospital.approval_status, HospitalApprovalStatus.REJECTED)
        self.assertEqual(self.hospital.rejection_reason, "No operating licence on file")
        self.assertTrue(
            self.user.notifications.filter(subject="Hospital registration rejected").exists()
        )

    def test_non_admin_cannot_review(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/hospitals/approvals/").status_code, 403)


class HospitalStaffManagementTests(TestCase):
    def setUp(self):
        register_hospital(self.client)
        self.user = User.objects.get(username="hsptl1")
        self.hospital = self.user.staff_profile.hospital
        self.hospital.approval_status = HospitalApprovalStatus.APPROVED
        self.hospital.save()

    def test_hospital_can_add_staff(self):
        response = self.client.post(
            "/hospitals/staff/add/",
            {
                "username": "nurse1", "email": "nurse1@example.com", "phone": "024-555-6666",
                "password1": "Staff-Pass-1", "password2": "Staff-Pass-1",
            },
        )
        self.assertRedirects(response, "/hospitals/staff/")
        staff = User.objects.get(username="nurse1")
        self.assertEqual(staff.role, Role.HOSPITAL_STAFF)
        self.assertEqual(staff.staff_profile.hospital, self.hospital)
        # The new staff member can sign in and work.
        self.client.logout()
        self.assertTrue(self.client.login(username="nurse1", password="Staff-Pass-1"))
        self.assertEqual(self.client.get("/inventory/stock/").status_code, 200)

    def test_hospital_can_remove_staff(self):
        nurse = User.objects.create_user(
            username="nurse2", password="x", role=Role.HOSPITAL_STAFF
        )
        profile = StaffProfile.objects.create(user=nurse, hospital=self.hospital)
        self.client.post(f"/hospitals/staff/{profile.pk}/remove/")
        nurse.refresh_from_db()
        self.assertFalse(nurse.is_active)
        self.assertFalse(StaffProfile.objects.filter(pk=profile.pk).exists())
        self.assertFalse(self.client.login(username="nurse2", password="x"))

    def test_hospital_cannot_remove_itself(self):
        own = self.user.staff_profile
        self.client.post(f"/hospitals/staff/{own.pk}/remove/")
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertTrue(StaffProfile.objects.filter(pk=own.pk).exists())

    def test_staff_cannot_manage_the_roster(self):
        staff = User.objects.create_user(
            username="nurse3", password="x", role=Role.HOSPITAL_STAFF
        )
        StaffProfile.objects.create(user=staff, hospital=self.hospital)
        self.client.force_login(staff)
        self.assertEqual(self.client.get("/hospitals/staff/").status_code, 403)


class HospitalAdminManageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="hadmin2", password="x", role=Role.ADMIN)
        self.approved = Hospital.objects.create(name="Alpha Hospital", city="Accra", address="a", phone="1")
        self.pending = Hospital.objects.create(
            name="Beta Clinic", city="Tema", address="b", phone="2",
            approval_status=HospitalApprovalStatus.PENDING,
        )
        self.hidden = Hospital.objects.create(
            name="Gamma Centre", city="Accra", address="c", phone="3", is_hidden=True
        )
        self.client.force_login(self.admin)

    def test_admin_directory_lists_every_hospital(self):
        page = self.client.get("/hospitals/manage/")
        self.assertContains(page, "Alpha Hospital")
        self.assertContains(page, "Beta Clinic")
        self.assertContains(page, "Gamma Centre")

    def test_filters_by_status_and_search(self):
        page = self.client.get("/hospitals/manage/?status=PENDING")
        self.assertContains(page, "Beta Clinic")
        self.assertNotContains(page, "Alpha Hospital")

        page = self.client.get("/hospitals/manage/?q=gamma")
        self.assertContains(page, "Gamma Centre")
        self.assertNotContains(page, "Alpha Hospital")

    def test_hide_toggle_is_audited_and_preserves_filters(self):
        response = self.client.post(
            f"/hospitals/manage/{self.approved.pk}/toggle-hidden/", {"next_qs": "status=APPROVED"}
        )
        self.assertRedirects(response, "/hospitals/manage/?status=APPROVED")
        self.approved.refresh_from_db()
        self.assertTrue(self.approved.is_hidden)

        # Now reveal it again.
        self.client.post(f"/hospitals/manage/{self.approved.pk}/toggle-hidden/")
        self.approved.refresh_from_db()
        self.assertFalse(self.approved.is_hidden)

    def test_only_admins_can_manage_hospitals(self):
        staff = User.objects.create_user(username="s1", password="x", role=Role.HOSPITAL_STAFF)
        StaffProfile.objects.create(user=staff, hospital=self.approved)
        self.client.force_login(staff)
        self.assertEqual(self.client.get("/hospitals/manage/").status_code, 403)
        self.assertEqual(
            self.client.post(f"/hospitals/manage/{self.approved.pk}/toggle-hidden/").status_code, 403
        )


class HospitalReportingTests(TestCase):
    def setUp(self):
        self.hospital = Hospital.objects.create(name="Report Hospital", city="Accra", address="a", phone="1")
        self.account = User.objects.create_user(username="reporthosp", password="x", role=Role.HOSPITAL)
        StaffProfile.objects.create(user=self.account, hospital=self.hospital)
        self.donor = make_donor("reportdonor")
        self.donation = Donation.objects.create(
            donor=self.donor, hospital=self.hospital, volume_ml=450,
            donated_at=timezone.now(), recorded_by=self.account,
        )
        BloodBag.objects.create(
            hospital=self.hospital, blood_group="O+", volume_ml=450,
            collected_date=timezone.localdate(),
            expiry_date=timezone.localdate() + timezone.timedelta(days=30),
        )
        BloodRequest.objects.create(
            patient=User.objects.create_user(username="rpat", password="x", role=Role.PATIENT),
            hospital=self.hospital, blood_group="O+", units_requested=1,
        )

    def test_reports_render_with_totals(self):
        self.client.force_login(self.account)
        page = self.client.get("/hospitals/reports/")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["totals"]["available"], 1)
        self.assertEqual(page.context["totals"]["donations"], 1)
        self.assertEqual(page.context["totals"]["volume_ml"], 450)
        self.assertIn("Donation recorded", str(self.client.get("/hospitals/activity/").content))

    def test_activity_feed_lists_donation_and_request_events(self):
        self.client.force_login(self.account)
        content = self.client.get("/hospitals/activity/").content.decode()
        self.assertIn("Donation recorded — Donor reportdonor", content)
        self.assertIn("Blood request submitted — rpat", content)

    def test_pending_hospital_is_blocked_from_reports_and_activity(self):
        self.hospital.approval_status = HospitalApprovalStatus.PENDING
        self.hospital.save()
        self.client.force_login(self.account)
        for url in ["/hospitals/reports/", "/hospitals/activity/"]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertIn("/accounts/dashboard/", response.url, url)

    def test_staff_can_read_reports_for_their_hospital(self):
        staff = User.objects.create_user(username="reporter", password="x", role=Role.HOSPITAL_STAFF)
        StaffProfile.objects.create(user=staff, hospital=self.hospital)
        self.client.force_login(staff)
        self.assertEqual(self.client.get("/hospitals/reports/").status_code, 200)


class HospitalVisibleToApprovalTests(TestCase):
    """Approval joins hidden as a visibility gate for non-admins."""

    def test_approved_hospital_visible_to_donor_facing_pages(self):
        approved = Hospital.objects.create(name="Live Hospital", city="Accra", address="a", phone="p")
        patient = User.objects.create_user(username="pat2", password="x", role=Role.PATIENT)
        self.client.force_login(patient)
        self.assertContains(self.client.get("/requests/hospitals/"), "Live Hospital")
        self.assertEqual(self.client.get(f"/requests/new/{approved.pk}/").status_code, 302)

    def test_staff_actions_still_work_at_approved_hospitals(self):
        hospital = Hospital.objects.create(name="Staff Hospital", city="Accra", address="a", phone="p")
        staff = User.objects.create_user(username="s1", password="x", role=Role.HOSPITAL_STAFF)
        StaffProfile.objects.create(user=staff, hospital=hospital)
        donor = make_donor("hospdonor")
        self.client.force_login(staff)
        self.assertEqual(self.client.get("/inventory/stock/").status_code, 200)
        self.assertEqual(
            self.client.get(f"/donors/screening/{donor.pk}/").status_code, 200
        )
