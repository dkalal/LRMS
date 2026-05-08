from django import forms

from .models import Broker


class BrokerForm(forms.ModelForm):
    class Meta:
        model = Broker
        fields = ("full_name", "phone_number", "location", "notes", "status")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["full_name"].widget.attrs["placeholder"] = "e.g. Juma Broker"
        self.fields["phone_number"].widget.attrs["placeholder"] = "e.g. 255700123456"
        self.fields["location"].required = False
        self.fields["location"].widget.attrs["placeholder"] = "Optional office or area"
        self.fields["notes"].required = False
        self.fields["notes"].widget.attrs["rows"] = 4
