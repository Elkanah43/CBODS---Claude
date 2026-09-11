from django.contrib.auth.models import AbstractUser
from django.db import models

from cbods.fields import GhanaPhoneField
from cbods.validators import validate_email_address, validate_ghana_phone_number


class Role(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    DONOR = "DONOR", "Donor"
    PATIENT = "PATIENT", "Patient"
    HOSPITAL_STAFF = "HOSPITAL_STAFF", "Hospital Staff"
    HOSPITAL = "HOSPITAL", "Hospital"


class User(AbstractUser):
    email = models.EmailField(
        blank=True,
        max_length=254,
        verbose_name="email address",
        validators=[validate_email_address],
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.DONOR)
    phone = GhanaPhoneField(
        max_length=13,
        null=True,
        blank=True,
        unique=True,
        validators=[validate_ghana_phone_number],
        help_text="Enter the 9 digits after +233, e.g. 241234567.",
    )

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
