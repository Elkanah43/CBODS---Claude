"""Single entry point for writing audit rows."""
from .models import AuditLog


def log_action(actor, action, entity, details=None):
    AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        entity_type=entity.__class__.__name__,
        entity_id=str(entity.pk),
        details=details or {},
    )
