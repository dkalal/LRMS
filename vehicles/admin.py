from django.contrib import admin

from .models import Vehicle


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("plate_number", "customer", "vehicle_category", "tenant", "status")
    list_filter = ("tenant", "vehicle_category", "status")
    search_fields = ("plate_number", "customer__full_name")
