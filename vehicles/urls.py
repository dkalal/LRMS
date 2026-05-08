from django.urls import path

from .views import (
    VehicleCreateView,
    VehicleListView,
    VehicleUpdateView,
    archive_vehicle,
    restore_vehicle,
)

urlpatterns = [
    path("", VehicleListView.as_view(), name="list"),
    path("new/", VehicleCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", VehicleUpdateView.as_view(), name="update"),
    path("<int:pk>/archive/", archive_vehicle, name="archive"),
    path("<int:pk>/restore/", restore_vehicle, name="restore"),
]
