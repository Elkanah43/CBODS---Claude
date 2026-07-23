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

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.units_requested}x {self.blood_group} at {self.hospital.name} ({self.status})"
