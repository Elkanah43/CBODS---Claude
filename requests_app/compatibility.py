"""ABO/Rh compatibility encoded as a data dict (decision tree: ABO first, then Rh).

COMPATIBLE_DONORS[recipient_group] -> tuple of acceptable donor groups.
"""
from django.conf import settings
from django.utils import timezone

COMPATIBLE_DONORS = {
    "O-": ("O-",),
    "O+": ("O-", "O+"),
    "A-": ("O-", "A-"),
    "A+": ("O-", "O+", "A-", "A+"),
    "B-": ("O-", "B-"),
    "B+": ("O-", "O+", "B-", "B+"),
    "AB-": ("O-", "A-", "B-", "AB-"),
    "AB+": ("O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"),
}

URGENCY_RANK = {"EMERGENCY": 0, "URGENT": 1, "ROUTINE": 2}


def is_compatible(recipient_group, donor_group):
    return donor_group in COMPATIBLE_DONORS[recipient_group]


def compatible_bags(hospital, recipient_group):
    """AVAILABLE bags at this hospital a recipient of `recipient_group` can take, FEFO order."""
    from inventory.models import BagStatus, BloodBag

    return BloodBag.objects.filter(
        hospital=hospital,
        status=BagStatus.AVAILABLE,
        blood_group__in=COMPATIBLE_DONORS[recipient_group],
    ).order_by("expiry_date")


def days_until_eligible(donor):
    from donors.services import days_since_last_donation

    days = days_since_last_donation(donor)
    if days is None or days >= settings.DONATION_INTERVAL_DAYS:
        return 0
    return settings.DONATION_INTERVAL_DAYS - days


def suggest_donors(hospital, recipient_group, urgency="ROUTINE", exclude_donor=None):
    """Compatible, APPROVED, available donors ranked by same city as the hospital,
    then soonest-eligible.

    Urgency changes which term dominates. The request's urgency is the same value
    for every donor in one call, so using it as a plain sort key could never
    reorder anything; instead it decides the ordering strategy:

    * EMERGENCY — donors who can donate today come first (blood is needed now),
      then same-city, then soonest-eligible.
    * URGENT / ROUTINE — same-city first (travel is feasible), then
      soonest-eligible.
    """
    from donors.models import Donor, RegistrationStatus

    donors = Donor.objects.filter(
        registration_status=RegistrationStatus.APPROVED,
        is_available=True,
        blood_group__in=COMPATIBLE_DONORS[recipient_group],
    )
    if exclude_donor:
        donors = donors.exclude(pk=exclude_donor.pk)

    def rank(donor):
        local = 0 if donor.city.lower() == hospital.city.lower() else 1
        wait = days_until_eligible(donor)
        if URGENCY_RANK.get(urgency, 2) == URGENCY_RANK["EMERGENCY"]:
            return (0 if wait == 0 else 1, local, wait)
        return (local, wait)

    return sorted(donors, key=rank)


def check_donor_for_recipient(hospital, recipient_group, donor, urgency="ROUTINE"):
    """Service-level enforcement: returns (True, None) when compatible, otherwise
    (False, alternatives) where alternatives holds ranked donors and compatible bags."""
    if is_compatible(recipient_group, donor.blood_group):
        return True, None
    return False, {
        "donors": suggest_donors(hospital, recipient_group, urgency, exclude_donor=donor),
        "bags": compatible_bags(hospital, recipient_group),
    }
