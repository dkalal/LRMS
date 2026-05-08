from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .forms import UserForm
from .models import User, UserVehiclePermission


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    add_form = UserForm
    list_display = ("username", "email", "role", "tenant", "is_active", "is_staff")
    list_filter = ("role", "tenant", "is_active")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Tenant Access", {"fields": ("tenant", "role")}),
    )


@admin.register(UserVehiclePermission)
class UserVehiclePermissionAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "vehicle_category", "created_at")
    list_filter = ("vehicle_category", "tenant")
    search_fields = ("user__username",)
