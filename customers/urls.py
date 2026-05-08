from django.urls import path

from .views import (
    CustomerCreateView,
    CustomerListView,
    CustomerUpdateView,
    archive_customer,
    restore_customer,
)

urlpatterns = [
    path("", CustomerListView.as_view(), name="list"),
    path("new/", CustomerCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", CustomerUpdateView.as_view(), name="update"),
    path("<int:pk>/archive/", archive_customer, name="archive"),
    path("<int:pk>/restore/", restore_customer, name="restore"),
]
