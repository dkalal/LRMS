from django.db import models

from tenants.models import TrackedTenantModel
from tenants.utils import normalize_phone_number


class Broker(TrackedTenantModel):
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=30)
    phone_normalized = models.CharField(max_length=30, blank=True, editable=False)
    location = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("full_name",)
        indexes = [
            models.Index(fields=("tenant", "status"), name="broker_tenant_status_idx"),
            models.Index(fields=("tenant", "full_name"), name="broker_tenant_name_idx"),
            models.Index(fields=("tenant", "phone_number"), name="broker_tenant_phone_idx"),
            models.Index(fields=("tenant", "phone_normalized"), name="broker_tenant_phonekey_idx"),
        ]

    def save(self, *args, **kwargs):
        self.phone_normalized = normalize_phone_number(self.phone_number)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.full_name
