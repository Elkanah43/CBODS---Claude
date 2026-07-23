"""Validation for the uploaded government-ID document.

Uploads are the one place untrusted files enter the system, so both the file
type and its size are constrained. Applied on the model field so the rule holds
for the donor form and the Django admin alike.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

validate_id_extension = FileExtensionValidator(
    allowed_extensions=["jpg", "jpeg", "png", "pdf"],
    message="Upload a JPG, PNG or PDF copy of your ID.",
)


def validate_id_size(value):
    limit = settings.ID_DOCUMENT_MAX_BYTES
    if value.size > limit:
        raise ValidationError(f"ID document must be smaller than {limit // (1024 * 1024)} MB.")
