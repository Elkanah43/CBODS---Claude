from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    DONOR = "DONOR", "Donor"
    PATIENT = "PATIENT", "Patient"
    HOSPITAL_STAFF = "HOSPITAL_STAFF", "Hospital Staff"


class User(AbstractUser):
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.DONOR)
    phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
