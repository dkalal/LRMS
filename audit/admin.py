from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "tenant", "actor", "action", "message")
    list_filter = ("tenant", "action")
    search_fields = ("message", "actor__username")
