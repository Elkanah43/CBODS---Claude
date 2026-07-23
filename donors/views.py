from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Prefetch
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from audit.services import log_action
from cbods.pagination import paginate
from notifications.services import notify

from . import services
from .forms import DonorProfileForm, RejectDonorForm, ScreeningForm
from .models import Donor, RegistrationStatus, ScreeningRecord


@role_required("DONOR")
def donor_profile(request):
    """Create, view, or (after a rejection) resubmit the donor's registration.

    A REJECTED donor can correct their details and upload a new ID; resubmitting
    returns the record to PENDING for a fresh admin review.
    """
    donor = Donor.objects.filter(user=request.user).first()
    resubmitting = donor is not None and donor.registration_status == RegistrationStatus.REJECTED
    if donor and not resubmitting:
        return render(request, "donors/profile_detail.html", {"donor": donor})

    if request.method == "POST":
        form = DonorProfileForm(request.POST, request.FILES, instance=donor)
        if form.is_valid():
            donor = form.save(commit=False)
            donor.user = request.user
            if resubmitting:
                donor.registration_status = RegistrationStatus.PENDING
                donor.rejection_reason = None
            donor.save()
            messages.success(
                request,
                "Registration resubmitted for review." if resubmitting
                else "Donor registration submitted. An administrator will review your ID.",
            )
            return redirect("dashboard")
    else:
        form = DonorProfileForm(instance=donor)
    return render(request, "donors/profile_form.html", {"form": form, "resubmitting": resubmitting, "donor": donor})


@role_required("ADMIN")
def id_document(request, donor_id):
    """Serve a donor's government ID through an authenticated view.

    ID scans are never exposed as plain media URLs: MEDIA_ROOT is not served by
    the URLconf, so this view is the only way to read one, and it is restricted
    to administrators reviewing registrations (spec rules 1 and 8).
    """
    donor = get_object_or_404(Donor, pk=donor_id)
    if not donor.id_document:
        raise Http404("No ID document on file.")
    return FileResponse(donor.id_document.open("rb"), filename=donor.id_document.name.rsplit("/", 1)[-1])


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

    page = paginate(request, donors.order_by("full_name"))
    return render(
        request,
        "donors/donor_search.html",
        {
            "donors": page.object_list,
            "page": page,
            "querystring": urlencode(
                {k: v for k, v in [("blood_group", blood_group), ("city", city), ("organ_type", organ_type)] if v}
            ),
            "blood_groups": BloodGroup.choices,
            "organ_types": OrganType.choices,
            "sel": {"blood_group": blood_group, "city": city, "organ_type": organ_type},
        },
    )


@role_required("HOSPITAL_STAFF")
def screening_list(request):
    # Prefetch screenings so the latest one per donor costs no extra query.
    donors = (
        Donor.objects.filter(registration_status=RegistrationStatus.APPROVED)
        .select_related("user")
        .prefetch_related(Prefetch("screenings", queryset=ScreeningRecord.objects.order_by("-created_at")))
        .order_by("full_name")
    )
    page = paginate(request, donors)
    rows = [(d, next(iter(d.screenings.all()), None)) for d in page.object_list]
    return render(request, "donors/screening_list.html", {"rows": rows, "page": page})


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
