from django.contrib import admin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone_number", "broker", "tenant", "status")
    list_filter = ("tenant", "status")
    search_fields = ("full_name", "phone_number", "alternative_phone")
