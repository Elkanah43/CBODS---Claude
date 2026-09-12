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
<<<<<<< HEAD
    email = forms.EmailField(
        required=True,
        validators=[validate_email_tld],
        help_text="Use a real address ending in a recognized top-level domain such as .com, .gh or .org.",
    )
    phone = forms.CharField(max_length=20, required=False)
=======
    email = forms.EmailField(required=True, validators=[validate_email_address])
    phone = forms.CharField(
        max_length=13,
        validators=[validate_ghana_phone_number],
        error_messages={"required": "Phone number is required."},
        help_text="Enter the 9 digits after +233, e.g. 241234567.",
    )
>>>>>>> 105dbc9af6477ee4cbfe5709c55e1d570dffedc3

    class Meta:
        model = User
        fields = ["username", "email", "phone", "role", "password1", "password2"]

    # Without these, password managers neither offer to generate a password nor
    # save the one that was used — which undermines the strength rules the
    # register page now shows live.
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
