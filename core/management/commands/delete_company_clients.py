"""
Management command to delete all company clients and all related data.

⚠️ WARNING: This is a DESTRUCTIVE operation that cannot be undone.
Deletes:
- All company clients (Client where is_company_client=True)
- All ClientExchange records for those clients
- All Transactions for those ClientExchanges
- All ClientDailyBalance records
- All DailyBalanceSnapshot records
- All CompanyShareRecord records
- All TallyLedger records
- All LossSnapshot records
- All PendingAmount records
- All OutstandingAmount records (if any exist for company clients)
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from core.models import (
    Client, ClientExchange, Transaction, ClientDailyBalance,
    DailyBalanceSnapshot, CompanyShareRecord, TallyLedger,
    LossSnapshot, PendingAmount, OutstandingAmount
)


class Command(BaseCommand):
    help = 'Delete all company clients and all related data (DESTRUCTIVE - cannot be undone)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        force = options['force']
        dry_run = options['dry_run']
        
        # Get all company clients
        company_clients = Client.objects.filter(is_company_client=True)
        company_client_count = company_clients.count()
        
        if company_client_count == 0:
            self.stdout.write(self.style.SUCCESS('✅ No company clients found. Nothing to delete.'))
            return
        
        # Get all related data counts
        company_client_exchanges = ClientExchange.objects.filter(client__is_company_client=True)
        company_transactions = Transaction.objects.filter(client_exchange__client__is_company_client=True)
        company_daily_balances = ClientDailyBalance.objects.filter(
            Q(client_exchange__client__is_company_client=True) | 
            Q(client__is_company_client=True)
        )
        company_snapshots = DailyBalanceSnapshot.objects.filter(client_exchange__client__is_company_client=True)
        company_share_records = CompanyShareRecord.objects.filter(client_exchange__client__is_company_client=True)
        company_tally_ledgers = TallyLedger.objects.filter(client_exchange__client__is_company_client=True)
        company_loss_snapshots = LossSnapshot.objects.filter(client_exchange__client__is_company_client=True)
        company_pending_amounts = PendingAmount.objects.filter(client_exchange__client__is_company_client=True)
        company_outstanding_amounts = OutstandingAmount.objects.filter(client_exchange__client__is_company_client=True)
        
        # Show summary
        self.stdout.write(self.style.WARNING('\n⚠️  COMPANY CLIENT DELETION SUMMARY'))
        self.stdout.write('=' * 60)
        self.stdout.write(f'Company Clients: {company_client_count}')
        self.stdout.write(f'Client Exchanges: {company_client_exchanges.count()}')
        self.stdout.write(f'Transactions: {company_transactions.count()}')
        self.stdout.write(f'Daily Balances: {company_daily_balances.count()}')
        self.stdout.write(f'Daily Snapshots: {company_snapshots.count()}')
        self.stdout.write(f'Company Share Records: {company_share_records.count()}')
        self.stdout.write(f'Tally Ledgers: {company_tally_ledgers.count()}')
        self.stdout.write(f'Loss Snapshots: {company_loss_snapshots.count()}')
        self.stdout.write(f'Pending Amounts: {company_pending_amounts.count()}')
        self.stdout.write(f'Outstanding Amounts: {company_outstanding_amounts.count()}')
        self.stdout.write('=' * 60)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n🔍 DRY RUN MODE - No data will be deleted'))
            self.stdout.write('Run without --dry-run to actually delete the data.')
            return
        
        if not force:
            self.stdout.write(self.style.ERROR('\n⚠️  WARNING: This will PERMANENTLY delete all company clients and related data!'))
            confirm = input('Type "DELETE ALL COMPANY CLIENTS" to confirm: ')
            if confirm != "DELETE ALL COMPANY CLIENTS":
                self.stdout.write(self.style.ERROR('❌ Deletion cancelled.'))
                return
        
        # Perform deletion in a transaction
        try:
            with transaction.atomic():
                self.stdout.write('\n🗑️  Starting deletion...')
                
                # Delete in reverse dependency order
                # 1. Delete related records first
                deleted_count = company_outstanding_amounts.count()
                company_outstanding_amounts.delete()
                self.stdout.write(f'  ✅ Deleted {deleted_count} Outstanding Amount records')
                
                deleted_count = company_pending_amounts.count()
                company_pending_amounts.delete()
                self.stdout.write(f'  ✅ Deleted {deleted_count} Pending Amount records')
                
                deleted_count = company_loss_snapshots.count()
                company_loss_snapshots.delete()
                self.stdout.write(f'  ✅ Deleted {deleted_count} Loss Snapshot records')
                
                deleted_count = company_tally_ledgers.count()
                company_tally_ledgers.delete()
                self.stdout.write(f'  ✅ Deleted {deleted_count} Tally Ledger records')
                
                deleted_count = company_share_records.count()
                company_share_records.delete()
                self.stdout.write(f'  ✅ Deleted {deleted_count} Company Share Record records')
                
                deleted_count = company_snapshots.count()
                company_snapshots.delete()
                self.stdout.write(f'  ✅ Deleted {deleted_count} Daily Balance Snapshot records')
                
                deleted_count = company_daily_balances.count()
                company_daily_balances.delete()
                self.stdout.write(f'  ✅ Deleted {deleted_count} Client Daily Balance records')
                
                # 2. Delete transactions (CASCADE will handle some, but delete explicitly for clarity)
                deleted_count = company_transactions.count()
                company_transactions.delete()
                self.stdout.write(f'  ✅ Deleted {deleted_count} Transaction records')
                
                # 3. Delete client exchanges (CASCADE will handle transactions, but we already deleted them)
                deleted_count = company_client_exchanges.count()
                company_client_exchanges.delete()
                self.stdout.write(f'  ✅ Deleted {deleted_count} Client Exchange records')
                
                # 4. Finally, delete company clients
                deleted_count = company_clients.count()
                company_clients.delete()
                self.stdout.write(f'  ✅ Deleted {deleted_count} Company Client records')
                
                self.stdout.write(self.style.SUCCESS('\n✅ Successfully deleted all company clients and related data!'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Error during deletion: {str(e)}'))
            self.stdout.write(self.style.ERROR('Transaction rolled back. No data was deleted.'))
            raise


