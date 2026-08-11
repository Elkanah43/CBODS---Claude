from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login
from django.db.models import Q
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts import password_rules
from accounts.decorators import role_required
from accounts.models import Role
from audit.services import log_action
from cbods.pagination import paginate
from notifications.services import notify

from . import services
from .decorators import require_approved_hospital
from .forms import HospitalProfileForm, HospitalRegisterForm, HospitalStaffAddForm
from .models import Hospital, HospitalApprovalStatus, StaffProfile
from .utils import staff_hospital


def hospital_register(request):
    """Self-service hospital signup.

    The account is usable straight away (login works, the dashboard explains
    the pending state) but every feature is gated until an admin approves the
    Hospital record. Rejected hospitals can register again under the same name:
    the form reuses their Hospital row and returns it to PENDING.
    """
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = HospitalRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            log_action(
                user, "HOSPITAL_REGISTERED", user.staff_profile.hospital,
                {"name": user.staff_profile.hospital.name},
            )
            messages.success(
                request,
                "Your hospital registration has been submitted. "
                "An administrator will review it before your hospital goes live.",
            )
            return redirect("dashboard")
    else:
        form = HospitalRegisterForm()
    return render(
        request,
        "hospitals/register.html",
        {"form": form, "password_rules": password_rules.get_rules()},
    )


def _hospital_account_user(hospital):
    """The Hospital's own account (role=HOSPITAL), if one exists."""
    profile = hospital.staff.filter(user__role=Role.HOSPITAL).first()
    return profile.user if profile else None


@role_required("HOSPITAL")
def hospital_profile(request):
    """View and edit the hospital's own record.

    Editing is allowed in every state, mirroring the donor resubmit flow: a
    rejected hospital can correct its details and save to return the record to
    PENDING for a fresh review. Only operational features require approval.
    """
    hospital = staff_hospital(request.user)
    if hospital is None:
        messages.error(request, "Your account is not linked to a hospital.")
        return redirect("dashboard")
    resubmitting = hospital.approval_status == HospitalApprovalStatus.REJECTED
    form = HospitalProfileForm(request.POST or None, instance=hospital)
    if request.method == "POST" and form.is_valid():
        form.save()
        if resubmitting:
            hospital.approval_status = HospitalApprovalStatus.PENDING
            hospital.rejection_reason = None
            hospital.save(update_fields=["approval_status", "rejection_reason"])
            log_action(request.user, "HOSPITAL_RESUBMITTED", hospital, {"name": hospital.name})
            messages.success(request, "Details updated — your registration has been resubmitted for review.")
        else:
            log_action(request.user, "HOSPITAL_UPDATED", hospital, {"name": hospital.name})
            messages.success(request, "Hospital profile updated.")
        return redirect("hospital_profile")
    return render(request, "hospitals/profile.html", {"form": form, "hospital": hospital})


@role_required("HOSPITAL")
@require_approved_hospital
def hospital_staff(request):
    """Staff roster for the hospital, with the add-staff form."""
    hospital = staff_hospital(request.user)
    staff = hospital.staff.select_related("user").order_by("user__username")
    add_form = HospitalStaffAddForm()
    return render(
        request,
        "hospitals/staff_list.html",
        {"hospital": hospital, "staff": staff, "add_form": add_form},
    )


@role_required("HOSPITAL")
@require_approved_hospital
def hospital_staff_add(request):
    """Provision a HOSPITAL_STAFF account for this hospital."""
    hospital = staff_hospital(request.user)
    add_form = HospitalStaffAddForm(request.POST or None)
    if add_form.is_valid():
        user = add_form.save(commit=False)
        user.role = Role.HOSPITAL_STAFF
        user.save()
        StaffProfile.objects.create(user=user, hospital=hospital)
        log_action(
            request.user, "STAFF_CREATED", user,
            {"hospital": hospital.name, "username": user.username},
        )
        notify(
            user,
            "Welcome to CBODS staff",
            f"You now have a staff account at {hospital.name}. Sign in to manage "
            "screening, inventory and blood requests.",
        )
        messages.success(request, f"Staff account '{user.username}' created for {hospital.name}.")
        return redirect("hospital_staff")
    staff = hospital.staff.select_related("user").order_by("user__username")
    return render(
        request,
        "hospitals/staff_list.html",
        {"hospital": hospital, "staff": staff, "add_form": add_form},
    )


@role_required("HOSPITAL")
@require_approved_hospital
@require_POST
def hospital_staff_remove(request, staff_id):
    """Remove a staff member: unlink and deactivate (audit trail survives)."""
    hospital = staff_hospital(request.user)
    profile = get_object_or_404(StaffProfile, pk=staff_id, hospital=hospital)
    user = profile.user
    if user == request.user:
        messages.error(request, "You cannot remove your own account.")
        return redirect("hospital_staff")
    profile.delete()
    user.is_active = False
    user.save(update_fields=["is_active"])
    log_action(
        request.user, "STAFF_REMOVED", user,
        {"hospital": hospital.name, "username": user.username},
    )
    messages.warning(request, f"'{user.username}' removed from staff and can no longer sign in.")
    return redirect("hospital_staff")


@role_required("ADMIN")
def hospital_approval_queue(request):
    pending = Hospital.objects.filter(
        approval_status=HospitalApprovalStatus.PENDING
    ).order_by("name")
    return render(request, "hospitals/approval_queue.html", {"pending": pending})


@role_required("ADMIN")
def hospital_approval_action(request, hospital_id):
    hospital = get_object_or_404(Hospital, pk=hospital_id)
    if request.method != "POST":
        return redirect("hospital_approval_queue")

    action = request.POST.get("action")
    account = _hospital_account_user(hospital)

    if action == "approve":
        hospital.approval_status = HospitalApprovalStatus.APPROVED
        hospital.rejection_reason = None
        hospital.save()
        log_action(request.user, "HOSPITAL_APPROVED", hospital, {"name": hospital.name})
        if account:
            notify(
                account,
                "Hospital registration approved",
                f"Your hospital {hospital.name} is now approved and live on CBODS. "
                "You can manage your profile, staff and blood bank operations.",
            )
        messages.success(request, f"{hospital.name} approved and live.")
    elif action == "reject":
        reason = request.POST.get("rejection_reason", "").strip()
        if not reason:
            messages.error(request, "A rejection reason is required.")
            return redirect("hospital_approval_queue")
        hospital.approval_status = HospitalApprovalStatus.REJECTED
        hospital.rejection_reason = reason
        hospital.save()
        log_action(request.user, "HOSPITAL_REJECTED", hospital, {"reason": reason})
        if account:
            notify(
                account,
                "Hospital registration rejected",
                f"Your hospital registration for {hospital.name} was rejected. "
                f"Reason: {reason}. You can correct the details and resubmit.",
            )
        messages.warning(request, f"{hospital.name} rejected.")
    else:
        messages.error(request, "Invalid action.")
        return redirect("hospital_approval_queue")
    return redirect("hospital_approval_queue")


@role_required("ADMIN")
def hospital_admin_list(request):
    """Admin directory of every hospital, with filters and hide/unhide actions."""
    hospitals = Hospital.objects.all()
    q = request.GET.get("q", "")
    status = request.GET.get("status", "")
    hidden = request.GET.get("hidden", "")
    if q:
        hospitals = hospitals.filter(Q(name__icontains=q) | Q(city__icontains=q))
    if status:
        hospitals = hospitals.filter(approval_status=status)
    if hidden == "yes":
        hospitals = hospitals.filter(is_hidden=True)
    elif hidden == "no":
        hospitals = hospitals.filter(is_hidden=False)
    page = paginate(request, hospitals.order_by("name"))
    return render(
        request,
        "hospitals/admin_list.html",
        {
            "hospitals": page.object_list,
            "page": page,
            "querystring": urlencode(
                {k: v for k, v in [("q", q), ("status", status), ("hidden", hidden)] if v}
            ),
            "statuses": HospitalApprovalStatus.choices,
            "sel": {"q": q, "status": status, "hidden": hidden},
        },
    )


@role_required("ADMIN")
@require_POST
def hospital_admin_toggle_hidden(request, hospital_id):
    """Hide or reveal a hospital without deleting it."""
    hospital = get_object_or_404(Hospital, pk=hospital_id)
    hospital.is_hidden = not hospital.is_hidden
    hospital.save(update_fields=["is_hidden"])
    log_action(
        request.user,
        "HOSPITAL_HIDDEN" if hospital.is_hidden else "HOSPITAL_UNHIDDEN",
        hospital,
        {"name": hospital.name},
    )
    if hospital.is_hidden:
        messages.warning(request, f"{hospital.name} is now hidden from patients and donors.")
    else:
        messages.success(request, f"{hospital.name} is now visible to patients and donors.")
    destination = reverse("hospital_admin_list")
    next_qs = request.POST.get("next_qs", "")
    if next_qs:
        destination += f"?{next_qs}"
    return redirect(destination)


@role_required("HOSPITAL_STAFF", "HOSPITAL")
@require_approved_hospital
def hospital_reports(request):
    """Hospital-level reporting: headline figures plus monthly series."""
    from inventory.models import BagStatus, BloodBag, Donation
    from inventory.services import stock_by_group
    from requests_app.models import BloodRequest, RequestStatus

    hospital = staff_hospital(request.user)
    donations = Donation.objects.filter(hospital=hospital)
    totals = {
        "available": sum(stock_by_group(hospital).values()),
        "issued": BloodBag.objects.filter(hospital=hospital, status=BagStatus.ISSUED).count(),
        "fulfilled": BloodRequest.objects.filter(
            hospital=hospital, status=RequestStatus.FULFILLED
        ).count(),
        "donations": donations.count(),
        "volume_ml": donations.aggregate(total=Sum("volume_ml"))["total"] or 0,
    }
    charts = {
        "donations_by_month": services.donations_by_month(hospital),
        "issued_by_month": services.issued_bags_by_month(hospital),
        "fulfilled_by_month": services.fulfilled_requests_by_month(hospital),
    }
    return render(
        request,
        "hospitals/reports.html",
        {
            "hospital": hospital,
            "totals": totals,
            "charts": charts,
            "recent_donations": donations.select_related("donor")[:10],
        },
    )


@role_required("HOSPITAL_STAFF", "HOSPITAL")
@require_approved_hospital
def hospital_activity(request):
    """The hospital's own recent activity, newest first."""
    hospital = staff_hospital(request.user)
    return render(
        request,
        "hospitals/activity.html",
        {"hospital": hospital, "items": services.hospital_activity_items(hospital)},
    )
