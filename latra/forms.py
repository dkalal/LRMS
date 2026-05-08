from django import forms

from brokers.models import Broker
from customers.models import Customer
from vehicles.models import Vehicle

from .models import LatraRecord


class LatraRecordForm(forms.ModelForm):
    class Meta:
        model = LatraRecord
        fields = (
            "customer",
            "vehicle",
            "broker",
            "service_name",
            "issue_date",
            "expiry_date",
            "notes",
            "status",
        )
        widgets = {
            "customer": forms.HiddenInput,
            "vehicle": forms.HiddenInput,
            "broker": forms.HiddenInput,
            "issue_date": forms.DateInput(attrs={"type": "date"}),
            "expiry_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        tenant = kwargs.pop("tenant", None)
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["service_name"].widget.attrs["placeholder"] = "e.g. Route Permit, Road Service Licence"
        self.fields["notes"].required = False
        self.fields["notes"].widget.attrs["rows"] = 4
        if tenant is not None:
            self.fields["customer"].queryset = Customer.objects.filter(tenant=tenant).order_by("full_name")
            self.fields["broker"].queryset = Broker.objects.filter(tenant=tenant).order_by("full_name")
            vehicle_queryset = Vehicle.objects.filter(tenant=tenant).select_related("customer")
            if user and not (user.is_superuser or user.has_all_vehicle_access()):
                vehicle_queryset = vehicle_queryset.filter(
                    vehicle_category__in=user.assigned_vehicle_categories()
                )
            self.fields["vehicle"].queryset = vehicle_queryset.order_by("plate_number")


class WhatsAppMessageForm(forms.Form):
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}))
