from django.urls import path

from core import views

urlpatterns = [
    path("", views.pending_summary, name="summary"),
]










