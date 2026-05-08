from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User, UserVehiclePermission, VehicleCategoryChoices


class UserForm(UserCreationForm):
    vehicle_categories = forms.MultipleChoiceField(
        choices=VehicleCategoryChoices.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email", "role", "is_active")


class UserVehiclePermissionForm(forms.ModelForm):
    class Meta:
        model = UserVehiclePermission
        fields = ("user", "vehicle_category")
