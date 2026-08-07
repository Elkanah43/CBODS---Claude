"""Single entry point for writing audit rows, plus the system-wide counts."""
from .models import AuditLog


def system_totals():
    """The four headline figures, counted rather than stored.

    Shared by the admin landing page and the charted system dashboard so the
    two can never disagree about how many donors or available bags exist.
    """
    from donors.models import Donor
    from inventory.models import BloodBag, Donation
    from requests_app.models import BloodRequest

    return {
        "donors": Donor.objects.count(),
        "available_bags": BloodBag.objects.filter(status="AVAILABLE").count(),
        "pending_requests": BloodRequest.objects.filter(status="PENDING").count(),
        "donations": Donation.objects.count(),
    }


def log_action(actor, action, entity, details=None):
    AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        entity_type=entity.__class__.__name__,
        entity_id=str(entity.pk),
        details=details or {},
    )
