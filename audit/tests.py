import datetime

from django.test import TestCase
from django.utils import timezone

from accounts.models import Role, User
from donors.tests import make_donor
from hospitals.models import Hospital
from inventory.models import BloodBag


class CsvExportTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="csvadmin", password="x", role=Role.ADMIN)
        self.hospital = Hospital.objects.create(name="Accra Central", city="Accra", address="a", phone="p")
        make_donor("csvdonor", blood_group="O+", city="Accra")
        today = timezone.localdate()
        BloodBag.objects.create(
            hospital=self.hospital, blood_group="O+", collected_date=today,
            expiry_date=today + datetime.timedelta(days=30),
        )

    def test_each_report_downloads_as_csv(self):
        self.client.force_login(self.admin)
        for report, header in [
            ("donors", "Name,Blood group"),
            ("donations", "Date,Donor"),
            ("requests", "Created,Patient"),
            ("bags", "Hospital,Blood group"),
            ("audit", "Time,Actor"),
        ]:
            r = self.client.get(f"/audit/export/{report}/")
            self.assertEqual(r.status_code, 200, report)
            self.assertEqual(r["Content-Type"], "text/csv")
            self.assertIn(f"cbods_{report.replace('requests', 'blood_requests').replace('bags', 'blood_bags')}",
                          r["Content-Disposition"])
            self.assertIn(header, r.content.decode())

    def test_donor_row_present(self):
        self.client.force_login(self.admin)
        r = self.client.get("/audit/export/donors/")
        self.assertIn("Donor csvdonor", r.content.decode())

    def test_unknown_report_404(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/audit/export/secrets/").status_code, 404)

    def test_non_admin_cannot_export(self):
        staff = User.objects.create_user(username="csvstaff", password="x", role=Role.HOSPITAL_STAFF)
        self.client.force_login(staff)
        self.assertEqual(self.client.get("/audit/export/donors/").status_code, 403)


class PaginationTests(TestCase):
    def test_donor_search_paginates(self):
        admin = User.objects.create_user(username="pgadmin", password="x", role=Role.ADMIN)
        for i in range(30):
            make_donor(f"pg{i}", city="Accra")
        self.client.force_login(admin)

        r = self.client.get("/donors/search/")
        self.assertEqual(len(r.context["donors"]), 25)
        self.assertContains(r, "Page 1 of 2")

        r = self.client.get("/donors/search/?page=2")
        self.assertEqual(len(r.context["donors"]), 5)

    def test_filters_survive_paging(self):
        admin = User.objects.create_user(username="pgadmin2", password="x", role=Role.ADMIN)
        for i in range(30):
            make_donor(f"pgf{i}", city="Tema")
        self.client.force_login(admin)
        r = self.client.get("/donors/search/?city=Tema")
        self.assertContains(r, "city=Tema&amp;page=2")
