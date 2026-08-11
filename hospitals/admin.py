from django.contrib import admin

from audit.services import log_action

from .models import Hospital, StaffProfile


@admin.register(Hospital)
class HospitalAdmin(admin.ModelAdmin):
    list_display = ["name", "city", "phone", "approval_status", "is_hidden"]
    list_filter = ["city", "approval_status", "is_hidden"]
    search_fields = ["name", "city"]

    def save_model(self, request, obj, form, change):
        hidden_changed = change and "is_hidden" in form.changed_data
        approval_changed = change and "approval_status" in form.changed_data
        super().save_model(request, obj, form, change)
        if hidden_changed:
            log_action(
                request.user,
                "HOSPITAL_HIDDEN" if obj.is_hidden else "HOSPITAL_UNHIDDEN",
                obj,
                {"name": obj.name},
            )
        if approval_changed:
            log_action(
                request.user,
                f"HOSPITAL_{obj.approval_status}",
                obj,
                {"name": obj.name},
            )


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "hospital"]
    list_filter = ["hospital"]
