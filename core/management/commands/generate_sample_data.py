"""
Management command to generate sample data:
- 10 clients
- Exchange accounts for each client
- Transactions spanning last 6 months
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
import random
from datetime import timedelta, datetime

from core.models import Client, Exchange, ClientExchangeAccount, Transaction


class Command(BaseCommand):
    help = 'Generate sample data: 10 clients with 6 months of transaction history'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to associate clients with (defaults to first user)',
        )

    def handle(self, *args, **options):
        # Get or create user
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

        self.stdout.write(self.style.SUCCESS(f'Using user: {user.username}'))

        # Get or create exchanges
        exchanges = []
        exchange_names = ['Binance', 'Coinbase', 'Kraken', 'Bybit']
        for name in exchange_names:
            exchange, created = Exchange.objects.get_or_create(name=name)
            exchanges.append(exchange)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created exchange: {name}'))

        # Client names
        client_names = [
            'Alice Johnson', 'Bob Smith', 'Charlie Brown', 'Diana Prince',
            'Ethan Hunt', 'Fiona Chen', 'George Wilson', 'Hannah Martinez',
            'Ian Thompson', 'Julia Rodriguez'
        ]

        # Generate 10 clients
        clients = []
        for i, name in enumerate(client_names):
            client, created = Client.objects.get_or_create(
                name=name,
                defaults={
                    'user': user,
                    'code': f'CLT{i+1:03d}' if i < 5 else None,  # First 5 have codes, rest don't
                    'referred_by': random.choice(['', 'Referral A', 'Referral B', '']) if i % 3 == 0 else '',
                    'is_company_client': i % 4 == 0,  # Every 4th client is company client
                }
            )
            clients.append(client)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created client: {name}'))

        # Generate accounts and transactions
        now = timezone.now()
        six_months_ago = now - timedelta(days=180)

        for client in clients:
            # Assign 1-2 exchanges per client
            num_exchanges = random.randint(1, 2)
            selected_exchanges = random.sample(exchanges, num_exchanges)

            for exchange in selected_exchanges:
                # Create or get account
                account, created = ClientExchangeAccount.objects.get_or_create(
                    client=client,
                    exchange=exchange,
                    defaults={
                        'funding': random.randint(50000, 500000),  # Initial funding: 50k to 500k
                        'exchange_balance': random.randint(40000, 600000),  # Initial balance
                        'my_percentage': random.choice([5, 10, 15, 20, 25]),
                        'loss_share_percentage': random.choice([5, 10, 15, 20]),
                        'profit_share_percentage': random.choice([5, 10, 15, 20, 25]),
                    }
                )

                if created:
                    self.stdout.write(self.style.SUCCESS(
                        f'Created account: {client.name} - {exchange.name}'
                    ))

                # Generate transactions for last 6 months
                # Start with initial funding transaction
                initial_funding = account.funding
                Transaction.objects.get_or_create(
                    client_exchange=account,
                    type='FUNDING',
                    date=six_months_ago,
                    defaults={
                        'amount': initial_funding,
                        'exchange_balance_after': account.exchange_balance,
                        'notes': f'Initial funding for {client.name}',
                    }
                )

                # Generate transactions over 6 months
                # Create transactions roughly every 3-7 days
                current_date = six_months_ago + timedelta(days=random.randint(1, 5))
                current_balance = account.exchange_balance

                transaction_count = 0
                while current_date < now:
                    # Random transaction type
                    tx_type = random.choices(
                        ['FUNDING', 'TRADE', 'FEE', 'ADJUSTMENT', 'RECORD_PAYMENT'],
                        weights=[5, 60, 15, 10, 10]  # More trades, fewer other types
                    )[0]

                    if tx_type == 'FUNDING':
                        amount = random.randint(10000, 100000)
                        current_balance += amount
                        notes = f'Additional funding for {client.name}'

                    elif tx_type == 'TRADE':
                        # Trades can be positive or negative
                        amount = random.randint(-50000, 80000)
                        current_balance += amount
                        notes = f'Trade execution - {client.name}'

                    elif tx_type == 'FEE':
                        amount = -random.randint(100, 5000)  # Fees are negative
                        current_balance += amount
                        notes = f'Trading fee - {exchange.name}'

                    elif tx_type == 'ADJUSTMENT':
                        amount = random.randint(-10000, 10000)
                        current_balance += amount
                        notes = f'Balance adjustment - {client.name}'

                    elif tx_type == 'RECORD_PAYMENT':
                        # Settlement payments - apply sign based on PnL
                        client_pnl = current_balance - account.funding
                        payment_amount = random.randint(500, 5000)
                        if client_pnl < 0:
                            # Loss case: Client pays you → positive
                            amount = payment_amount
                        else:
                            # Profit case: You pay client → negative
                            amount = -payment_amount
                        # Note: RECORD_PAYMENT doesn't change balance, but we'll track it
                        notes = f'Settlement payment - {client.name}'

                    # Ensure balance doesn't go too negative
                    if current_balance < -100000:
                        current_balance = random.randint(0, 100000)

                    # Create transaction
                    Transaction.objects.create(
                        client_exchange=account,
                        type=tx_type,
                        date=current_date,
                        amount=amount,
                        exchange_balance_after=current_balance,
                        notes=notes,
                    )

                    transaction_count += 1

                    # Move to next date (3-7 days later)
                    current_date += timedelta(days=random.randint(3, 7))

                # Update account balance to final value
                account.exchange_balance = current_balance
                account.save()

                self.stdout.write(self.style.SUCCESS(
                    f'  Generated {transaction_count} transactions for {client.name} - {exchange.name}'
                ))

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Successfully generated sample data:\n'
            f'  - {len(clients)} clients\n'
            f'  - {ClientExchangeAccount.objects.filter(client__user=user).count()} exchange accounts\n'
            f'  - {Transaction.objects.filter(client_exchange__client__user=user).count()} total transactions'
        ))

