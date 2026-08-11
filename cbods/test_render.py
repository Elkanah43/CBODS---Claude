"""Every page renders, for every role that can reach it.

The behavioural tests elsewhere assert status codes and querysets, which means
a template can break — a missing {% load %}, a filter typo, a renamed context
variable — without a single test going red. These load each page for a user who
is allowed to see it and fail on any template error.
"""
import datetime
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from donors.tests import make_donor
from hospitals.models import Hospital, HospitalApprovalStatus, StaffProfile
from inventory.models import BloodBag, Donation
from organs.models import OrganDonationRequest
from requests_app.models import BloodRequest


class PageRenderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.hospital = Hospital.objects.create(
            name="Alpha General", city="Nairobi", address="1 Main St", phone="0700000001"
        )

        cls.donor = make_donor("renderdonor", city="Nairobi")
        cls.patient = User.objects.create_user(username="renderpat", password="x", role=Role.PATIENT)
        cls.admin = User.objects.create_user(
            username="renderadmin", password="x", role=Role.ADMIN, is_superuser=True
        )
        cls.staff = User.objects.create_user(username="renderstaff", password="x", role=Role.HOSPITAL_STAFF)
        StaffProfile.objects.create(user=cls.staff, hospital=cls.hospital)

        cls.hospital_account = User.objects.create_user(
            username="renderhosp", password="x", role=Role.HOSPITAL
        )
        StaffProfile.objects.create(user=cls.hospital_account, hospital=cls.hospital)

        cls.pending_hospital = Hospital.objects.create(
            name="Pending General", city="Accra", address="p", phone="0",
            approval_status=HospitalApprovalStatus.PENDING,
        )
        cls.pending_account = User.objects.create_user(
            username="renderpending", password="x", role=Role.HOSPITAL
        )
        StaffProfile.objects.create(user=cls.pending_account, hospital=cls.pending_hospital)

        # One row of every kind, so tables render their populated branch rather
        # than their empty state.
        today = timezone.localdate()
        BloodBag.objects.create(
            hospital=cls.hospital, blood_group="O+", collected_date=today,
            expiry_date=today + datetime.timedelta(days=30),
        )
        Donation.objects.create(
            donor=cls.donor, hospital=cls.hospital, volume_ml=450,
            donated_at=timezone.now(),
        )
        cls.blood_request = BloodRequest.objects.create(
            patient=cls.patient, hospital=cls.hospital, blood_group="O+", units_requested=1
        )
        cls.organ_request = OrganDonationRequest.objects.create(
            donor=cls.donor, hospital=cls.hospital, organ_type="KIDNEY"
        )

    def assertRenders(self, user, pages):
        """`pages` is a list of url names, or (name, args) pairs."""
        if user is not None:
            self.client.force_login(user)
        else:
            self.client.logout()
        for page in pages:
            name, args = page if isinstance(page, tuple) else (page, ())
            url = reverse(name, args=args)
            with self.subTest(page=name, user=getattr(user, "username", "anonymous")):
                # Any TemplateSyntaxError or missing-filter error raises here.
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, f"{url} -> {response.status_code}")
                self.assertNoTemplateSyntaxLeaked(response, url)

    def assertNoTemplateSyntaxLeaked(self, response, url):
        """No unrendered template syntax reaches the browser.

        Django's {# #} comment is single-line only: a multi-line one never finds
        its closing marker, so the whole thing is emitted as visible text. This
        shipped twice — once across the top of every page, once inside the
        navbar — because it renders without error and no assertion looked for
        it. {% comment %} is the multi-line form.
        """
        body = response.content.decode()
        for marker in ("{#", "#}", "{%", "{{"):
            self.assertNotIn(
                marker, body,
                f"{url} leaked unrendered template syntax {marker!r} into the page",
            )

    def test_public_pages(self):
        self.assertRenders(None, [
            "login", "register", "hospital_register",
            "password_reset", "password_reset_done", "password_reset_complete",
        ])

    def test_donor_pages(self):
        self.assertRenders(self.donor.user, [
            "dashboard", "donor_profile", "organ_my_requests",
            "organ_request_create", "notification_list",
        ])

    def test_patient_pages(self):
        self.assertRenders(self.patient, [
            "dashboard", "hospital_list", "my_requests",
            ("request_create", [self.hospital.pk]), "notification_list",
        ])

    def test_hospital_staff_pages(self):
        self.assertRenders(self.staff, [
            "dashboard", "stock_dashboard", "record_donation", "request_inbox",
            "compatibility_check", "donor_search", "screening_list",
            ("screening_run", [self.donor.pk]), "organ_review_list",
            "hospital_reports", "hospital_activity", "notification_list",
        ])

    def test_hospital_account_pages(self):
        """The Hospital's own account reaches every feature a staff account can,
        plus its profile and staff management."""
        self.assertRenders(self.hospital_account, [
            "dashboard", "hospital_profile", "hospital_staff",
            "stock_dashboard", "record_donation", "request_inbox",
            "compatibility_check", "donor_search", "screening_list",
            ("screening_run", [self.donor.pk]), "organ_review_list",
            "hospital_reports", "hospital_activity", "notification_list",
        ])

    def test_pending_hospital_account_sees_only_dashboard_and_profile(self):
        """A pending registration redirects every feature to the dashboard;
        only the dashboard banner and the profile page (for correcting details)
        render."""
        self.assertRenders(self.pending_account, [
            "dashboard", "hospital_profile", "notification_list",
        ])

    def test_admin_pages(self):
        self.assertRenders(self.admin, [
            "dashboard", "admin_dashboard", "audit_log", "donor_approval_queue",
            "hospital_approval_queue", "hospital_admin_list",
            ("donor_approval_detail", [self.donor.pk]), "donor_search", "notification_list",
            ("hospital_review_detail", [self.pending_hospital.pk]),
            ("hospital_review_detail", [self.hospital.pk]),
        ])

    def test_status_badges_render_a_colour_class(self):
        """The badge filter is loaded wherever it is used."""
        self.client.force_login(self.staff)
        response = self.client.get("/requests/inbox/")
        self.assertContains(response, "badge bg-warning text-dark")  # PENDING
        self.assertNotContains(response, "badge </span>")  # filter silently returning ""
