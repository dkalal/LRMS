from django.views.generic import RedirectView, TemplateView
from django.conf import settings
from django.core.cache import cache
from django.contrib import messages

from accounts.mixins import ReportAccessMixin, TenantAccessMixin

from .services import get_dashboard_context, get_reports_context


class HomeRedirectView(RedirectView):
    pattern_name = "dashboard:home"


class DashboardHomeView(TenantAccessMixin, TemplateView):
    template_name = "dashboard/home.html"
    fallback_context = {
        "total_customers": 0,
        "total_brokers": 0,
        "total_vehicles": 0,
        "active_records": 0,
        "expiring_30_records": 0,
        "expiring_7_records": 0,
        "today_records": 0,
        "expired_records": 0,
        "recent_records": [],
        "followup_records": [],
        "table_columns": ["Plate", "Customer", "Service", "Expiry"],
        "dashboard_cards": [],
        "dashboard_error": True,
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cache_key = (
            f"dashboard:v1:tenant:{self.request.user.tenant_id}:"
            f"user:{self.request.user.pk}"
        )
        dashboard_context = cache.get(cache_key)
        if dashboard_context is None:
            try:
                dashboard_context = get_dashboard_context(self.request.user)
                dashboard_context["dashboard_error"] = False
                cache.set(cache_key, dashboard_context, settings.DASHBOARD_CACHE_TIMEOUT)
            except Exception:
                dashboard_context = self.fallback_context.copy()
                messages.error(
                    self.request,
                    "Dashboard data could not be loaded right now. Try refreshing, or open the record pages directly.",
                )
        context.update(dashboard_context)
        return context


class ReportsView(ReportAccessMixin, TemplateView):
    template_name = "dashboard/reports.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query_string = self.request.META.get("QUERY_STRING", "")
        cache_key = (
            f"reports:v1:tenant:{self.request.user.tenant_id}:"
            f"user:{self.request.user.pk}:query:{query_string}"
        )
        reports_context = cache.get(cache_key)
        if reports_context is None:
            reports_context = get_reports_context(self.request.user, self.request.GET)
            cache.set(cache_key, reports_context, settings.REPORT_CACHE_TIMEOUT)
        context.update(reports_context)
        return context
