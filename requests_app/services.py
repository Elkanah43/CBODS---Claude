"""Blood request lifecycle. Reserving and issuing are race-safe:
both run inside transaction.atomic() with select_for_update() and re-check
bag status, so a bag can never be reserved or issued twice.
"""
from django.db import transaction
from django.utils import timezone

from audit.services import log_action
from inventory.models import BagStatus, BloodBag, BloodComponent, ComponentStatus
from inventory.services import set_bag_status, set_component_status
from notifications.services import notify, notify_many

from .compatibility import COMPATIBLE_DONORS
from .models import BloodRequest, RequestStatus


class InsufficientStock(Exception):
    def __init__(self, available):
        self.available = available
        super().__init__(f"Only {available} bag(s) available.")


def accept_request(staff_user, blood_request):
    """Reserve `units_requested` AVAILABLE bags, soonest expiry first (FEFO).
    If request.emergency_override is True, bypasses compatibility and reserves O- bags.
    """
    with transaction.atomic():
        req = BloodRequest.objects.select_for_update().get(pk=blood_request.pk)
        if req.status != RequestStatus.PENDING:
            raise ValueError("Request is no longer pending.")
        
        # Emergency override: bypass compatibility, reserve O- only
        if req.emergency_override:
            if req.blood_group != "O-":
                raise ValueError("Emergency override only valid for O-negative requests.")
            bags = list(
                BloodBag.objects.select_for_update()
                .filter(hospital=req.hospital, blood_group="O-", status=BagStatus.AVAILABLE)
                .order_by("expiry_date")[: req.units_requested]
            )
        else:
            bags = list(
                BloodBag.objects.select_for_update()
                .filter(hospital=req.hospital, blood_group=req.blood_group, status=BagStatus.AVAILABLE)
                .order_by("expiry_date")[: req.units_requested]
            )
        
        if len(bags) < req.units_requested:
            raise InsufficientStock(len(bags))
        for bag in bags:
            # inside the lock; set_bag_status re-saves and audits
            bag.reserved_for = req
            bag.save(update_fields=["reserved_for"])
            set_bag_status(bag, BagStatus.RESERVED, staff_user, {"request_id": req.pk})
        req.status = RequestStatus.ACCEPTED
        req.save(update_fields=["status"])
    log_action(staff_user, "REQUEST_ACCEPTED", req, {"units": req.units_requested, "blood_group": req.blood_group})
    notify(
        req.patient,
        "Blood request accepted",
        f"Your request for {req.units_requested} unit(s) of {req.blood_group} at {req.hospital.name} "
        "was accepted; the bags are reserved for you.",
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


def reserve_emergency(staff_user, blood_request, justification):
    """
    Reserve O-neg bags for an EMERGENCY request with override.
    Only allowed when:
    - request.urgency == EMERGENCY
    - request.blood_group == O-
    - justification provided
    - staff_user has HOSPITAL_STAFF or ADMIN role
    """
    if blood_request.urgency != "EMERGENCY":
        raise ValueError("Emergency override only allowed for EMERGENCY urgency requests.")
    if blood_request.blood_group != "O-":
        raise ValueError("Emergency override only allowed for O-negative blood group.")
    if not justification or not justification.strip():
        raise ValueError("Emergency override requires a clinical justification.")

    from accounts.models import UserRole
    if staff_user.role not in (UserRole.HOSPITAL_STAFF, UserRole.ADMIN):
        raise ValueError("Only hospital staff or admins can authorize emergency overrides.")

    with transaction.atomic():
        req = BloodRequest.objects.select_for_update().get(pk=blood_request.pk)
        if req.status != RequestStatus.PENDING:
            raise ValueError("Request is no longer pending.")
        if req.emergency_override:
            raise ValueError("Emergency override already authorized.")

        bags = list(
            BloodBag.objects.select_for_update()
            .filter(hospital=req.hospital, blood_group="O-", status=BagStatus.AVAILABLE)
            .order_by("expiry_date")[: req.units_requested]
        )
        if len(bags) < req.units_requested:
            raise InsufficientStock(len(bags))

        for bag in bags:
            bag.reserved_for = req
            bag.save(update_fields=["reserved_for"])
            set_bag_status(bag, BagStatus.RESERVED, staff_user, {"request_id": req.pk})

        req.emergency_override = True
        req.emergency_justification = justification
        req.override_authorized_by = staff_user
        req.override_at = timezone.now()
        req.status = RequestStatus.ACCEPTED
        req.save(update_fields=["emergency_override", "emergency_justification", "override_authorized_by", "override_at", "status"])

    log_action(staff_user, "REQUEST_EMERGENCY_OVERRIDE", req, {
        "units": req.units_requested,
        "blood_group": req.blood_group,
        "justification": justification,
    })
    notify(
        req.patient,
        "Emergency blood request accepted",
        f"Your EMERGENCY request for {req.units_requested} unit(s) of O- at {req.hospital.name} "
        "was accepted via emergency override; bags are reserved.",
    )
    # Notify blood bank supervisor separately
    from accounts.models import User
    supervisors = User.objects.filter(role=UserRole.ADMIN)
    notify_many(
        list(supervisors),
        f"EMERGENCY OVERRIDE: O- blood issued at {req.hospital.name}",
        f"Staff {staff_user.get_full_name() or staff_user.username} authorized emergency "
        f"override for {req.units_requested} unit(s) O-. Justification: {justification}",
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


# --- Component-level reservation and fulfilment ---

def accept_request_component(staff_user, blood_request):
    """Reserve AVAILABLE components of the request's component_type, FEFO order."""
    from .compatibility import compatible_components

    with transaction.atomic():
        req = BloodRequest.objects.select_for_update().get(pk=blood_request.pk)
        if req.status != RequestStatus.PENDING:
            raise ValueError("Request is no longer pending.")

        components = list(
            compatible_components(req.hospital, req.blood_group, req.component_type)
            .select_for_update()
            .order_by("expiry_date")[: req.units_requested]
        )
        if len(components) < req.units_requested:
            raise InsufficientStock(len(components))

        for comp in components:
            comp.reserved_for = req
            comp.save(update_fields=["reserved_for"])
            set_component_status(comp, ComponentStatus.RESERVED, staff_user, {"request_id": req.pk})

        req.status = RequestStatus.ACCEPTED
        req.save(update_fields=["status"])

    log_action(staff_user, "REQUEST_ACCEPTED", req, {
        "units": req.units_requested,
        "blood_group": req.blood_group,
        "component_type": req.component_type,
    })
    notify(
        req.patient,
        "Blood request accepted",
        f"Your request for {req.units_requested} unit(s) of {req.component_type} {req.blood_group} "
        f"at {req.hospital.name} was accepted; components are reserved.",
    )
    return req


def fulfil_request_component(staff_user, blood_request):
    """Issue the reserved components. select_for_update re-checks RESERVED status."""
    with transaction.atomic():
        req = BloodRequest.objects.select_for_update().get(pk=blood_request.pk)
        if req.status != RequestStatus.ACCEPTED:
            raise ValueError("Only accepted requests can be fulfilled.")

        components = list(
            BloodComponent.objects.select_for_update()
            .filter(reserved_for=req, status=ComponentStatus.RESERVED)
            .order_by("expiry_date")
        )
        if len(components) < req.units_requested:
            raise ValueError("Reserved components are missing; cannot fulfil.")

        for comp in components:
            set_component_status(comp, ComponentStatus.ISSUED, staff_user, {"request_id": req.pk})

        req.status = RequestStatus.FULFILLED
        req.save(update_fields=["status"])

    log_action(staff_user, "REQUEST_FULFILLED", req, {
        "units": req.units_requested,
        "component_type": req.component_type,
    })
    notify(
        req.patient,
        "Blood request fulfilled",
        f"Your request for {req.units_requested} unit(s) of {req.component_type} {req.blood_group} "
        f"at {req.hospital.name} has been fulfilled.",
    )
    return req


# --- Transfusion recording ---

def record_transfusion(staff_user, request, component, patient, volume_ml, transfused_at=None):
    """Called when staff confirm transfusion at bedside."""
    from .models import TransfusionRecord

    if component.status != ComponentStatus.RESERVED or component.reserved_for != request:
        raise ValueError("Component not reserved for this request.")
    if request.patient != patient:
        raise ValueError("Patient mismatch.")

    transfusion = TransfusionRecord.objects.create(
        request=request,
        component=component,
        patient=patient,
        hospital=request.hospital,
        transfused_at=transfused_at or timezone.now(),
        volume_ml=volume_ml,
        recorded_by=staff_user,
    )
    set_component_status(component, ComponentStatus.ISSUED, staff_user, {"transfusion_id": transfusion.pk})
    request.status = RequestStatus.FULFILLED
    request.save(update_fields=["status"])
    log_action(staff_user, "TRANSFUSION_RECORDED", transfusion, {
        "component_id": component.pk,
        "patient_id": patient.pk,
    })
    return transfusion


def record_reaction(transfusion, reaction_type, staff_user, notes="", onset_minutes=None, new_antibodies=None):
    """Record a transfusion reaction; flag donor for serious reactions."""
    from inventory.models import BloodComponent

    transfusion.reaction = reaction_type
    transfusion.reaction_notes = notes
    transfusion.reaction_onset_minutes = onset_minutes
    if new_antibodies:
        transfusion.new_antibodies = new_antibodies
    transfusion.save(update_fields=["reaction", "reaction_notes", "reaction_onset_minutes", "new_antibodies"])
    log_action(staff_user, "TRANSFUSION_REACTION", transfusion, {"reaction": reaction_type})

    # Flag donor if TRALI/hemolytic (implicate donor)
    if reaction_type in ("TRALI", "HEMOLYTIC_ACUTE", "HEMOLYTIC_DELAYED"):
        donor = transfusion.component.parent_bag.donation.donor
        donor.is_available = False
        donor.save(update_fields=["is_available"])
        notify(
            donor.user,
            "Important: Your donation was associated with a transfusion reaction",
            f"A patient experienced a {transfusion.get_reaction_display()} reaction after receiving "
            f"a component from your donation at {transfusion.hospital.name}. "
            f"Please contact the blood bank for counselling and follow-up testing.",
        )
    return transfusion
