from django.conf import settings
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


class RecipientHLATyping(models.Model):
    """Recipient HLA typing attached to organ request."""
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recipient_hla")
    alleles = models.JSONField(default=dict)
    typed_at = models.DateTimeField(auto_now_add=True)
    typed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    unacceptable_antigens = models.JSONField(default=list)  # ["B*27:05", "DRB1*04:01"]
    pra_percent = models.PositiveIntegerField(null=True, blank=True)  # Panel Reactive Antibody %

    class Meta:
        verbose_name = "Recipient HLA typing"
        verbose_name_plural = "Recipient HLA typings"

    def __str__(self):
        return f"HLA typing for {self.patient.get_full_name() or self.patient.username}"


class OrganDonationRequest(models.Model):
    donor = models.ForeignKey(Donor, on_delete=models.CASCADE, related_name="organ_requests")
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name="organ_requests")
    organ_type = models.CharField(max_length=10, choices=OrganType.choices)
    status = models.CharField(max_length=10, choices=OrganRequestStatus.choices, default=OrganRequestStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    # HLA matching fields
    recipient_hla = models.OneToOneField(
        "organs.RecipientHLATyping", on_delete=models.SET_NULL, null=True, blank=True, related_name="organ_request"
    )
    hla_mismatch_count = models.PositiveIntegerField(null=True, blank=True)
    crossmatch_result = models.CharField(max_length=20, blank=True)  # NEGATIVE/POSITIVE/PENDING

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_organ_type_display()} from {self.donor.full_name} to {self.hospital.name} ({self.status})"
