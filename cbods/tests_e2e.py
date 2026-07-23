"""End-to-end walkthrough of the whole system, driven entirely through HTTP.

Every step below is performed the way a real user would perform it — logging in,
submitting forms, following redirects — so this test proves the demo story works
from registration to audit trail, not just that the services behave in isolation.
"""
import datetime

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from accounts.models import Role, User
from audit.models import AuditLog
from donors.models import Donor
from hospitals.models import Hospital, StaffProfile
from inventory.models import BagStatus, BloodBag
from notifications.models import Notification
from organs.models import OrganDonationRequest
from requests_app.models import BloodRequest

PASSWORD = "Str0ngPass!234"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d4944415478da63fcff9fa10e0002d40197ec1f83660000000049454e44ae426082"
)


class FullDemoFlowTests(TestCase):
    """The complete journey: donor registers -> admin approves -> screening ->
    donation -> patient request -> reserve -> issue -> emergency broadcast ->
    organ request -> admin dashboard and audit log."""

    def setUp(self):
        self.hospital = Hospital.objects.create(
            name="Accra Central Hospital", city="Accra",
            address="12 Independence Ave", phone="030-222-1111",
        )
        self.admin = User.objects.create_user(username="e2e_admin", password=PASSWORD, role=Role.ADMIN)
        self.staff = User.objects.create_user(username="e2e_staff", password=PASSWORD, role=Role.HOSPITAL_STAFF)
        StaffProfile.objects.create(user=self.staff, hospital=self.hospital)

    def test_full_demo_flow(self):
        c = self.client

        # 1. Donor self-registers and uploads a government ID.
        c.post("/accounts/register/", {
            "username": "e2e_donor", "email": "d@example.com", "phone": "024-000-0001",
            "role": "DONOR", "password1": PASSWORD, "password2": PASSWORD,
        })
        c.post("/donors/profile/", {
            "full_name": "Ama Mensah", "date_of_birth": "1995-03-03", "sex": "F",
            "blood_group": "B+", "weight_kg": "68.0", "city": "Accra",
            "contact_phone": "024-000-0001", "medical_history": "",
            "id_document": SimpleUploadedFile("id.png", PNG, content_type="image/png"),
        })
        donor = Donor.objects.get(user__username="e2e_donor")
        self.assertEqual(donor.registration_status, "PENDING")

        # 2. Admin reviews the ID through the gated view and approves.
        c.force_login(self.admin)
        detail = c.get(f"/donors/approvals/{donor.pk}/")
        self.assertContains(detail, f"/donors/approvals/{donor.pk}/id-document/")
        self.assertEqual(c.get(f"/donors/approvals/{donor.pk}/id-document/").status_code, 200)
        c.post(f"/donors/approvals/{donor.pk}/", {"action": "approve"})
        donor.refresh_from_db()
        self.assertEqual(donor.registration_status, "APPROVED")
        self.assertTrue(Notification.objects.filter(user=donor.user, subject__icontains="approved").exists())

        # 3. Hospital staff screen the donor; both stages pass.
        c.force_login(self.staff)
        c.post(f"/donors/screening/{donor.pk}/", {
            "hemoglobin_g_dl": "13.8", "systolic_bp": "118", "diastolic_bp": "76",
        })
        self.assertEqual(donor.screenings.first().outcome, "ELIGIBLE")

        # 4. Staff record the donation, which creates an AVAILABLE bag.
        c.post("/inventory/donate/", {"donor": donor.pk, "volume_ml": 450})
        bag = BloodBag.objects.get(donation__donor=donor)
        self.assertEqual(bag.status, BagStatus.AVAILABLE)
        self.assertEqual(bag.blood_group, "B+")
        self.assertEqual(bag.hospital, self.hospital)
        self.assertEqual(bag.expiry_date, bag.collected_date + datetime.timedelta(days=35))

        # 5. A patient registers and requests a group the hospital has in stock.
        c.post("/accounts/logout/")
        c.post("/accounts/register/", {
            "username": "e2e_patient", "email": "p@example.com", "phone": "024-000-0002",
            "role": "PATIENT", "password1": PASSWORD, "password2": PASSWORD,
        })
        patient = User.objects.get(username="e2e_patient")
        form = c.get(f"/requests/new/{self.hospital.pk}/")
        self.assertContains(form, 'value="B+"')
        c.post(f"/requests/new/{self.hospital.pk}/", {
            "blood_group": "B+", "units_requested": 1, "urgency": "URGENT",
        })
        blood_request = BloodRequest.objects.get(patient=patient)
        self.assertEqual(blood_request.status, "PENDING")

        # 6. Staff accept (bag reserved, FEFO) then fulfil (bag issued).
        c.force_login(self.staff)
        c.post(f"/requests/action/{blood_request.pk}/", {"action": "accept"})
        blood_request.refresh_from_db()
        bag.refresh_from_db()
        self.assertEqual(blood_request.status, "ACCEPTED")
        self.assertEqual(bag.status, BagStatus.RESERVED)
        self.assertEqual(bag.reserved_for, blood_request)

        c.post(f"/requests/action/{blood_request.pk}/", {"action": "fulfil"})
        blood_request.refresh_from_db()
        bag.refresh_from_db()
        self.assertEqual(blood_request.status, "FULFILLED")
        self.assertEqual(bag.status, BagStatus.ISSUED)
        self.assertTrue(Notification.objects.filter(user=patient, subject__icontains="fulfilled").exists())

        # 7. An EMERGENCY request that stock cannot meet triggers the donor broadcast
        #    and sends staff to the ranked suggestions page.
        emergency = BloodRequest.objects.create(
            patient=patient, hospital=self.hospital, blood_group="B+",
            units_requested=5, urgency="EMERGENCY",
        )
        response = c.post(f"/requests/action/{emergency.pk}/", {"action": "accept"}, follow=True)
        self.assertContains(response, "Emergency broadcast sent")
        self.assertContains(response, "Compatible donor suggestions")
        # the donor is B+ in the hospital's city, so they are compatible and reached
        self.assertTrue(Notification.objects.filter(user=donor.user, subject__startswith="URGENT").exists())
        emergency.refresh_from_db()
        self.assertEqual(emergency.status, "PENDING")  # nothing reserved on failure

        # 8. Organ request goes PENDING -> APPROVED and shows live on the donor's dashboard.
        c.force_login(donor.user)
        c.post("/organs/new/", {"organ_type": "CORNEA", "hospital": self.hospital.pk})
        organ = OrganDonationRequest.objects.get(donor=donor)
        self.assertEqual(organ.status, "PENDING")

        c.force_login(self.staff)
        c.post(f"/organs/review/{organ.pk}/", {"status": "APPROVED"})
        organ.refresh_from_db()
        self.assertEqual(organ.status, "APPROVED")
        self.assertIsNotNone(organ.decided_at)

        c.force_login(donor.user)
        dashboard = c.get("/accounts/dashboard/")
        self.assertContains(dashboard, "Cornea")
        self.assertContains(dashboard, "Approved")

        # 9. Admin dashboard and audit log reflect every step above.
        c.force_login(self.admin)
        self.assertEqual(c.get("/audit/dashboard/").status_code, 200)
        self.assertEqual(c.get("/audit/log/").status_code, 200)
        for action in [
            "DONOR_APPROVED", "BAG_CREATED", "BAG_RESERVED", "BAG_ISSUED",
            "REQUEST_ACCEPTED", "REQUEST_FULFILLED", "ORGAN_REQUEST_APPROVED",
        ]:
            self.assertTrue(AuditLog.objects.filter(action=action).exists(), action)

    def test_expiry_command_and_low_stock_alert(self):
        """The daily command expires past-due bags and warns that hospital's staff."""
        from inventory.services import expire_past_due_bags

        today = timezone.localdate()
        stale = BloodBag.objects.create(
            hospital=self.hospital, blood_group="O+",
            collected_date=today - datetime.timedelta(days=40),
            expiry_date=today - datetime.timedelta(days=5),
        )
        expired_count = expire_past_due_bags()
        stale.refresh_from_db()
        self.assertEqual(expired_count, 1)
        self.assertEqual(stale.status, BagStatus.EXPIRED)
        self.assertTrue(AuditLog.objects.filter(action="BAG_EXPIRED").exists())
        self.assertTrue(
            Notification.objects.filter(user=self.staff, subject__icontains="Low stock").exists()
        )
