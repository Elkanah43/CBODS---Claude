from django.conf import settings
from django.db import models
from django.utils import timezone

from cbods.constants import BloodGroup

from .validators import validate_id_extension, validate_id_size


class Sex(models.TextChoices):
    MALE = "M", "Male"
    FEMALE = "F", "Female"


class RegistrationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class Donor(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="donor_profile")
    full_name = models.CharField(max_length=200)
    date_of_birth = models.DateField()
    sex = models.CharField(max_length=1, choices=Sex.choices)
    blood_group = models.CharField(max_length=3, choices=BloodGroup.choices)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=1)
    city = models.CharField(max_length=100)
    contact_phone = models.CharField(max_length=20)
    medical_history = models.TextField(blank=True)
    id_document = models.FileField(
        upload_to="donor_ids/",
        validators=[validate_id_extension, validate_id_size],
        help_text="JPG, PNG or PDF. Visible only to administrators reviewing your registration.",
    )
    registration_status = models.CharField(
        max_length=10, choices=RegistrationStatus.choices, default=RegistrationStatus.PENDING
    )
    is_available = models.BooleanField(default=True)
    rejection_reason = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.full_name} ({self.blood_group})"

    @property
    def id_document_url(self):
        """Admin-only view that streams the ID scan — never a raw media URL."""
        from django.urls import reverse

        return reverse("donor_id_document", args=[self.pk])

    @property
    def age(self):
        today = timezone.localdate()
        dob = self.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


class ScreeningOutcome(models.TextChoices):
    ELIGIBLE = "ELIGIBLE", "Eligible"
    TEMP_DEFERRED = "TEMP_DEFERRED", "Temporarily deferred"
    INELIGIBLE = "INELIGIBLE", "Ineligible"


class ScreeningRecord(models.Model):
    donor = models.ForeignKey(Donor, on_delete=models.CASCADE, related_name="screenings")
    stage1_passed = models.BooleanField()
    hemoglobin_g_dl = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    systolic_bp = models.IntegerField(null=True, blank=True)
    diastolic_bp = models.IntegerField(null=True, blank=True)
    outcome = models.CharField(max_length=15, choices=ScreeningOutcome.choices)
    failed_reasons = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Screening of {self.donor.full_name}: {self.outcome}"
