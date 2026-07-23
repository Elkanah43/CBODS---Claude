from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required
from audit.services import log_action
from hospitals.utils import staff_hospital
from notifications.services import notify

from .forms import OrganRequestForm
from .models import OrganDonationRequest, OrganRequestStatus


@role_required("DONOR")
def organ_request_create(request):
    donor = getattr(request.user, "donor_profile", None)
    if donor is None:
        messages.warning(request, "Complete donor registration before submitting organ donation requests.")
        return redirect("donor_profile")
    if donor.registration_status != "APPROVED":
        messages.warning(request, "Organ donation requests are available once your registration is approved.")
        return redirect("dashboard")
    form = OrganRequestForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        organ_request = OrganDonationRequest.objects.create(
            donor=donor,
            hospital=form.cleaned_data["hospital"],
            organ_type=form.cleaned_data["organ_type"],
        )
        log_action(request.user, "ORGAN_REQUEST_CREATED", organ_request, {"organ": organ_request.organ_type})
        messages.success(request, f"Organ donation request sent to {organ_request.hospital.name} for review.")
        return redirect("organ_my_requests")
    return render(request, "organs/request_form.html", {"form": form})


@role_required("DONOR")
def organ_my_requests(request):
    donor = getattr(request.user, "donor_profile", None)
    reqs = donor.organ_requests.select_related("hospital") if donor else []
    return render(request, "organs/my_requests.html", {"reqs": reqs})


@role_required("HOSPITAL_STAFF")
def organ_review_list(request):
    hospital = staff_hospital(request.user)
    if hospital is None:
        messages.error(request, "Your staff account is not linked to a hospital.")
        return redirect("dashboard")
    reqs = OrganDonationRequest.objects.filter(hospital=hospital).select_related("donor")
    return render(request, "organs/review_list.html", {"hospital": hospital, "reqs": reqs})


@role_required("HOSPITAL_STAFF")
def organ_review_action(request, request_id):
    hospital = staff_hospital(request.user)
    organ_request = get_object_or_404(OrganDonationRequest, pk=request_id, hospital=hospital)
    if request.method != "POST":
        return redirect("organ_review_list")

    new_status = request.POST.get("status")
    valid = {OrganRequestStatus.REQUESTED, OrganRequestStatus.APPROVED, OrganRequestStatus.REJECTED}
    if new_status not in valid:
        messages.error(request, "Invalid status.")
        return redirect("organ_review_list")

    old = organ_request.status
    organ_request.status = new_status
    if new_status in (OrganRequestStatus.APPROVED, OrganRequestStatus.REJECTED):
        organ_request.decided_at = timezone.now()
    organ_request.save()
    log_action(request.user, f"ORGAN_REQUEST_{new_status}", organ_request, {"from": old, "to": new_status})
    notify(
        organ_request.donor.user,
        f"Organ donation request {organ_request.get_status_display().lower()}",
        f"Your {organ_request.get_organ_type_display()} donation request at {organ_request.hospital.name} "
        f"is now: {organ_request.get_status_display()}.",
    )
    messages.success(request, f"Request marked {organ_request.get_status_display()}; donor notified.")
    return redirect("organ_review_list")
