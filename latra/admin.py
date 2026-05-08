from django.contrib import admin

from .models import LatraRecord


@admin.register(LatraRecord)
class LatraRecordAdmin(admin.ModelAdmin):
    list_display = ("vehicle", "customer", "service_name", "issue_date", "expiry_date", "status", "tenant")
    list_filter = ("tenant", "status")
    search_fields = ("vehicle__plate_number", "customer__full_name", "service_name")
