from django.contrib import admin

from audit.services import log_action

from .models import OrganDonationRequest, RecipientHLATyping


@admin.register(OrganDonationRequest)
class OrganDonationRequestAdmin(admin.ModelAdmin):
    list_display = ["donor", "hospital", "organ_type", "status", "hla_mismatch_count", "crossmatch_result", "created_at"]
    list_filter = ["status", "organ_type", "hospital", "crossmatch_result"]
    search_fields = ["donor__full_name"]
    readonly_fields = ["hla_mismatch_count", "crossmatch_result"]
    actions = ["calculate_hla_match"]

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

    def calculate_hla_match(self, request, queryset):
        """Calculate HLA mismatch for selected organ requests."""
        from organs.services import calculate_hla_match
        count = 0
        for obj in queryset:
            if hasattr(obj.donor, "hla_typing") and obj.recipient_hla:
                calculate_hla_match(obj.donor, obj)
                count += 1
        self.message_user(request, f"Calculated HLA match for {count} request(s).")
    calculate_hla_match.short_description = "Calculate HLA match for selected requests"


@admin.register(RecipientHLATyping)
class RecipientHLATypingAdmin(admin.ModelAdmin):
    list_display = ["patient", "pra_percent", "typed_at"]
    search_fields = ["patient__username", "patient__first_name", "patient__last_name"]
    readonly_fields = ["patient", "alleles", "unacceptable_antigens", "pra_percent", "typed_by", "typed_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
