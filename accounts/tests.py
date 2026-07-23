"""Privacy-partition tests: role gates and per-hospital data isolation."""
import datetime

from django.test import TestCase
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
