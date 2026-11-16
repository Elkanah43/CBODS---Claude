"""Two-stage donation eligibility.

Stage 1: hard rules derived from the donor record and past donations.
Stage 2: health metrics captured by hospital staff at screening time.
Nothing here is stored except the ScreeningRecord itself — the last-donation
interval is always derived from Donation rows.
"""
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from audit.services import log_action
from notifications.services import notify

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


def can_donate(donor):
    """Donation recording is allowed only for an APPROVED donor whose most recent
    screening is ELIGIBLE and newer than their most recent donation, and who has
    no active deferrals."""
    from inventory.models import Donation

    if donor.registration_status != "APPROVED":
        return False, "Donor registration is not approved."
    record = latest_screening(donor)
    if record is None:
        return False, "No screening on file. Run screening first."
    if record.outcome != OUTCOME_ELIGIBLE:
        return False, f"Latest screening outcome is {record.outcome}: {'; '.join(record.failed_reasons)}"
    last = Donation.objects.filter(donor=donor).order_by("-donated_at").first()
    if last and last.donated_at >= record.created_at:
        return False, "Latest screening predates the last donation. Screen again."
    # Check active deferrals
    active = get_active_deferrals(donor)
    if active.exists():
        return False, f"Deferred: {', '.join(d.get_reason_display() for d in active)}"
    return True, ""


# --- Deferral management ---

PERMANENT_DEFERRAL_REASONS = {
    "HEPATITIS_B",
    "HEPATITIS_C",
    "HIV",
    "SYPHILIS",
    "CANCER",
    "HEART_DISEASE",
    "OTHER_PERMANENT",
}


def get_active_deferrals(donor):
    """Active = permanent OR end_date is future/None AND not lifted."""
    today = timezone.localdate()
    return donor.deferrals.filter(
        models.Q(is_permanent=True) |
        models.Q(end_date__gte=today) | models.Q(end_date__isnull=True),
        lifted_at__isnull=True,
    )


def create_deferral(donor, reason, staff_user, notes="", end_date=None):
    """Create deferral, auto-calculating end_date from reason if not provided."""
    is_permanent = reason in PERMANENT_DEFERRAL_REASONS
    if not is_permanent and end_date is None:
        duration = settings.DEFERRAL_DURATIONS_DAYS.get(reason, 0)
        end_date = timezone.localdate() + timedelta(days=duration) if duration else None
    from .models import Deferral
    deferral = Deferral.objects.create(
        donor=donor, reason=reason, is_permanent=is_permanent,
        end_date=end_date, notes=notes, created_by=staff_user
    )
    log_action(staff_user, "DONOR_DEFERRED", donor, {
        "reason": reason, "is_permanent": is_permanent, "end_date": str(end_date)
    })
    donor.is_available = False
    donor.save(update_fields=["is_available"])
    return deferral


def lift_deferral(deferral, staff_user, reason):
    """Manually lift a deferral before expiry."""
    deferral.lifted_by = staff_user
    deferral.lifted_at = timezone.now()
    deferral.lifted_reason = reason
    deferral.save(update_fields=["lifted_by", "lifted_at", "lifted_reason"])
    # Re-evaluate donor availability
    donor = deferral.donor
    if not get_active_deferrals(donor).exists():
        donor.is_available = True
        donor.save(update_fields=["is_available"])
    log_action(staff_user, "DONOR_DEFERRAL_LIFTED", donor, {"deferral_id": deferral.pk})
