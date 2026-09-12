from django.contrib.auth import forms as auth_forms
from django.contrib.auth import views as auth_views
from django.contrib.auth.tokens import default_token_generator
from django.urls import path

from . import views


class HttpsPasswordResetForm(auth_forms.PasswordResetForm):
    """Password reset form whose links match how the app is actually served.

    The form used to force use_https=True unconditionally, so a copy of the
    app running plain HTTP (every local/dev run) emailed
    ``https://127.0.0.1:8000/...`` links that the browser rejected with
    ERR_SSL_PROTOCOL_ERROR — the server never speaks TLS. Now the link's
    scheme follows the request that produced it: https when the app itself
    is behind TLS (protecting the token end to end), http when not.
    """
    def save(
        self,
        domain_override=None,
        subject_template_name="registration/password_reset_subject.txt",
        email_template_name="registration/password_reset_email.html",
        use_https=False,
        token_generator=default_token_generator,
        from_email=None,
        request=None,
        html_email_template_name=None,
        extra_email_context=None,
    ):
        return super().save(
            domain_override=domain_override,
            subject_template_name=subject_template_name,
            email_template_name=email_template_name,
            use_https=request.is_secure() if request is not None else use_https,
            token_generator=token_generator,
            from_email=from_email,
            request=request,
            html_email_template_name=html_email_template_name,
            extra_email_context=extra_email_context,
        )


urlpatterns = [
    path("register/", views.register, name="register"),
    path("password-rules/", views.password_rules_check, name="password_rules"),
    path("login/", auth_views.LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),

    # Django's own reset flow: a signed, expiring token in a link. Rolling our
    # own numeric code would be more code doing the same job with none of the
    # scrutiny this has had. The url names are Django's defaults because the
    # views redirect to each other by name.
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            form_class=HttpsPasswordResetForm,
            template_name="accounts/password_reset_form.html",
            email_template_name="accounts/password_reset_email.txt",
            subject_template_name="accounts/password_reset_subject.txt",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/sent/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html"
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
]
