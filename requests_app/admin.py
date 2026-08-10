from django.contrib import admin

from audit.services import log_action

from .models import BloodRequest


@admin.register(BloodRequest)
class BloodRequestAdmin(admin.ModelAdmin):
    list_display = ["patient", "hospital", "blood_group", "units_requested", "urgency", "status", "created_at"]
    list_filter = ["status", "urgency", "blood_group", "hospital"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        log_action(
            request.user,
            "REQUEST_CREATED" if not change else "REQUEST_UPDATED",
            obj,
            {"units": obj.units_requested, "blood_group": obj.blood_group, "status": obj.status},
        )

    def delete_model(self, request, obj):
        log_action(request.user, "REQUEST_DELETED", obj, {"units": obj.units_requested})
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        # The built-in "Delete selected" action calls delete_queryset, not
        # delete_model, so audit each row here or bulk deletes go unrecorded.
        for obj in queryset:
            log_action(request.user, "REQUEST_DELETED", obj, {"units": obj.units_requested})
        super().delete_queryset(request, queryset)
