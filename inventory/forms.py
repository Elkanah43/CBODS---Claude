from django import forms

from donors.models import Donor, RegistrationStatus


class RecordDonationForm(forms.Form):
    donor = forms.ModelChoiceField(
        queryset=Donor.objects.filter(registration_status=RegistrationStatus.APPROVED),
        label="Approved donor",
    )
    volume_ml = forms.IntegerField(min_value=200, max_value=550, initial=450, label="Volume (ml)")
