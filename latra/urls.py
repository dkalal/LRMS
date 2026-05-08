from django.urls import path

from .views import (
    LatraRecordCreateView,
    LatraRecordListView,
    LatraRecordUpdateView,
    LatraRenewView,
    ReminderStatusListView,
    WhatsAppPreviewView,
    broker_lookup,
    cancel_latra_record,
    customer_lookup,
    restore_latra_record,
    vehicle_lookup,
)

urlpatterns = [
    path("", LatraRecordListView.as_view(), name="list"),
    path("new/", LatraRecordCreateView.as_view(), name="create"),
    path("lookups/customers/", customer_lookup, name="customer_lookup"),
    path("lookups/vehicles/", vehicle_lookup, name="vehicle_lookup"),
    path("lookups/brokers/", broker_lookup, name="broker_lookup"),
    path("<int:pk>/edit/", LatraRecordUpdateView.as_view(), name="update"),
    path("<int:pk>/renew/", LatraRenewView.as_view(), name="renew"),
    path("<int:pk>/whatsapp/", WhatsAppPreviewView.as_view(), name="whatsapp"),
    path("<int:pk>/cancel/", cancel_latra_record, name="cancel"),
    path("<int:pk>/restore/", restore_latra_record, name="restore"),
    path("status/<str:status_name>/", ReminderStatusListView.as_view(), name="status_list"),
]
