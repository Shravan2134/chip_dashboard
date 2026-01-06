# PARTIAL PAYMENTS - CAUSAL STRUCTURE FIXED

**All 8 Critical Causal Errors Fixed - Balance-Record-Driven Architecture**

---

## 🔴 ALL 8 CRITICAL CAUSAL ERRORS & FIXES

### **CRITICAL-1: LOSS is Recomputed from CAPITAL that Includes Future Settlements**

**❌ Problem**: LOSS is computed from global CAPITAL instead of balance-record-specific capital.

**💥 Why Wrong**:
```python
# ❌ WRONG: Mixes historical losses
capital = get_capital(client_exchange)  # Σ(FUNDING) − Σ(CAPITAL_CLOSED)
loss_current = max(capital - cb_snapshot, 0)
```

**💥 Failure Example**:
```
Funding = 100
Trade-1 loss → CB = 40 → LOSS = 60
Partial settlement closes 30 → CAPITAL = 70

Later:
CB still 40 (no new trade)
LOSS = CAPITAL - CB = 30  ❌ (This is not a new loss!)
```

**✅ Correct Fix**:
```python
# LOSS must be tied to balance record, not global CAPITAL
class BalanceRecord(models.Model):
    client_exchange = ForeignKey(ClientExchange)
    date = DateField()
    remaining_balance = DecimalField()
    capital_at_balance_time = DecimalField()  # ✅ CAPITAL when this balance was recorded
    loss_at_balance_time = DecimalField()  # ✅ LOSS when this balance was recorded

# When balance record is created:
def create_balance_record(client_exchange, date, remaining_balance):
    capital_at_time = get_capital(client_exchange)  # Current CAPITAL
    loss_at_time = max(capital_at_time - remaining_balance, 0)
    
    BalanceRecord.objects.create(
        client_exchange=client_exchange,
        date=date,
        remaining_balance=remaining_balance,
        capital_at_balance_time=capital_at_time,
        loss_at_balance_time=loss_at_time
    )

# LOSS for settlement is from balance record:
def get_loss_for_settlement(balance_record_id):
    balance_record = BalanceRecord.objects.get(pk=balance_record_id)
    return balance_record.loss_at_balance_time  # ✅ Loss at that specific time
```

---

### **CRITICAL-2: LossSnapshot Creation is Undefined**

**❌ Problem**: LossSnapshot creation rule is not defined.

**💥 Why Critical**: If multiple balance records exist or loss already partially settled, lookup can fail.

**✅ Mandatory Fix**:
```python
class LossSnapshot(models.Model):
    client_exchange = ForeignKey(ClientExchange)
    balance_record = OneToOneField(BalanceRecord)  # ✅ One-to-one with balance record
    loss_amount = DecimalField()
    capital_at_loss_time = DecimalField()
    my_share_pct = DecimalField()  # ✅ Frozen at creation
    company_share_pct = DecimalField()  # ✅ Frozen at creation
    created_at = DateTimeField(auto_now_add=True)
    is_settled = BooleanField(default=False)

# Exact creation rule:
def create_loss_snapshot_if_needed(balance_record):
    """
    Create LossSnapshot when:
    - CB drops below CAPITAL (loss occurs)
    - AND previous LOSS = 0 (new loss, not continuation)
    """
    client_exchange = balance_record.client_exchange
    capital_at_time = balance_record.capital_at_balance_time
    cb_at_time = balance_record.remaining_balance
    
    # Check if loss exists
    loss_at_time = max(capital_at_time - cb_at_time, 0)
    
    if loss_at_time > 0:
        # Check if this is a new loss (previous LOSS = 0)
        previous_balance = BalanceRecord.objects.filter(
            client_exchange=client_exchange,
            date__lt=balance_record.date
        ).order_by('-date').first()
        
        if previous_balance:
            previous_loss = previous_balance.loss_at_balance_time
            if previous_loss > 0:
                # Loss continues from previous - don't create new snapshot
                return None
        
        # New loss - create snapshot
        my_share_pct = client_exchange.my_share_pct or Decimal(0)
        if client_exchange.client.is_company_client:
            company_share_pct = Decimal(9)
            my_share_pct_effective = Decimal(1)
        else:
            company_share_pct = Decimal(0)
            my_share_pct_effective = my_share_pct
        
        LossSnapshot.objects.create(
            client_exchange=client_exchange,
            balance_record=balance_record,  # ✅ One-to-one
            loss_amount=loss_at_time,
            capital_at_loss_time=capital_at_time,
            my_share_pct=my_share_pct_effective,
            company_share_pct=company_share_pct,
            is_settled=False
        )
```

---

### **CRITICAL-3: PROFIT Path is Incomplete (Asymmetric Design)**

**❌ Problem**: PROFIT only has auto-close mention, no snapshot, no ledger event, no settlement path.

**💥 Why Critical**: Profit withdrawal will reuse `CB - CAPITAL`, but CAPITAL changes over time → profit meaning changes retroactively.

**✅ Mandatory Fix**:
```python
# Option A: ProfitSnapshot (symmetric to LossSnapshot)
class ProfitSnapshot(models.Model):
    client_exchange = ForeignKey(ClientExchange)
    balance_record = OneToOneField(BalanceRecord)
    profit_amount = DecimalField()
    capital_at_profit_time = DecimalField()
    created_at = DateTimeField(auto_now_add=True)
    is_withdrawn = BooleanField(default=False)

# Option B: Profit is always withdrawn immediately (no pending state)
def handle_profit(client_exchange, balance_record):
    """
    Profit must be withdrawn immediately when detected.
    No pending profit state allowed.
    """
    capital = get_capital(client_exchange)
    cb = balance_record.remaining_balance
    profit = max(cb - capital, 0)
    
    if profit > 0:
        # Auto-withdraw profit immediately
        Transaction.objects.create(
            client_exchange=client_exchange,
            transaction_type=Transaction.TYPE_PROFIT_WITHDRAWAL,
            amount=profit,
            balance_record_id=balance_record.id,
            note="Auto-withdraw profit on balance update"
        )
        # Update CB
        balance_record.remaining_balance = capital
        balance_record.save()
```

**Recommended**: Option B (immediate withdrawal) - simpler and safer.

---

### **CRITICAL-4: Auto-Close Settlement Changes CAPITAL Without Share Accounting**

**❌ Problem**: Auto-close closes CAPITAL but does not split shares for company clients.

**💥 Why Critical**: Breaks `Σ(client payments) = Σ(your share + company share)`

**✅ Mandatory Fix**:
```python
# Auto-close must still allocate shares
if loss_current < AUTO_CLOSE_THRESHOLD:
    # Get share % from loss snapshot
    loss_snapshot = LossSnapshot.objects.get(
        balance_record_id=balance_record_id
    )
    
    my_share_pct = loss_snapshot.my_share_pct
    company_share_pct = loss_snapshot.company_share_pct
    
    # Calculate shares even for auto-close
    your_share_amount = (loss_current * my_share_pct) / 100
    company_share_amount = (loss_current * company_share_pct) / 100
    
    # Create settlement with share allocation
    Transaction.objects.create(
        transaction_type=Transaction.TYPE_SETTLEMENT,
        amount=Decimal(0),  # No payment
        capital_closed=loss_current,
        your_share_amount=your_share_amount,  # ✅ Allocated
        company_share_amount=company_share_amount,  # ✅ Allocated
        balance_record_id=balance_record_id,
        note="Auto-close: LOSS < ₹0.01"
    )
```

---

### **CRITICAL-5: Payment Upper Bound Uses LOSS, Not ClientPayable**

**❌ Problem**: Validation uses capital space instead of share space.

**💥 Why Critical**: Client pays share space, not capital space. Client can overpay relative to share.

**✅ Correct Fix**:
```python
# Calculate ClientPayable (share space)
loss_snapshot = LossSnapshot.objects.get(
    balance_record_id=balance_record_id
)
total_share_pct = loss_snapshot.my_share_pct + loss_snapshot.company_share_pct
client_payable = (loss_snapshot.loss_amount * total_share_pct) / 100

# Validate in share space
if payment > client_payable:
    REJECT  # Payment exceeds ClientPayable

# Then convert to capital space for settlement
capital_closed_raw = (payment * 100) / total_share_pct
if capital_closed_raw > loss_snapshot.loss_amount:
    REJECT  # Also validate in capital space
```

---

### **CRITICAL-6: Funding During LOSS is Still Undefined**

**❌ Problem**: Funding during LOSS changes CB and LOSS meaning.

**💥 Why Critical**: Funding becomes a partial settlement without share accounting.

**✅ Mandatory Fix** (Choose ONE):

**Option A: Block Funding When LOSS > 0**
```python
def can_fund(client_exchange):
    # Get latest balance record
    latest_balance = BalanceRecord.objects.filter(
        client_exchange=client_exchange
    ).order_by('-date').first()
    
    if latest_balance and latest_balance.loss_at_balance_time > 0:
        return False, "Cannot fund while LOSS exists. Settle loss first."
    
    return True, None
```

**Option B: Separate Principal Buckets**
```python
class FundingBucket(models.Model):
    client_exchange = ForeignKey(ClientExchange)
    amount = DecimalField()
    loss_at_funding = DecimalField()  # LOSS when funding occurred
    is_settled = BooleanField(default=False)

# CAPITAL = sum of all unsettled funding buckets
# LOSS is calculated per bucket
```

**Recommended**: Option A (block funding) - simpler and safer.

---

### **CRITICAL-7: Invariant Enforcement is Undefined**

**❌ Problem**: `enforce_invariants()` is a placeholder, not a rule.

**💥 Why Critical**: Without hard failure, corruption persists silently.

**✅ Mandatory Fix**:
```python
def enforce_invariants(client_exchange):
    """
    Hard assertions that MUST pass after every write operation.
    If any fails, raise exception and rollback transaction.
    """
    capital = get_capital(client_exchange)  # From ledger
    cb = get_exchange_balance(client_exchange)
    loss = max(capital - cb, 0)
    profit = max(cb - capital, 0)
    
    # Invariant 1: CAPITAL conservation
    total_funding = Transaction.objects.filter(
        client_exchange=client_exchange,
        transaction_type=Transaction.TYPE_FUNDING
    ).aggregate(Sum('amount'))['amount__sum'] or Decimal(0)
    
    total_capital_closed = Transaction.objects.filter(
        client_exchange=client_exchange,
        transaction_type=Transaction.TYPE_SETTLEMENT
    ).aggregate(Sum('capital_closed'))['capital_closed__sum'] or Decimal(0)
    
    derived_capital = total_funding - total_capital_closed
    
    if abs(capital - derived_capital) > Decimal("0.01"):
        raise ValueError(
            f"Invariant violation: CAPITAL={capital} != derived={derived_capital}"
        )
    
    # Invariant 2: LOSS > 0 ⇒ CAPITAL > CB
    if loss > 0 and capital <= cb:
        raise ValueError(
            f"Invariant violation: LOSS={loss} but CAPITAL={capital} <= CB={cb}"
        )
    
    # Invariant 3: PROFIT > 0 ⇒ CB > CAPITAL
    if profit > 0 and cb <= capital:
        raise ValueError(
            f"Invariant violation: PROFIT={profit} but CB={cb} <= CAPITAL={capital}"
        )
    
    # Invariant 4: LOSS = 0 and PROFIT = 0 ⇒ CAPITAL = CB
    if loss == 0 and profit == 0:
        if abs(capital - cb) > Decimal("0.01"):
            raise ValueError(
                f"Invariant violation: LOSS=0, PROFIT=0, but CAPITAL={capital} != CB={cb}"
            )
    
    # Invariant 5: LOSS and PROFIT are mutually exclusive
    if loss > 0 and profit > 0:
        raise ValueError(
            f"Invariant violation: Both LOSS={loss} and PROFIT={profit} exist"
        )
    
    # Invariant 6: Share conservation
    settlements = Transaction.objects.filter(
        client_exchange=client_exchange,
        transaction_type=Transaction.TYPE_SETTLEMENT
    )
    
    total_your_share = settlements.aggregate(
        Sum('your_share_amount')
    )['your_share_amount__sum'] or Decimal(0)
    
    total_company_share = settlements.aggregate(
        Sum('company_share_amount')
    )['company_share_amount__sum'] or Decimal(0)
    
    total_capital_closed = settlements.aggregate(
        Sum('capital_closed')
    )['capital_closed__sum'] or Decimal(0)
    
    if abs(total_your_share + total_company_share - total_capital_closed) > Decimal("0.01"):
        raise ValueError(
            f"Invariant violation: Shares don't sum to capital_closed"
        )
    
    return True
```

---

### **CRITICAL-8: LOSS Can Exist Without Trade (CB Unchanged)**

**❌ Problem**: LOSS is derived from `CAPITAL − CB`, not trade delta. CAPITAL reduced by settlement, CB unchanged → phantom loss.

**💥 Why Critical**: Creates phantom loss with no trading activity.

**✅ Correct Fix**:
```python
# LOSS must only be created by balance records, never by settlements
def create_balance_record(client_exchange, date, remaining_balance):
    """
    LOSS can only be created when balance record is created (trading activity).
    Settlements never create new LOSS.
    """
    capital_at_time = get_capital(client_exchange)
    cb_at_time = remaining_balance
    
    # Calculate loss at this balance time
    loss_at_time = max(capital_at_time - cb_at_time, 0)
    
    # Create balance record
    balance_record = BalanceRecord.objects.create(
        client_exchange=client_exchange,
        date=date,
        remaining_balance=remaining_balance,
        capital_at_balance_time=capital_at_time,
        loss_at_balance_time=loss_at_time
    )
    
    # Create loss snapshot if new loss occurred
    if loss_at_time > 0:
        create_loss_snapshot_if_needed(balance_record)
    
    return balance_record

# Settlement never creates new LOSS
def settle_payment(client_exchange_id, payment, balance_record_id):
    """
    Settlement only reduces existing LOSS, never creates new LOSS.
    """
    balance_record = BalanceRecord.objects.get(pk=balance_record_id)
    loss_snapshot = LossSnapshot.objects.get(balance_record=balance_record)
    
    # Use loss from snapshot (frozen at balance time)
    loss_current = loss_snapshot.loss_amount  # ✅ From snapshot, not CAPITAL - CB
    
    # ... settlement logic ...
    
    # After settlement, update snapshot
    loss_snapshot.loss_amount = loss_new
    if loss_new == 0:
        loss_snapshot.is_settled = True
    loss_snapshot.save()
```

---

## 🔄 CORRECTED ARCHITECTURE

### **Balance-Record-Driven LOSS Model**

```python
# ✅ CORRECT: LOSS is tied to balance record
class BalanceRecord(models.Model):
    client_exchange = ForeignKey(ClientExchange)
    date = DateField()
    remaining_balance = DecimalField()
    capital_at_balance_time = DecimalField()  # ✅ Frozen at balance time
    loss_at_balance_time = DecimalField()  # ✅ Frozen at balance time

class LossSnapshot(models.Model):
    client_exchange = ForeignKey(ClientExchange)
    balance_record = OneToOneField(BalanceRecord)  # ✅ One-to-one
    loss_amount = DecimalField()
    capital_at_loss_time = DecimalField()
    my_share_pct = DecimalField()  # ✅ Frozen at creation
    company_share_pct = DecimalField()  # ✅ Frozen at creation
    is_settled = BooleanField(default=False)

# LOSS for settlement comes from snapshot, not global CAPITAL
def get_loss_for_settlement(balance_record_id):
    loss_snapshot = LossSnapshot.objects.get(
        balance_record_id=balance_record_id
    )
    return loss_snapshot.loss_amount  # ✅ From snapshot
```

### **Corrected Settlement Flow**

```python
@transaction.atomic
def settle_payment(client_exchange_id, payment, balance_record_id):
    # Lock for concurrency
    client_exchange = ClientExchange.objects.select_for_update().get(
        pk=client_exchange_id
    )
    
    # Check idempotency
    settlement_id = generate_unique_id(client_exchange_id, balance_record_id, payment)
    if Transaction.objects.filter(settlement_id=settlement_id).exists():
        return {"status": "duplicate"}
    
    # Get balance record
    balance_record = BalanceRecord.objects.get(pk=balance_record_id)
    
    # Get loss snapshot (CRITICAL-1: From snapshot, not global CAPITAL)
    loss_snapshot = LossSnapshot.objects.get(
        balance_record=balance_record
    )
    
    # Use loss from snapshot
    loss_current = loss_snapshot.loss_amount  # ✅ From snapshot
    
    # Validate loss exists
    if loss_current == 0 or loss_snapshot.is_settled:
        REJECT  # Loss already settled
    
    # Get share % from snapshot (CRITICAL-2: Frozen at creation)
    my_share_pct = loss_snapshot.my_share_pct
    company_share_pct = loss_snapshot.company_share_pct
    total_share_pct = my_share_pct + company_share_pct
    
    # CRITICAL-5: Validate in share space first
    client_payable = (loss_current * total_share_pct) / 100
    if payment > client_payable:
        REJECT  # Payment exceeds ClientPayable
    
    # Convert to capital space
    capital_closed_raw = (payment * 100) / total_share_pct
    
    # Validate in capital space
    if capital_closed_raw > loss_current:
        REJECT
    
    # Round
    capital_closed = capital_closed_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    # Reduce LOSS
    loss_new = loss_current - capital_closed
    
    # Guard against negative
    if loss_new < 0:
        REJECT
    
    # Apply auto-close
    if loss_new < Decimal("0.01"):
        capital_closed += loss_new  # Close remaining
        loss_new = Decimal(0)
    
    # Calculate shares (CRITICAL-4: Even for auto-close)
    your_share_amount = (capital_closed * my_share_pct) / 100
    company_share_amount = (capital_closed * company_share_pct) / 100
    
    # Create settlement event
    Transaction.objects.create(
        transaction_type=Transaction.TYPE_SETTLEMENT,
        settlement_id=settlement_id,
        amount=payment,
        capital_closed=capital_closed,
        your_share_amount=your_share_amount,  # ✅ Allocated
        company_share_amount=company_share_amount,  # ✅ Allocated
        balance_record_id=balance_record_id
    )
    
    # Update loss snapshot
    loss_snapshot.loss_amount = loss_new
    if loss_new == 0:
        loss_snapshot.is_settled = True
    loss_snapshot.save()
    
    # CRITICAL-7: Enforce invariants
    enforce_invariants(client_exchange)
    
    return {"status": "success"}
```

---

## 📋 INVARIANT CHECKLIST (MANDATORY)

### **After Every Write Operation**

```python
def enforce_all_invariants(client_exchange):
    """
    Hard assertions that MUST pass. If any fails, raise exception.
    """
    capital = get_capital(client_exchange)
    cb = get_exchange_balance(client_exchange)
    loss = max(capital - cb, 0)
    profit = max(cb - capital, 0)
    
    # 1. CAPITAL conservation
    total_funding = get_total_funding(client_exchange)
    total_capital_closed = get_total_capital_closed(client_exchange)
    derived_capital = total_funding - total_capital_closed
    assert abs(capital - derived_capital) <= Decimal("0.01")
    
    # 2. LOSS > 0 ⇒ CAPITAL > CB
    if loss > 0:
        assert capital > cb
    
    # 3. PROFIT > 0 ⇒ CB > CAPITAL
    if profit > 0:
        assert cb > capital
    
    # 4. LOSS = 0 and PROFIT = 0 ⇒ CAPITAL = CB
    if loss == 0 and profit == 0:
        assert abs(capital - cb) <= Decimal("0.01")
    
    # 5. LOSS and PROFIT are mutually exclusive
    assert not (loss > 0 and profit > 0)
    
    # 6. Share conservation
    total_your_share = get_total_your_share(client_exchange)
    total_company_share = get_total_company_share(client_exchange)
    total_capital_closed = get_total_capital_closed(client_exchange)
    assert abs(total_your_share + total_company_share - total_capital_closed) <= Decimal("0.01")
    
    return True
```

---

## 🎯 SUMMARY

### **Key Architectural Changes**

1. **LOSS is balance-record-driven** - Not from global CAPITAL
2. **LossSnapshot created at balance time** - With exact rules
3. **PROFIT handled immediately** - No pending profit state
4. **Auto-close allocates shares** - Even for ₹0 payment
5. **Payment validated in share space** - ClientPayable is authoritative
6. **Funding blocked during LOSS** - Or separate buckets
7. **Invariants enforced** - Hard assertions after every write
8. **LOSS only from balance records** - Never from settlements

### **Critical Rules**

```
✅ LOSS = loss_snapshot.loss_amount (from snapshot, not CAPITAL - CB)
✅ LossSnapshot created when CB drops below CAPITAL AND previous LOSS = 0
✅ PROFIT withdrawn immediately (no pending state)
✅ Auto-close allocates shares (your_share_amount + company_share_amount)
✅ Payment validated: payment <= ClientPayable (share space)
✅ Funding blocked when LOSS > 0
✅ Invariants enforced after every write
✅ LOSS only created by balance records, never by settlements
```

---

**Document Version**: 8.0  
**Last Updated**: 2026-01-05  
**Status**: ✅ All 8 Causal Errors Fixed, Balance-Record-Driven Architecture


