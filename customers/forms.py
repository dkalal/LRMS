from django import forms

from brokers.models import Broker

from .models import Customer


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = (
            "full_name",
            "phone_number",
            "broker",
            "notes",
            "status",
        )

    def __init__(self, *args, **kwargs):
        tenant = kwargs.pop("tenant", None)
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["broker"].queryset = Broker.objects.filter(tenant=tenant).order_by("full_name")


class QuickBrokerForm(forms.ModelForm):
    class Meta:
        model = Broker
        fields = ("full_name", "phone_number", "location")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["full_name"].label = "Broker name"
        self.fields["phone_number"].label = "Broker phone"
        self.fields["location"].required = False
        for field_name in ("full_name", "phone_number"):
            self.fields[field_name].widget.attrs["data-required-when-visible"] = "true"
            self.fields[field_name].widget.attrs.pop("required", None)
