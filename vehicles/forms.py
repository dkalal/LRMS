from django import forms

from customers.models import Customer
from accounts.models import VehicleCategoryChoices

from .models import Vehicle


class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = ("customer", "plate_number", "vehicle_category", "notes", "status")

    def __init__(self, *args, **kwargs):
        tenant = kwargs.pop("tenant", None)
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["customer"].queryset = Customer.objects.filter(tenant=tenant).order_by("full_name")
        choices = [
            choice
            for choice in VehicleCategoryChoices.choices
            if choice[0] != VehicleCategoryChoices.ALL
        ]
        if user and not user.is_superuser and not user.has_all_vehicle_access() and user.role != "admin":
            allowed = set(user.assigned_vehicle_categories())
            choices = [choice for choice in choices if choice[0] in allowed]
        self.fields["vehicle_category"].choices = choices
        self.fields["plate_number"].widget.attrs["placeholder"] = "e.g. T123 ABC"
        self.fields["notes"].required = False
        self.fields["notes"].widget.attrs["rows"] = 4
