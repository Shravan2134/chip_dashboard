"""
Django signals to automatically update cached/denormalized fields.
This keeps performance-optimized fields in sync with source data.
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from decimal import Decimal
from django.db.models import Sum

from .models import Transaction, ClientDailyBalance, ClientExchange


def update_client_exchange_cache(client_exchange):
    """
    Update cached balance fields for a ClientExchange.
    This is called when transactions or balances change.
    Avoids circular imports by importing views functions here.
    """
    try:
        # Import here to avoid circular imports
        from .views import get_exchange_balance, get_old_balance_after_settlement
        
        # Update cached current balance (don't use cache to avoid recursion)
        current_balance = get_exchange_balance(client_exchange, use_cache=False)
        
        # Update cached old balance
        old_balance = get_old_balance_after_settlement(client_exchange)
        
        # Update cached total funding
        total_funding = Transaction.objects.filter(
            client_exchange=client_exchange,
            transaction_type=Transaction.TYPE_FUNDING
        ).aggregate(total=Sum("amount"))["total"] or Decimal(0)
        
        # Update the cached fields (use update() to avoid triggering signals again)
        ClientExchange.objects.filter(pk=client_exchange.pk).update(
            cached_current_balance=current_balance,
            cached_old_balance=old_balance,
            cached_total_funding=total_funding,
            balance_last_updated=timezone.now()
        )
    except Exception:
        # If calculation fails, don't break the transaction save
        # The cache will be updated on next access
        pass


@receiver(post_save, sender=Transaction)
def update_cache_on_transaction_save(sender, instance, **kwargs):
    """Update cached fields when a transaction is saved."""
    if instance.client_exchange:
        # ✅ ERROR 24 FIX: Bootstrap cached_old_balance IMMEDIATELY on first FUNDING
        # This must happen at FUNDING creation time, not lazily during settlement
        if instance.transaction_type == Transaction.TYPE_FUNDING:
            # Check if this is the first FUNDING (cached_old_balance is NULL or 0)
            client_exchange = instance.client_exchange
            if client_exchange.cached_old_balance is None or client_exchange.cached_old_balance == 0:
                # First FUNDING - initialize cached_old_balance immediately
                total_funding = Transaction.objects.filter(
                    client_exchange=client_exchange,
                    transaction_type=Transaction.TYPE_FUNDING
                ).aggregate(total=Sum("amount"))["total"] or Decimal(0)
                
                # Update cached_old_balance immediately (bootstrap)
                ClientExchange.objects.filter(pk=client_exchange.pk).update(
                    cached_old_balance=total_funding,
                    balance_last_updated=timezone.now()
                )
        
        # ✅ ERROR 17 FIX: Funding after settlement increases OB immediately
        if instance.transaction_type == Transaction.TYPE_FUNDING:
            # Check if there's a settlement (OB should be updated)
            has_settlement = Transaction.objects.filter(
                client_exchange=instance.client_exchange,
                transaction_type=Transaction.TYPE_SETTLEMENT
            ).exists()
            
            if has_settlement:
                # Funding after settlement - increase OB immediately
                client_exchange = instance.client_exchange
                current_ob = client_exchange.cached_old_balance or Decimal(0)
                new_ob = current_ob + instance.amount
                
                ClientExchange.objects.filter(pk=client_exchange.pk).update(
                    cached_old_balance=new_ob,
                    balance_last_updated=timezone.now()
                )
        
        # Update all cached fields
        update_client_exchange_cache(instance.client_exchange)


@receiver(post_delete, sender=Transaction)
def update_cache_on_transaction_delete(sender, instance, **kwargs):
    """Update cached fields when a transaction is deleted."""
    if instance.client_exchange:
        update_client_exchange_cache(instance.client_exchange)


@receiver(post_save, sender=ClientDailyBalance)
def update_cache_on_balance_save(sender, instance, **kwargs):
    """Update cached fields when a balance record is saved."""
    if instance.client_exchange:
        update_client_exchange_cache(instance.client_exchange)


@receiver(post_delete, sender=ClientDailyBalance)
def update_cache_on_balance_delete(sender, instance, **kwargs):
    """Update cached fields when a balance record is deleted."""
    if instance.client_exchange:
        update_client_exchange_cache(instance.client_exchange)

