from django.db import models

from donors.models import Donor
from hospitals.models import Hospital


class OrganType(models.TextChoices):
    KIDNEY = "KIDNEY", "Kidney"
    LIVER = "LIVER", "Liver"
    HEART = "HEART", "Heart"
    LUNG = "LUNG", "Lung"
    CORNEA = "CORNEA", "Cornea"
    PANCREAS = "PANCREAS", "Pancreas"
    SKIN = "SKIN", "Skin"


class OrganRequestStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    REQUESTED = "REQUESTED", "Requested"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class OrganDonationRequest(models.Model):
    donor = models.ForeignKey(Donor, on_delete=models.CASCADE, related_name="organ_requests")
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name="organ_requests")
    organ_type = models.CharField(max_length=10, choices=OrganType.choices)
    status = models.CharField(max_length=10, choices=OrganRequestStatus.choices, default=OrganRequestStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_organ_type_display()} from {self.donor.full_name} to {self.hospital.name} ({self.status})"
