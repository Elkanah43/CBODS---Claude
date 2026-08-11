from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from cbods.pagination import paginate
from hospitals.decorators import require_approved_hospital
from hospitals.models import Hospital
from hospitals.utils import staff_hospital
from inventory.services import available_groups, available_groups_map

from . import compatibility, services
from .forms import BloodRequestForm, CompatibilityCheckForm, RejectRequestForm
from .models import BloodRequest, RequestStatus


@role_required("PATIENT")
def hospital_list(request):
    hospitals = list(Hospital.objects.visible_to(request.user))
    stock = available_groups_map(hospitals)  # one query for every hospital
    rows = [(h, stock[h.pk]) for h in hospitals]
    return render(request, "requests_app/hospital_list.html", {"rows": rows})


@role_required("PATIENT")
def request_create(request, hospital_id):
    hospital = get_object_or_404(Hospital.objects.visible_to(request.user), pk=hospital_id)
    groups = available_groups(hospital)
    if not groups:
        messages.warning(request, f"{hospital.name} has no blood available right now.")
        return redirect("hospital_list")
    form = BloodRequestForm(request.POST or None, available_groups=groups)
    if request.method == "POST" and form.is_valid():
        BloodRequest.objects.create(
            patient=request.user,
            hospital=hospital,
            blood_group=form.cleaned_data["blood_group"],
            units_requested=form.cleaned_data["units_requested"],
            urgency=form.cleaned_data["urgency"],
        )
        messages.success(request, "Blood request submitted. The hospital will review it.")
        return redirect("my_requests")
    return render(request, "requests_app/request_form.html", {"form": form, "hospital": hospital, "groups": groups})


@role_required("PATIENT")
def my_requests(request):
    reqs = BloodRequest.objects.filter(patient=request.user).select_related("hospital")
    return render(request, "requests_app/my_requests.html", {"reqs": reqs})


@role_required("HOSPITAL_STAFF", "HOSPITAL")
@require_approved_hospital
def request_inbox(request):
    hospital = staff_hospital(request.user)
    if hospital is None:
        messages.error(request, "Your staff account is not linked to a hospital.")
        return redirect("dashboard")
    reqs = BloodRequest.objects.filter(hospital=hospital).select_related("patient")
    page = paginate(request, reqs)
    reject_form = RejectRequestForm()
    return render(
        request,
        "requests_app/request_inbox.html",
        {"hospital": hospital, "reqs": page.object_list, "page": page, "reject_form": reject_form},
    )


@role_required("HOSPITAL_STAFF", "HOSPITAL")
@require_approved_hospital
def request_action(request, request_id):
    hospital = staff_hospital(request.user)
    blood_request = get_object_or_404(BloodRequest, pk=request_id, hospital=hospital)
    if request.method != "POST":
        return redirect("request_inbox")

    action = request.POST.get("action")
    try:
        if action == "accept":
            services.accept_request(request.user, blood_request)
            messages.success(request, "Request accepted; bags reserved (soonest expiry first).")
        elif action == "reject":
            form = RejectRequestForm(request.POST)
            if form.is_valid():
                services.reject_request(request.user, blood_request, form.cleaned_data["rejection_reason"])
                messages.warning(request, "Request rejected.")
            else:
                messages.error(request, "A rejection reason is required.")
        elif action == "fulfil":
            services.fulfil_request(request.user, blood_request)
            messages.success(request, "Request fulfilled; bags issued.")
    except services.InsufficientStock as exc:
        msg = (
            f"Insufficient stock: only {exc.available} AVAILABLE {blood_request.blood_group} bag(s). "
            "Reject the request or source more stock."
        )
        if blood_request.urgency == "EMERGENCY":
            reached = services.broadcast_emergency(blood_request)
            msg += (
                f" Emergency broadcast sent to {len(reached)} compatible donor(s) in "
                f"{blood_request.hospital.city}."
            )
        messages.error(request, msg)
        if blood_request.urgency == "EMERGENCY":
            return redirect("donor_suggestions", request_id=blood_request.pk)
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("request_inbox")


@role_required("HOSPITAL_STAFF", "HOSPITAL")
@require_approved_hospital
def compatibility_check(request):
    hospital = staff_hospital(request.user)
    if hospital is None:
        messages.error(request, "Your staff account is not linked to a hospital.")
        return redirect("dashboard")
    form = CompatibilityCheckForm(request.POST or None)
    result = None
    if request.method == "POST" and form.is_valid():
        donor = form.cleaned_data["donor"]
        recipient_group = form.cleaned_data["recipient_group"]
        urgency = form.cleaned_data["urgency"]
        ok, alternatives = compatibility.check_donor_for_recipient(hospital, recipient_group, donor, urgency)
        result = {
            "ok": ok,
            "donor": donor,
            "recipient_group": recipient_group,
            "alternatives": alternatives,
        }
    return render(
        request,
        "requests_app/compatibility_check.html",
        {"form": form, "result": result, "hospital": hospital},
    )


@role_required("HOSPITAL_STAFF", "HOSPITAL")
@require_approved_hospital
def donor_suggestions(request, request_id):
    """Ranked compatible-donor suggestions for a blood request (used when stock is short)."""
    hospital = staff_hospital(request.user)
    blood_request = get_object_or_404(BloodRequest, pk=request_id, hospital=hospital)
    donors = compatibility.suggest_donors(hospital, blood_request.blood_group, blood_request.urgency)
    bags = compatibility.compatible_bags(hospital, blood_request.blood_group)
    return render(
        request,
        "requests_app/donor_suggestions.html",
        {"blood_request": blood_request, "donors": donors, "bags": bags, "hospital": hospital},
    )
