from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from audit.services import log_action
from notifications.services import notify

from . import services
from .forms import DonorProfileForm, RejectDonorForm, ScreeningForm
from .models import Donor, RegistrationStatus


@role_required("DONOR")
def donor_profile(request):
    """Create (or view) the donor's registration profile."""
    donor = Donor.objects.filter(user=request.user).first()
    if donor:
        return render(request, "donors/profile_detail.html", {"donor": donor})
    if request.method == "POST":
        form = DonorProfileForm(request.POST, request.FILES)
        if form.is_valid():
            donor = form.save(commit=False)
            donor.user = request.user
            donor.save()
            messages.success(request, "Donor registration submitted. An administrator will review your ID.")
            return redirect("dashboard")
    else:
        form = DonorProfileForm()
    return render(request, "donors/profile_form.html", {"form": form})


@role_required("ADMIN")
def approval_queue(request):
    pending = Donor.objects.filter(registration_status=RegistrationStatus.PENDING).select_related("user")
    return render(request, "donors/approval_queue.html", {"pending": pending})


@role_required("ADMIN")
def approval_detail(request, donor_id):
    donor = get_object_or_404(Donor, pk=donor_id)
    reject_form = RejectDonorForm()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "approve":
            donor.registration_status = RegistrationStatus.APPROVED
            donor.rejection_reason = None
            donor.save()
            log_action(request.user, "DONOR_APPROVED", donor, {"full_name": donor.full_name})
            notify(
                donor.user,
                "Donor registration approved",
                "Congratulations! Your donor registration has been approved. "
                "You now appear in donor search and may donate at participating hospitals.",
            )
            messages.success(request, f"{donor.full_name} approved.")
            return redirect("donor_approval_queue")
        if action == "reject":
            reject_form = RejectDonorForm(request.POST)
            if reject_form.is_valid():
                donor.registration_status = RegistrationStatus.REJECTED
                donor.rejection_reason = reject_form.cleaned_data["rejection_reason"]
                donor.save()
                log_action(request.user, "DONOR_REJECTED", donor, {"reason": donor.rejection_reason})
                notify(
                    donor.user,
                    "Donor registration rejected",
                    f"Your donor registration was rejected. Reason: {donor.rejection_reason}",
                )
                messages.warning(request, f"{donor.full_name} rejected.")
                return redirect("donor_approval_queue")

    return render(request, "donors/approval_detail.html", {"donor": donor, "reject_form": reject_form})


@role_required("HOSPITAL_STAFF", "ADMIN")
def donor_search(request):
    """Available Donors: APPROVED + is_available only. Contact details are shown
    because this page is restricted to hospital staff and admins."""
    donors = Donor.objects.filter(
        registration_status=RegistrationStatus.APPROVED, is_available=True
    ).select_related("user")

    blood_group = request.GET.get("blood_group", "")
    city = request.GET.get("city", "")
    organ_type = request.GET.get("organ_type", "")
    if blood_group:
        donors = donors.filter(blood_group=blood_group)
    if city:
        donors = donors.filter(city__icontains=city)
    if organ_type:
        donors = donors.filter(organ_requests__organ_type=organ_type).distinct()

    from cbods.constants import BloodGroup
    from organs.models import OrganType

    return render(
        request,
        "donors/donor_search.html",
        {
            "donors": donors,
            "blood_groups": BloodGroup.choices,
            "organ_types": OrganType.choices,
            "sel": {"blood_group": blood_group, "city": city, "organ_type": organ_type},
        },
    )


@role_required("HOSPITAL_STAFF")
def screening_list(request):
    donors = Donor.objects.filter(registration_status=RegistrationStatus.APPROVED).select_related("user")
    rows = [(d, services.latest_screening(d)) for d in donors]
    return render(request, "donors/screening_list.html", {"rows": rows})


@role_required("HOSPITAL_STAFF")
def screening_run(request, donor_id):
    donor = get_object_or_404(Donor, pk=donor_id, registration_status=RegistrationStatus.APPROVED)
    stage1_passed, stage1_reasons, _ = services.run_stage1(donor)
    form = ScreeningForm()

    if request.method == "POST":
        if stage1_passed:
            form = ScreeningForm(request.POST)
            if form.is_valid():
                record = services.screen_donor(donor, **form.cleaned_data)
            else:
                record = None
        else:
            record = services.screen_donor(donor)

        if record:
            notify(
                donor.user,
                f"Screening outcome: {record.get_outcome_display()}",
                (
                    "You appear eligible to donate — the final decision is made at the hospital."
                    if record.outcome == "ELIGIBLE"
                    else "Screening outcome: " + record.get_outcome_display() + ". Reasons: " + "; ".join(record.failed_reasons)
                ),
            )
            messages.info(request, f"Screening recorded: {record.get_outcome_display()}")
            return redirect("screening_list")

    return render(
        request,
        "donors/screening_form.html",
        {
            "donor": donor,
            "form": form,
            "stage1_passed": stage1_passed,
            "stage1_reasons": stage1_reasons,
            "latest": services.latest_screening(donor),
        },
    )
