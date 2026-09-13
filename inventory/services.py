"""Inventory logic. Stock is always computed from AVAILABLE bag rows — never stored."""
from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from audit.services import log_action
from cbods.constants import BloodGroup
from donors.services import can_donate
from notifications.services import notify, notify_many

from .models import BagStatus, BloodBag, Donation, TTIResult, TTITestRecord


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


def available_groups_map(hospitals):
    """{hospital_id: [groups]} for many hospitals in a single query."""
    pairs = (
        BloodBag.objects.filter(hospital__in=hospitals, status=BagStatus.AVAILABLE)
        .values_list("hospital_id", "blood_group")
        .distinct()
    )
    groups = {h.pk: [] for h in hospitals}
    for hospital_id, blood_group in pairs:
        groups[hospital_id].append(blood_group)
    return {hospital_id: sorted(gs) for hospital_id, gs in groups.items()}


def stock_map(hospitals):
    """{hospital_id: {blood_group: available_count}} for many hospitals, all 8
    groups present, from a single aggregate query — the donor-facing directory
    uses it to show counts and flag short groups without N+1 queries."""
    rows = (
        BloodBag.objects.filter(hospital__in=hospitals, status=BagStatus.AVAILABLE)
        .values("hospital_id", "blood_group")
        .annotate(n=Count("id"))
        .values_list("hospital_id", "blood_group", "n")
    )
    stock = {h.pk: {bg: 0 for bg in BloodGroup.values} for h in hospitals}
    for hospital_id, blood_group, n in rows:
        stock[hospital_id][blood_group] = n
    return stock


def record_donation(staff_user, donor, hospital, volume_ml=450):
    """Record a completed donation and create its blood bag and TTI record.

    The bag is born UNTESTED: it cannot be reserved or issued until the
    laboratory has screened it for transfusion-transmissible infections and
    every marker is non-reactive (see record_tti_results). Raises ValueError
    when the donor is not currently eligible — eligibility is enforced here in
    the service, not only in the UI.
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
        status=BagStatus.UNTESTED,
    )
    record = TTITestRecord.objects.create(donation=donation)
    log_action(staff_user, "BAG_CREATED", bag, {"status": bag.status, "blood_group": bag.blood_group})
    log_action(staff_user, "TTI_RECORD_CREATED", record, {"donation_id": donation.pk})
    return donation, bag


def record_tti_results(staff_user, donation, **marker_results):
    """Store the laboratory's TTI results for one donation and gate its bag.

    All four markers must be supplied. When every result is NEGATIVE the
    donation's bag becomes AVAILABLE and enters the stock pool; when any is
    POSITIVE the bag is DISCARDED with the reactive markers as the reason —
    the same rule BSIS enforces before a unit may be labelled and issued.

    Idempotent on an already-decided record: results may be corrected while
    the screening is incomplete, but a reactive unit stays discarded and a
    cleared unit stays available.
    """
    missing = [f for f in TTITestRecord.MARKER_FIELDS if f not in marker_results]
    if missing:
        raise ValueError(f"Missing TTI results for: {', '.join(missing)}")
    unknown = set(marker_results) - set(TTITestRecord.MARKER_FIELDS)
    if unknown:
        raise ValueError(f"Unknown TTI markers: {', '.join(sorted(unknown))}")

    record, _ = TTITestRecord.objects.get_or_create(donation=donation)
    if record.is_complete:
        raise ValueError("TTI screening for this donation has already been completed.")

    for field, value in marker_results.items():
        if value not in TTIResult.values:
            raise ValueError(f"Invalid result {value!r} for {field}.")
        setattr(record, field, value)
    record.tested_by = staff_user
    record.save()

    bag = BloodBag.objects.filter(donation=donation).first()
    if not record.is_complete:
        return record, bag

    if bag is not None:
        reactive = record.reactive_markers
        if reactive:
            set_bag_status(
                bag, BagStatus.DISCARDED, staff_user,
                {"reason": f"Reactive TTI result: {', '.join(reactive)}", "tti_record_id": record.pk},
            )
            record.discarded_reason = f"Reactive TTI result: {', '.join(reactive)}"
            record.save(update_fields=["discarded_reason"])
            notify(
                donation.donor.user,
                "Your recent donation could not be used",
                "Thank you for donating at "
                f"{donation.hospital.name}. Routine laboratory screening means we cannot "
                "use your most recent donation, and we ask that you speak to a healthcare "
                "provider about further testing. Please contact the blood bank for "
                "counselling and support.",
            )
        elif bag.expiry_date < timezone.localdate():
            # Screening cleared but the unit aged out while awaiting the lab:
            # it must not enter the pool past its shelf life.
            set_bag_status(bag, BagStatus.EXPIRED, staff_user, {"reason": "expired while awaiting TTI screening"})
        else:
            set_bag_status(bag, BagStatus.AVAILABLE, staff_user, {"tti_record_id": record.pk})
    return record, bag


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
        expiry_date__lt=today, status__in=[BagStatus.UNTESTED, BagStatus.AVAILABLE, BagStatus.RESERVED]
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
