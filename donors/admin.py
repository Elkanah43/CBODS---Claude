from django.contrib import admin

from audit.services import log_action

from .models import Deferral, Donor, ScreeningRecord


@admin.register(Donor)
class DonorAdmin(admin.ModelAdmin):
    list_display = ["full_name", "blood_group", "city", "registration_status", "is_available"]
    list_filter = ["registration_status", "blood_group", "city", "is_available"]
    search_fields = ["full_name", "city"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            log_action(request.user, "DONOR_CREATED", obj, {"full_name": obj.full_name})
            return
        if form.initial.get("registration_status") == obj.registration_status:
            log_action(request.user, "DONOR_UPDATED", obj, {"full_name": obj.full_name})
        elif obj.registration_status == "APPROVED":
            # Same action names as the in-app approval queue, so approving a
            # donor here shows up identically in the audit log and dashboard.
            log_action(request.user, "DONOR_APPROVED", obj, {"full_name": obj.full_name})
        elif obj.registration_status == "REJECTED":
            log_action(request.user, "DONOR_REJECTED", obj, {"reason": obj.rejection_reason})
        else:
            log_action(
                request.user, "DONOR_STATUS_CHANGED", obj,
                {"from": form.initial.get("registration_status"), "to": obj.registration_status},
            )

    def delete_model(self, request, obj):
        log_action(request.user, "DONOR_DELETED", obj, {"full_name": obj.full_name})
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        # The built-in "Delete selected" action calls delete_queryset, not
        # delete_model, so audit each row here or bulk deletes go unrecorded.
        for obj in queryset:
            log_action(request.user, "DONOR_DELETED", obj, {"full_name": obj.full_name})
        super().delete_queryset(request, queryset)


class DeferralInline(admin.TabularInline):
    model = Deferral
    extra = 0
    readonly_fields = ["reason", "is_permanent", "start_date", "end_date", "auto_expire", "notes", "created_by", "created_at", "lifted_by", "lifted_at", "lifted_reason"]
    fields = ["reason", "is_permanent", "start_date", "end_date", "auto_expire", "notes", "created_by", "created_at", "lifted_by", "lifted_at", "lifted_reason"]
    can_delete = False
    ordering = ["-created_at"]


# Add DeferralInline to DonorAdmin
DonorAdmin.inlines = [DeferralInline]


@admin.register(Deferral)
class DeferralAdmin(admin.ModelAdmin):
    list_display = ["donor", "reason", "is_permanent", "start_date", "end_date", "lifted_at"]
    list_filter = ["reason", "is_permanent", "lifted_at"]
    search_fields = ["donor__full_name", "notes"]
    readonly_fields = ["donor", "reason", "is_permanent", "start_date", "end_date", "auto_expire", "notes", "created_by", "created_at", "lifted_by", "lifted_at", "lifted_reason"]
    actions = ["lift_expired_deferrals"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def lift_expired_deferrals(self, request, queryset):
        """Bulk action to manually lift expired temporary deferrals."""
        from donors.services import get_active_deferrals
        from django.utils import timezone
        today = timezone.localdate()
        count = 0
        for d in queryset.filter(is_permanent=False, end_date__lt=today, lifted_at__isnull=True):
            d.lifted_by = request.user
            d.lifted_at = timezone.now()
            d.lifted_reason = "Manually lifted by admin"
            d.save(update_fields=["lifted_by", "lifted_at", "lifted_reason"])
            if not get_active_deferrals(d.donor).exists():
                d.donor.is_available = True
                d.donor.save(update_fields=["is_available"])
            count += 1
        self.message_user(request, f"Lifted {count} expired deferral(s).")
    lift_expired_deferrals.short_description = "Lift selected expired deferrals"


@admin.register(ScreeningRecord)
class ScreeningRecordAdmin(admin.ModelAdmin):
    """Eligibility records are written by the hospital screening flow only, so
    the admin view is read-only, like the audit log."""
    list_display = ["donor", "outcome", "hemoglobin_g_dl", "systolic_bp", "diastolic_bp", "created_at"]
    list_filter = ["outcome"]
    search_fields = ["donor__full_name"]
    readonly_fields = ["donor", "stage1_passed", "hemoglobin_g_dl", "systolic_bp", "diastolic_bp", "outcome", "failed_reasons", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
