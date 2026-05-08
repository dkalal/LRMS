from django.core.exceptions import PermissionDenied

from .models import RoleChoices, VehicleCategoryChoices


def filter_records_by_user_vehicle_permission(queryset, user, field_name="vehicle__vehicle_category"):
    if not user.is_authenticated:
        return queryset.none()
    if user.is_superuser or user.role == RoleChoices.ADMIN or user.has_all_vehicle_access():
        return queryset.filter(tenant=user.tenant)

    categories = [category for category in user.assigned_vehicle_categories() if category]
    if not categories:
        return queryset.none()
    return queryset.filter(tenant=user.tenant, **{f"{field_name}__in": categories})


def enforce_tenant_scope(queryset, user):
    if not user.is_authenticated:
        raise PermissionDenied("Authentication required.")
    if user.is_superuser:
        return queryset
    return queryset.filter(tenant=user.tenant)


def enforce_vehicle_category_access(obj, user, category_value):
    if user.is_superuser or user.role == RoleChoices.ADMIN or user.has_all_vehicle_access():
        return obj
    if category_value not in user.assigned_vehicle_categories():
        raise PermissionDenied("You do not have permission for this vehicle category.")
    return obj
