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
