"""Shared presentation helpers."""
from django import template

register = template.Library()

# Every status vocabulary in the project — request status, donor registration,
# screening outcome, bag state, urgency — shares one colour language: green is
# settled and positive, amber is waiting on a person, cyan is in progress, red
# is refused or demands attention, grey is closed out. Holding the map here
# means adding a status is a one-line change instead of an edit to six
# templates that were previously easy to leave inconsistent.
STATUS_CLASSES = {
    # Settled, positive
    "APPROVED": "bg-success",
    "FULFILLED": "bg-success",
    "ELIGIBLE": "bg-success",
    "AVAILABLE": "bg-success",
    # Waiting on a person
    "PENDING": "bg-warning text-dark",
    "TEMP_DEFERRED": "bg-warning text-dark",
    "URGENT": "bg-warning text-dark",
    # In progress
    "REQUESTED": "bg-info text-dark",
    "ACCEPTED": "bg-info text-dark",
    "RESERVED": "bg-info text-dark",
    # Refused, or demanding attention
    "REJECTED": "bg-danger",
    "INELIGIBLE": "bg-danger",
    "EMERGENCY": "bg-danger",
    # Closed out
    "ISSUED": "bg-secondary",
    "ROUTINE": "bg-secondary",
    "EXPIRED": "bg-dark",
    "DISCARDED": "bg-light text-dark",
}

DEFAULT_STATUS_CLASS = "bg-secondary"


@register.filter
def status_class(status):
    """Bootstrap badge classes for a status, urgency or outcome code.

    Unrecognised codes fall back to neutral grey. The per-template if/else
    ladders this replaces ended in a bare `{% else %}Rejected{% endif %}`, so
    any status they had not been taught about was rendered to the user as a
    rejection — which on a blood request is the opposite of harmless.
    """
    return STATUS_CLASSES.get(str(status).upper(), DEFAULT_STATUS_CLASS)
