import csv
from urllib.parse import urlencode

from django.db.models import Count
from django.http import Http404, HttpResponse
from django.shortcuts import render

from accounts.decorators import role_required
from cbods.pagination import paginate
from donors.models import Donor
from inventory.models import BloodBag, Donation
from requests_app.models import BloodRequest

from .models import AuditLog
from .services import system_totals


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
            "totals": system_totals(),
        },
    )


def _csv_response(filename, header, rows):
    """Stream a report as CSV using Django's own response — no extra dependency."""
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(header)
    writer.writerows(rows)
    return response


@role_required("ADMIN")
def export_csv(request, report):
    """Admin reports: donors, donations, requests, bags, audit."""
    if report == "donors":
        return _csv_response(
            "cbods_donors.csv",
            ["Name", "Blood group", "Age", "City", "Status", "Available", "Contact"],
            Donor.objects.select_related("user").values_list(
                "full_name", "blood_group", "date_of_birth", "city",
                "registration_status", "is_available", "contact_phone",
            ),
        )
    if report == "donations":
        return _csv_response(
            "cbods_donations.csv",
            ["Date", "Donor", "Blood group", "Hospital", "Volume (ml)"],
            Donation.objects.select_related("donor", "hospital").values_list(
                "donated_at", "donor__full_name", "donor__blood_group", "hospital__name", "volume_ml",
            ),
        )
    if report == "requests":
        return _csv_response(
            "cbods_blood_requests.csv",
            ["Created", "Patient", "Hospital", "Blood group", "Units", "Urgency", "Status"],
            BloodRequest.objects.select_related("patient", "hospital").values_list(
                "created_at", "patient__username", "hospital__name", "blood_group",
                "units_requested", "urgency", "status",
            ),
        )
    if report == "bags":
        return _csv_response(
            "cbods_blood_bags.csv",
            ["Hospital", "Blood group", "Collected", "Expires", "Status", "Volume (ml)"],
            BloodBag.objects.select_related("hospital").values_list(
                "hospital__name", "blood_group", "collected_date", "expiry_date", "status", "volume_ml",
            ),
        )
    if report == "audit":
        return _csv_response(
            "cbods_audit_log.csv",
            ["Time", "Actor", "Action", "Entity type", "Entity id", "Details"],
            AuditLog.objects.select_related("actor").values_list(
                "created_at", "actor__username", "action", "entity_type", "entity_id", "details",
            ),
        )
    raise Http404("Unknown report.")


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
    page = paginate(request, logs)
    return render(
        request,
        "audit/audit_log.html",
        {
            "logs": page.object_list,
            "page": page,
            "querystring": urlencode({k: v for k, v in [("action", action), ("entity", entity)] if v}),
            "entity_types": entity_types,
            "sel": {"action": action, "entity": entity},
        },
    )
