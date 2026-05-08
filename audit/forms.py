from django import forms


class ReasonForm(forms.Form):
    reason = forms.CharField(
        label="Reason",
        min_length=5,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Example: Created by mistake, duplicate record, wrong plate number...",
            }
        ),
    )
