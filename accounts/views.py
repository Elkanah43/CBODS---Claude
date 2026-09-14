from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from . import password_rules
from .forms import RegisterForm
from .models import User


def _send_welcome_notifications(user):
    """Tell the newly registered account it exists.

    Email goes through notifications.notify (in-app row + email); SMS goes
    through accounts.sms, whose console provider logs behind the
    CBODS-RESET-SMS marker so demos work with no gateway configured. A
    failure of either channel must never break the signup itself, so each
    leg is guarded and only logged.
    """
    import logging

    from notifications.services import notify

    logger = logging.getLogger("cbods.email")

    subject = "Welcome to CBODS"
    body = (
        f"Hello {user.username}, your CBODS account has been created "
        f"successfully. You can now sign in and use the system."
    )
    try:
        notify(user, subject, body)
    except Exception:
        logger.exception("Welcome notification failed for %s", user.username)

    if user.phone:
        from .sms import normalize_ghana_phone, send_sms

        try:
            # The column holds whatever shape arrived (024… local, +233… E.164);
            # providers want one unambiguous form.
            send_sms(
                normalize_ghana_phone(str(user.phone)),
                f"CBODS: Welcome, {user.username}! Your account has been created successfully.",
            )
        except Exception as e:  # noqa: BLE001 — a welcome text must never break signup
            logger.warning(
                "Welcome SMS to %s failed: %s", user.phone, e
            )


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            _send_welcome_notifications(user)
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


class LoginViewWithResetGate(LoginView):
    """Login page that keeps "Forgot password?" out of reach until a try fails.

    A user who clicks the reset link before the system has refused their
    credentials may only be misremembering the password — recovering it then
    loses the working one. So the first failed attempt marks the session, and
    only from then on the link is live. Before that the link renders inert and
    the card asks for username and password to confirm first. Success clears
    the flag, so a later visit starts gated again.
    """

    RESET_UNLOCK_KEY = "login_failed_once"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # reset_unlocked: this visit has already had credentials refused, so
        # the reset link is live. reset_blocked: the user just clicked the
        # gated link — remind them to confirm credentials first.
        context["reset_unlocked"] = bool(
            self.request.session.get(self.RESET_UNLOCK_KEY)
        )
        context["reset_blocked"] = self.request.GET.get("reset") == "blocked"
        return context

    def form_valid(self, form):
        # A successful sign-in clears any earlier failed attempt, so the gate
        # applies fresh on the next visit.
        self.request.session.pop(self.RESET_UNLOCK_KEY, None)
        return super().form_valid(form)

    def form_invalid(self, form):
        # LoginView.form_invalid only re-renders; mark the session so the
        # template may offer the reset link. Flags set via [] persist on the
        # next response (SESSION_SAVE_EVERY_REQUEST is on anyway).
        self.request.session[self.RESET_UNLOCK_KEY] = True
        return super().form_invalid(form)


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
