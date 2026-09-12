from django.conf import settings
from django.db import models
from django.utils import timezone

from cbods.constants import BloodGroup
from cbods.fields import GhanaPhoneField
from cbods.validators import validate_ghana_phone_number
from hospitals.models import Hospital

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
    contact_phone = GhanaPhoneField(
        max_length=13,
        unique=True,
        validators=[validate_ghana_phone_number],
        help_text="Enter the 9 digits after +233, e.g. 241234567.",
    )
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


class AppointmentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    CONFIRMED = "CONFIRMED", "Confirmed"
    DECLINED = "DECLINED", "Declined"
    COMPLETED = "COMPLETED", "Completed"


class Appointment(models.Model):
    """A donor's request to walk in and donate at a specific hospital on a date.

    Booked from the donor-facing "Where to donate" directory, so hospitals
    short on blood — the ones the page flags as urgent — are where donors
    commit to coming. Hospital staff confirm or decline; the record gives both
    sides a shared status instead of an untracked phone call.
    """
    donor = models.ForeignKey(Donor, on_delete=models.CASCADE, related_name="appointments")
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name="appointments")
    requested_for = models.DateField(help_text="The day the donor proposes to come in.")
    status = models.CharField(
        max_length=10, choices=AppointmentStatus.choices, default=AppointmentStatus.PENDING
    )
    donor_note = models.TextField(blank=True, help_text="Optional message from the donor to the hospital.")
    staff_note = models.TextField(null=True, blank=True, help_text="Optional message sent back to the donor.")
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.donor.full_name} at {self.hospital.name} on {self.requested_for}: {self.status}"


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
