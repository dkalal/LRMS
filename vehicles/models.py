from django.db import models

from accounts.models import VehicleCategoryChoices
from customers.models import Customer
from tenants.models import TrackedTenantModel


class Vehicle(TrackedTenantModel):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="vehicles")
    plate_number = models.CharField(max_length=30)
    vehicle_category = models.CharField(max_length=20, choices=VehicleCategoryChoices.choices)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("plate_number",)
        indexes = [
            models.Index(fields=("tenant", "status"), name="vehicle_tenant_status_idx"),
            models.Index(fields=("tenant", "vehicle_category"), name="vehicle_tenant_cat_idx"),
            models.Index(fields=("tenant", "plate_number"), name="vehicle_tenant_plate_idx"),
            models.Index(fields=("tenant", "customer"), name="vehicle_tenant_customer_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "plate_number"),
                name="unique_vehicle_plate_per_tenant",
            )
        ]

    def __str__(self) -> str:
        return self.plate_number
