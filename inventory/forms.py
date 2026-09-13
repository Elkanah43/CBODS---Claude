from django import forms

from donors.models import Donor, RegistrationStatus

from .models import TTIResult


class RecordDonationForm(forms.Form):
    donor = forms.ModelChoiceField(
        queryset=Donor.objects.filter(registration_status=RegistrationStatus.APPROVED),
        label="Approved donor",
    )
    volume_ml = forms.IntegerField(min_value=200, max_value=550, initial=450, label="Volume (ml)")


class TTIResultsForm(forms.Form):
    """Staff entry of laboratory TTI screening results for one donation.

    Every marker must be filled before the form is valid: a partially entered
    screening can neither release a unit into the pool nor discard it, so the
    gate stays closed until the laboratory has decided all four.
    """

    hiv = forms.TypedChoiceField(
        label="HIV", choices=TTIResult.choices, coerce=str,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    hepatitis_b = forms.TypedChoiceField(
        label="Hepatitis B", choices=TTIResult.choices, coerce=str,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    hepatitis_c = forms.TypedChoiceField(
        label="Hepatitis C", choices=TTIResult.choices, coerce=str,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    syphilis = forms.TypedChoiceField(
        label="Syphilis", choices=TTIResult.choices, coerce=str,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
