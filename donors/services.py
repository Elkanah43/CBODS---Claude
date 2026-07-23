"""Two-stage donation eligibility.

Stage 1: hard rules derived from the donor record and past donations.
Stage 2: health metrics captured by hospital staff at screening time.
Nothing here is stored except the ScreeningRecord itself — the last-donation
interval is always derived from Donation rows.
"""
from django.conf import settings
from django.utils import timezone

OUTCOME_ELIGIBLE = "ELIGIBLE"
OUTCOME_TEMP_DEFERRED = "TEMP_DEFERRED"
OUTCOME_INELIGIBLE = "INELIGIBLE"


def days_since_last_donation(donor):
    """Days since the donor's most recent completed donation, or None if never donated."""
    from inventory.models import Donation

    last = Donation.objects.filter(donor=donor).order_by("-donated_at").first()
    if last is None:
        return None
    return (timezone.now() - last.donated_at).days


def run_stage1(donor):
    """Returns (passed, reasons, permanent) — permanent=True means INELIGIBLE, else TEMP_DEFERRED."""
    reasons = []
    permanent = False

    age = donor.age
    if age < settings.DONOR_MIN_AGE:
        reasons.append(f"Age {age} is below the minimum of {settings.DONOR_MIN_AGE}.")
    if age > settings.DONOR_MAX_AGE:
        reasons.append(f"Age {age} is above the maximum of {settings.DONOR_MAX_AGE}.")
        permanent = True

    if donor.weight_kg < settings.DONOR_MIN_WEIGHT_KG:
        reasons.append(f"Weight {donor.weight_kg} kg is below the minimum of {settings.DONOR_MIN_WEIGHT_KG} kg.")

    days = days_since_last_donation(donor)
    if days is not None and days < settings.DONATION_INTERVAL_DAYS:
        reasons.append(
            f"Only {days} days since last donation; {settings.DONATION_INTERVAL_DAYS} days required."
        )

    return (not reasons, reasons, permanent)


def run_stage2(hemoglobin_g_dl, systolic_bp, diastolic_bp):
    """Returns (passed, reasons) for the health metrics entered by staff."""
    reasons = []
    if hemoglobin_g_dl is None or float(hemoglobin_g_dl) < settings.SCREENING_HEMOGLOBIN_MIN:
        reasons.append(
            f"Hemoglobin {hemoglobin_g_dl} g/dL is below the minimum of {settings.SCREENING_HEMOGLOBIN_MIN} g/dL."
        )
    if systolic_bp is None or not (settings.SCREENING_SYSTOLIC_MIN <= systolic_bp <= settings.SCREENING_SYSTOLIC_MAX):
        reasons.append(
            f"Systolic BP {systolic_bp} is outside the allowed range "
            f"{settings.SCREENING_SYSTOLIC_MIN}-{settings.SCREENING_SYSTOLIC_MAX}."
        )
    if diastolic_bp is None or not (settings.SCREENING_DIASTOLIC_MIN <= diastolic_bp <= settings.SCREENING_DIASTOLIC_MAX):
        reasons.append(
            f"Diastolic BP {diastolic_bp} is outside the allowed range "
            f"{settings.SCREENING_DIASTOLIC_MIN}-{settings.SCREENING_DIASTOLIC_MAX}."
        )
    return (not reasons, reasons)


def screen_donor(donor, hemoglobin_g_dl=None, systolic_bp=None, diastolic_bp=None):
    """Run both stages and persist a ScreeningRecord. Returns the record."""
    from .models import ScreeningRecord

    stage1_passed, reasons, permanent = run_stage1(donor)
    if not stage1_passed:
        outcome = OUTCOME_INELIGIBLE if permanent else OUTCOME_TEMP_DEFERRED
        return ScreeningRecord.objects.create(
            donor=donor, stage1_passed=False, outcome=outcome, failed_reasons=reasons,
        )

    stage2_passed, stage2_reasons = run_stage2(hemoglobin_g_dl, systolic_bp, diastolic_bp)
    outcome = OUTCOME_ELIGIBLE if stage2_passed else OUTCOME_TEMP_DEFERRED
    return ScreeningRecord.objects.create(
        donor=donor,
        stage1_passed=True,
        hemoglobin_g_dl=hemoglobin_g_dl,
        systolic_bp=systolic_bp,
        diastolic_bp=diastolic_bp,
        outcome=outcome,
        failed_reasons=stage2_reasons,
    )


def latest_screening(donor):
    return donor.screenings.order_by("-created_at").first()


def screening_expires_on(record):
    """The moment a screening stops authorising a donation."""
    from datetime import timedelta

    return record.created_at + timedelta(days=settings.SCREENING_VALID_DAYS)


def can_donate(donor):
    """Donation recording is allowed only for an APPROVED donor whose most recent
    screening is ELIGIBLE, newer than their most recent donation, and still
    within the validity window (health metrics go stale)."""
    from inventory.models import Donation

    if donor.registration_status != "APPROVED":
        return False, "Donor registration is not approved."
    record = latest_screening(donor)
    if record is None:
        return False, "No screening on file. Run screening first."
    if record.outcome != OUTCOME_ELIGIBLE:
        return False, f"Latest screening outcome is {record.outcome}: {'; '.join(record.failed_reasons)}"
    if timezone.now() > screening_expires_on(record):
        return False, (
            f"Screening is older than {settings.SCREENING_VALID_DAYS} days "
            f"(taken {record.created_at:%Y-%m-%d}). Screen again."
        )
    last = Donation.objects.filter(donor=donor).order_by("-donated_at").first()
    if last and last.donated_at >= record.created_at:
        return False, "Latest screening predates the last donation. Screen again."
    return True, ""
