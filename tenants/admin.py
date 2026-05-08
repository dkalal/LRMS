from django.contrib import admin

from .models import TenantCompany


@admin.register(TenantCompany)
class TenantCompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "contact_phone", "is_active", "created_at")
    search_fields = ("name", "slug", "contact_phone", "contact_email")
