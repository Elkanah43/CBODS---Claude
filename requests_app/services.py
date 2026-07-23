"""Blood request lifecycle. Reserving and issuing are race-safe:
both run inside transaction.atomic() with select_for_update() and re-check
bag status, so a bag can never be reserved or issued twice.
"""
from django.db import transaction

from audit.services import log_action
from inventory.models import BagStatus, BloodBag
from inventory.services import set_bag_status
from notifications.services import notify, notify_many

from .compatibility import COMPATIBLE_DONORS, reservable_bags
from .models import BloodRequest, RequestStatus


class InsufficientStock(Exception):
    def __init__(self, available):
        self.available = available
        super().__init__(f"Only {available} bag(s) available.")


def accept_request(staff_user, blood_request):
    """Reserve `units_requested` AVAILABLE bags, soonest expiry first (FEFO)."""
    with transaction.atomic():
        req = BloodRequest.objects.select_for_update().get(pk=blood_request.pk)
        if req.status != RequestStatus.PENDING:
            raise ValueError("Request is no longer pending.")
        # Lock this hospital's available stock, then pick compatible bags:
        # exact blood-group match first, then other compatible groups (FEFO within
        # each block). Compatibility is enforced here in the service.
        locked = set(
            BloodBag.objects.select_for_update()
            .filter(hospital=req.hospital, status=BagStatus.AVAILABLE)
            .values_list("pk", flat=True)
        )
        candidates = [b for b in reservable_bags(req.hospital, req.blood_group) if b.pk in locked]
        bags = candidates[: req.units_requested]
        if len(bags) < req.units_requested:
            raise InsufficientStock(len(bags))
        substituted = [b.blood_group for b in bags if b.blood_group != req.blood_group]
        for bag in bags:
            # inside the lock; set_bag_status re-saves and audits
            bag.reserved_for = req
            bag.save(update_fields=["reserved_for"])
            set_bag_status(bag, BagStatus.RESERVED, staff_user, {"request_id": req.pk})
        req.status = RequestStatus.ACCEPTED
        req.save(update_fields=["status"])
    log_action(
        staff_user, "REQUEST_ACCEPTED", req,
        {"units": req.units_requested, "blood_group": req.blood_group, "substituted_groups": substituted},
    )
    notify(
        req.patient,
        "Blood request accepted",
        f"Your request for {req.units_requested} unit(s) of {req.blood_group} at {req.hospital.name} "
        "was accepted; the bags are reserved for you."
        + (
            f" Note: {len(substituted)} unit(s) are compatible substitutes "
            f"({', '.join(sorted(set(substituted)))}) rather than an exact {req.blood_group} match."
            if substituted else ""
        ),
    )
    return req


def reject_request(staff_user, blood_request, reason):
    with transaction.atomic():
        req = BloodRequest.objects.select_for_update().get(pk=blood_request.pk)
        if req.status != RequestStatus.PENDING:
            raise ValueError("Request is no longer pending.")
        req.status = RequestStatus.REJECTED
        req.rejection_reason = reason
        req.save(update_fields=["status", "rejection_reason"])
    log_action(staff_user, "REQUEST_REJECTED", req, {"reason": reason})
    notify(
        req.patient,
        "Blood request rejected",
        f"Your request for {req.units_requested} unit(s) of {req.blood_group} at {req.hospital.name} "
        f"was rejected. Reason: {reason}",
    )
    return req


def broadcast_emergency(blood_request):
    """Urgent broadcast to compatible APPROVED, available donors in the hospital's
    city when an EMERGENCY request cannot be met from stock. Returns donors reached."""
    from donors.models import Donor, RegistrationStatus

    donors = Donor.objects.filter(
        registration_status=RegistrationStatus.APPROVED,
        is_available=True,
        blood_group__in=COMPATIBLE_DONORS[blood_request.blood_group],
        city__iexact=blood_request.hospital.city,
    ).select_related("user")
    notify_many(
        [d.user for d in donors],
        f"URGENT: {blood_request.blood_group} blood needed at {blood_request.hospital.name}",
        f"{blood_request.hospital.name} in {blood_request.hospital.city} urgently needs "
        f"{blood_request.blood_group}-compatible blood for an emergency and stock is short. "
        f"Your blood group is compatible. Please contact {blood_request.hospital.phone} "
        "if you can donate.",
    )
    return list(donors)


def fulfil_request(staff_user, blood_request):
    """Issue the reserved bags. select_for_update re-checks RESERVED status so a
    bag can never be issued twice, even under concurrent fulfilment."""
    with transaction.atomic():
        req = BloodRequest.objects.select_for_update().get(pk=blood_request.pk)
        if req.status != RequestStatus.ACCEPTED:
            raise ValueError("Only accepted requests can be fulfilled.")
        # Only the bags reserved for THIS request, so concurrent requests for the
        # same group can never consume each other's reservations.
        bags = list(
            BloodBag.objects.select_for_update()
            .filter(reserved_for=req, status=BagStatus.RESERVED)
            .order_by("expiry_date")
        )
        if len(bags) < req.units_requested:
            raise ValueError("Reserved bags are missing; cannot fulfil.")
        for bag in bags:
            bag.status = BagStatus.ISSUED
            bag.save(update_fields=["status"])
            log_action(staff_user, "BAG_ISSUED", bag, {"from": "RESERVED", "to": "ISSUED", "request_id": req.pk})
        req.status = RequestStatus.FULFILLED
        req.save(update_fields=["status"])
    log_action(staff_user, "REQUEST_FULFILLED", req, {"units": req.units_requested})
    notify(
        req.patient,
        "Blood request fulfilled",
        f"Your request for {req.units_requested} unit(s) of {req.blood_group} at {req.hospital.name} "
        "has been fulfilled.",
    )
    return req
