from django.conf import settings
from django.db import models

from tenants.models import TenantScopedModel


class AuditLog(TenantScopedModel):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100)
    message = models.CharField(max_length=255)
    reason = models.TextField(blank=True)
    content_type = models.CharField(max_length=100, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("tenant", "-created_at"), name="audit_tenant_created_idx"),
            models.Index(fields=("tenant", "action"), name="audit_tenant_action_idx"),
            models.Index(fields=("tenant", "content_type", "object_id"), name="audit_tenant_object_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action} @ {self.created_at:%Y-%m-%d %H:%M}"
