from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Role, User

# Self-service signup is limited to donor/patient; staff and admin
# accounts are provisioned by an administrator.
SIGNUP_ROLES = [
    (Role.DONOR, "Donor"),
    (Role.PATIENT, "Patient"),
]


class RegisterForm(UserCreationForm):
    role = forms.ChoiceField(choices=SIGNUP_ROLES)
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=20, required=False)

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
