from django.contrib.auth.models import AbstractUser
from django.db import models

from tenants.models import TenantCompany


class RoleChoices(models.TextChoices):
    ADMIN = "admin", "Admin"
    MANAGER = "manager", "Manager"
    RECEPTIONIST = "receptionist", "Receptionist"


class VehicleCategoryChoices(models.TextChoices):
    CAR = "CAR", "Car"
    MOTORCYCLE = "MOTORCYCLE", "Motorcycle"
    BAJAJI = "BAJAJI", "Bajaji"
    OTHER = "OTHER", "Other"
    ALL = "ALL", "All Categories"


class User(AbstractUser):
    tenant = models.ForeignKey(
        TenantCompany,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
    )
    role = models.CharField(
        max_length=20,
        choices=RoleChoices.choices,
        default=RoleChoices.RECEPTIONIST,
    )

    def can_manage_users(self) -> bool:
        return self.role == RoleChoices.ADMIN

    def can_view_reports(self) -> bool:
        return self.role in {RoleChoices.ADMIN, RoleChoices.MANAGER}

    def is_managerial(self) -> bool:
        return self.role in {RoleChoices.ADMIN, RoleChoices.MANAGER}

    def assigned_vehicle_categories(self):
        categories = list(
            self.vehicle_permissions.values_list("vehicle_category", flat=True).distinct()
        )
        if not categories and self.role == RoleChoices.ADMIN:
            return [VehicleCategoryChoices.ALL]
        return categories

    def has_all_vehicle_access(self) -> bool:
        return VehicleCategoryChoices.ALL in self.assigned_vehicle_categories()


class UserVehiclePermission(models.Model):
    tenant = models.ForeignKey(
        TenantCompany,
        on_delete=models.CASCADE,
        related_name="vehicle_permissions",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="vehicle_permissions",
    )
    vehicle_category = models.CharField(max_length=20, choices=VehicleCategoryChoices.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "vehicle_category")
        ordering = ("user__username", "vehicle_category")
        indexes = [
            models.Index(fields=("tenant", "user"), name="userperm_tenant_user_idx"),
            models.Index(fields=("tenant", "vehicle_category"), name="userperm_tenant_cat_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user.username} -> {self.vehicle_category}"
