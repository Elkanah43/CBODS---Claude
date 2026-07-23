from django import forms

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


class RejectDonorForm(forms.Form):
    rejection_reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), label="Reason for rejection")


class ScreeningForm(forms.Form):
    hemoglobin_g_dl = forms.DecimalField(max_digits=4, decimal_places=1, label="Hemoglobin (g/dL)")
    systolic_bp = forms.IntegerField(label="Systolic BP (mmHg)")
    diastolic_bp = forms.IntegerField(label="Diastolic BP (mmHg)")
