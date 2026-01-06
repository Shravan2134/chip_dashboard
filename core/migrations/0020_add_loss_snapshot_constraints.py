# Generated migration for LossSnapshot constraints
# This migration should be applied when LossSnapshot model is added to the system

from django.db import migrations


class Migration(migrations.Migration):
    """
    Add DB-level constraints for LossSnapshot:
    1. Partial unique index to enforce ONE active LossSnapshot per client
    2. This prevents race conditions in concurrent transactions
    """
    
    dependencies = [
        ('core', '0019_add_security_deposit'),
    ]
    
    operations = [
        # Partial unique index: Only ONE active (is_settled=false) LossSnapshot per client_exchange
        migrations.RunSQL(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS unique_active_loss_per_client
            ON core_losssnapshot (client_exchange_id)
            WHERE is_settled = false;
            """,
            reverse_sql="DROP INDEX IF EXISTS unique_active_loss_per_client;",
            # Only run if LossSnapshot table exists
            state_operations=[]  # No model changes, just index
        ),
    ]


