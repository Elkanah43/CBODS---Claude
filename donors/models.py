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


class DeferralReason(models.TextChoices):
    # Temporary (auto-expiring)
    TRAVEL_MALARIA = "TRAVEL_MALARIA", "Travel to malaria-endemic area"
    TRAVEL_OTHER = "TRAVEL_OTHER", "Travel to other deferral zone"
    MEDICATION = "MEDICATION", "Temporary medication (antibiotics, etc.)"
    TATTOO_PIERCING = "TATTOO_PIERCING", "Recent tattoo/piercing (< 4 months)"
    PREGNANCY = "PREGNANCY", "Pregnancy / recent delivery"
    LOW_HEMOGLOBIN = "LOW_HEMOGLOBIN", "Hemoglobin below threshold"
    HIGH_BP = "HIGH_BP", "Blood pressure outside range"
    ILLNESS = "ILLNESS", "Acute illness / infection"
    VACCINATION = "VACCINATION", "Recent live-attenuated vaccine"
    # Permanent
    HEPATITIS_B = "HEPATITIS_B", "Hepatitis B positive"
    HEPATITIS_C = "HEPATITIS_C", "Hepatitis C positive"
    HIV = "HIV", "HIV positive"
    SYPHILIS = "SYPHILIS", "Syphilis positive (treated)"
    CANCER = "CANCER", "History of malignancy"
    HEART_DISEASE = "HEART_DISEASE", "Significant cardiac disease"
    OTHER_PERMANENT = "OTHER_PERMANENT", "Other permanent medical reason"


PERMANENT_DEFERRAL_REASONS = {
    DeferralReason.HEPATITIS_B,
    DeferralReason.HEPATITIS_C,
    DeferralReason.HIV,
    DeferralReason.SYPHILIS,
    DeferralReason.CANCER,
    DeferralReason.HEART_DISEASE,
    DeferralReason.OTHER_PERMANENT,
}


class Deferral(models.Model):
    """A donor deferral (temporary or permanent) with structured reason and auto-expiry."""
    donor = models.ForeignKey(Donor, on_delete=models.CASCADE, related_name="deferrals")
    reason = models.CharField(max_length=30, choices=DeferralReason.choices)
    is_permanent = models.BooleanField(default=False)
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)  # None = permanent or unknown
    auto_expire = models.BooleanField(default=True)  # for temporary with known duration
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    lifted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lifted_deferrals",
    )
    lifted_at = models.DateTimeField(null=True, blank=True)
    lifted_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["donor", "is_permanent"]),
            models.Index(fields=["end_date"]),
        ]

    def __str__(self):
        return f"{self.donor.full_name}: {self.get_reason_display()} ({'permanent' if self.is_permanent else 'temporary'})"


class DonorHLATyping(models.Model):
    """High-resolution HLA typing for a donor (deceased or living)."""
    donor = models.OneToOneField(Donor, on_delete=models.CASCADE, related_name="hla_typing")
    # Stored as 4-digit alleles, e.g., "A*02:01", "DRB1*15:01"
    alleles = models.JSONField(default=dict)  # {"A": ["02:01", "24:02"], "DRB1": ["15:01", "07:01"]}
    typed_at = models.DateTimeField(auto_now_add=True)
    typed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    method = models.CharField(max_length=50, blank=True)  # "SSO", "SBT", "NGS"

    def get_mismatch_count(self, recipient_typing):
        """Count HLA mismatches at A, B, DRB1 (standard for kidney)."""
        mismatches = 0
        for locus in ("A", "B", "DRB1"):
            donor_alleles = set(self.alleles.get(locus, []))
            recip_alleles = set(recipient_typing.alleles.get(locus, []))
            mismatches += len(recip_alleles - donor_alleles)
        return mismatches

    def __str__(self):
        return f"HLA typing for {self.donor.full_name}"


class PushSubscription(models.Model):
    """Web Push subscription for a donor/user."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.URLField()
    p256dh = models.CharField(max_length=255)  # base64url encoded
    auth = models.CharField(max_length=255)  # base64url encoded
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["user", "endpoint"]]

    def __str__(self):
        return f"Push subscription for {self.user.username}"
