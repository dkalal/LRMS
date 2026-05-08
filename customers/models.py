from django.db import models

from brokers.models import Broker
from tenants.models import TrackedTenantModel
from tenants.utils import normalize_phone_number


class Customer(TrackedTenantModel):
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=30, blank=True)
    phone_normalized = models.CharField(max_length=30, blank=True, editable=False)
    alternative_phone = models.CharField(max_length=30, blank=True)
    broker = models.ForeignKey(Broker, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("full_name",)
        indexes = [
            models.Index(fields=("tenant", "status"), name="customer_tenant_status_idx"),
            models.Index(fields=("tenant", "full_name"), name="customer_tenant_name_idx"),
            models.Index(fields=("tenant", "phone_number"), name="customer_tenant_phone_idx"),
            models.Index(fields=("tenant", "phone_normalized"), name="customer_tenant_phonekey_idx"),
            models.Index(fields=("tenant", "broker"), name="customer_tenant_broker_idx"),
        ]

    def save(self, *args, **kwargs):
        self.phone_normalized = normalize_phone_number(self.phone_number)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.full_name
