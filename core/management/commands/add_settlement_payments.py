"""
Management command to add RECORD_PAYMENT transactions (settlements) for existing clients.
Creates settlement payments for accounts with pending amounts.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
import random
from datetime import timedelta

from core.models import Client, ClientExchangeAccount, Transaction, Settlement


class Command(BaseCommand):
    help = 'Add RECORD_PAYMENT transactions (settlements) for clients with pending amounts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to process clients for (defaults to first user)',
        )
        parser.add_argument(
            '--min-payments',
            type=int,
            default=2,
            help='Minimum number of payments per account (default: 2)',
        )
        parser.add_argument(
            '--max-payments',
            type=int,
            default=4,
            help='Maximum number of payments per account (default: 4)',
        )

    def handle(self, *args, **options):
        # Get user
        user_id = options.get('user_id')
        if user_id:
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'User with ID {user_id} not found'))
                return
        else:
            user = User.objects.first()
            if not user:
                self.stdout.write(self.style.ERROR('No users found. Please create a user first.'))
                return

        self.stdout.write(self.style.SUCCESS(f'Processing settlements for user: {user.username}'))

        # Get all accounts for this user
        accounts = ClientExchangeAccount.objects.filter(client__user=user).select_related('client', 'exchange')

        total_payments = 0
        now = timezone.now()

        self.stdout.write(f'Found {accounts.count()} accounts to process')

        for account in accounts:
            try:
                # CRITICAL: Refresh account from DB to ensure we have latest state
                account.refresh_from_db()
                
                # Calculate current PnL (use original account state)
                client_pnl = account.compute_client_pnl()
                
                # Skip if PnL is 0 (no settlement needed)
                if client_pnl == 0:
                    continue

                # Lock share for consistency BEFORE any calculations
                account.lock_initial_share_if_needed()
                account.refresh_from_db()  # Refresh to get locked values
                
                # Get locked share (use locked if available, otherwise compute)
                if account.locked_initial_final_share is not None and account.locked_initial_final_share > 0:
                    initial_final_share = account.locked_initial_final_share
                else:
                    initial_final_share = account.compute_my_share()
                    if initial_final_share > 0:
                        # Lock it now
                        account.lock_initial_share_if_needed()
                        account.refresh_from_db()
                        initial_final_share = account.locked_initial_final_share or initial_final_share

                # Skip if no share to settle
                if initial_final_share == 0:
                    continue
                
                # Get existing settlements for THIS account only (CRITICAL: account-specific filter)
                existing_settlements = Settlement.objects.filter(client_exchange=account)
                total_settled = sum(s.amount for s in existing_settlements) if existing_settlements.exists() else 0
                remaining_amount = max(0, initial_final_share - total_settled)
                
                # Store original account state BEFORE any modifications
                original_funding = account.funding
                original_exchange_balance = account.exchange_balance
                original_locked_pnl = account.locked_initial_pnl or abs(client_pnl)
                
                # Create payments: use 30-70% of initial share
                # Always create payments even if remaining is 0 (for historical data)
                target_payment_amount = int(initial_final_share * random.uniform(0.3, 0.7))
                payment_base = target_payment_amount  # Use target amount regardless of remaining
                
                # Ensure payment_base is reasonable (at least 1)
                if payment_base < 1:
                    payment_base = max(1, int(initial_final_share * 0.1))
                
                if payment_base < 1:
                    self.stdout.write(self.style.WARNING(
                        f'  Skipping {account.client.name} - {account.exchange.name}: share too small ({initial_final_share})'
                    ))
                    continue

                # Determine number of payments
                num_payments = random.randint(
                    options['min_payments'],
                    options['max_payments']
                )

                # Distribute payment_base across payments
                payments = []
                remaining = payment_base
                
                for i in range(num_payments):
                    if i == num_payments - 1:
                        payment_amount = max(1, remaining)
                    else:
                        percentage = random.uniform(0.4, 0.6)
                        payment_amount = max(1, int(remaining * percentage))
                        remaining -= payment_amount
                    
                    if payment_amount > 0:
                        payments.append(payment_amount)
                
                # Skip if no valid payments
                if not payments:
                    continue

                # Create payment dates (spread over last 3 months)
                payment_dates = []
                for i in range(len(payments)):
                    days_ago = random.randint(0, 90)
                    payment_date = now - timedelta(days=days_ago)
                    payment_dates.append(payment_date)
                
                payment_dates.sort()  # Oldest first

                # CRITICAL: Calculate all masked capitals BEFORE updating balances
                # This ensures each payment uses the ORIGINAL account state
                masked_capitals = []
                cumulative_funding = original_funding
                cumulative_exchange_balance = original_exchange_balance
                
                for payment_amount in payments:
                    if initial_final_share > 0:
                        masked_capital = int((payment_amount * abs(original_locked_pnl)) / initial_final_share)
                    else:
                        masked_capital = 0
                    
                    masked_capitals.append(masked_capital)
                    
                    # Track cumulative changes (for transaction records)
                    if client_pnl < 0:
                        cumulative_funding = max(0, cumulative_funding - masked_capital)
                    else:
                        cumulative_exchange_balance = max(0, cumulative_exchange_balance - masked_capital)

                # Now create all payments and update account ONCE at the end
                for i, (payment_amount, payment_date, masked_capital) in enumerate(zip(payments, payment_dates, masked_capitals)):
                    # FINAL SIGN LOGIC: Apply sign based on ORIGINAL PnL direction
                    if client_pnl < 0:
                        transaction_amount = payment_amount  # Positive (client pays you)
                    else:
                        transaction_amount = -payment_amount  # Negative (you pay client)

                    # Calculate exchange_balance_after for this transaction
                    if client_pnl < 0:
                        # LOSS: funding decreases, exchange_balance unchanged
                        exchange_balance_after = original_exchange_balance
                        # Calculate funding after this payment
                        funding_after = original_funding - sum(masked_capitals[:i+1])
                    else:
                        # PROFIT: exchange_balance decreases, funding unchanged
                        exchange_balance_after = original_exchange_balance - sum(masked_capitals[:i+1])
                        funding_after = original_funding

                    # Create Settlement record (CRITICAL: filtered by account)
                    Settlement.objects.create(
                        client_exchange=account,  # This ensures account isolation
                        amount=payment_amount,
                        date=payment_date,
                        notes=f'Settlement payment {i+1} of {len(payments)} - {account.client.name} - {account.exchange.name}',
                    )

                    # Create Transaction record (CRITICAL: filtered by account)
                    Transaction.objects.create(
                        client_exchange=account,  # This ensures account isolation
                        type='RECORD_PAYMENT',
                        date=payment_date,
                        amount=transaction_amount,
                        exchange_balance_after=exchange_balance_after,
                        notes=f'Settlement payment {i+1} of {len(payments)} - {account.client.name} - {account.exchange.name}. '
                              f'Masked Capital: {masked_capital}, Share Payment: {payment_amount}',
                    )

                    total_payments += 1

                    self.stdout.write(self.style.SUCCESS(
                        f'  Created payment {i+1}/{len(payments)} for {account.client.name} - {account.exchange.name}: '
                        f'₹{payment_amount} ({"+" if transaction_amount > 0 else ""}{transaction_amount})'
                    ))
                
                # Update account balances ONCE after all payments are created
                # This ensures account state is consistent
                if client_pnl < 0:
                    account.funding = max(0, original_funding - sum(masked_capitals))
                else:
                    account.exchange_balance = max(0, original_exchange_balance - sum(masked_capitals))
                
                account.save()
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'  Error processing {account.client.name} - {account.exchange.name}: {str(e)}'
                ))
                import traceback
                traceback.print_exc()
                continue

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Successfully created {total_payments} settlement payments'
        ))
