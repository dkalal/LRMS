from django.conf import settings
from django.db import models

from tenants.models import TenantScopedModel


class ReminderLog(TenantScopedModel):
    latra_record = models.ForeignKey("latra.LatraRecord", on_delete=models.CASCADE, related_name="reminder_logs")
    contact_name = models.CharField(max_length=255, blank=True)
    contact_type = models.CharField(max_length=20, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    message = models.TextField(blank=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"Reminder for {self.latra_record}"
