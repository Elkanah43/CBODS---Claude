from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from . import password_rules
from .forms import RegisterForm
from .models import User


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Welcome to CBODS! Your account has been created.")
            return redirect("dashboard")
    else:
        form = RegisterForm()
    return render(
        request,
        "accounts/register.html",
        {"form": form, "password_rules": password_rules.get_rules()},
    )


@require_POST
def password_rules_check(request):
    """Live per-rule verdicts for the register page checklist.

    Username and email come along because UserAttributeSimilarityValidator
    compares the password against them, and on an unsubmitted form they exist
    only in the browser. The probe user is never saved.
    """
    probe = User(
        username=request.POST.get("username", ""),
        email=request.POST.get("email", ""),
    )
    results = password_rules.check(request.POST.get("password", ""), probe)
    return JsonResponse({"results": results})


def _admin_context():
    """Headline figures and the newest audit rows.

    The landing page answers 'what is the state of the system'; the charted
    system dashboard answers 'how is it distributed'. Both read the same
    counting function, so they cannot disagree.
    """
    from audit.models import AuditLog
    from audit.services import system_totals
    from donors.models import Donor, RegistrationStatus
    from hospitals.models import Hospital, HospitalApprovalStatus

    return {
        "totals": system_totals(),
        "pending_donors": Donor.objects.filter(
            registration_status=RegistrationStatus.PENDING
        ).count(),
        "pending_hospitals": Hospital.objects.filter(
            approval_status=HospitalApprovalStatus.PENDING
        ).count(),
        "recent_audit": AuditLog.objects.select_related("actor")[:8],
    }


def _staff_context(user):
    """What this shift needs to act on: short groups, expiring units, new requests."""
    from django.conf import settings

    from hospitals.utils import staff_hospital
    from inventory.services import near_expiry_qs, stock_by_group
    from requests_app.models import BloodRequest, RequestStatus

    hospital = staff_hospital(user)
    if hospital is None:
        return {}

    stock = stock_by_group(hospital)
    return {
        "hospital": hospital,
        "stock": stock,
        "low_stock": {g: n for g, n in stock.items() if n < settings.LOW_STOCK_THRESHOLD},
        "near_expiry_count": near_expiry_qs(hospital).count(),
        "pending_requests": BloodRequest.objects.filter(
            hospital=hospital, status=RequestStatus.PENDING
        ).select_related("patient")[:5],
    }


def _patient_context(user):
    from requests_app.models import BloodRequest

    return {"my_requests": BloodRequest.objects.filter(patient=user).select_related("hospital")[:5]}


@login_required
def dashboard(request):
    context = {}
    if request.user.role == "ADMIN" or request.user.is_superuser:
        context.update(_admin_context())
    # A Hospital account is the organisation itself and carries the same shift
    # context as its staff (stock, pending requests) once approved.
    if request.user.role in ("HOSPITAL_STAFF", "HOSPITAL"):
        context.update(_staff_context(request.user))
    if request.user.role == "PATIENT":
        context.update(_patient_context(request.user))
    if request.user.role == "DONOR":
        donor = getattr(request.user, "donor_profile", None)
        if donor:
            from django.conf import settings

            from donors import services

            stage1_passed, stage1_reasons, _ = services.run_stage1(donor)
            days = services.days_since_last_donation(donor)
            days_until_next = None
            if days is not None and days < settings.DONATION_INTERVAL_DAYS:
                days_until_next = settings.DONATION_INTERVAL_DAYS - days
            context.update(
                {
                    "stage1_passed": stage1_passed,
                    "stage1_reasons": stage1_reasons,
                    "latest_screening": services.latest_screening(donor),
                    "days_until_next": days_until_next,
                    "donations": donor.donations.select_related("hospital")[:10],
                    "organ_requests": donor.organ_requests.select_related("hospital")[:10],
                }
            )
    return render(request, "accounts/dashboard.html", context)
