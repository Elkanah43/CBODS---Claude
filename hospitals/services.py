"""Hospital-level reporting: monthly aggregates and the activity feed.

The monthly series are label->count dicts (oldest first) ready for Chart.js;
the activity feed is a flat list of {at, kind, text, actor} events, newest
first, so a hospital can see its own story without consulting an admin.
"""
from django.db.models import Count
from django.db.models.functions import TruncMonth

from audit.models import AuditLog
from inventory.models import BagStatus, BloodBag, Donation
from organs.models import OrganDonationRequest
from requests_app.models import BloodRequest, RequestStatus

# How many recent events the activity feed shows.
FEED_CAP = 50

# Audit actions that mark a blood request's status, and the verb for each.
REQUEST_ACTIONS = {
    "REQUEST_ACCEPTED": "accepted",
    "REQUEST_REJECTED": "rejected",
    "REQUEST_FULFILLED": "fulfilled",
}

# Hospital lifecycle events worth surfacing in the feed.
HOSPITAL_LIFECYCLE = (
    ("HOSPITAL_REGISTERED", "Registration submitted"),
    ("HOSPITAL_APPROVED", "Registration approved"),
    ("HOSPITAL_REJECTED", "Registration rejected"),
    ("HOSPITAL_RESUBMITTED", "Registration resubmitted"),
)


def donations_by_month(hospital):
    """{"Jan 2026": n} of recorded donations, oldest first."""
    qs = (
        Donation.objects.filter(hospital=hospital)
        .annotate(month=TruncMonth("donated_at"))
        .values("month")
        .annotate(n=Count("id"))
        .order_by("month")
    )
    return {row["month"].strftime("%b %Y"): row["n"] for row in qs}


def _audited_by_month(entity_type, action, entity_ids):
    """Count audit entries of one action against the given entity ids.

    The audit trail is generic, so entries are matched by entity id rather than
    by a hospital column. Returns {"Jan 2026": n}, oldest first.
    """
    ids = [str(i) for i in entity_ids]
    if not ids:
        return {}
    logs = AuditLog.objects.filter(
        entity_type=entity_type, entity_id__in=ids, action=action
    ).order_by("created_at")
    months = {}
    for log in logs:
        key = log.created_at.strftime("%b %Y")
        months[key] = months.get(key, 0) + 1
    return months


def issued_bags_by_month(hospital):
    """Issued bags over time, timed by their BAG_ISSUED audit entry."""
    ids = BloodBag.objects.filter(hospital=hospital, status=BagStatus.ISSUED).values_list("id", flat=True)
    return _audited_by_month("BloodBag", "BAG_ISSUED", ids)


def fulfilled_requests_by_month(hospital):
    """Fulfilled blood requests over time, timed by REQUEST_FULFILLED."""
    ids = BloodRequest.objects.filter(
        hospital=hospital, status=RequestStatus.FULFILLED
    ).values_list("id", flat=True)
    return _audited_by_month("BloodRequest", "REQUEST_FULFILLED", ids)


def hospital_activity_items(hospital):
    """Recent events for the hospital, newest first, capped at FEED_CAP."""
    items = []

    for d in hospital.donations.select_related("donor", "recorded_by"):
        items.append({
            "at": d.donated_at,
            "kind": "donation",
            "text": f"Donation recorded — {d.donor.full_name} ({d.donor.blood_group}), {d.volume_ml} ml",
            "actor": d.recorded_by.username if d.recorded_by else "system",
        })

    # Creation events are worded as "submitted" so the current status (which
    # may have changed since) never misdates the feed; status changes are
    # carried separately by the audit entries below.
    for r in hospital.blood_requests.select_related("patient"):
        items.append({
            "at": r.created_at,
            "kind": "request",
            "text": (f"Blood request submitted — {r.patient.username}, "
                     f"{r.units_requested}×{r.blood_group}"),
            "actor": r.patient.username,
        })

    for o in hospital.organ_requests.select_related("donor"):
        items.append({
            "at": o.decided_at or o.created_at,
            "kind": "organ",
            "text": (f"Organ request {o.get_status_display().lower()} — {o.donor.full_name}, "
                     f"{o.get_organ_type_display()}"),
            "actor": o.donor.full_name,
        })

    # Status-change events carry the staff member who acted.
    req_ids = [str(i) for i in hospital.blood_requests.values_list("id", flat=True)]
    if req_ids:
        logs = AuditLog.objects.filter(
            entity_type="BloodRequest", entity_id__in=req_ids,
            action__in=REQUEST_ACTIONS,
        ).select_related("actor")
        for log in logs:
            items.append({
                "at": log.created_at,
                "kind": "request",
                "text": f"Blood request {REQUEST_ACTIONS[log.action]} by staff",
                "actor": log.actor.username if log.actor else "system",
            })

    # Hospital lifecycle events (registration submitted, approved, rejected…).
    for action, text in HOSPITAL_LIFECYCLE:
        logs = AuditLog.objects.filter(
            entity_type="Hospital", entity_id=str(hospital.pk), action=action
        ).select_related("actor")
        for log in logs:
            items.append({
                "at": log.created_at,
                "kind": "hospital",
                "text": text,
                "actor": log.actor.username if log.actor else "system",
            })

    items.sort(key=lambda item: item["at"], reverse=True)
    return items[:FEED_CAP]
