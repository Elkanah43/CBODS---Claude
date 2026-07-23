from django import forms

from hospitals.models import Hospital

from .models import OrganType


class OrganRequestForm(forms.Form):
    organ_type = forms.ChoiceField(choices=OrganType.choices)
    hospital = forms.ModelChoiceField(queryset=Hospital.objects.none(), label="Hospital to review the request")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["hospital"].queryset = Hospital.objects.visible_to(user)
