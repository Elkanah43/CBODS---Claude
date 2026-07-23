"""Inventory logic. Stock is always computed from AVAILABLE bag rows — never stored."""
from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from audit.services import log_action
from cbods.constants import BloodGroup
from donors.services import can_donate
from notifications.services import notify_many

from .models import BagStatus, BloodBag, Donation


def stock_by_group(hospital):
    """{blood_group: available_count} for one hospital, all 8 groups present."""
    counts = dict(
        BloodBag.objects.filter(hospital=hospital, status=BagStatus.AVAILABLE)
        .values_list("blood_group")
        .annotate(n=Count("id"))
        .values_list("blood_group", "n")
    )
    return {bg: counts.get(bg, 0) for bg in BloodGroup.values}


def available_groups(hospital):
    """Blood groups this hospital currently has AVAILABLE."""
    return sorted(
        BloodBag.objects.filter(hospital=hospital, status=BagStatus.AVAILABLE)
        .values_list("blood_group", flat=True)
        .distinct()
    )


def record_donation(staff_user, donor, hospital, volume_ml=450):
    """Record a completed donation and create its AVAILABLE blood bag.

    Raises ValueError when the donor is not currently eligible — eligibility is
    enforced here in the service, not only in the UI.
    """
    ok, why = can_donate(donor)
    if not ok:
        raise ValueError(why)

    now = timezone.now()
    donation = Donation.objects.create(
        donor=donor, hospital=hospital, donated_at=now, volume_ml=volume_ml, recorded_by=staff_user
    )
    collected = now.date()
    bag = BloodBag.objects.create(
        hospital=hospital,
        blood_group=donor.blood_group,
        volume_ml=volume_ml,
        collected_date=collected,
        expiry_date=collected + timedelta(days=settings.BLOOD_BAG_SHELF_LIFE_DAYS),
        donation=donation,
    )
    log_action(staff_user, "BAG_CREATED", bag, {"status": bag.status, "blood_group": bag.blood_group})
    return donation, bag


def set_bag_status(bag, new_status, actor=None, details=None):
    """Single choke point for bag status changes so every one is audited."""
    old = bag.status
    if old == new_status:
        return bag
    bag.status = new_status
    bag.save(update_fields=["status"])
    log_action(actor, f"BAG_{new_status}", bag, {"from": old, "to": new_status, **(details or {})})
    if old == BagStatus.AVAILABLE:
        check_low_stock(bag.hospital, bag.blood_group)
    return bag


def check_low_stock(hospital, blood_group):
    """Notify the hospital's staff when a group's available count falls below threshold."""
    count = BloodBag.objects.filter(
        hospital=hospital, blood_group=blood_group, status=BagStatus.AVAILABLE
    ).count()
    if count < settings.LOW_STOCK_THRESHOLD:
        staff_users = [sp.user for sp in hospital.staff.select_related("user")]
        notify_many(
            staff_users,
            f"Low stock: {blood_group} at {hospital.name}",
            f"Only {count} AVAILABLE {blood_group} bag(s) remain at {hospital.name} "
            f"(threshold {settings.LOW_STOCK_THRESHOLD}).",
        )


def expire_past_due_bags(actor=None):
    """Mark past-expiry AVAILABLE/RESERVED bags EXPIRED. Returns number expired."""
    today = timezone.localdate()
    bags = BloodBag.objects.filter(
        expiry_date__lt=today, status__in=[BagStatus.AVAILABLE, BagStatus.RESERVED]
    )
    n = 0
    for bag in bags:
        set_bag_status(bag, BagStatus.EXPIRED, actor, {"expiry_date": str(bag.expiry_date)})
        n += 1
    return n


def near_expiry_qs(hospital):
    """AVAILABLE bags at this hospital expiring within the warning window."""
    today = timezone.localdate()
    return BloodBag.objects.filter(
        hospital=hospital,
        status=BagStatus.AVAILABLE,
        expiry_date__lte=today + timedelta(days=settings.EXPIRY_WARNING_DAYS),
    )
