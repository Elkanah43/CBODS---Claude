from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.db.models import Prefetch
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from audit.services import log_action
from cbods.pagination import paginate
from hospitals.decorators import require_approved_hospital
from hospitals.models import Hospital
from hospitals.utils import staff_hospital
from inventory.services import stock_map
from notifications.services import notify, notify_many

from . import services
from .forms import AppointmentForm, DonorProfileForm, RejectDonorForm, ScreeningForm
from .models import Appointment, AppointmentStatus, Donor, RegistrationStatus, ScreeningRecord


def notify_many_hospital_staff(hospital, subject, body):
    """Notify every staff account of a hospital (hospital account included)."""
    notify_many([sp.user for sp in hospital.staff.select_related("user")], subject, body)


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


@role_required("DONOR")
def donor_profile_edit(request):
    """Allow approved donors to update their profile details."""
    donor = Donor.objects.filter(user=request.user).first()
    if not donor:
        messages.warning(request, "You must register as a donor first.")
        return redirect("donor_profile")

    if request.method == "POST":
        form = DonorProfileForm(request.POST, request.FILES, instance=donor)
        if form.is_valid():
            form.save()
            messages.success(request, "Your donor profile has been updated.")
            return redirect("donor_profile")
    else:
        form = DonorProfileForm(instance=donor)
    return render(request, "donors/profile_form.html", {"form": form, "editing": True, "donor": donor})


@role_required("DONOR")
def donation_sites(request):
    """Donor-facing directory of approved hospitals with live stock.

    Informational only: the donor picks where to walk in, and eligibility is
    still decided by hospital staff at screening time. The donor's city ranks
    first, then hospitals short on the donor's own blood group, so the page
    answers both "where can I go" and "where am I most useful".
    """
    donor = Donor.objects.filter(user=request.user).first()
    hospitals = list(Hospital.objects.visible_to(request.user))
    stock = stock_map(hospitals)  # one aggregate query for every hospital

    rows = []
    for hospital in hospitals:
        counts = stock[hospital.pk]
        low = [g for g, n in counts.items() if n < settings.LOW_STOCK_THRESHOLD]
        rows.append(
            {
                "hospital": hospital,
                "stock": counts,
                "low_groups": low,
                "needs_mine": donor is not None and donor.blood_group in low,
                "same_city": donor is not None
                and bool(donor.city)
                and donor.city.lower() == hospital.city.lower(),
            }
        )
    rows.sort(key=lambda r: (not r["same_city"], not r["needs_mine"], r["hospital"].name))

    # Hospitals where this donor already has an open booking, so the card CTA
    # can say "Appointment pending" instead of offering a second booking.
    pending_ids = set(
        Appointment.objects.filter(
            donor=donor,
            hospital__in=hospitals,
            status=AppointmentStatus.PENDING,
        ).values_list("hospital_id", flat=True)
    ) if donor else set()

    return render(
        request,
        "donors/donation_sites.html",
        {
            "rows": rows,
            "donor": donor,
            "low_threshold": settings.LOW_STOCK_THRESHOLD,
            "pending_ids": pending_ids,
        },
    )


@role_required("DONOR")
def book_appointment(request, hospital_id):
    """Book a walk-in donation appointment at one hospital from the directory.

    The hospital must be one the directory already shows (approved, not
    hidden); the donor needs an approved registration, since unverified
    visitors cannot commit hospital screening slots. Booking is informational
    for the hospital — eligibility is still decided at screening.
    """
    donor = Donor.objects.filter(user=request.user).first()
    if donor is None or donor.registration_status != RegistrationStatus.APPROVED:
        messages.warning(request, "Your donor registration must be approved before booking an appointment.")
        return redirect("donation_sites")

    hospital = get_object_or_404(Hospital.objects.visible_to(request.user), pk=hospital_id)
    open_appointment = Appointment.objects.filter(
        donor=donor, hospital=hospital, status=AppointmentStatus.PENDING
    ).first()
    if open_appointment:
        messages.info(request, f"You already have a pending appointment at {hospital.name}.")
        return redirect("my_appointments")

    if request.method == "POST":
        form = AppointmentForm(request.POST)
        if form.is_valid():
            appointment = Appointment.objects.create(
                donor=donor,
                hospital=hospital,
                requested_for=form.cleaned_data["requested_for"],
                donor_note=form.cleaned_data["donor_note"],
            )
            log_action(request.user, "APPOINTMENT_BOOKED", appointment, {
                "hospital": hospital.name,
                "requested_for": str(appointment.requested_for),
            })
            notify_many_hospital_staff(
                hospital,
                f"New donation appointment: {donor.full_name} ({donor.blood_group})",
                f"{donor.full_name} booked to donate {donor.blood_group} on "
                f"{appointment.requested_for} at {hospital.name}.",
            )
            messages.success(
                request,
                f"Appointment requested at {hospital.name} for {appointment.requested_for}. "
                "Staff will confirm it.",
            )
            return redirect("my_appointments")
    else:
        form = AppointmentForm()

    return render(
        request,
        "donors/appointment_form.html",
        {"form": form, "hospital": hospital, "donor": donor},
    )


@role_required("DONOR")
def my_appointments(request):
    """The donor's bookings with their current status and any staff reply."""
    appointments = Appointment.objects.filter(donor__user=request.user).select_related("hospital")
    return render(request, "donors/my_appointments.html", {"appointments": appointments})


@role_required("DONOR")
@require_POST
def appointment_cancel(request, appointment_id):
    """The donor withdraws a pending booking (audited; staff are told)."""
    appointment = get_object_or_404(
        Appointment, pk=appointment_id, donor__user=request.user, status=AppointmentStatus.PENDING
    )
    appointment.status = AppointmentStatus.DECLINED
    appointment.decided_at = timezone.now()
    appointment.staff_note = "Cancelled by the donor."
    appointment.save(update_fields=["status", "decided_at", "staff_note"])
    log_action(request.user, "APPOINTMENT_CANCELLED", appointment, {"hospital": appointment.hospital.name})
    notify_many_hospital_staff(
        appointment.hospital,
        f"Appointment cancelled: {appointment.donor.full_name}",
        f"{appointment.donor.full_name} cancelled the donation appointment "
        f"for {appointment.requested_for} at {appointment.hospital.name}.",
    )
    messages.info(request, "Appointment cancelled.")
    return redirect("my_appointments")


@role_required("HOSPITAL_STAFF", "HOSPITAL")
@require_approved_hospital
def appointment_inbox(request):
    """Donation bookings made through the public directory, for staff to decide."""
    hospital = staff_hospital(request.user)
    appointments = (
        Appointment.objects.filter(hospital=hospital)
        .select_related("donor", "donor__user")
        .order_by("-created_at")
    )
    open_count = appointments.filter(status=AppointmentStatus.PENDING).count()
    return render(
        request,
        "donors/appointment_inbox.html",
        {"appointments": appointments, "open_count": open_count},
    )


@role_required("HOSPITAL_STAFF", "HOSPITAL")
@require_approved_hospital
@require_POST
def appointment_decide(request, appointment_id):
    """Confirm or decline one booking. The donor is notified either way."""
    hospital = staff_hospital(request.user)
    appointment = get_object_or_404(
        Appointment, pk=appointment_id, hospital=hospital, status=AppointmentStatus.PENDING
    )
    action = request.POST.get("action")
    if action == "confirm":
        appointment.status = AppointmentStatus.CONFIRMED
        subject = "Donation appointment confirmed"
        body = (
            f"{hospital.name} confirmed your donation appointment for "
            f"{appointment.requested_for}. Bring your government ID."
        )
        messages.success(request, f"Appointment for {appointment.donor.full_name} confirmed.")
    elif action == "decline":
        appointment.status = AppointmentStatus.DECLINED
        subject = "Donation appointment declined"
        body = (
            f"{hospital.name} could not take your donation appointment for "
            f"{appointment.requested_for}. {request.POST.get('staff_note', '')}".strip()
        )
        messages.warning(request, f"Appointment for {appointment.donor.full_name} declined.")
    else:
        raise Http404("Unknown action.")

    appointment.decided_at = timezone.now()
    staff_note = request.POST.get("staff_note", "").strip()
    if staff_note:
        appointment.staff_note = staff_note
    appointment.save(update_fields=["status", "decided_at", "staff_note"])
    log_action(request.user, f"APPOINTMENT_{appointment.status}", appointment, {
        "donor": appointment.donor.full_name,
        "requested_for": str(appointment.requested_for),
    })
    notify(appointment.donor.user, subject, body)
    return redirect("appointment_inbox")


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


@role_required("HOSPITAL_STAFF", "HOSPITAL", "ADMIN")
@require_approved_hospital
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


@role_required("HOSPITAL_STAFF", "HOSPITAL")
@require_approved_hospital
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


@role_required("HOSPITAL_STAFF", "HOSPITAL")
@require_approved_hospital
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
