from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from accounts.models import Role, User
from cbods.forms import apply_ghana_phone_attrs
from cbods.validators import (
    normalize_ghana_phone_number,
    validate_email_address,
    validate_ghana_phone_number,
)

from .models import Hospital, HospitalApprovalStatus, StaffProfile


class HospitalRegisterForm(UserCreationForm):
    """Self-service hospital signup.

    Creates the hospital's own account (role=HOSPITAL) plus the Hospital record
    and the StaffProfile that links the two, mirroring the profile-creation step
    a donor registration does. The hospital starts PENDING admin approval, so a
    rejected application can be corrected and resubmitted without losing the
    account or duplicating the Hospital row.
    """

    email = forms.EmailField(required=True, validators=[validate_email_address])
    phone = forms.CharField(
        max_length=13,
        validators=[validate_ghana_phone_number],
        error_messages={"required": "Phone number is required."},
        help_text="Enter the 9 digits after +233, e.g. 241234567.",
    )

    hospital_name = forms.CharField(max_length=200, label="Hospital name")
    city = forms.CharField(max_length=100)
    address = forms.CharField(max_length=255)
    hospital_phone = forms.CharField(
        max_length=13,
        label="Hospital phone",
        validators=[validate_ghana_phone_number],
        error_messages={"required": "Phone number is required."},
        help_text="Enter the 9 digits after +233, e.g. 241234567.",
    )
    services_offered = forms.CharField(
        widget=forms.Textarea, required=False,
        help_text="e.g. Blood bank, transfusion, organ intake",
    )
    organ_requirements = forms.CharField(
        widget=forms.Textarea, required=False,
        help_text="e.g. Kidney, liver, cornea",
    )

    class Meta:
        model = User
        fields = ["username", "email", "phone", "password1", "password2"]

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
        apply_ghana_phone_attrs(self, "phone", "hospital_phone")

    def clean_phone(self):
        phone = self.cleaned_data.get("phone")
        if not phone:
            return phone
        return normalize_ghana_phone_number(phone)

    def clean_hospital_phone(self):
        phone = self.cleaned_data.get("hospital_phone")
        if not phone:
            return phone
        return normalize_ghana_phone_number(phone)

    def clean_hospital_name(self):
        name = self.cleaned_data["hospital_name"].strip()
        conflict = Hospital.objects.filter(name__iexact=name).exclude(
            approval_status=HospitalApprovalStatus.REJECTED
        )
        if conflict.exists():
            raise ValidationError("A hospital with this name is already registered.")
        return name

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = Role.HOSPITAL
        if commit:
            user.save()

        name = self.cleaned_data["hospital_name"]
        hospital = (
            Hospital.objects.filter(
                name__iexact=name, approval_status=HospitalApprovalStatus.REJECTED
            ).first()
        )
        if hospital is None:
            hospital = Hospital(name=name)
        hospital.city = self.cleaned_data["city"]
        hospital.address = self.cleaned_data["address"]
        hospital.phone = self.cleaned_data["hospital_phone"]
        hospital.services_offered = self.cleaned_data["services_offered"]
        hospital.organ_requirements = self.cleaned_data["organ_requirements"]
        hospital.approval_status = HospitalApprovalStatus.PENDING
        hospital.rejection_reason = None
        hospital.save()

        StaffProfile.objects.get_or_create(user=user, defaults={"hospital": hospital})
        return user


class HospitalProfileForm(forms.ModelForm):
    class Meta:
        model = Hospital
        fields = ["name", "city", "address", "phone", "services_offered", "organ_requirements"]
        labels = {"phone": "Hospital phone"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_ghana_phone_attrs(self, "phone")

    def clean_phone(self):
        """Normalise so the form's cleaned value matches what the model stores
        (otherwise unchanged posts look changed, and audits misfire)."""
        phone = self.cleaned_data.get("phone")
        if not phone:
            return phone
        return normalize_ghana_phone_number(phone)


class HospitalAdminEditForm(forms.ModelForm):
    """Admin fixes a registration's details from the review page.

    Unlike the hospital's own profile form (which must allow an exact-name
    resubmit after rejection), an admin rename must not collide with another
    hospital's name.
    """

    class Meta:
        model = Hospital
        fields = ["name", "city", "address", "phone", "services_offered", "organ_requirements"]
        labels = {"phone": "Hospital phone"}
        widgets = {
            "services_offered": forms.Textarea(attrs={"rows": 2}),
            "organ_requirements": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        apply_ghana_phone_attrs(self, "phone")

    def clean_phone(self):
        """Normalise so an unchanged phone is not reported as edited."""
        phone = self.cleaned_data.get("phone")
        if not phone:
            return phone
        return normalize_ghana_phone_number(phone)

    @property
    def changed_data(self):
        """Re-enter the number under its canonical spelling.

        Django compares the raw form value against the stored initial, so
        posting "240222444" when the record holds "+233240222444" looks like
        an edit even though the numbers are identical. Normalising the
        comparison keeps unchanged resubmits out of the audit log.
        """
        changed = list(super().changed_data)
        if "phone" in changed and self.initial.get("phone") == self.cleaned_data.get("phone"):
            changed.remove("phone")
        return changed

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise ValidationError("Hospital name cannot be blank.")
        conflict = Hospital.objects.filter(name__iexact=name).exclude(pk=self.instance.pk)
        if conflict.exists():
            raise ValidationError("A hospital with this name is already registered.")
        return name


class HospitalStaffAddForm(UserCreationForm):
    """The hospital's own account provisions staff accounts for its hospital.

    A freshly created staff member belongs to the hospital immediately and can
    sign in — no administrator in the loop for routine staffing.
    """

    email = forms.EmailField(required=True, validators=[validate_email_address])
    phone = forms.CharField(
        max_length=13,
        validators=[validate_ghana_phone_number],
        error_messages={"required": "Phone number is required."},
        help_text="Enter the 9 digits after +233, e.g. 241234567.",
    )

    class Meta:
        model = User
        fields = ["username", "email", "phone", "password1", "password2"]

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
        phone = self.cleaned_data.get("phone")
        if not phone:
            return phone
        return normalize_ghana_phone_number(phone)
