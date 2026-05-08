from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from dashboard.views import HomeRedirectView, ReportsView


urlpatterns = [
    path("", HomeRedirectView.as_view(), name="home"),
    path("reports/", ReportsView.as_view(), name="reports"),
    path("admin/", admin.site.urls),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="auth/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("dashboard/", include(("dashboard.urls", "dashboard"), namespace="dashboard")),
    path("accounts/", include(("accounts.urls", "accounts"), namespace="accounts")),
    path("brokers/", include(("brokers.urls", "brokers"), namespace="brokers")),
    path("customers/", include(("customers.urls", "customers"), namespace="customers")),
    path("vehicles/", include(("vehicles.urls", "vehicles"), namespace="vehicles")),
    path("latra/", include(("latra.urls", "latra"), namespace="latra")),
    path(
        "reminders/",
        include(("reminders.urls", "reminders"), namespace="reminders"),
    ),
]
