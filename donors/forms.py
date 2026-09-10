import datetime

from django import forms
from django.conf import settings
from django.utils import timezone

from .models import Donor


class DonorProfileForm(forms.ModelForm):
    class Meta:
        model = Donor
        fields = [
            "full_name", "date_of_birth", "sex", "blood_group", "weight_kg",
            "city", "contact_phone", "medical_history", "id_document",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "medical_history": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {"id_document": "Government ID document (image or PDF)"}
        help_texts = {
            "weight_kg": f"Minimum {settings.DONOR_MIN_WEIGHT_KG} kg required to donate.",
        }


class RejectDonorForm(forms.Form):
    rejection_reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), label="Reason for rejection")


class ScreeningForm(forms.Form):
    hemoglobin_g_dl = forms.DecimalField(max_digits=4, decimal_places=1, label="Hemoglobin (g/dL)")
    systolic_bp = forms.IntegerField(label="Systolic BP (mmHg)")
    diastolic_bp = forms.IntegerField(label="Diastolic BP (mmHg)")


class AppointmentForm(forms.Form):
    """The donor picks a day and leaves an optional note for hospital staff."""

    requested_for = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="I would like to come in on",
    )
    donor_note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Note for the hospital (optional)",
        help_text="Anything staff should know before you arrive.",
    )

    def clean_requested_for(self):
        day = self.cleaned_data["requested_for"]
        today = timezone.localdate()
        if day < today:
            raise forms.ValidationError("Pick today or a future date.")
        if day > today + datetime.timedelta(days=60):
            raise forms.ValidationError("Appointments can be booked at most 60 days ahead.")
        return day
