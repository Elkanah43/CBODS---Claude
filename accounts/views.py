from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import RegisterForm


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Welcome to CBODS! Your account has been created.")
            return redirect("dashboard")
    else:
        form = RegisterForm()
    return render(request, "accounts/register.html", {"form": form})


@login_required
def dashboard(request):
    context = {}
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
