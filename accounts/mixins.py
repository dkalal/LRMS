from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from .models import RoleChoices


class TenantAccessMixin(LoginRequiredMixin):
    def get_tenant(self):
        return self.request.user.tenant


class AdminRequiredMixin(TenantAccessMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser and request.user.role != RoleChoices.ADMIN:
            raise PermissionDenied("Admin access is required.")
        return super().dispatch(request, *args, **kwargs)


class ReportAccessMixin(TenantAccessMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser and not request.user.can_view_reports():
            raise PermissionDenied("Report access is required.")
        return super().dispatch(request, *args, **kwargs)
