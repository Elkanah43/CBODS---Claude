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
    UNTESTED = "UNTESTED", "Untested"
    AVAILABLE = "AVAILABLE", "Available"
    RESERVED = "RESERVED", "Reserved"
    ISSUED = "ISSUED", "Issued"
    EXPIRED = "EXPIRED", "Expired"
    DISCARDED = "DISCARDED", "Discarded"


class TTIMarker(models.TextChoices):
    """Transfusion-transmissible infections screened for in the laboratory.

    The NBSG/BSIS analogue is the TTI panel every donation undergoes before its
    units may be labelled and issued; a reactive marker excludes the donation.
    HIV screening additionally drives donor deferral and linkage to care.
    """

    HIV = "HIV", "HIV"
    HEPATITIS_B = "HBV", "Hepatitis B"
    HEPATITIS_C = "HCV", "Hepatitis C"
    SYPHILIS = "SYPHILIS", "Syphilis"


class BloodBag(models.Model):
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name="blood_bags")
    blood_group = models.CharField(max_length=3, choices=BloodGroup.choices)
    volume_ml = models.PositiveIntegerField(default=450)
    collected_date = models.DateField()
    expiry_date = models.DateField()
    status = models.CharField(max_length=20, choices=BagStatus.choices, default=BagStatus.UNTESTED)
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


class ComponentType(models.TextChoices):
    WHOLE_BLOOD = "WHOLE_BLOOD", "Whole Blood"
    RBC = "RBC", "Red Blood Cells"
    PLASMA = "PLASMA", "Fresh Frozen Plasma"
    PLATELETS = "PLATELETS", "Platelets"
    CRYOPRECIPITATE = "CRYO", "Cryoprecipitate"


class ComponentStatus(models.TextChoices):
    UNTESTED = "UNTESTED", "Untested"
    AVAILABLE = "AVAILABLE", "Available"
    RESERVED = "RESERVED", "Reserved"
    ISSUED = "ISSUED", "Issued"
    EXPIRED = "EXPIRED", "Expired"
    DISCARDED = "DISCARDED", "Discarded"


COMPONENT_SHELF_LIFE_DAYS = {
    "WHOLE_BLOOD": 35,
    "RBC": 35,
    "PLASMA": 365,
    "PLATELETS": 7,
    "CRYO": 365,
}


class BloodComponent(models.Model):
    """A split component derived from a parent BloodBag (whole blood donation)."""
    parent_bag = models.ForeignKey(BloodBag, on_delete=models.CASCADE, related_name="components")
    component_type = models.CharField(max_length=20, choices=ComponentType.choices)
    volume_ml = models.PositiveIntegerField()
    collected_date = models.DateField()
    expiry_date = models.DateField()
    status = models.CharField(max_length=20, choices=ComponentStatus.choices, default=ComponentStatus.UNTESTED)
    # For platelets: pool identifier
    pool_id = models.CharField(max_length=50, blank=True)
    # Storage location (fridge/freezer/agitator)
    storage_location = models.CharField(max_length=100, blank=True)
    # Set when a component is RESERVED so fulfilment issues only the components reserved for
    # that request; kept after issue for traceability.
    reserved_for = models.ForeignKey(
        "requests_app.BloodRequest", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="components",
    )

    class Meta:
        ordering = ["expiry_date"]
        indexes = [
            models.Index(fields=["parent_bag", "component_type"]),
            models.Index(fields=["status", "expiry_date"]),
        ]

    def save(self, *args, **kwargs):
        if not self.expiry_date and self.collected_date:
            shelf_life = COMPONENT_SHELF_LIFE_DAYS.get(self.component_type, 35)
            self.expiry_date = self.collected_date + timedelta(days=shelf_life)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.component_type} #{self.pk} from Bag #{self.parent_bag_id} ({self.status})"

    @property
    def hospital(self):
        return self.parent_bag.hospital

    @property
    def blood_group(self):
        return self.parent_bag.blood_group


class TTIResult(models.TextChoices):
    NEGATIVE = "NEGATIVE", "Non-reactive (negative)"
    POSITIVE = "POSITIVE", "Reactive (positive)"


class TTITestRecord(models.Model):
    """Laboratory TTI screening of one donation.

    Created UNTESTED alongside the bag when the donation is recorded; the lab
    enters one result per marker and the service layer moves the donation's
    bag to AVAILABLE only when every marker is non-reactive, or DISCARDED with
    the reason recorded when any is reactive. The record is kept after either
    outcome so the deferral reason and audit trail survive.
    """

    donation = models.OneToOneField(Donation, on_delete=models.CASCADE, related_name="tti_record")
    hiv = models.CharField(max_length=8, choices=TTIResult.choices, null=True, blank=True)
    hepatitis_b = models.CharField(max_length=8, choices=TTIResult.choices, null=True, blank=True)
    hepatitis_c = models.CharField(max_length=8, choices=TTIResult.choices, null=True, blank=True)
    syphilis = models.CharField(max_length=8, choices=TTIResult.choices, null=True, blank=True)
    tested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    tested_at = models.DateTimeField(auto_now_add=True)
    discarded_reason = models.TextField(blank=True, help_text="Reactive marker(s), when the unit was discarded.")

    MARKER_FIELDS = ("hiv", "hepatitis_b", "hepatitis_c", "syphilis")
    MARKER_LABELS = {
        "hiv": "HIV",
        "hepatitis_b": "Hepatitis B",
        "hepatitis_c": "Hepatitis C",
        "syphilis": "Syphilis",
    }

    class Meta:
        verbose_name = "TTI test record"

    def __str__(self):
        return f"TTI screening of donation #{self.donation_id}"

    @property
    def is_complete(self):
        return all(getattr(self, f) for f in self.MARKER_FIELDS)

    @property
    def reactive_markers(self):
        """Markers currently entered as reactive; empty when none are."""
        return [
            self.MARKER_LABELS[f] for f in self.MARKER_FIELDS if getattr(self, f) == TTIResult.POSITIVE
        ]

    @property
    def results_table(self):
        """[(marker label, TTIResult or None)] in display order, for templates."""
        return [(self.MARKER_LABELS[f], getattr(self, f)) for f in self.MARKER_FIELDS]
