from django.urls import path

from .views import DashboardHomeView, ReportsView

urlpatterns = [
    path("", DashboardHomeView.as_view(), name="home"),
    path("reports/", ReportsView.as_view(), name="reports"),
]
