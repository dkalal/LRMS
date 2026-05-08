from django.core.exceptions import ValidationError
from django.db import models

from brokers.models import Broker
from customers.models import Customer
from tenants.models import TrackedTenantModel
from vehicles.models import Vehicle


class LatraRecordStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    RENEWED = "renewed", "Renewed"
    CANCELLED = "cancelled", "Cancelled"


class LatraRecord(TrackedTenantModel):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="latra_records")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="latra_records")
    broker = models.ForeignKey(Broker, on_delete=models.SET_NULL, null=True, blank=True)
    service_name = models.CharField(max_length=255)
    issue_date = models.DateField()
    expiry_date = models.DateField()
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=LatraRecordStatus.choices,
        default=LatraRecordStatus.ACTIVE,
    )
    previous_record = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="renewal_children",
    )

    class Meta:
        ordering = ("expiry_date", "-created_at")
        indexes = [
            models.Index(fields=("tenant", "status"), name="latra_tenant_status_idx"),
            models.Index(fields=("tenant", "expiry_date"), name="latra_tenant_expiry_idx"),
            models.Index(fields=("tenant", "status", "expiry_date"), name="latra_tenant_stat_exp_idx"),
            models.Index(fields=("tenant", "vehicle"), name="latra_tenant_vehicle_idx"),
            models.Index(fields=("tenant", "customer"), name="latra_tenant_customer_idx"),
            models.Index(fields=("tenant", "broker"), name="latra_tenant_broker_idx"),
            models.Index(fields=("tenant", "service_name"), name="latra_tenant_service_idx"),
        ]

    def clean(self):
        if self.expiry_date and self.issue_date and self.expiry_date < self.issue_date:
            raise ValidationError({"expiry_date": "Expiry date must be on or after issue date."})
        if self.vehicle_id and self.customer_id and self.vehicle.customer_id != self.customer_id:
            raise ValidationError({"vehicle": "Vehicle must belong to the selected customer."})

    def __str__(self) -> str:
        return f"{self.vehicle.plate_number} - {self.service_name}"
