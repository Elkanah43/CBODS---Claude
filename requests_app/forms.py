from django import forms

from cbods.constants import BloodGroup
from donors.models import Donor, RegistrationStatus

from .models import Urgency


class BloodRequestForm(forms.Form):
    """Blood group choices are limited to what the chosen hospital has AVAILABLE."""

    blood_group = forms.ChoiceField(choices=[])
    units_requested = forms.IntegerField(min_value=1, max_value=10, initial=1)
    urgency = forms.ChoiceField(choices=Urgency.choices)

    def __init__(self, *args, available_groups=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["blood_group"].choices = [(g, g) for g in (available_groups or [])]


class RejectRequestForm(forms.Form):
    rejection_reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), label="Reason for rejection")


class CompatibilityCheckForm(forms.Form):
    recipient_group = forms.ChoiceField(choices=BloodGroup.choices, label="Recipient blood group")
    donor = forms.ModelChoiceField(
        queryset=Donor.objects.filter(registration_status=RegistrationStatus.APPROVED, is_available=True),
        label="Candidate donor",
    )
    urgency = forms.ChoiceField(choices=Urgency.choices, initial=Urgency.ROUTINE)
