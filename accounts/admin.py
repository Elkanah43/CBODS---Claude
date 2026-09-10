from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


def send_reset_email(modeladmin, request, queryset):
    """Send a password-reset link to each selected user by email.

    Uses Django's own reset machinery, so the link is a signed, expiring 토큰
    routed through the same ``PasswordResetView`` the self-service flow uses.
    Users without an email address are skipped with an admin message.
    """
    from django.contrib.auth.forms import PasswordResetForm

    users_with_email = [u for u in queryset if u.email]
    users_without = queryset.count() - len(users_with_email)

    if not users_with_email:
        modeladmin.message_user(
            request,
            "No selected users have an email address — nothing was sent.",
            level="warning",
        )
        return

    form = PasswordResetForm()
    form.cleaned_data = {"email": ""}  # satisfy the form's contract; save() ignores it

    sent = 0
    for user in users_with_email:
        form.save(
            request=request,
            email_template_name="accounts/password_reset_email.txt",
            subject_template_name="accounts/password_reset_subject.txt",
            use_https=True,
        )
        sent += 1

    msg = f"Reset link sent to {sent} user{'s' if sent != 1 else ''}."
    if users_without:
        msg += f" {users_without} user{'s' if users_without != 1 else ''} skipped (no email)."
    modeladmin.message_user(request, msg)


send_reset_email.short_description = "Send password-reset link to selected users"


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ["username", "email", "role", "phone", "is_active"]
    list_filter = ["role", "is_active"]
    actions = [send_reset_email]
    fieldsets = UserAdmin.fieldsets + (("CBODS", {"fields": ("role", "phone")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("CBODS", {"fields": ("role", "phone")}),)
