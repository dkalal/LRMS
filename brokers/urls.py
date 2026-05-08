from django.urls import path
from django.views.generic import RedirectView

from .views import (
    BrokerCreateView,
    BrokerListView,
    BrokerReportListView,
    BrokerUpdateView,
    archive_broker,
    restore_broker,
)

urlpatterns = [
    path("", BrokerListView.as_view(), name="list"),
    path("new/", BrokerCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", BrokerUpdateView.as_view(), name="update"),
    path("<int:pk>/archive/", archive_broker, name="archive"),
    path("<int:pk>/restore/", restore_broker, name="restore"),
    path("reports/", RedirectView.as_view(pattern_name="reports", permanent=False), name="reports"),
]
