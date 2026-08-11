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
from audit.models import AuditLog
from audit.services import log_action
from cbods.pagination import paginate
from notifications.services import notify

from . import services
from .decorators import require_approved_hospital
from .forms import (
    HospitalAdminEditForm,
    HospitalProfileForm,
    HospitalRegisterForm,
    HospitalStaffAddForm,
)
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
    """Pending registrations, oldest first, with a name/city search box."""
    pending = Hospital.objects.filter(
        approval_status=HospitalApprovalStatus.PENDING
    ).order_by("created_at", "pk")
    q = request.GET.get("q", "")
    if q:
        pending = pending.filter(Q(name__icontains=q) | Q(city__icontains=q))
    accounts = services.hospital_account_map(pending)
    for hospital in pending:
        hospital.account_user = accounts.get(hospital.pk)
    return render(
        request,
        "hospitals/approval_queue.html",
        {
            "pending": pending,
            "q": q,
            # One glance at how much work is waiting, and links to the other
            # lists. Status filters live on the manage page, so the counts
            # only need to point there.
            "counts": {
                status: Hospital.objects.filter(approval_status=status).count()
                for status in HospitalApprovalStatus.values
            },
        },
    )


# Human-readable labels for the review page's decision history.
_HISTORY_LABELS = {
    "HOSPITAL_REGISTERED": "Registration submitted",
    "HOSPITAL_UPDATED": "Details updated",
    "HOSPITAL_EDITED_BY_ADMIN": "Edited by admin",
    "HOSPITAL_RESUBMITTED": "Resubmitted for review",
    "HOSPITAL_APPROVED": "Approved",
    "HOSPITAL_REJECTED": "Rejected",
    "HOSPITAL_HIDDEN": "Hidden from patients",
    "HOSPITAL_UNHIDDEN": "Revealed to patients",
}


def _review_history(hospital):
    """The hospital's audit trail, newest first, ready for the template."""
    logs = AuditLog.objects.filter(
        entity_type="Hospital", entity_id=str(hospital.pk)
    ).select_related("actor")[:10]
    return [
        {
            "at": log.created_at,
            "label": _HISTORY_LABELS.get(
                log.action, log.action.replace("_", " ").title()
            ),
            "actor": log.actor.username if log.actor else "system",
        }
        for log in logs
    ]


def _duplicate_hints(hospital):
    """Approved hospitals that may be the same organisation, to flag in review.

    Matches on an exact name, or a shared city plus the first word of the name
    — enough to catch re-registrations under a slightly different name without
    drowning the reviewer in near-misses.
    """
    parts = hospital.name.split()
    if not parts or not hospital.city:
        # No name (or whitespace-only) and no city give nothing to match on;
        # an empty city would otherwise flag every other blank-city hospital.
        return Hospital.objects.none()
    first_word = parts[0]
    return (
        Hospital.objects.filter(approval_status=HospitalApprovalStatus.APPROVED)
        .exclude(pk=hospital.pk)
        .filter(
            Q(name__iexact=hospital.name)
            | Q(city__iexact=hospital.city, name__icontains=first_word)
        )
    )


def _review_context(hospital):
    """Everything the review page needs beyond the edit form."""
    return {
        "hospital": hospital,
        "account": _hospital_account_user(hospital),
        "history": _review_history(hospital),
        "reviewable": hospital.approval_status in (
            HospitalApprovalStatus.PENDING,
            HospitalApprovalStatus.REJECTED,
        ),
        "duplicates": _duplicate_hints(hospital),
        "next_pending": (
            Hospital.objects.filter(approval_status=HospitalApprovalStatus.PENDING)
            .exclude(pk=hospital.pk)
            .order_by("created_at", "pk")
            .first()
        ),
    }


@role_required("ADMIN")
def hospital_review_detail(request, hospital_id):
    """Full review of one registration: record, account, history, decision.

    The decision buttons work for PENDING and REJECTED registrations, so an
    admin can also reverse an earlier rejection (after a phone call, say)
    without the hospital having to resubmit. Approved hospitals show a "live"
    state instead, with pointers to the management actions.
    """
    hospital = get_object_or_404(Hospital, pk=hospital_id)
    context = _review_context(hospital)
    context["edit_form"] = HospitalAdminEditForm(instance=hospital)
    return render(request, "hospitals/review_detail.html", context)


@role_required("ADMIN")
def hospital_admin_edit(request, hospital_id):
    """Admin fixes a registration's details (typos, contact info) in place.

    Works in any approval state; the change is audited so it appears in the
    review history and the hospital's activity feed. A failed validation
    re-renders the review page with the form open and its errors inline.
    """
    hospital = get_object_or_404(Hospital, pk=hospital_id)
    edit_form = HospitalAdminEditForm(request.POST or None, instance=hospital)
    if request.method == "POST" and edit_form.is_valid():
        changed = edit_form.changed_data
        if changed:
            edit_form.save()
            log_action(request.user, "HOSPITAL_EDITED_BY_ADMIN", hospital, {"changed": changed})
            messages.success(request, f"{hospital.name} updated.")
        else:
            messages.info(request, "No changes were made.")
        return redirect("hospital_review_detail", hospital.pk)
    context = _review_context(hospital)
    context["edit_form"] = edit_form
    return render(request, "hospitals/review_detail.html", context)


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
            if request.POST.get("next") == "review":
                return redirect("hospital_review_detail", hospital.pk)
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
        if request.POST.get("next") == "review":
            return redirect("hospital_review_detail", hospital.pk)
        return redirect("hospital_approval_queue")
    # From the review page, stay on the review page; from the queue, return to
    # the queue. Everything else keeps the old redirect for compatibility.
    if request.POST.get("next") == "review":
        return redirect("hospital_review_detail", hospital.pk)
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
