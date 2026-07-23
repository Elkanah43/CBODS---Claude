from django.contrib import admin

from .models import BloodRequest


@admin.register(BloodRequest)
class BloodRequestAdmin(admin.ModelAdmin):
    list_display = ["patient", "hospital", "blood_group", "units_requested", "urgency", "status", "created_at"]
    list_filter = ["status", "urgency", "blood_group", "hospital"]
