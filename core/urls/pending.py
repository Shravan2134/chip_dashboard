from django.urls import path

from core import views

urlpatterns = [
    path("", views.pending_summary, name="summary"),
    path("export/csv/", views.export_pending_csv, name="export_csv"),
]












