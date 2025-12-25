from django.urls import path

from core import views

urlpatterns = [
    path("", views.my_clients_list, name="list"),
    path("add/", views.my_client_create, name="add"),
    path("<int:pk>/", views.client_detail, name="detail"),
    path("<int:client_pk>/link-exchange/", views.my_client_exchange_create, name="link_exchange"),
    path("<int:client_pk>/give-money/", views.client_give_money, name="give_money"),
    path("<int:client_pk>/report/", views.report_client, name="report"),
    path("<int:client_pk>/balance/", views.client_balance, name="balance"),
    path("<int:client_pk>/balance/latest/", views.get_latest_balance_for_exchange, name="get_latest_balance"),
    path("settle-payment/", views.settle_payment, name="settle_payment"),
    path("<int:pk>/delete/", views.client_delete, name="delete"),
]

