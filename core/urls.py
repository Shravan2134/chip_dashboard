"""
URL configuration for core app
"""
from django.urls import path, include
from . import views

urlpatterns = [
    # Authentication
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Clients
    path('clients/', views.client_list, name='client_list'),
    path('clients/create/', views.client_create, name='client_create'),
    path('clients/<int:pk>/', views.client_detail, name='client_detail'),
    path('clients/<int:pk>/delete/', views.client_delete, name='client_delete'),
    
    # Exchanges
    path('exchanges/', views.exchange_list, name='exchange_list'),
    path('exchanges/create/', views.exchange_create, name='exchange_create'),
    path('exchanges/link/', views.link_client_to_exchange, name='exchange_link'),
    path('exchanges/account/<int:pk>/', views.exchange_account_detail, name='exchange_account_detail'),
    
    # Funding & Transactions
    path('exchanges/account/<int:account_id>/funding/', views.add_funding, name='add_funding'),
    path('exchanges/account/<int:account_id>/update-balance/', views.update_exchange_balance, name='update_balance'),
    path('exchanges/account/<int:account_id>/record-payment/', views.record_payment, name='record_payment'),
    
    # Transactions (audit trail)
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('transactions/<int:pk>/', views.transaction_detail, name='transaction_detail'),
    
    # Pending Payments
    path('pending/', views.pending_summary, name='pending_summary'),
    path('pending/export/', views.export_pending_csv, name='export_pending_csv'),
    
    # Reports
    path('reports/', views.report_overview, name='report_overview'),
    path('reports/daily/', views.report_daily, name='report_daily'),
    path('reports/weekly/', views.report_weekly, name='report_weekly'),
    path('reports/monthly/', views.report_monthly, name='report_monthly'),
    path('reports/custom/', views.report_custom, name='report_custom'),
    path('reports/client/<int:pk>/', views.report_client, name='report_client'),
    path('reports/exchange/<int:pk>/', views.report_exchange, name='report_exchange'),
    path('reports/time-travel/', views.report_time_travel, name='report_time_travel'),
]

