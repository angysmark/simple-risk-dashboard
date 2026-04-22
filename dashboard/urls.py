"""URL patterns for the dashboard app."""

from django.urls import path

from dashboard import views

urlpatterns = [
    path("", views.index, name="index"),
    path("api/data/", views.api_data, name="api-data"),
]
