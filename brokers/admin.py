from django.contrib import admin

from .models import Broker


@admin.register(Broker)
class BrokerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone_number", "tenant", "status", "created_at")
    list_filter = ("tenant", "status")
    search_fields = ("full_name", "phone_number")
