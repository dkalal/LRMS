from django.contrib import admin

from .models import ReminderLog


@admin.register(ReminderLog)
class ReminderLogAdmin(admin.ModelAdmin):
    list_display = ("latra_record", "contact_name", "contact_type", "phone_number", "created_at")
    list_filter = ("tenant", "contact_type")
