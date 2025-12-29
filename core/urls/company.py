from django.urls import path

from core import views

urlpatterns = [
    path("", views.company_share_summary, name="summary"),
]














