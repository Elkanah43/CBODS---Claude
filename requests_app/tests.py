import datetime

from django.test import TestCase
from django.utils import timezone

from accounts.models import Role, User
from donors.tests import make_donor
from hospitals.models import Hospital, StaffProfile
from inventory.models import BagStatus, BloodBag, Donation

from . import compatibility, services
from .compatibility import COMPATIBLE_DONORS, check_donor_for_recipient, is_compatible
from .models import BloodRequest

ALL_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]


class CompatibilityTreeTests(TestCase):
    """Full decision tree: every recipient group against every donor group."""

    EXPECTED = {
        "O-": {"O-"},
        "O+": {"O-", "O+"},
        "A-": {"O-", "A-"},
        "A+": {"O-", "O+", "A-", "A+"},
        "B-": {"O-", "B-"},
        "B+": {"O-", "O+", "B-", "B+"},
        "AB-": {"O-", "A-", "B-", "AB-"},
        "AB+": set(ALL_GROUPS),
    }

    def test_all_eight_recipients(self):
        for recipient, expected_donors in self.EXPECTED.items():
            self.assertEqual(set(COMPATIBLE_DONORS[recipient]), expected_donors, recipient)
            for donor_group in ALL_GROUPS:
                self.assertEqual(
                    is_compatible(recipient, donor_group),
                    donor_group in expected_donors,
                    f"{donor_group} -> {recipient}",
                )


class DenyWithAlternativesTests(TestCase):
    def setUp(self):
        self.hospital = Hospital.objects.create(name="H", city="Nairobi", address="a", phone="p")

    def test_incompatible_denied_with_alternatives(self):
        opos = make_donor("opos", blood_group="O+")
        oneg = make_donor("oneg", blood_group="O-")
        BloodBag.objects.create(
            hospital=self.hospital, blood_group="O-",
            collected_date=timezone.localdate(),
            expiry_date=timezone.localdate() + datetime.timedelta(days=30),
        )
        ok, alternatives = check_donor_for_recipient(self.hospital, "O-", opos)
        self.assertFalse(ok)
        self.assertIn(oneg, alternatives["donors"])
        self.assertEqual(alternatives["bags"].count(), 1)

    def test_compatible_allowed(self):
        oneg = make_donor("oneg2", blood_group="O-")
        ok, alternatives = check_donor_for_recipient(self.hospital, "A+", oneg)
        self.assertTrue(ok)
        self.assertIsNone(alternatives)


def make_stock(hospital, group, n, start_days=5):
    bags = []
    today = timezone.localdate()
    for i in range(n):
        bags.append(
            BloodBag.objects.create(
                hospital=hospital, blood_group=group, collected_date=today,
                expiry_date=today + datetime.timedelta(days=start_days + i * 5),
            )
        )
    return bags


class RequestLifecycleTests(TestCase):
    def setUp(self):
        self.hospital = Hospital.objects.create(name="H", city="Nairobi", address="a", phone="p")
        self.staff = User.objects.create_user(username="staff", password="x", role=Role.HOSPITAL_STAFF)
        StaffProfile.objects.create(user=self.staff, hospital=self.hospital)
        self.patient = User.objects.create_user(username="pat", password="x", role=Role.PATIENT)

    def _request(self, units=2, urgency="ROUTINE", group="O+"):
        return BloodRequest.objects.create(
            patient=self.patient, hospital=self.hospital, blood_group=group,
            units_requested=units, urgency=urgency,
        )

    def test_accept_reserves_fefo(self):
        bags = make_stock(self.hospital, "O+", 3)
        req = self._request(units=2)
        services.accept_request(self.staff, req)
        for bag in bags:
            bag.refresh_from_db()
        # soonest two expire first -> reserved; latest stays available
        self.assertEqual(bags[0].status, BagStatus.RESERVED)
        self.assertEqual(bags[1].status, BagStatus.RESERVED)
        self.assertEqual(bags[2].status, BagStatus.AVAILABLE)

    def test_double_issue_race(self):
        """A bag can never be issued twice: second fulfilment finds no RESERVED
        bags (status re-checked under select_for_update) and raises."""
        make_stock(self.hospital, "O+", 2)
        req = self._request(units=2)
        services.accept_request(self.staff, req)
        stale_copy = BloodRequest.objects.get(pk=req.pk)

        services.fulfil_request(self.staff, req)
        issued = BloodBag.objects.filter(status=BagStatus.ISSUED).count()
        self.assertEqual(issued, 2)

        stale_copy.status = "ACCEPTED"  # simulate a racing worker with stale state
        with self.assertRaises(ValueError):
            services.fulfil_request(self.staff, stale_copy)
        self.assertEqual(BloodBag.objects.filter(status=BagStatus.ISSUED).count(), 2)

    def test_insufficient_stock(self):
        make_stock(self.hospital, "O+", 1)
        req = self._request(units=3)
        with self.assertRaises(services.InsufficientStock):
            services.accept_request(self.staff, req)
        req.refresh_from_db()
        self.assertEqual(req.status, "PENDING")

    def test_reject_sets_reason(self):
        req = self._request()
        services.reject_request(self.staff, req, "no stock")
        req.refresh_from_db()
        self.assertEqual(req.status, "REJECTED")
        self.assertEqual(req.rejection_reason, "no stock")

    def test_fulfil_issues_only_its_own_reserved_bags(self):
        """Two accepted requests for the same group: fulfilling one must not
        consume the bags reserved for the other."""
        make_stock(self.hospital, "O+", 4)
        other_patient = User.objects.create_user(username="pat_b", password="x", role=Role.PATIENT)
        req_a = self._request(units=2)
        req_b = BloodRequest.objects.create(
            patient=other_patient, hospital=self.hospital, blood_group="O+", units_requested=2
        )
        services.accept_request(self.staff, req_a)
        services.accept_request(self.staff, req_b)

        services.fulfil_request(self.staff, req_a)
        self.assertEqual(BloodBag.objects.filter(reserved_for=req_a, status=BagStatus.ISSUED).count(), 2)
        # req_b's reservations survive untouched and it can still be fulfilled
        self.assertEqual(BloodBag.objects.filter(reserved_for=req_b, status=BagStatus.RESERVED).count(), 2)
        services.fulfil_request(self.staff, req_b)
        self.assertEqual(BloodBag.objects.filter(reserved_for=req_b, status=BagStatus.ISSUED).count(), 2)

    def test_accept_substitutes_compatible_bags(self):
        """An A+ request is served by A+ stock first, topped up with compatible O-."""
        make_stock(self.hospital, "A+", 1)
        make_stock(self.hospital, "O-", 2, start_days=40)
        req = self._request(units=2, group="A+")
        services.accept_request(self.staff, req)
        reserved = BloodBag.objects.filter(reserved_for=req, status=BagStatus.RESERVED)
        self.assertEqual(reserved.count(), 2)
        self.assertEqual(reserved.filter(blood_group="A+").count(), 1)
        self.assertEqual(reserved.filter(blood_group="O-").count(), 1)

    def test_accept_never_reserves_incompatible_bags(self):
        make_stock(self.hospital, "AB+", 3)
        req = self._request(units=1, group="O-")  # O- can only take O-
        with self.assertRaises(services.InsufficientStock):
            services.accept_request(self.staff, req)
        self.assertEqual(BloodBag.objects.filter(status=BagStatus.RESERVED).count(), 0)

    def test_emergency_ranks_eligible_donors_first(self):
        """Urgency changes the ranking strategy: for EMERGENCY a donor who can give
        today outranks a same-city donor who is still inside the 90-day interval."""
        local_waiting = make_donor("local_wait", blood_group="O-", city="Nairobi")
        far_ready = make_donor("far_ready", blood_group="O-", city="Mombasa")
        Donation.objects.create(
            donor=local_waiting, hospital=self.hospital,
            donated_at=timezone.now() - datetime.timedelta(days=10), volume_ml=450,
        )
        emergency = compatibility.suggest_donors(self.hospital, "O-", "EMERGENCY")
        self.assertEqual(emergency[0], far_ready)
        routine = compatibility.suggest_donors(self.hospital, "O-", "ROUTINE")
        self.assertEqual(routine[0], local_waiting)

    def test_emergency_broadcast_targets_compatible_same_city(self):
        compatible_same_city = make_donor("c1", blood_group="O-", city="Nairobi")
        compatible_other_city = make_donor("c2", blood_group="O+", city="Mombasa")
        incompatible_same_city = make_donor("c3", blood_group="AB+", city="Nairobi")
        req = self._request(units=5, urgency="EMERGENCY")
        reached = services.broadcast_emergency(req)
        self.assertIn(compatible_same_city, reached)
        self.assertNotIn(compatible_other_city, reached)
        self.assertNotIn(incompatible_same_city, reached)


class AvailabilityFormTests(TestCase):
    def setUp(self):
        self.hospital = Hospital.objects.create(name="H", city="Nairobi", address="a", phone="p")
        self.patient = User.objects.create_user(username="pat2", password="x", role=Role.PATIENT)
        self.client.force_login(self.patient)

    def test_form_only_offers_groups_stock_can_serve(self):
        """Offered groups are driven by real stock, read through the compatibility
        tree: an A+ bag serves A+ and AB+ recipients and nobody else."""
        make_stock(self.hospital, "A+", 1)
        # an issued bag is not stock and must not widen the offer
        bag = make_stock(self.hospital, "B+", 1)[0]
        bag.status = BagStatus.ISSUED
        bag.save()

        r = self.client.get(f"/requests/new/{self.hospital.pk}/")
        self.assertContains(r, 'value="A+"')
        self.assertContains(r, 'value="AB+"')
        for unservable in ["O-", "O+", "A-", "B+", "B-", "AB-"]:
            self.assertNotContains(r, f'value="{unservable}"')

        # server-side: posting a group the stock cannot serve creates nothing
        r = self.client.post(
            f"/requests/new/{self.hospital.pk}/",
            {"blood_group": "B+", "units_requested": 1, "urgency": "ROUTINE"},
        )
        self.assertEqual(BloodRequest.objects.count(), 0)

    def test_universal_donor_stock_serves_every_group(self):
        make_stock(self.hospital, "O-", 1)
        r = self.client.get(f"/requests/new/{self.hospital.pk}/")
        for group in ALL_GROUPS:
            self.assertContains(r, f'value="{group}"')
