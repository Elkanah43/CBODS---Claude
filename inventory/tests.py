"""TTI laboratory screening gate.

A donation's bag is born UNTESTED and can only reach the stock pool through
record_tti_results with all four markers non-reactive; a reactive marker
discards the bag, notifies the donor, and records why.
"""
import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import Role, User
from audit.models import AuditLog
from donors.services import screen_donor
from donors.tests import make_donor
from hospitals.models import Hospital, StaffProfile
from inventory.models import BagStatus, BloodBag, TTIResult, TTITestRecord
from inventory.services import expire_past_due_bags, record_donation, record_tti_results
from notifications.models import Notification
from requests_app.models import BloodRequest
from requests_app.services import accept_request

NEG = TTIResult.NEGATIVE
POS = TTIResult.POSITIVE


class TTIGateTests(TestCase):
    def setUp(self):
        self.hospital = Hospital.objects.create(name="Lab Hospital", city="Accra", address="a", phone="1")
        self.staff = User.objects.create_user(username="labstaff", password="x", role=Role.HOSPITAL_STAFF)
        StaffProfile.objects.create(user=self.staff, hospital=self.hospital)
        self.patient = User.objects.create_user(username="labpat", password="x", role=Role.PATIENT)

    def _donor(self, username="ttidonor", blood_group="O+"):
        return make_donor(username, blood_group=blood_group, city="Accra")

    def _donate(self, username="ttidonor", blood_group="O+"):
        donor = self._donor(username, blood_group)
        screen_donor(donor, Decimal("13.5"), 120, 80)
        _, bag = record_donation(self.staff, donor, self.hospital)
        return donor, bag

    def _results(self, **overrides):
        results = {f: NEG for f in TTITestRecord.MARKER_FIELDS}
        results.update(overrides)
        return results

    def test_donation_creates_untested_bag_and_tti_record(self):
        donor, bag = self._donate()
        self.assertEqual(bag.status, BagStatus.UNTESTED)
        record = bag.donation.tti_record
        self.assertIsNotNone(record)
        self.assertFalse(record.is_complete)
        self.assertTrue(AuditLog.objects.filter(action="TTI_RECORD_CREATED", entity_id=str(record.pk)).exists())

    def test_untested_bag_is_invisible_to_the_stock_pool(self):
        _, bag = self._donate()
        stock = BloodBag.objects.filter(hospital=self.hospital, status=BagStatus.AVAILABLE)
        self.assertNotIn(bag, stock)

    def test_untested_bag_cannot_be_reserved(self):
        _, bag = self._donate()
        req = BloodRequest.objects.create(
            patient=self.patient, hospital=self.hospital,
            blood_group=bag.blood_group, units_requested=1,
        )
        with self.assertRaises(Exception):
            accept_request(self.staff, req)
        req.refresh_from_db()
        bag.refresh_from_db()
        self.assertEqual(req.status, "PENDING")
        self.assertEqual(bag.status, BagStatus.UNTESTED)

    def test_partial_results_are_rejected_and_do_not_release(self):
        """The service refuses a screening that is not complete, so a partially
        entered result can never release or discard the bag."""
        _, bag = self._donate()
        with self.assertRaises(ValueError):
            record_tti_results(self.staff, bag.donation, hiv=NEG, hepatitis_b=NEG)
        bag.refresh_from_db()
        self.assertEqual(bag.status, BagStatus.UNTESTED)
        record = bag.donation.tti_record
        record.refresh_from_db()
        self.assertIsNone(record.hiv)  # nothing persisted from the partial call

    def test_negative_results_release_bag_into_pool(self):
        donor, bag = self._donate()
        record, released = record_tti_results(self.staff, bag.donation, **self._results())
        bag.refresh_from_db()
        self.assertEqual(bag.status, BagStatus.AVAILABLE)
        self.assertTrue(record.is_complete)
        self.assertEqual(released.status, BagStatus.AVAILABLE)
        self.assertTrue(AuditLog.objects.filter(action="BAG_AVAILABLE", entity_id=str(bag.pk)).exists())
        # A released bag can now be reserved.
        req = BloodRequest.objects.create(
            patient=self.patient, hospital=self.hospital,
            blood_group=donor.blood_group, units_requested=1,
        )
        accept_request(self.staff, req)
        bag.refresh_from_db()
        self.assertEqual(bag.status, BagStatus.RESERVED)

    def test_completed_screening_is_idempotent(self):
        _, bag = self._donate()
        record_tti_results(self.staff, bag.donation, **self._results())
        with self.assertRaises(ValueError):
            record_tti_results(self.staff, bag.donation, **self._results())

    def test_reactive_marker_discards_bag_and_notifies_donor(self):
        donor, bag = self._donate()
        record, _ = record_tti_results(self.staff, bag.donation, **self._results(hiv=POS))
        bag.refresh_from_db()
        self.assertEqual(bag.status, BagStatus.DISCARDED)
        self.assertIn("HIV", record.discarded_reason)
        self.assertTrue(AuditLog.objects.filter(action="BAG_DISCARDED", entity_id=str(bag.pk)).exists())
        self.assertTrue(
            Notification.objects.filter(user=donor.user, subject__icontains="could not be used").exists()
        )

    def test_reactive_marker_blocks_reservation_too(self):
        _, bag = self._donate()
        record_tti_results(self.staff, bag.donation, **self._results(syphilis=POS))
        req = BloodRequest.objects.create(
            patient=self.patient, hospital=self.hospital, blood_group="O+", units_requested=1,
        )
        with self.assertRaises(Exception):
            accept_request(self.staff, req)

    def test_missing_and_unknown_markers_raise(self):
        _, bag = self._donate()
        with self.assertRaises(ValueError):
            record_tti_results(self.staff, bag.donation, hiv=NEG)
        with self.assertRaises(ValueError):
            record_tti_results(self.staff, bag.donation, **self._results(), malaria=NEG)

    def test_unit_aged_out_while_awaiting_lab_expires_instead(self):
        _, bag = self._donate()
        BloodBag.objects.filter(pk=bag.pk).update(
            expiry_date=timezone.localdate() - datetime.timedelta(days=1)
        )
        record_tti_results(self.staff, bag.donation, **self._results())
        bag.refresh_from_db()
        self.assertEqual(bag.status, BagStatus.EXPIRED)
        self.assertFalse(
            BloodBag.objects.filter(hospital=self.hospital, status=BagStatus.AVAILABLE).exists()
        )

    def test_expire_bags_command_covers_untested_bags(self):
        _, bag = self._donate()
        BloodBag.objects.filter(pk=bag.pk).update(
            expiry_date=timezone.localdate() - datetime.timedelta(days=1)
        )
        self.assertEqual(expire_past_due_bags(), 1)
        bag.refresh_from_db()
        self.assertEqual(bag.status, BagStatus.EXPIRED)
