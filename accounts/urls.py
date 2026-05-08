from django.urls import path

from .views import (
    UserCreateView,
    UserListView,
    UserVehiclePermissionCreateView,
    accounts_home_redirect,
    archive_user,
    restore_user,
)

urlpatterns = [
    path("", accounts_home_redirect, name="home"),
    path("users/", UserListView.as_view(), name="user_list"),
    path("users/new/", UserCreateView.as_view(), name="user_create"),
    path("users/<int:pk>/deactivate/", archive_user, name="user_archive"),
    path("users/<int:pk>/restore/", restore_user, name="user_restore"),
    path("permissions/new/", UserVehiclePermissionCreateView.as_view(), name="permission_create"),
]
