from django.urls import path

from .views import reminders_redirect

urlpatterns = [
    path("", reminders_redirect, name="home"),
]
