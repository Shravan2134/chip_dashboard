from django.contrib import admin

from .models import Client, Exchange, ClientExchange, Transaction, DailyBalanceSnapshot, CompanyShareRecord, SystemSettings, ClientDailyBalance


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "code")


@admin.register(Exchange)
class ExchangeAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "code")


@admin.register(ClientExchange)
class ClientExchangeAdmin(admin.ModelAdmin):
    list_display = ("client", "exchange", "my_share_pct", "company_share_pct", "is_active")
    list_filter = ("is_active", "client", "exchange")
    search_fields = ("client__name", "client__code", "exchange__name")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "client_exchange",
        "transaction_type",
        "amount",
        "client_share_amount",
        "your_share_amount",
        "company_share_amount",
    )
    list_filter = ("transaction_type", "client_exchange__client", "client_exchange__exchange")
    date_hierarchy = "date"
    search_fields = ("client_exchange__exchange__name", "client_exchange__client__name", "client_exchange__client__code")


@admin.register(DailyBalanceSnapshot)
class DailyBalanceSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "client_exchange",
        "client_net_balance",
        "you_net_balance",
        "pending_client_owes_you",
        "pending_you_owe_client",
    )
    list_filter = ("date", "client_exchange__client", "client_exchange__exchange")


@admin.register(CompanyShareRecord)
class CompanyShareRecordAdmin(admin.ModelAdmin):
    list_display = ("date", "client_exchange", "transaction", "company_amount")
    list_filter = ("date", "client_exchange__client", "client_exchange__exchange")


@admin.register(ClientDailyBalance)
class ClientDailyBalanceAdmin(admin.ModelAdmin):
    list_display = ("date", "client_exchange", "remaining_balance", "note", "created_at")
    list_filter = ("date", "client_exchange__client", "client_exchange__exchange")
    date_hierarchy = "date"
    search_fields = ("client_exchange__client__name", "client_exchange__client__code", "client_exchange__exchange__name", "note")


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    list_display = ("weekly_report_day", "auto_generate_weekly_reports")
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False

