from django.conf import settings
from django.db import models

from cbods.constants import BloodGroup
from hospitals.models import Hospital


class Urgency(models.TextChoices):
    ROUTINE = "ROUTINE", "Routine"
    URGENT = "URGENT", "Urgent"
    EMERGENCY = "EMERGENCY", "Emergency"


class RequestStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    ACCEPTED = "ACCEPTED", "Accepted"
    REJECTED = "REJECTED", "Rejected"
    FULFILLED = "FULFILLED", "Fulfilled"


class BloodRequest(models.Model):
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blood_requests")
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name="blood_requests")
    blood_group = models.CharField(max_length=3, choices=BloodGroup.choices)
    units_requested = models.PositiveIntegerField(default=1)
    urgency = models.CharField(max_length=10, choices=Urgency.choices, default=Urgency.ROUTINE)
    status = models.CharField(max_length=10, choices=RequestStatus.choices, default=RequestStatus.PENDING)
    rejection_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Emergency override for O-negative in life-threatening situations
    emergency_override = models.BooleanField(default=False)
    emergency_justification = models.TextField(blank=True)
    override_authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authorized_overrides",
    )
    override_at = models.DateTimeField(null=True, blank=True)
    # Component type for component-level requests (default RBC for backward compat)
    component_type = models.CharField(
        max_length=20,
        choices=[("RBC", "Red Blood Cells"), ("PLASMA", "Fresh Frozen Plasma"), ("PLATELETS", "Platelets"), ("CRYO", "Cryoprecipitate")],
        default="RBC",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.units_requested}x {self.blood_group} at {self.hospital.name} ({self.status})"


class ReactionType(models.TextChoices):
    NONE = "NONE", "No reaction"
    FEBRILE = "FEBRILE", "Febrile non-hemolytic (FNHTR)"
    ALLERGIC = "ALLERGIC", "Allergic / urticarial"
    ANAPHYLACTIC = "ANAPHYLACTIC", "Anaphylactic"
    HEMOLYTIC_ACUTE = "HEMOLYTIC_ACUTE", "Acute hemolytic (AHTR)"
    HEMOLYTIC_DELAYED = "HEMOLYTIC_DELAYED", "Delayed hemolytic (DHTR)"
    TRALI = "TRALI", "TRALI"
    TACO = "TACO", "TACO"
    BACTERIAL = "BACTERIAL", "Bacterial contamination"
    OTHER = "OTHER", "Other"


class TransfusionRecord(models.Model):
    request = models.ForeignKey(BloodRequest, on_delete=models.CASCADE, related_name="transfusions")
    component = models.ForeignKey("inventory.BloodComponent", on_delete=models.PROTECT, related_name="transfusions")
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transfusion_records")
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE)
    transfused_at = models.DateTimeField()
    volume_ml = models.PositiveIntegerField()
    reaction = models.CharField(max_length=20, choices=ReactionType.choices, default=ReactionType.NONE)
    reaction_notes = models.TextField(blank=True)
    reaction_onset_minutes = models.PositiveIntegerField(null=True, blank=True)
    # Alloantibodies detected post-transfusion
    new_antibodies = models.JSONField(default=list, blank=True)  # [{"specificity": "anti-K", "date": "2026-01-15"}]
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ["-transfused_at"]
        indexes = [
            models.Index(fields=["patient", "transfused_at"]),
            models.Index(fields=["component"]),
        ]

    def __str__(self):
        return f"{self.component} to {self.patient} at {self.transfused_at:%Y-%m-%d}"
