from django import forms
from django.contrib.auth.forms import UserCreationForm

from cbods.forms import apply_ghana_phone_attrs
from cbods.validators import (
    normalize_ghana_phone_number,
    validate_email_address,
    validate_ghana_phone_number,
)
from .models import Role, User
from .validators import validate_email_tld


# Self-service signup is limited to donor/patient; staff and admin
# accounts are provisioned by an administrator.
SIGNUP_ROLES = [
    (Role.DONOR, "Donor"),
    (Role.PATIENT, "Patient"),
]


class RegisterForm(UserCreationForm):
    role = forms.ChoiceField(choices=SIGNUP_ROLES)

    email = forms.EmailField(
        required=True,
        # Order matters: format and phone-number checks first, then the TLD
        # check — so a number typed into the email box is reported as one.
        validators=[validate_email_address, validate_email_tld],
        help_text=(
            "Use a real address ending in a recognized top-level domain "
            "such as .com, .gh or .org."
        ),
    )

    phone = forms.CharField(
        max_length=13,
        validators=[validate_ghana_phone_number],
        error_messages={"required": "Phone number is required."},
        help_text="Enter the 9 digits after +233, e.g. 241234567.",
    )

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "phone",
            "role",
            "password1",
            "password2",
        ]

    AUTOCOMPLETE = {
        "username": "username",
        "email": "email",
        "phone": "tel",
        "password1": "new-password",
        "password2": "new-password",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for name, token in self.AUTOCOMPLETE.items():
            if name in self.fields:
                self.fields[name].widget.attrs["autocomplete"] = token

        apply_ghana_phone_attrs(self, "phone")

    def clean_phone(self):
        """Store the number in the canonical +233XXXXXXXXX form."""
        phone = self.cleaned_data.get("phone")

        if not phone:
            return phone

        return normalize_ghana_phone_number(phone)

    def clean_email(self):
        """Refuse an email that an active account already uses."""
        email = self.cleaned_data.get("email")

        if email and User.objects.filter(
            email__iexact=email,
            is_active=True
        ).exists():
            raise forms.ValidationError(
                "An active account is already registered with this email "
                "address. Try signing in, or use “Forgot password” on the "
                "login page."
            )

        return email