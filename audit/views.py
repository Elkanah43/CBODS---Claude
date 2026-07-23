from django.db.models import Count
from django.shortcuts import render

from accounts.decorators import role_required
from donors.models import Donor
from inventory.models import BloodBag, Donation
from requests_app.models import BloodRequest

from .models import AuditLog


@role_required("ADMIN")
def admin_dashboard(request):
    donors_by_status = dict(
        Donor.objects.values_list("registration_status").annotate(n=Count("id")).values_list("registration_status", "n")
    )
    bags_by_group = dict(
        BloodBag.objects.filter(status="AVAILABLE")
        .values_list("blood_group")
        .annotate(n=Count("id"))
        .values_list("blood_group", "n")
    )
    bags_by_hospital = dict(
        BloodBag.objects.filter(status="AVAILABLE")
        .values_list("hospital__name")
        .annotate(n=Count("id"))
        .values_list("hospital__name", "n")
    )
    requests_by_status = dict(
        BloodRequest.objects.values_list("status").annotate(n=Count("id")).values_list("status", "n")
    )
    requests_by_urgency = dict(
        BloodRequest.objects.values_list("urgency").annotate(n=Count("id")).values_list("urgency", "n")
    )
    recent_donations = Donation.objects.select_related("donor", "hospital")[:10]

    charts = {
        "donors_by_status": donors_by_status,
        "bags_by_group": bags_by_group,
        "bags_by_hospital": bags_by_hospital,
        "requests_by_status": requests_by_status,
        "requests_by_urgency": requests_by_urgency,
    }
    return render(
        request,
        "audit/admin_dashboard.html",
        {
            "charts": charts,
            "recent_donations": recent_donations,
            "totals": {
                "donors": Donor.objects.count(),
                "available_bags": BloodBag.objects.filter(status="AVAILABLE").count(),
                "pending_requests": BloodRequest.objects.filter(status="PENDING").count(),
                "donations": Donation.objects.count(),
            },
        },
    )


@role_required("ADMIN")
def audit_log(request):
    logs = AuditLog.objects.select_related("actor")
    action = request.GET.get("action", "")
    entity = request.GET.get("entity", "")
    if action:
        logs = logs.filter(action__icontains=action)
    if entity:
        logs = logs.filter(entity_type__iexact=entity)
    entity_types = AuditLog.objects.values_list("entity_type", flat=True).distinct().order_by("entity_type")
    return render(
        request,
        "audit/audit_log.html",
        {"logs": logs[:200], "entity_types": entity_types, "sel": {"action": action, "entity": entity}},
    )
