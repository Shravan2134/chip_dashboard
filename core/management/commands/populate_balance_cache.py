"""
Management command to populate cached balance fields for all ClientExchange records.
Run this after adding the cache fields to populate them for existing data.

Usage:
    python manage.py populate_balance_cache
"""
from django.core.management.base import BaseCommand
from core.models import ClientExchange
from core.signals import update_client_exchange_cache


class Command(BaseCommand):
    help = 'Populate cached balance fields for all ClientExchange records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of records to process in each batch (default: 100)',
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        
        # Get all ClientExchange records
        client_exchanges = ClientExchange.objects.all()
        total = client_exchanges.count()
        
        self.stdout.write(f'Processing {total} ClientExchange records...')
        
        processed = 0
        for i in range(0, total, batch_size):
            batch = client_exchanges[i:i + batch_size]
            for client_exchange in batch:
                try:
                    update_client_exchange_cache(client_exchange)
                    processed += 1
                    if processed % 10 == 0:
                        self.stdout.write(f'Processed {processed}/{total}...', ending='\r')
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f'Error processing {client_exchange}: {str(e)}'
                        )
                    )
        
        self.stdout.write(self.style.SUCCESS(
            f'\nSuccessfully processed {processed}/{total} ClientExchange records.'
        ))







