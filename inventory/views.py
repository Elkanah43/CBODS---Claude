from django.conf import settings
from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render

from accounts.decorators import role_required
from hospitals.decorators import require_approved_hospital
from hospitals.utils import staff_hospital

from . import services
from .forms import RecordDonationForm, TTIResultsForm
from .models import BagStatus, BloodBag, TTITestRecord


@role_required("HOSPITAL_STAFF", "HOSPITAL")
@require_approved_hospital
def stock_dashboard(request):
    hospital = staff_hospital(request.user)
    if hospital is None:
        messages.error(request, "Your staff account is not linked to a hospital.")
        return redirect("dashboard")
    near_expiry = services.near_expiry_qs(hospital)
    near_expiry_ids = set(near_expiry.values_list("id", flat=True))
    bags = hospital.blood_bags.exclude(status=BagStatus.DISCARDED).order_by("status", "expiry_date")[:200]
    return render(
        request,
        "inventory/stock_dashboard.html",
        {
            "hospital": hospital,
            "stock": services.stock_by_group(hospital),
            "near_expiry_count": len(near_expiry_ids),
            "low_stock_threshold": settings.LOW_STOCK_THRESHOLD,
            "near_expiry_ids": near_expiry_ids,
            "bags": bags,
        },
    )


@role_required("HOSPITAL_STAFF", "HOSPITAL")
@require_approved_hospital
def record_donation(request):
    hospital = staff_hospital(request.user)
    if hospital is None:
        messages.error(request, "Your staff account is not linked to a hospital.")
        return redirect("dashboard")
    form = RecordDonationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            donation, bag = services.record_donation(
                request.user, form.cleaned_data["donor"], hospital, form.cleaned_data["volume_ml"]
            )
        except ValueError as exc:
            messages.error(request, f"Donation blocked: {exc}")
        else:
            messages.success(
                request,
                f"Donation recorded for {donation.donor.full_name}; "
                f"bag #{bag.pk} ({bag.blood_group}) added as UNTESTED — it enters the stock "
                f"pool once laboratory TTI screening clears it. Expires {bag.expiry_date}.",
            )
            return redirect("tti_screening_list")
    return render(request, "inventory/record_donation.html", {"form": form, "hospital": hospital})


@role_required("HOSPITAL_STAFF", "HOSPITAL")
@require_approved_hospital
def tti_screening_list(request):
    """Donations of this hospital awaiting laboratory TTI screening, oldest first."""
    hospital = staff_hospital(request.user)
    if hospital is None:
        messages.error(request, "Your staff account is not linked to a hospital.")
        return redirect("dashboard")
    pending = (
        TTITestRecord.objects.filter(donation__hospital=hospital)
        .exclude(donation__bags__status__in=[BagStatus.AVAILABLE, BagStatus.DISCARDED])
        .select_related("donation", "donation__donor")
        .order_by("donation__donated_at")
    )
    # Resolve each donation's bag (a donation has one in practice; the reverse
    # relation is a manager, so a plain join cannot fetch it).
    rows = [
        (record, BloodBag.objects.filter(donation=record.donation).first())
        for record in pending
    ]
    return render(request, "inventory/tti_screening_list.html", {"rows": rows, "hospital": hospital})


@role_required("HOSPITAL_STAFF", "HOSPITAL")
@require_approved_hospital
def tti_screening_run(request, donation_id):
    """Enter the lab's TTI results for one donation; the service gates the bag."""
    hospital = staff_hospital(request.user)
    if hospital is None:
        messages.error(request, "Your staff account is not linked to a hospital.")
        return redirect("dashboard")
    donation = hospital.donations.select_related("donor").filter(pk=donation_id).first()
    if donation is None:
        raise Http404("No such donation at your hospital.")
    bag = BloodBag.objects.filter(donation=donation).first()
    record, _ = TTITestRecord.objects.get_or_create(donation=donation)
    decided = record.is_complete

    if decided:
        messages.info(request, "TTI screening for this donation has already been completed.")
        return redirect("tti_screening_list")

    form = TTIResultsForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.record_tti_results(request.user, donation, **form.cleaned_data)
        except ValueError as exc:
            messages.error(request, f"TTI screening blocked: {exc}")
        else:
            if bag is not None:
                bag.refresh_from_db()
            if bag is not None and bag.status == BagStatus.DISCARDED:
                messages.warning(
                    request,
                    f"Reactive TTI result recorded for donation #{donation.pk}; bag #{bag.pk} was "
                    "discarded. The donor has been notified to seek counselling and confirmatory testing.",
                )
            elif bag is not None:
                messages.success(
                    request,
                    f"All markers non-reactive: bag #{bag.pk} ({bag.blood_group}) is now AVAILABLE "
                    "and has entered the stock pool.",
                )
            else:
                messages.success(request, "TTI results recorded.")
            return redirect("tti_screening_list")
    return render(
        request,
        "inventory/tti_screening_run.html",
        {"donation": donation, "bag": bag, "form": form},
    )
