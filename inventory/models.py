from datetime import timedelta

from django.conf import settings
from django.db import models

from cbods.constants import BloodGroup
from donors.models import Donor
from hospitals.models import Hospital


class Donation(models.Model):
    donor = models.ForeignKey(Donor, on_delete=models.CASCADE, related_name="donations")
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name="donations")
    donated_at = models.DateTimeField()
    volume_ml = models.PositiveIntegerField(default=450)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ["-donated_at"]

    def __str__(self):
        return f"{self.donor.full_name} at {self.hospital.name} on {self.donated_at:%Y-%m-%d}"


class BagStatus(models.TextChoices):
    AVAILABLE = "AVAILABLE", "Available"
    RESERVED = "RESERVED", "Reserved"
    ISSUED = "ISSUED", "Issued"
    EXPIRED = "EXPIRED", "Expired"
    DISCARDED = "DISCARDED", "Discarded"


class BloodBag(models.Model):
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name="blood_bags")
    blood_group = models.CharField(max_length=3, choices=BloodGroup.choices)
    volume_ml = models.PositiveIntegerField(default=450)
    collected_date = models.DateField()
    expiry_date = models.DateField()
    status = models.CharField(max_length=10, choices=BagStatus.choices, default=BagStatus.AVAILABLE)
    donation = models.ForeignKey(Donation, on_delete=models.SET_NULL, null=True, blank=True, related_name="bags")
    # Set when a bag is RESERVED so fulfilment issues only the bags reserved for
    # that request; kept after issue for traceability.
    reserved_for = models.ForeignKey(
        "requests_app.BloodRequest", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="bags",
    )

    class Meta:
        ordering = ["expiry_date"]

    def save(self, *args, **kwargs):
        if not self.expiry_date and self.collected_date:
            self.expiry_date = self.collected_date + timedelta(days=settings.BLOOD_BAG_SHELF_LIFE_DAYS)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Bag #{self.pk} {self.blood_group} @ {self.hospital.name} ({self.status})"
