from django.contrib import admin

from audit.services import log_action

from .models import OrganDonationRequest


@admin.register(OrganDonationRequest)
class OrganDonationRequestAdmin(admin.ModelAdmin):
    list_display = ["donor", "hospital", "organ_type", "status", "created_at"]
    list_filter = ["status", "organ_type", "hospital"]
    search_fields = ["donor__full_name"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        log_action(
            request.user,
            "ORGAN_REQUEST_CREATED" if not change else "ORGAN_REQUEST_UPDATED",
            obj,
            {"organ": obj.organ_type, "status": obj.status},
        )

    def delete_model(self, request, obj):
        log_action(request.user, "ORGAN_REQUEST_DELETED", obj, {"organ": obj.organ_type})
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        # The built-in "Delete selected" action calls delete_queryset, not
        # delete_model, so audit each row here or bulk deletes go unrecorded.
        for obj in queryset:
            log_action(request.user, "ORGAN_REQUEST_DELETED", obj, {"organ": obj.organ_type})
        super().delete_queryset(request, queryset)
