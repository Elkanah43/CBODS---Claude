from django import forms
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html

from audit.services import log_action
from notifications.services import notify

from . import services
from .models import Hospital, HospitalApprovalStatus, StaffProfile


class RejectHospitalForm(forms.Form):
    """Reason box for the intermediate step of the Reject action."""

    rejection_reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "class": "vLargeTextField"}),
        help_text="The hospital will see this reason and may correct its details and resubmit.",
    )


@admin.register(Hospital)
class HospitalAdmin(admin.ModelAdmin):
    list_display = ["name", "city", "phone", "approval_status", "is_hidden", "review_link"]
    list_filter = ["city", "approval_status", "is_hidden"]
    search_fields = ["name", "city"]
    actions = ["approve_hospitals", "reject_hospitals"]

    def get_urls(self):
        """The changelist's Review link jumps to the full review workflow."""
        urls = super().get_urls()
        custom = [
            path(
                "<path:object_id>/review/",
                self.admin_site.admin_view(self.review_view),
                name="hospitals_hospital_review",
            ),
        ]
        return custom + urls

    def review_view(self, request, object_id):
        hospital = self.get_object(request, object_id)
        if hospital is None:
            raise Http404("No hospital found.")
        return HttpResponseRedirect(reverse("hospital_review_detail", args=[hospital.pk]))

    @admin.display(description="Review")
    def review_link(self, obj):
        url = reverse("admin:hospitals_hospital_review", args=[obj.pk])
        return format_html('<a class="button" href="{}">Review &#8594;</a>', url)

    def _notify_account(self, hospital, subject, body):
        """Tell the hospital's own account (role HOSPITAL) about the decision."""
        account = services.hospital_account(hospital)
        if account:
            notify(account, subject, body)

    @admin.action(description="Approve selected hospitals (make live)")
    def approve_hospitals(self, request, queryset):
        count = 0
        for hospital in queryset:
            hospital.approval_status = HospitalApprovalStatus.APPROVED
            hospital.rejection_reason = None
            hospital.save()
            log_action(request.user, "HOSPITAL_APPROVED", hospital, {"name": hospital.name})
            self._notify_account(
                hospital,
                "Hospital registration approved",
                f"Your hospital {hospital.name} is now approved and live on CBODS. "
                "You can manage your profile, staff and blood bank operations.",
            )
            count += 1
        self.message_user(
            request, f"{count} hospital registration{'s' if count != 1 else ''} approved and live."
        )

    @admin.action(description="Reject selected hospitals (with reason)")
    def reject_hospitals(self, request, queryset):
        """Reject with a required reason, captured on an intermediate page."""
        if "apply" in request.POST:
            form = RejectHospitalForm(request.POST)
            if form.is_valid():
                reason = form.cleaned_data["rejection_reason"]
                count = 0
                for hospital in queryset:
                    hospital.approval_status = HospitalApprovalStatus.REJECTED
                    hospital.rejection_reason = reason
                    hospital.save()
                    log_action(
                        request.user, "HOSPITAL_REJECTED", hospital, {"reason": reason}
                    )
                    self._notify_account(
                        hospital,
                        "Hospital registration rejected",
                        f"Your hospital registration for {hospital.name} was rejected. "
                        f"Reason: {reason}. You can correct the details and resubmit.",
                    )
                    count += 1
                self.message_user(
                    request,
                    f"{count} hospital registration{'s' if count != 1 else ''} rejected.",
                    messages.WARNING,
                )
                return HttpResponseRedirect(request.get_full_path())
            # Invalid reason: fall through and re-render the prompt with errors.
        else:
            form = RejectHospitalForm()
        return render(
            request,
            "admin/reject_hospitals.html",
            {
                "hospitals": queryset,
                "form": form,
                "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            },
        )

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
            # Keep the change-form path in step with the actions: a decision
            # made here still reaches the hospital's account.
            if obj.approval_status == HospitalApprovalStatus.APPROVED:
                self._notify_account(
                    obj,
                    "Hospital registration approved",
                    f"Your hospital {obj.name} is now approved and live on CBODS. "
                    "You can manage your profile, staff and blood bank operations.",
                )
            elif obj.approval_status == HospitalApprovalStatus.REJECTED:
                reason = obj.rejection_reason or "No reason given."
                self._notify_account(
                    obj,
                    "Hospital registration rejected",
                    f"Your hospital registration for {obj.name} was rejected. "
                    f"Reason: {reason}. You can correct the details and resubmit.",
                )


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "hospital"]
    list_filter = ["hospital"]
