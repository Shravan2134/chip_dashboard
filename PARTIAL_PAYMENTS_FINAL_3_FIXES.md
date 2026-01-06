# PARTIAL PAYMENTS - FINAL 3 CRITICAL FIXES

**Complete Fixes for Idempotency, DB Constraints, and LOSS Invariant**

---

## 🔴 CRITICAL ERROR #1: Idempotency Logic is Mathematically Wrong

**❌ Problem**: UUID generated inside function can never collide, making idempotency check useless.

**💥 Why Critical**:
```
Client clicks "Pay ₹3" twice quickly
Two HTTP requests
Two different UUIDs
Both pass idempotency check
LOSS reduced twice (60 → 0)
Capital closed = 60 instead of 30 ❌
```

**✅ Correct Fix** (Deterministic Idempotency Key):
```python
import hashlib

def generate_settlement_id(client_exchange_id, balance_record_id, payment, loss_snapshot_id):
    """
    Generate deterministic settlement ID from input parameters.
    Same inputs → same ID → true idempotency.
    """
    # Normalize payment to string (handle decimal precision)
    payment_str = str(payment.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    
    # Create deterministic key
    key_string = f"{client_exchange_id}_{balance_record_id}_{payment_str}_{loss_snapshot_id}"
    
    # Generate hash (deterministic)
    settlement_id = hashlib.sha256(key_string.encode()).hexdigest()
    
    return settlement_id

# Usage in settlement:
@transaction.atomic
def settle_payment(client_exchange_id, payment, balance_record_id):
    # Lock for concurrency
    client_exchange = ClientExchange.objects.select_for_update().get(
        pk=client_exchange_id
    )
    
    # Get loss snapshot
    balance_record = BalanceRecord.objects.get(pk=balance_record_id)
    loss_snapshot = LossSnapshot.objects.get(balance_record=balance_record)
    
    # ✅ CRITICAL FIX: Generate deterministic settlement ID
    settlement_id = generate_settlement_id(
        client_exchange_id,
        balance_record_id,
        payment,
        loss_snapshot.id  # Include snapshot ID for uniqueness
    )
    
    # ✅ CRITICAL FIX: Check idempotency (now actually works)
    existing_settlement = Transaction.objects.filter(
        settlement_id=settlement_id
    ).first()
    
    if existing_settlement:
        return {
            "status": "duplicate",
            "message": "This settlement was already processed",
            "existing_settlement_id": existing_settlement.id
        }
    
    # ... rest of settlement logic ...
    
    # Create settlement with deterministic ID
    Transaction.objects.create(
        transaction_type=Transaction.TYPE_SETTLEMENT,
        settlement_id=settlement_id,  # ✅ Deterministic
        amount=payment,
        capital_closed=capital_closed,
        # ... other fields ...
    )
```

**Alternative: Composite Unique Constraint**:
```python
# In models.py
class Transaction(models.Model):
    client_exchange = ForeignKey(ClientExchange)
    balance_record = ForeignKey(BalanceRecord)
    amount = DecimalField()
    settlement_id = CharField(max_length=64, unique=True)
    
    class Meta:
        # Additional unique constraint for idempotency
        constraints = [
            models.UniqueConstraint(
                fields=['client_exchange', 'balance_record', 'amount'],
                condition=models.Q(transaction_type='SETTLEMENT'),
                name='unique_settlement_per_balance'
            )
        ]

# In settlement code:
@transaction.atomic
def settle_payment(client_exchange_id, payment, balance_record_id):
    try:
        transaction = Transaction.objects.create(
            client_exchange_id=client_exchange_id,
            balance_record_id=balance_record_id,
            transaction_type=Transaction.TYPE_SETTLEMENT,
            amount=payment,
            # ... other fields ...
        )
    except IntegrityError:
        # Duplicate settlement detected
        existing = Transaction.objects.get(
            client_exchange_id=client_exchange_id,
            balance_record_id=balance_record_id,
            transaction_type=Transaction.TYPE_SETTLEMENT,
            amount=payment
        )
        return {"status": "duplicate", "existing": existing.id}
```

---

## 🟠 HIGH-RISK ERROR #1: No Hard DB Constraint for ONE Active LossSnapshot

**❌ Problem**: Code-level check only, no DB constraint. Race condition possible.

**💥 Why Critical**: Two concurrent BalanceRecords could create two active LossSnapshots.

**✅ Required Fix** (DB-Level Constraint):
```python
# In models.py (Django migration)
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_initial'),
    ]
    
    operations = [
        # Add partial unique constraint
        migrations.RunSQL(
            """
            CREATE UNIQUE INDEX unique_active_loss_per_client
            ON core_losssnapshot (client_exchange_id)
            WHERE is_settled = false;
            """,
            reverse_sql="DROP INDEX IF EXISTS unique_active_loss_per_client;"
        ),
    ]

# In models.py
class LossSnapshot(models.Model):
    client_exchange = ForeignKey(ClientExchange)
    balance_record = OneToOneField(BalanceRecord)
    loss_amount = DecimalField()
    is_settled = BooleanField(default=False)
    
    class Meta:
        # Note: Partial unique constraint is added via migration above
        # Django doesn't support partial unique constraints directly
        pass

# Code-level enforcement (additional safety)
@transaction.atomic
def create_loss_snapshot_if_needed(balance_record):
    """Create LossSnapshot with DB constraint enforcement"""
    client_exchange = balance_record.client_exchange
    
    # Lock to prevent concurrent creation
    client_exchange = ClientExchange.objects.select_for_update().get(
        pk=client_exchange.id
    )
    
    # Check if active loss exists
    active_loss = LossSnapshot.objects.filter(
        client_exchange=client_exchange,
        is_settled=False
    ).first()
    
    if active_loss:
        # Auto-settle old loss
        active_loss.is_settled = True
        active_loss.save()
        
        # Create settlement event for old loss
        Transaction.objects.create(
            client_exchange=client_exchange,
            transaction_type=Transaction.TYPE_SETTLEMENT,
            amount=Decimal(0),
            capital_closed=active_loss.loss_amount,
            note="Auto-settled: New loss created"
        )
    
    # Now create new loss snapshot
    # DB constraint will prevent duplicates if somehow two get through
    try:
        loss_snapshot = LossSnapshot.objects.create(
            client_exchange=client_exchange,
            balance_record=balance_record,
            loss_amount=balance_record.loss_at_balance_time,
            # ... other fields ...
        )
    except IntegrityError:
        # DB constraint caught duplicate (shouldn't happen, but safety)
        raise ValueError("Active loss already exists (DB constraint violation)")
    
    return loss_snapshot
```

---

## 🟠 HIGH-RISK ERROR #2: Missing LOSS Formula Invariant

**❌ Problem**: Invariant `LOSS == max(CAPITAL - CB, 0)` is not explicitly enforced.

**💥 Why Critical**: Silent corruption can exist forever undetected.

**✅ Required Fix** (Complete Invariant Enforcement):
```python
def enforce_invariants(client_exchange):
    """
    Complete invariant enforcement - throws hard errors on violation
    Runs INSIDE transaction, aborts commit on failure
    """
    capital = get_capital(client_exchange)
    cb = get_exchange_balance(client_exchange)
    
    # Invariant 1: CAPITAL conservation
    total_funding = get_total_funding(client_exchange)
    total_capital_closed = get_total_capital_closed(client_exchange)
    derived_capital = total_funding - total_capital_closed
    
    if abs(capital - derived_capital) > Decimal("0.01"):
        raise ValueError(
            f"Invariant 1 violation: CAPITAL={capital} != derived={derived_capital}"
        )
    
    # Invariant 2: Σ(CAPITAL_CLOSED) ≤ Σ(FUNDING)
    if total_capital_closed > total_funding:
        raise ValueError(
            f"Invariant 2 violation: capital_closed={total_capital_closed} > funding={total_funding}"
        )
    
    # Invariant 3: Only one active LOSS
    active_losses = LossSnapshot.objects.filter(
        client_exchange=client_exchange,
        is_settled=False
    ).count()
    
    if active_losses > 1:
        raise ValueError(
            f"Invariant 3 violation: {active_losses} active losses exist (max 1 allowed)"
        )
    
    # Invariant 4: LOSS exists ⇒ CAPITAL > CB
    active_loss = LossSnapshot.objects.filter(
        client_exchange=client_exchange,
        is_settled=False
    ).first()
    
    if active_loss:
        if capital <= cb:
            raise ValueError(
                f"Invariant 4 violation: LOSS exists but CAPITAL={capital} <= CB={cb}"
            )
    
    # ✅ HIGH-RISK ERROR #2 FIX: LOSS formula invariant
    if active_loss:
        balance_record = active_loss.balance_record
        cb_from_snapshot = balance_record.remaining_balance
        
        # Calculate expected LOSS from ledger
        expected_loss = max(capital - cb_from_snapshot, Decimal("0.00"))
        actual_loss = active_loss.loss_amount
        
        # CRITICAL: Enforce LOSS == max(CAPITAL - CB, 0)
        if abs(expected_loss - actual_loss) > Decimal("0.01"):
            raise ValueError(
                f"Invariant 5 violation: LOSS formula mismatch!\n"
                f"  LossSnapshot.loss_amount = {actual_loss}\n"
                f"  Expected LOSS = max(CAPITAL - CB, 0) = max({capital} - {cb_from_snapshot}, 0) = {expected_loss}\n"
                f"  Difference = {abs(expected_loss - actual_loss)}\n"
                f"  This indicates data corruption. Transaction aborted."
            )
    
    # Invariant 6: Share conservation
    settlements = Transaction.objects.filter(
        client_exchange=client_exchange,
        transaction_type=Transaction.TYPE_SETTLEMENT
    )
    
    for settlement in settlements:
        your_share = settlement.your_share_amount or Decimal(0)
        company_share = settlement.company_share_amount or Decimal(0)
        capital_closed = settlement.capital_closed
        
        if abs(your_share + company_share - capital_closed) > Decimal("0.01"):
            raise ValueError(
                f"Invariant 6 violation: shares={your_share + company_share} != capital_closed={capital_closed}"
            )
    
    return True
```

---

## 🔄 COMPLETE CORRECTED SETTLEMENT FLOW

### **With All 3 Fixes Integrated**

```python
import hashlib
import uuid
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError

@transaction.atomic
def settle_payment(client_exchange_id, payment, balance_record_id):
    """
    Complete settlement flow with all fixes:
    1. Deterministic idempotency key
    2. DB constraint for active LossSnapshot
    3. LOSS formula invariant enforcement
    """
    # STEP 1: Lock for concurrency
    client_exchange = ClientExchange.objects.select_for_update().get(
        pk=client_exchange_id
    )
    
    # STEP 2: Get balance record and loss snapshot
    balance_record = BalanceRecord.objects.get(pk=balance_record_id)
    loss_snapshot = LossSnapshot.objects.get(balance_record=balance_record)
    
    # STEP 3: ✅ CRITICAL FIX #1: Generate deterministic settlement ID
    payment_normalized = payment.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    key_string = f"{client_exchange_id}_{balance_record_id}_{payment_normalized}_{loss_snapshot.id}"
    settlement_id = hashlib.sha256(key_string.encode()).hexdigest()
    
    # STEP 4: ✅ CRITICAL FIX #1: Check idempotency (now actually works)
    existing_settlement = Transaction.objects.filter(
        settlement_id=settlement_id
    ).first()
    
    if existing_settlement:
        return {
            "status": "duplicate",
            "message": "This settlement was already processed",
            "existing_settlement_id": existing_settlement.id
        }
    
    # STEP 5: Validate loss exists
    loss_current = loss_snapshot.loss_amount
    if loss_current == 0 or loss_snapshot.is_settled:
        raise ValidationError("No loss to settle")
    
    # STEP 6: Get shares from snapshot
    my_share_pct = loss_snapshot.my_share_pct
    company_share_pct = loss_snapshot.company_share_pct
    total_share_pct = my_share_pct + company_share_pct
    
    # STEP 7: Validate in share space
    client_payable = (loss_current * total_share_pct) / 100
    if payment > client_payable:
        raise ValidationError(f"Payment {payment} exceeds ClientPayable {client_payable}")
    
    # STEP 8: Convert to capital space
    capital_closed_raw = (payment * 100) / total_share_pct
    if capital_closed_raw > loss_current:
        raise ValidationError(f"Capital closed {capital_closed_raw} exceeds LOSS {loss_current}")
    
    # STEP 9: Check CAPITAL cannot go negative
    total_funding = get_total_funding(client_exchange)
    total_capital_closed = get_total_capital_closed(client_exchange)
    if total_capital_closed + capital_closed_raw > total_funding:
        raise ValidationError("Settlement would make CAPITAL negative")
    
    # STEP 10: Round
    capital_closed = capital_closed_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    # STEP 11: Reduce LOSS
    loss_new = loss_current - capital_closed
    if loss_new < 0:
        raise ValidationError("Settlement would create negative LOSS")
    
    # STEP 12: Auto-close
    if loss_new < Decimal("0.01"):
        capital_closed = loss_current
        loss_new = Decimal(0)
    
    # STEP 13: Calculate shares
    your_share_amount = (capital_closed * my_share_pct) / 100
    company_share_amount = (capital_closed * company_share_pct) / 100
    
    # STEP 14: Create settlement event
    Transaction.objects.create(
        transaction_type=Transaction.TYPE_SETTLEMENT,
        settlement_id=settlement_id,  # ✅ Deterministic
        amount=payment,
        capital_closed=capital_closed,
        your_share_amount=your_share_amount,
        company_share_amount=company_share_amount,
        balance_record_id=balance_record_id
    )
    
    # STEP 15: Update loss snapshot
    loss_snapshot.loss_amount = loss_new
    if loss_new == 0:
        loss_snapshot.is_settled = True
    loss_snapshot.save()
    
    # STEP 16: ✅ HIGH-RISK ERROR #2 FIX: Enforce invariants (includes LOSS formula check)
    try:
        enforce_invariants(client_exchange)
    except ValueError as e:
        # Transaction will rollback automatically
        raise ValidationError(f"Settlement aborted: {str(e)}")
    
    return {"status": "success"}
```

---

## 📋 COMPLETE INVARIANT ENFORCEMENT (All 6 Invariants)

```python
def enforce_invariants(client_exchange):
    """
    Complete invariant enforcement - all 6 invariants
    
    Behavior:
    - Runs INSIDE transaction
    - Raises ValueError on failure
    - Aborts commit automatically
    """
    capital = get_capital(client_exchange)
    cb = get_exchange_balance(client_exchange)
    
    # Invariant 1: CAPITAL conservation
    total_funding = get_total_funding(client_exchange)
    total_capital_closed = get_total_capital_closed(client_exchange)
    derived_capital = total_funding - total_capital_closed
    
    if abs(capital - derived_capital) > Decimal("0.01"):
        raise ValueError(f"Invariant 1: CAPITAL={capital} != derived={derived_capital}")
    
    # Invariant 2: Σ(CAPITAL_CLOSED) ≤ Σ(FUNDING)
    if total_capital_closed > total_funding:
        raise ValueError(f"Invariant 2: capital_closed={total_capital_closed} > funding={total_funding}")
    
    # Invariant 3: Only one active LOSS
    active_losses = LossSnapshot.objects.filter(
        client_exchange=client_exchange,
        is_settled=False
    ).count()
    
    if active_losses > 1:
        raise ValueError(f"Invariant 3: {active_losses} active losses exist (max 1)")
    
    # Invariant 4: LOSS exists ⇒ CAPITAL > CB
    active_loss = LossSnapshot.objects.filter(
        client_exchange=client_exchange,
        is_settled=False
    ).first()
    
    if active_loss:
        if capital <= cb:
            raise ValueError(f"Invariant 4: LOSS exists but CAPITAL={capital} <= CB={cb}")
    
    # ✅ Invariant 5: LOSS formula (HIGH-RISK ERROR #2 FIX)
    if active_loss:
        balance_record = active_loss.balance_record
        cb_from_snapshot = balance_record.remaining_balance
        
        # Calculate expected LOSS from ledger
        expected_loss = max(capital - cb_from_snapshot, Decimal("0.00"))
        actual_loss = active_loss.loss_amount
        
        # Enforce LOSS == max(CAPITAL - CB, 0)
        if abs(expected_loss - actual_loss) > Decimal("0.01"):
            raise ValueError(
                f"Invariant 5: LOSS formula mismatch!\n"
                f"  LossSnapshot.loss_amount = {actual_loss}\n"
                f"  Expected = max({capital} - {cb_from_snapshot}, 0) = {expected_loss}\n"
                f"  Difference = {abs(expected_loss - actual_loss)}"
            )
    
    # Invariant 6: Share conservation
    settlements = Transaction.objects.filter(
        client_exchange=client_exchange,
        transaction_type=Transaction.TYPE_SETTLEMENT
    )
    
    for settlement in settlements:
        your_share = settlement.your_share_amount or Decimal(0)
        company_share = settlement.company_share_amount or Decimal(0)
        capital_closed = settlement.capital_closed
        
        if abs(your_share + company_share - capital_closed) > Decimal("0.01"):
            raise ValueError(
                f"Invariant 6: shares={your_share + company_share} != capital_closed={capital_closed}"
            )
    
    return True
```

---

## 🗄️ DB CONSTRAINTS (SQL Migration)

### **Partial Unique Index for Active LossSnapshot**

```python
# Migration file: core/migrations/XXXX_add_loss_snapshot_constraint.py
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_initial'),
    ]
    
    operations = [
        migrations.RunSQL(
            """
            CREATE UNIQUE INDEX unique_active_loss_per_client
            ON core_losssnapshot (client_exchange_id)
            WHERE is_settled = false;
            """,
            reverse_sql="DROP INDEX IF EXISTS unique_active_loss_per_client;"
        ),
    ]
```

### **Composite Unique Constraint for Settlement Idempotency**

```python
# Migration file: core/migrations/XXXX_add_settlement_idempotency.py
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_initial'),
    ]
    
    operations = [
        migrations.RunSQL(
            """
            CREATE UNIQUE INDEX unique_settlement_per_balance
            ON core_transaction (client_exchange_id, balance_record_id, amount)
            WHERE transaction_type = 'SETTLEMENT';
            """,
            reverse_sql="DROP INDEX IF EXISTS unique_settlement_per_balance;"
        ),
    ]
```

---

## 🎯 SUMMARY

### **All 3 Errors Fixed**

1. ✅ **CRITICAL ERROR #1**: Deterministic idempotency key (hash of inputs, not UUID)
2. ✅ **HIGH-RISK ERROR #1**: DB constraint for ONE active LossSnapshot (partial unique index)
3. ✅ **HIGH-RISK ERROR #2**: LOSS formula invariant enforced (`LOSS == max(CAPITAL - CB, 0)`)

### **Complete Invariant List (6 Invariants)**

```
1. CAPITAL = Σ(FUNDING) − Σ(CAPITAL_CLOSED)  (±₹0.01)
2. Σ(CAPITAL_CLOSED) ≤ Σ(FUNDING)  (hard failure)
3. Only ONE active LossSnapshot  (hard failure)
4. LOSS exists ⇒ CAPITAL > CB  (hard failure)
5. LOSS == max(CAPITAL - CB, 0)  (±₹0.01)  ✅ NEW
6. Σ(your_share + company_share) = Σ(capital_closed)  (±₹0.01)
```

### **Critical Rules**

```
✅ Settlement ID is deterministic (hash of inputs)
✅ DB constraint enforces ONE active LossSnapshot
✅ LOSS formula invariant enforced (detects corruption)
✅ All invariants run inside transaction
✅ All invariants abort commits on failure
✅ No partial commits possible
```

---

**Document Version**: 11.0  
**Last Updated**: 2026-01-05  
**Status**: ✅ All 3 Final Errors Fixed, Production-Safe Transaction System


