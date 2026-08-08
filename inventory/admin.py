from django.contrib import admin

from audit.services import log_action

from .models import BloodBag, Donation


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = ["donated_at", "donor", "hospital", "volume_ml", "recorded_by"]
    list_filter = ["hospital", "donated_at"]
    search_fields = ["donor__full_name"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        log_action(
            request.user,
            "DONATION_CREATED" if not change else "DONATION_UPDATED",
            obj,
            {"volume_ml": obj.volume_ml},
        )

    def delete_model(self, request, obj):
        log_action(request.user, "DONATION_DELETED", obj, {"volume_ml": obj.volume_ml})
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        # The built-in "Delete selected" action calls delete_queryset, not
        # delete_model, so audit each row here or bulk deletes go unrecorded.
        for obj in queryset:
            log_action(request.user, "DONATION_DELETED", obj, {"volume_ml": obj.volume_ml})
        super().delete_queryset(request, queryset)


@admin.register(BloodBag)
class BloodBagAdmin(admin.ModelAdmin):
    list_display = ["pk", "hospital", "blood_group", "volume_ml", "expiry_date", "status"]
    list_filter = ["status", "blood_group", "hospital"]
    search_fields = ["hospital__name"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        log_action(
            request.user,
            "BAG_CREATED" if not change else "BAG_UPDATED",
            obj,
            {"status": obj.status, "blood_group": obj.blood_group},
        )

    def delete_model(self, request, obj):
        log_action(request.user, "BAG_DELETED", obj, {"status": obj.status})
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        # The built-in "Delete selected" action calls delete_queryset, not
        # delete_model, so audit each row here or bulk deletes go unrecorded.
        for obj in queryset:
            log_action(request.user, "BAG_DELETED", obj, {"status": obj.status})
        super().delete_queryset(request, queryset)
