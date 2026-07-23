from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render

from accounts.decorators import role_required
from hospitals.utils import staff_hospital

from . import services
from .forms import RecordDonationForm
from .models import BagStatus


@role_required("HOSPITAL_STAFF")
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


@role_required("HOSPITAL_STAFF")
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
                f"bag #{bag.pk} ({bag.blood_group}) added as AVAILABLE, expires {bag.expiry_date}.",
            )
            return redirect("stock_dashboard")
    return render(request, "inventory/record_donation.html", {"form": form, "hospital": hospital})
