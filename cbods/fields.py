"""Custom model fields shared across apps.

``GhanaPhoneField`` stores Ghanaian mobile numbers consistently as
``+233XXXXXXXXX`` no matter which form (registration, profile edit, Django
admin) wrote them. The strict rules live in :mod:`cbods.validators`; this
field only performs the mechanical normalisation.
"""
from django.core.exceptions import ValidationError
from django.db import models

from .validators import normalize_ghana_phone_number


class GhanaPhoneField(models.CharField):
    """A phone number stored as ``+233XXXXXXXXX`` and validated as a
    Ghanaian mobile number.

    ``to_python`` normalises whatever is bound into the field — ModelForms,
    the admin, ``full_clean()`` — and is deliberately lenient: values it
    cannot parse pass through untouched so the model-level validator can
    report a clear, specific error, and so reading legacy rows back from the
    database never crashes. ``get_prep_value`` maps blank input to NULL on
    nullable fields, so the unique constraint treats "no phone" as absent
    rather than as a value every account-less user would collide on.
    """

    def to_python(self, value):
        value = super().to_python(value)
        if value in (None, ""):
            return value
        try:
            return normalize_ghana_phone_number(value)
        except ValidationError:
            return value

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value == "" and self.null:
            return None
        return value