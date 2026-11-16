"""Organ matching and HLA compatibility services."""
from django.utils import timezone

from audit.services import log_action
from notifications.services import notify


def calculate_hla_match(donor, organ_request):
    """Compute mismatch count, check unacceptable antigens, update request."""
    if not hasattr(donor, "hla_typing") or not organ_request.recipient_hla:
        return None

    mismatch = donor.hla_typing.get_mismatch_count(organ_request.recipient_hla)
    unacceptable = set(organ_request.recipient_hla.unacceptable_antigens)
    donor_alleles = set()
    for locus in ("A", "B", "DRB1", "DQB1"):
        donor_alleles.update(donor.hla_typing.alleles.get(locus, []))
    has_unacceptable = bool(unacceptable & donor_alleles)

    organ_request.hla_mismatch_count = mismatch
    organ_request.crossmatch_result = "POSITIVE" if has_unacceptable else "NEGATIVE"
    organ_request.save(update_fields=["hla_mismatch_count", "crossmatch_result"])

    log_action(None, "ORGAN_HLA_MATCH_CALCULATED", organ_request, {
        "mismatch": mismatch,
        "unacceptable_match": has_unacceptable,
        "donor_id": donor.pk,
    })

    return {"mismatch": mismatch, "unacceptable_match": has_unacceptable}


def approve_organ_request(staff_user, organ_request):
    """Approve an organ donation request."""
    if organ_request.status != "PENDING":
        raise ValueError("Only pending requests can be approved.")

    organ_request.status = "APPROVED"
    organ_request.decided_at = timezone.now()
    organ_request.save(update_fields=["status", "decided_at"])

    log_action(staff_user, "ORGAN_REQUEST_APPROVED", organ_request, {"organ_type": organ_request.organ_type})
    notify(
        organ_request.donor.user,
        "Organ donation request approved",
        f"Your {organ_request.get_organ_type_display()} donation request has been approved. "
        f"The transplant team at {organ_request.hospital.name} will contact you shortly.",
    )
    return organ_request


def reject_organ_request(staff_user, organ_request, reason):
    """Reject an organ donation request."""
    if organ_request.status != "PENDING":
        raise ValueError("Only pending requests can be rejected.")

    organ_request.status = "REJECTED"
    organ_request.decided_at = timezone.now()
    organ_request.save(update_fields=["status", "decided_at"])

    log_action(staff_user, "ORGAN_REQUEST_REJECTED", organ_request, {"reason": reason})
    notify(
        organ_request.donor.user,
        "Organ donation request declined",
        f"Your {organ_request.get_organ_type_display()} donation request was declined. "
        f"Reason: {reason}",
    )
    return organ_request