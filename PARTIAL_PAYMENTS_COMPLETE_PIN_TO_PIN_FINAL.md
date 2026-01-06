# PARTIAL PAYMENTS - COMPLETE PIN TO PIN GUIDE

**Everything Explained: How Partial Payments Work, All Formulas, Display Rules, Complete Flow**

---

## 📋 TABLE OF CONTENTS

1. [Core Definitions & What They Mean](#core-definitions)
2. [Fundamental Formulas (All Calculations)](#fundamental-formulas)
3. [How Partial Payments Work (Step-by-Step)](#partial-payments-flow)
4. [Pending Payments Calculation & Display](#pending-payments)
5. [Share Calculations (My Share vs Company Share)](#share-calculations)
6. [How Everything is Displayed in UI](#ui-display)
7. [Complete Examples (Real Scenarios)](#complete-examples)
8. [State Management & Invariants](#state-management)

---

## 🔑 CORE DEFINITIONS

### **CAPITAL (C) / Old Balance**
- **What It Is**: Total money you have put into the exchange that is not yet settled
- **Formula**: `CAPITAL = Σ(FUNDING) − Σ(CAPITAL_CLOSED)` (always derived from ledger)
- **Database**: `ClientExchange.cached_old_balance` (cache, ledger is source of truth)
- **When It Changes**:
  - ✅ On settlement (recomputed from ledger)
  - ✅ On funding (added to ledger)
  - ❌ NEVER on profit withdrawal
- **Display**: Shown as "Old Balance" in UI, rounded to 2 decimals

### **Current Balance (CB)**
- **What It Is**: Actual exchange balance from `BALANCE_RECORD`
- **Database**: `ClientDailyBalance.remaining_balance`
- **When It Changes**:
  - ✅ On new `BALANCE_RECORD` creation (trading activity)
  - ✅ On profit withdrawal (decreases CB)
  - ✅ On funding (when auto-credited by exchange)
- **Display**: Shown as "Current Balance" in UI, rounded to 2 decimals
- **Important**: For pending display, CB comes from `loss_snapshot.balance_record` (causal consistency)

### **LOSS**
- **Formula**: `LOSS = max(CAPITAL - CB, 0)`
- **Meaning**: Client's receivable (money client owes you)
- **When It Exists**: Only when `CAPITAL > CB`
- **Source**: From `LossSnapshot.loss_amount` (frozen at balance time, not global CAPITAL)
- **Auto-Close**: If `LOSS < ₹0.01`, auto-closed to ₹0.00 (with settlement event)
- **Display**: Used to calculate pending amounts

### **PROFIT**
- **Formula**: `PROFIT = max(CB - CAPITAL, 0)`
- **Meaning**: Your liability (money you owe client)
- **When It Exists**: Only when `CB > CAPITAL`
- **Handling**: Withdrawn immediately when detected (atomic flag `profit_consumed`)
- **Auto-Close**: If `PROFIT < ₹0.01`, auto-closed to ₹0.00 (with adjustment event)
- **Display**: Shown in "You Owe Clients" section (rarely shown, withdrawn immediately)

### **NET Movement**
- **Formula**: `NET = CB - CAPITAL`
- **Meaning**: Informational only (signed difference)
- **Usage**: NOT used in business logic, only for display/reporting
- **Display**: Shows direction of movement (positive = profit, negative = loss)

---

## 📐 FUNDAMENTAL FORMULAS

### **🧠 GOLDEN FORMULAS (All Calculations)**

```python
# Core calculations (exact, 2 decimals)
LOSS = max(CAPITAL - CB, 0)
PROFIT = max(CB - CAPITAL, 0)
NET = CB - CAPITAL  # Informational only

# CAPITAL (always derived from ledger, never assigned)
CAPITAL = Σ(FUNDING) − Σ(CAPITAL_CLOSED)

# Receivables (share space)
ClientPayable = LOSS × total_share_pct / 100
YourReceivable = LOSS × my_share_pct / 100
CompanyReceivable = LOSS × company_share_pct / 100

# Auto-close threshold
AUTO_CLOSE_THRESHOLD = Decimal("0.01")
```

### **Share Space vs Capital Space**

**Share Space**: What client pays (in ₹)
- `ClientPayable = LOSS × total_share_pct / 100`
- Example: LOSS = 60, total_share_pct = 10% → ClientPayable = ₹6

**Capital Space**: What LOSS is reduced by (in ₹)
- `capital_closed = payment × 100 / total_share_pct`
- Example: payment = ₹3, total_share_pct = 10% → capital_closed = ₹30

**Conversion**:
- Share → Capital: `capital = (share × 100) / share_pct`
- Capital → Share: `share = (capital × share_pct) / 100`

---

## 🔄 PARTIAL PAYMENTS FLOW

### **Complete Step-by-Step Process**

```python
@transaction.atomic
def settle_payment(client_exchange_id, payment, balance_record_id):
    """
    Complete partial payment settlement flow
    """
    # STEP 1: Lock for concurrency
    client_exchange = ClientExchange.objects.select_for_update().get(
        pk=client_exchange_id
    )
    
    # STEP 2: Get balance record and loss snapshot
    balance_record = BalanceRecord.objects.get(pk=balance_record_id)
    loss_snapshot = LossSnapshot.objects.get(balance_record=balance_record)
    
    # STEP 3: Generate deterministic settlement ID (idempotency)
    payment_normalized = payment.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    key_string = f"{client_exchange_id}_{balance_record_id}_{payment_normalized}_{loss_snapshot.id}"
    settlement_id = hashlib.sha256(key_string.encode()).hexdigest()
    
    # STEP 4: Check idempotency (prevent double settlement)
    existing_settlement = Transaction.objects.filter(
        settlement_id=settlement_id
    ).first()
    
    if existing_settlement:
        return {"status": "duplicate", "message": "Already processed"}
    
    # STEP 5: Get current LOSS from snapshot
    loss_current = loss_snapshot.loss_amount
    
    # STEP 6: Validate loss exists
    if loss_current == 0 or loss_snapshot.is_settled:
        raise ValidationError("No loss to settle")
    
    # STEP 7: Get shares from snapshot (frozen at LOSS creation)
    my_share_pct = loss_snapshot.my_share_pct
    company_share_pct = loss_snapshot.company_share_pct
    total_share_pct = my_share_pct + company_share_pct
    
    # STEP 8: Validate payment in share space
    client_payable = (loss_current * total_share_pct) / 100
    if payment > client_payable:
        raise ValidationError(f"Payment {payment} exceeds ClientPayable {client_payable}")
    
    # STEP 9: Convert payment to capital space
    capital_closed_raw = (payment * 100) / total_share_pct
    
    # STEP 10: Validate capital_closed doesn't exceed LOSS
    if capital_closed_raw > loss_current:
        raise ValidationError(f"Capital closed {capital_closed_raw} exceeds LOSS {loss_current}")
    
    # STEP 11: Check CAPITAL cannot go negative
    total_funding = get_total_funding(client_exchange)
    total_capital_closed = get_total_capital_closed(client_exchange)
    if total_capital_closed + capital_closed_raw > total_funding:
        raise ValidationError("Settlement would make CAPITAL negative")
    
    # STEP 12: Round capital_closed
    capital_closed = capital_closed_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    # STEP 13: Reduce LOSS (LOSS-first approach)
    loss_new = loss_current - capital_closed
    if loss_new < 0:
        raise ValidationError("Settlement would create negative LOSS")
    
    # STEP 14: Auto-close if LOSS < ₹0.01
    if loss_new < Decimal("0.01"):
        capital_closed = loss_current
        loss_new = Decimal(0)
    
    # STEP 15: Calculate share amounts
    your_share_amount = (capital_closed * my_share_pct) / 100
    company_share_amount = (capital_closed * company_share_pct) / 100
    
    # STEP 16: Get CB snapshot (for CAPITAL recalculation)
    cb_snapshot = balance_record.remaining_balance
    
    # STEP 17: Re-derive CAPITAL (LOSS-first approach)
    if loss_new == 0:
        # Full settlement
        capital_new = cb_snapshot
    else:
        # Partial settlement
        capital_new = cb_snapshot + loss_new
    
    # STEP 18: Validate CAPITAL_new >= CB (prevent LOSS → PROFIT flip)
    if loss_new > Decimal("0.01") and capital_new < cb_snapshot:
        raise ValidationError("Settlement would flip LOSS to PROFIT")
    
    # STEP 19: Create settlement transaction
    Transaction.objects.create(
        transaction_type=Transaction.TYPE_SETTLEMENT,
        settlement_id=settlement_id,
        amount=payment,
        capital_closed=capital_closed,
        your_share_amount=your_share_amount,
        company_share_amount=company_share_amount,
        balance_record_id=balance_record_id,
        client_exchange=client_exchange
    )
    
    # STEP 20: Update loss snapshot
    loss_snapshot.loss_amount = loss_new
    if loss_new == 0:
        loss_snapshot.is_settled = True
    loss_snapshot.save()
    
    # STEP 21: Update cached CAPITAL
    client_exchange.cached_old_balance = capital_new
    client_exchange.save()
    
    # STEP 22: Enforce invariants (aborts if violation)
    enforce_invariants(client_exchange)
    
    return {"status": "success", "loss_remaining": loss_new}
```

### **Key Points in Partial Payment Flow**

1. **LOSS-First Approach**: Always reduce LOSS first, then re-derive CAPITAL
2. **Deterministic Idempotency**: Settlement ID is hash of inputs, not random UUID
3. **Share Space Validation**: Payment validated against `ClientPayable` (share space)
4. **Capital Space Conversion**: Payment converted to `capital_closed` (capital space)
5. **Auto-Close**: LOSS < ₹0.01 automatically closed to ₹0.00
6. **Invariant Enforcement**: All invariants checked before commit

---

## 💰 PENDING PAYMENTS

### **What is Pending?**

**Pending** = Money client owes you (unrealized settlement obligation)

- **Exists Only When**: `LOSS > 0`
- **Never Exists For**: PROFIT (profit is withdrawn immediately)
- **Formula**: `Pending = LOSS × total_share_pct / 100`

### **Pending Calculation**

```python
def calculate_pending(client_exchange):
    """
    Calculate pending payments (what client owes)
    """
    # Get active loss snapshot
    loss_snapshot = LossSnapshot.objects.filter(
        client_exchange=client_exchange,
        is_settled=False
    ).first()
    
    if not loss_snapshot:
        # No active loss → no pending
        return {
            "client_payable": Decimal(0),
            "your_receivable": Decimal(0),
            "company_receivable": Decimal(0),
            "loss_amount": Decimal(0)
        }
    
    # Get LOSS from snapshot
    loss_amount = loss_snapshot.loss_amount
    
    # Get shares from snapshot (frozen)
    my_share_pct = loss_snapshot.my_share_pct
    company_share_pct = loss_snapshot.company_share_pct
    total_share_pct = my_share_pct + company_share_pct
    
    # Calculate receivables (share space)
    client_payable = (loss_amount * total_share_pct) / 100
    your_receivable = (loss_amount * my_share_pct) / 100
    company_receivable = (loss_amount * company_share_pct) / 100
    
    # Round to 2 decimals
    client_payable = client_payable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    your_receivable = your_receivable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    company_receivable = company_receivable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    return {
        "client_payable": client_payable,
        "your_receivable": your_receivable,
        "company_receivable": company_receivable,
        "loss_amount": loss_amount
    }
```

### **Pending Display Rules**

1. **Show Pending Only When**: `LOSS > 0`
2. **Hide Pending When**: `LOSS == 0` or `LOSS < ₹0.01` (auto-closed)
3. **Display Format**: 
   - "Client Payable: ₹X.XX"
   - "Your Receivable: ₹X.XX"
   - "Company Receivable: ₹X.XX" (for company clients)

---

## 📊 SHARE CALCULATIONS

### **My Share vs Company Share**

**For My Clients**:
- `my_share_pct = 10%` (example)
- `company_share_pct = 0%`
- `total_share_pct = 10%`
- Client pays: `LOSS × 10%`
- You receive: `LOSS × 10%`
- Company receives: `₹0`

**For Company Clients**:
- `my_share_pct = 1%` (your cut)
- `company_share_pct = 9%` (company cut)
- `total_share_pct = 10%` (what client pays)
- Client pays: `LOSS × 10%`
- You receive: `LOSS × 1%`
- Company receives: `LOSS × 9%`

### **Share Calculation Formula**

```python
# Total share (what client pays)
total_share_pct = my_share_pct + company_share_pct

# Client payable (share space)
client_payable = LOSS × total_share_pct / 100

# Your receivable (share space)
your_receivable = LOSS × my_share_pct / 100

# Company receivable (share space)
company_receivable = LOSS × company_share_pct / 100

# Conversion: Share space → Capital space
capital_closed = payment × 100 / total_share_pct

# Your share in capital space
your_share_capital = capital_closed × my_share_pct / 100

# Company share in capital space
company_share_capital = capital_closed × company_share_pct / 100
```

### **Share Freezing**

**Critical Rule**: Share percentages are **frozen at LOSS creation time**, not at settlement time.

- When `LossSnapshot` is created, it stores:
  - `my_share_pct` (frozen)
  - `company_share_pct` (frozen)
- All settlements use these frozen percentages
- Even if share config changes later, old LOSS uses old percentages

---

## 🖥️ UI DISPLAY

### **How Values Are Shown**

#### **1. Old Balance (CAPITAL)**
- **Source**: `ClientExchange.cached_old_balance`
- **Display**: "Old Balance: ₹X.XX"
- **Rounding**: 2 decimals
- **Update**: On funding, on settlement

#### **2. Current Balance (CB)**
- **Source**: `ClientDailyBalance.remaining_balance` (latest)
- **Display**: "Current Balance: ₹X.XX"
- **Rounding**: 2 decimals
- **Update**: On balance record, on profit withdrawal

#### **3. Pending Amount**
- **Source**: Calculated from `LossSnapshot`
- **Display**: 
  - "Client Payable: ₹X.XX"
  - "Your Receivable: ₹X.XX"
  - "Company Receivable: ₹X.XX" (if company client)
- **Show When**: `LOSS > 0`
- **Hide When**: `LOSS == 0`

#### **4. Loss Amount**
- **Source**: `LossSnapshot.loss_amount`
- **Display**: "Loss: ₹X.XX"
- **Show When**: `LOSS > 0`
- **Hide When**: `LOSS == 0`

#### **5. Profit Amount**
- **Source**: Calculated as `max(CB - CAPITAL, 0)`
- **Display**: "Profit: ₹X.XX" (rarely shown, withdrawn immediately)
- **Show When**: `PROFIT > 0` and not yet withdrawn
- **Hide When**: `PROFIT == 0` or withdrawn

#### **6. NET Movement**
- **Source**: `CB - CAPITAL`
- **Display**: "NET: ₹X.XX" (signed, positive = profit, negative = loss)
- **Usage**: Informational only, not used in business logic

### **UI Display Rules**

1. **Causal Consistency**: CB shown from `loss_snapshot.balance_record` when LOSS exists
2. **Rounding**: All amounts rounded to 2 decimals for display
3. **Auto-Hide**: Values < ₹0.01 auto-hidden (treated as ₹0.00)
4. **Color Coding**: 
   - Red: Loss/Pending (client owes)
   - Green: Profit (you owe)
   - Black: Break-even

---

## 📖 COMPLETE EXAMPLES

### **Example 1: Simple Partial Payment**

**Initial State**:
- CAPITAL = ₹100
- CB = ₹40
- LOSS = ₹60
- total_share_pct = 10%
- ClientPayable = ₹6

**Client Pays ₹3 (Partial)**:
1. Payment = ₹3 (share space)
2. capital_closed = ₹3 × 100 / 10 = ₹30 (capital space)
3. loss_new = ₹60 - ₹30 = ₹30
4. CAPITAL_new = ₹40 + ₹30 = ₹70
5. Your share = ₹30 × 1% / 100 = ₹0.30 (if company client)

**Final State**:
- CAPITAL = ₹70
- CB = ₹40
- LOSS = ₹30
- ClientPayable = ₹3

### **Example 2: Full Settlement**

**Initial State**:
- CAPITAL = ₹100
- CB = ₹40
- LOSS = ₹60
- ClientPayable = ₹6

**Client Pays ₹6 (Full)**:
1. Payment = ₹6 (share space)
2. capital_closed = ₹6 × 100 / 10 = ₹60 (capital space)
3. loss_new = ₹60 - ₹60 = ₹0
4. CAPITAL_new = ₹40 (full settlement)
5. Auto-close: LOSS = ₹0 → settled

**Final State**:
- CAPITAL = ₹40
- CB = ₹40
- LOSS = ₹0
- ClientPayable = ₹0

### **Example 3: Multiple Partial Payments**

**Initial State**:
- CAPITAL = ₹100
- CB = ₹40
- LOSS = ₹60
- ClientPayable = ₹6

**Payment 1: ₹2**:
- capital_closed = ₹20
- loss_new = ₹40
- CAPITAL_new = ₹80

**Payment 2: ₹2**:
- capital_closed = ₹20
- loss_new = ₹20
- CAPITAL_new = ₹60

**Payment 3: ₹2**:
- capital_closed = ₹20
- loss_new = ₹0
- CAPITAL_new = ₹40 (full settlement)

### **Example 4: Company Client Share Split**

**Initial State**:
- CAPITAL = ₹100
- CB = ₹40
- LOSS = ₹60
- my_share_pct = 1%
- company_share_pct = 9%
- total_share_pct = 10%
- ClientPayable = ₹6

**Client Pays ₹6 (Full)**:
- capital_closed = ₹60
- Your share = ₹60 × 1% / 100 = ₹0.60
- Company share = ₹60 × 9% / 100 = ₹5.40
- Total = ₹0.60 + ₹5.40 = ₹6.00 ✓

---

## 🔒 STATE MANAGEMENT

### **Invariants (6 Mandatory Rules)**

```python
def enforce_invariants(client_exchange):
    """
    Enforce all 6 invariants - aborts transaction on violation
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
    
    # Invariant 5: LOSS formula (LOSS == max(CAPITAL - CB, 0))
    if active_loss:
        balance_record = active_loss.balance_record
        cb_from_snapshot = balance_record.remaining_balance
        
        expected_loss = max(capital - cb_from_snapshot, Decimal("0.00"))
        actual_loss = active_loss.loss_amount
        
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

### **State Transitions**

**LOSS State**:
- Created: When CB drops below CAPITAL
- Reduced: On partial settlement
- Closed: On full settlement or auto-close (< ₹0.01)
- Blocked: Trading and funding blocked when LOSS exists

**PROFIT State**:
- Created: When CB rises above CAPITAL
- Withdrawn: Immediately (atomic flag)
- Closed: Auto-close if < ₹0.01

**CAPITAL State**:
- Increased: On funding
- Decreased: On settlement (LOSS case)
- Unchanged: On profit withdrawal

---

## 🎯 SUMMARY

### **Key Rules**

1. **LOSS-First Approach**: Always reduce LOSS first, then re-derive CAPITAL
2. **Deterministic Idempotency**: Settlement ID is hash of inputs, not random
3. **Share Freezing**: Share percentages frozen at LOSS creation
4. **Auto-Close**: LOSS < ₹0.01 automatically closed
5. **Invariant Enforcement**: All 6 invariants checked before commit
6. **Causal Consistency**: CB from `loss_snapshot.balance_record` when LOSS exists

### **Formulas Summary**

```
LOSS = max(CAPITAL - CB, 0)
PROFIT = max(CB - CAPITAL, 0)
CAPITAL = Σ(FUNDING) − Σ(CAPITAL_CLOSED)
ClientPayable = LOSS × total_share_pct / 100
capital_closed = payment × 100 / total_share_pct
```

### **Display Summary**

- **Old Balance**: CAPITAL (from cache)
- **Current Balance**: CB (from latest balance record)
- **Pending**: ClientPayable (from LossSnapshot)
- **Loss**: LossSnapshot.loss_amount
- **Profit**: max(CB - CAPITAL, 0) (withdrawn immediately)

---

**Document Version**: 12.0  
**Last Updated**: 2026-01-05  
**Status**: ✅ Complete Pin-to-Pin Guide, All Formulas, All Display Rules, Production-Safe


