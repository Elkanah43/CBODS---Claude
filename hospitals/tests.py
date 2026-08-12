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


class HospitalReviewWorkflowTests(TestCase):
    """The admin review page: full record, account, history, duplicate hints,
    and decisions that can also reverse a rejection."""

    def setUp(self):
        self.admin = User.objects.create_user(username="rvadmin", password="x", role=Role.ADMIN)
        register_hospital(self.client)
        self.user = User.objects.get(username="hsptl1")
        self.hospital = self.user.staff_profile.hospital
        self.client.force_login(self.admin)

    def test_review_page_shows_record_account_and_history(self):
        page = self.client.get(f"/hospitals/approvals/{self.hospital.pk}/review/")
        self.assertContains(page, "Ridge Clinic")
        self.assertContains(page, "hsptl1")  # the registering account
        self.assertContains(page, "Registration submitted")  # audit history

    def test_review_page_approve_stays_on_review(self):
        response = self.client.post(
            f"/hospitals/approvals/{self.hospital.pk}/",
            {"action": "approve", "next": "review"},
        )
        self.assertRedirects(response, f"/hospitals/approvals/{self.hospital.pk}/review/")
        self.hospital.refresh_from_db()
        self.assertEqual(self.hospital.approval_status, HospitalApprovalStatus.APPROVED)

    def test_review_page_reject_requires_reason_and_stays(self):
        response = self.client.post(
            f"/hospitals/approvals/{self.hospital.pk}/",
            {"action": "reject", "next": "review"},
            follow=True,
        )
        self.assertContains(response, "rejection reason is required")
        self.hospital.refresh_from_db()
        self.assertEqual(self.hospital.approval_status, HospitalApprovalStatus.PENDING)

    def test_review_page_reject_records_reason(self):
        response = self.client.post(
            f"/hospitals/approvals/{self.hospital.pk}/",
            {"action": "reject", "rejection_reason": "No licence", "next": "review"},
        )
        self.assertRedirects(response, f"/hospitals/approvals/{self.hospital.pk}/review/")
        self.hospital.refresh_from_db()
        self.assertEqual(self.hospital.approval_status, HospitalApprovalStatus.REJECTED)
        self.assertEqual(self.hospital.rejection_reason, "No licence")

    def test_admin_can_reverse_a_rejection_from_review(self):
        self.hospital.approval_status = HospitalApprovalStatus.REJECTED
        self.hospital.rejection_reason = "No licence"
        self.hospital.save()
        response = self.client.post(
            f"/hospitals/approvals/{self.hospital.pk}/",
            {"action": "approve", "next": "review"},
        )
        self.hospital.refresh_from_db()
        self.assertEqual(self.hospital.approval_status, HospitalApprovalStatus.APPROVED)
        self.assertIsNone(self.hospital.rejection_reason)

    def test_review_page_flags_possible_duplicates(self):
        Hospital.objects.create(name="Ridge Clinic", city="Accra", address="x", phone="0")
        page = self.client.get(f"/hospitals/approvals/{self.hospital.pk}/review/")
        self.assertContains(page, "Possible duplicate")

    def test_approved_hospital_shows_live_state_not_decision_form(self):
        self.hospital.approval_status = HospitalApprovalStatus.APPROVED
        self.hospital.save()
        page = self.client.get(f"/hospitals/approvals/{self.hospital.pk}/review/")
        self.assertContains(page, "live")
        self.assertNotContains(page, "Approve hospital")

    def test_non_admin_cannot_review(self):
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get(f"/hospitals/approvals/{self.hospital.pk}/review/").status_code, 403
        )

    def test_queue_is_fifo_and_shows_account(self):
        second = Hospital.objects.create(
            name="Second Clinic", city="Tema", address="y", phone="1",
            approval_status=HospitalApprovalStatus.PENDING,
        )
        Hospital.objects.filter(pk=second.pk).update(
            created_at=self.hospital.created_at + timezone.timedelta(minutes=1)
        )
        page = self.client.get("/hospitals/approvals/")
        self.assertContains(page, "hsptl1")
        # Oldest first: Ridge Clinic (older) appears before Second Clinic.
        self.assertLess(
            page.content.index(b"Ridge Clinic"), page.content.index(b"Second Clinic")
        )

    def test_queue_search_filters_pending(self):
        Hospital.objects.create(
            name="Tema Harbour Hospital", city="Tema", address="y", phone="1",
            approval_status=HospitalApprovalStatus.PENDING,
        )
        page = self.client.get("/hospitals/approvals/?q=tema")
        self.assertContains(page, "Tema Harbour Hospital")
        self.assertNotContains(page, "Ridge Clinic")

    def test_admin_dashboard_lists_recent_registrations(self):
        page = self.client.get("/audit/dashboard/")
        self.assertContains(page, "Recent hospital registrations")
        self.assertContains(page, "Ridge Clinic")
        self.assertContains(page, "hsptl1")

    def test_admin_dashboard_always_shows_awaiting_review_with_links(self):
        """The system dashboard surfaces pending registrations and links each
        one straight into the review page — even the empty state is shown."""
        page = self.client.get("/audit/dashboard/")
        self.assertContains(page, "Hospitals awaiting review")
        self.assertContains(page, f"/hospitals/approvals/{self.hospital.pk}/review/")

        self.hospital.approval_status = HospitalApprovalStatus.APPROVED
        self.hospital.save()
        empty = self.client.get("/audit/dashboard/")
        self.assertContains(empty, "No hospital registrations waiting for review.")


class HospitalAdminEditTests(TestCase):
    """Admin fixes a registration's details from the review page."""

    def setUp(self):
        self.admin = User.objects.create_user(username="edadmin", password="x", role=Role.ADMIN)
        register_hospital(self.client)
        self.user = User.objects.get(username="hsptl1")
        self.hospital = self.user.staff_profile.hospital
        self.client.force_login(self.admin)

    def _post_edit(self, **overrides):
        # Defaults mirror exactly what register_hospital() created, so an
        # unmodified post changes nothing.
        data = {
            "name": "Ridge Clinic", "city": "Accra", "address": "1 Ridge Rd",
            "phone": "030-222-4444", "services_offered": "Blood bank, transfusion",
            "organ_requirements": "Kidney, cornea",
        }
        data.update(overrides)
        return self.client.post(f"/hospitals/approvals/{self.hospital.pk}/edit/", data)

    def test_admin_edits_hospital_details(self):
        response = self._post_edit(address="9 Fixed Rd")
        self.assertRedirects(response, f"/hospitals/approvals/{self.hospital.pk}/review/")
        self.hospital.refresh_from_db()
        self.assertEqual(self.hospital.address, "9 Fixed Rd")
        # A typo fix never disturbs the approval state.
        self.assertEqual(self.hospital.approval_status, HospitalApprovalStatus.PENDING)

    def test_admin_edit_is_audited_and_shown_in_history(self):
        self._post_edit(address="9 Fixed Rd")
        page = self.client.get(f"/hospitals/approvals/{self.hospital.pk}/review/")
        self.assertContains(page, "Edited by admin")
        self.assertContains(page, "edadmin")

    def test_edit_cannot_duplicate_another_hospitals_name(self):
        Hospital.objects.create(name="Other Clinic", city="Tema", address="x", phone="0")
        response = self._post_edit(name="Other Clinic")
        self.assertEqual(response.status_code, 200)  # review page re-rendered
        self.assertContains(response, "already registered")
        self.hospital.refresh_from_db()
        self.assertEqual(self.hospital.name, "Ridge Clinic")

    def test_edit_form_renders_on_review_page(self):
        page = self.client.get(f"/hospitals/approvals/{self.hospital.pk}/review/")
        self.assertContains(page, "Edit")
        self.assertContains(page, 'id="editHospitalForm"')

    def test_edit_surfaces_in_the_hospital_activity_feed(self):
        self._post_edit(address="9 Fixed Rd")
        self.client.post(
            f"/hospitals/approvals/{self.hospital.pk}/", {"action": "approve"}
        )
        self.client.force_login(self.user)
        self.assertContains(self.client.get("/hospitals/activity/"), "Details corrected by admin")

    def test_unchanged_post_is_not_audited(self):
        response = self._post_edit()  # same values the record already has
        self.assertRedirects(response, f"/hospitals/approvals/{self.hospital.pk}/review/")
        from audit.models import AuditLog
        self.assertFalse(
            AuditLog.objects.filter(
                action="HOSPITAL_EDITED_BY_ADMIN", entity_id=str(self.hospital.pk)
            ).exists()
        )

    def test_non_admin_cannot_edit(self):
        self.client.force_login(self.user)
        response = self._post_edit(address="9 Fixed Rd")
        self.assertEqual(response.status_code, 403)


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


class HospitalAdminSiteLinkageTests(TestCase):
    """The Django admin links into the review workflow and can decide
    registrations without leaving /admin/."""

    def setUp(self):
        self.superuser = User.objects.create_user(
            username="adminlink", password="x", role=Role.ADMIN,
            is_staff=True, is_superuser=True,
        )
        register_hospital(self.client)
        self.user = User.objects.get(username="hsptl1")
        self.hospital = self.user.staff_profile.hospital
        self.client.force_login(self.superuser)

    def test_changelist_links_each_hospital_to_its_review_page(self):
        page = self.client.get("/admin/hospitals/hospital/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Ridge Clinic")
        # Each row links to the admin review URL, which redirects to the full
        # review workflow page.
        self.assertContains(page, f"/admin/hospitals/hospital/{self.hospital.pk}/review/")

    def test_changelist_review_link_redirects_to_review_page(self):
        response = self.client.get(f"/admin/hospitals/hospital/{self.hospital.pk}/review/")
        self.assertRedirects(response, f"/hospitals/approvals/{self.hospital.pk}/review/")

    def test_approve_action_makes_live_notifies_and_audits(self):
        response = self.client.post(
            "/admin/hospitals/hospital/",
            {
                "action": "approve_hospitals",
                "_selected_action": [self.hospital.pk],
                "index": "0",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.hospital.refresh_from_db()
        self.assertEqual(self.hospital.approval_status, HospitalApprovalStatus.APPROVED)
        self.assertTrue(
            self.user.notifications.filter(subject="Hospital registration approved").exists()
        )
        from audit.models import AuditLog
        self.assertTrue(
            AuditLog.objects.filter(
                action="HOSPITAL_APPROVED", entity_id=str(self.hospital.pk)
            ).exists()
        )

    def test_reject_action_asks_for_a_reason_first(self):
        """The first post renders the reason prompt instead of rejecting."""
        response = self.client.post(
            "/admin/hospitals/hospital/",
            {
                "action": "reject_hospitals",
                "_selected_action": [self.hospital.pk],
                "index": "0",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reject hospital registrations")
        self.hospital.refresh_from_db()
        self.assertEqual(self.hospital.approval_status, HospitalApprovalStatus.PENDING)

    def test_reject_action_with_reason_rejects_and_notifies(self):
        response = self.client.post(
            "/admin/hospitals/hospital/",
            {
                "action": "reject_hospitals",
                "_selected_action": [self.hospital.pk],
                "index": "0",
                "apply": "Reject hospitals",
                "rejection_reason": "No operating licence",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.hospital.refresh_from_db()
        self.assertEqual(self.hospital.approval_status, HospitalApprovalStatus.REJECTED)
        self.assertEqual(self.hospital.rejection_reason, "No operating licence")
        self.assertTrue(
            self.user.notifications.filter(subject="Hospital registration rejected").exists()
        )

    def test_reject_action_without_reason_rerenders_with_error(self):
        response = self.client.post(
            "/admin/hospitals/hospital/",
            {
                "action": "reject_hospitals",
                "_selected_action": [self.hospital.pk],
                "index": "0",
                "apply": "Reject hospitals",
                "rejection_reason": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.hospital.refresh_from_db()
        self.assertEqual(self.hospital.approval_status, HospitalApprovalStatus.PENDING)


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
