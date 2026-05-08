from django.conf import settings
from django.db import models


class ActiveStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantCompany(TimeStampedModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Tenant Company"
        verbose_name_plural = "Tenant Companies"

    def __str__(self) -> str:
        return self.name


class TenantScopedModel(TimeStampedModel):
    tenant = models.ForeignKey(TenantCompany, on_delete=models.PROTECT)

    class Meta:
        abstract = True


class TrackedTenantModel(TenantScopedModel):
    status = models.CharField(
        max_length=20,
        choices=ActiveStatus.choices,
        default=ActiveStatus.ACTIVE,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_updated",
    )

    class Meta:
        abstract = True
