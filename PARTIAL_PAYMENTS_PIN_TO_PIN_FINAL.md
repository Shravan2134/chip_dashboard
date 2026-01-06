# PARTIAL PAYMENTS - PIN TO PIN COMPLETE GUIDE

**Everything Explained: How Partial Payments Work, All Formulas, Display Rules**

---

## 📋 TABLE OF CONTENTS

1. [Core Definitions](#core-definitions)
2. [Fundamental Formulas](#fundamental-formulas)
3. [How Partial Payments Work](#partial-payments)
4. [Pending Payments Calculation](#pending-payments)
5. [Share Calculations](#share-calculations)
6. [How Everything is Displayed](#ui-display)
7. [Complete Examples](#examples)

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
- **Display**: Shown as "Old Balance: ₹X.XX" in UI

### **Current Balance (CB)**
- **What It Is**: Actual exchange balance from `BALANCE_RECORD`
- **Database**: `ClientDailyBalance.remaining_balance`
- **When It Changes**:
  - ✅ On new `BALANCE_RECORD` creation (trading activity)
  - ✅ On profit withdrawal (decreases CB)
  - ✅ On funding (when auto-credited by exchange)
- **Display**: Shown as "Current Balance: ₹X.XX" in UI
- **Important**: When LOSS exists, CB comes from `loss_snapshot.balance_record` (frozen)

### **LOSS**
- **Formula**: `LOSS = max(CAPITAL - CB, 0)`
- **Meaning**: Client's receivable (money client owes you)
- **When It Exists**: Only when `CAPITAL > CB`
- **Source**: From `LossSnapshot.loss_amount` (frozen at balance time, never recalculated)
- **Auto-Close**: If `LOSS < ₹0.01`, auto-closed to ₹0.00
- **Display**: Used to calculate pending amounts

### **PROFIT**
- **Formula**: `PROFIT = max(CB - CAPITAL, 0)`
- **Meaning**: Your liability (money you owe client)
- **When It Exists**: Only when `CB > CAPITAL`
- **Handling**: Withdrawn immediately when detected (atomic flag `profit_consumed`)
- **Auto-Close**: If `PROFIT < ₹0.01`, auto-closed to ₹0.00
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
# Core calculations (2 decimal precision)
LOSS = max(CAPITAL - CB, 0)
PROFIT = max(CB - CAPITAL, 0)
NET = CB - CAPITAL  # Informational only

# CAPITAL (always derived from ledger, never assigned)
CAPITAL = Σ(FUNDING) − Σ(CAPITAL_CLOSED)

# Receivables (share space - what client pays)
ClientPayable = LOSS × total_share_pct / 100
YourReceivable = LOSS × my_share_pct / 100
CompanyReceivable = LOSS × company_share_pct / 100

# Conversion: Share space → Capital space
capital_closed = payment × 100 / total_share_pct

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

## 🔄 HOW PARTIAL PAYMENTS WORK

### **Step-by-Step Process**

**Initial State**:
- CAPITAL = ₹100
- CB = ₹40
- LOSS = ₹60 (frozen in LossSnapshot)
- total_share_pct = 10% (frozen in LossSnapshot)
- ClientPayable = ₹6

**Client Pays ₹3 (Partial Payment)**:

1. **Payment Received**: ₹3 (share space)
2. **Validate Payment**: 
   - Check `payment <= ClientPayable` (₹3 <= ₹6) ✅
3. **Convert to Capital Space**: 
   - `capital_closed = ₹3 × 100 / 10 = ₹30`
4. **Validate Capital Closed**: 
   - Check `capital_closed <= LOSS` (₹30 <= ₹60) ✅
5. **Reduce LOSS** (LOSS-first approach): 
   - `loss_new = ₹60 - ₹30 = ₹30`
6. **Re-derive CAPITAL**: 
   - `CAPITAL_new = CB + loss_new = ₹40 + ₹30 = ₹70`
7. **Auto-Close Check**: 
   - `loss_new = ₹30` (>= ₹0.01) → No auto-close
8. **Calculate Shares**:
   - Your share = ₹30 × 1% / 100 = ₹0.30 (if company client)
   - Company share = ₹30 × 9% / 100 = ₹2.70 (if company client)
9. **Create Settlement Transaction**:
   - Record payment, capital_closed, shares
10. **Update LossSnapshot**:
    - `loss_amount = ₹30`
    - `is_settled = False` (still has remaining loss)
11. **Update Cached CAPITAL**:
    - `cached_old_balance = ₹70` (cache only, ledger is source)
12. **Enforce Invariants**:
    - Check all 6 invariants, abort if violated

**Final State**:
- CAPITAL = ₹70 (derived from ledger)
- CB = ₹40 (frozen from snapshot)
- LOSS = ₹30 (frozen in LossSnapshot)
- ClientPayable = ₹3

### **Complete Settlement Flow**

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
    
    # STEP 2: Get active loss snapshot (frozen LOSS)
    loss_snapshot = LossSnapshot.objects.get(
        client_exchange=client_exchange,
        is_settled=False
    )
    
    # STEP 3: Get frozen values from snapshot
    LOSS = loss_snapshot.loss_amount  # Frozen, never recalculated
    CB = loss_snapshot.balance_record.remaining_balance  # Frozen CB
    my_share_pct = loss_snapshot.my_share_pct  # Frozen shares
    company_share_pct = loss_snapshot.company_share_pct
    total_share_pct = my_share_pct + company_share_pct
    
    # STEP 4: Validate payment in share space
    client_payable = (LOSS * total_share_pct) / 100
    if payment > client_payable:
        raise ValidationError(f"Payment {payment} exceeds ClientPayable {client_payable}")
    
    # STEP 5: Convert payment to capital space
    capital_closed_raw = (payment * 100) / total_share_pct
    
    # STEP 6: Validate capital_closed doesn't exceed LOSS (validate raw first)
    if capital_closed_raw > LOSS:
        raise ValidationError(f"Capital closed {capital_closed_raw} exceeds LOSS {LOSS}")
    
    # STEP 7: Round capital_closed (after validation)
    capital_closed = capital_closed_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    # STEP 8: Reduce LOSS (LOSS-first approach)
    loss_new = LOSS - capital_closed
    
    # STEP 9: Auto-close if LOSS < ₹0.01
    if loss_new < Decimal("0.01"):
        capital_closed = LOSS
        loss_new = Decimal(0)
    
    # STEP 10: Re-derive CAPITAL (LOSS-first)
    if loss_new == 0:
        CAPITAL_new = CB  # Full settlement
    else:
        CAPITAL_new = CB + loss_new  # Partial settlement
    
    # STEP 11: Guard against LOSS → PROFIT flip
    if loss_new > Decimal("0.01") and CAPITAL_new < CB:
        raise ValidationError("Settlement would flip LOSS to PROFIT")
    
    # STEP 12: Calculate share amounts
    your_share_amount = (capital_closed * my_share_pct) / 100
    company_share_amount = (capital_closed * company_share_pct) / 100
    
    # STEP 13: Generate deterministic settlement ID
    settlement_id = generate_settlement_id(
        client_exchange_id,
        balance_record_id,
        payment,
        loss_snapshot.id
    )
    
    # STEP 14: Check idempotency
    if Transaction.objects.filter(settlement_id=settlement_id).exists():
        return {"status": "duplicate"}
    
    # STEP 15: Create settlement transaction
    Transaction.objects.create(
        transaction_type=Transaction.TYPE_SETTLEMENT,
        settlement_id=settlement_id,
        amount=payment,
        capital_closed=capital_closed,
        your_share_amount=your_share_amount,
        company_share_amount=company_share_amount,
        balance_record_id=balance_record_id
    )
    
    # STEP 16: Update loss snapshot
    loss_snapshot.loss_amount = loss_new
    if loss_new == 0:
        loss_snapshot.is_settled = True
    loss_snapshot.save()
    
    # STEP 17: Derive CAPITAL from ledger
    total_funding = get_total_funding(client_exchange)
    total_capital_closed = get_total_capital_closed(client_exchange)
    CAPITAL_derived = total_funding - total_capital_closed
    
    # STEP 18: Update cached CAPITAL (cache only, ledger is source)
    client_exchange.cached_old_balance = CAPITAL_derived
    client_exchange.save()
    
    # STEP 19: Enforce invariants (aborts if violated)
    enforce_invariants(client_exchange)
    
    return {"status": "success", "loss_remaining": loss_new}
```

---

## 💰 PENDING PAYMENTS

### **What is Pending?**

**Pending** = Money client owes you (unrealized settlement obligation)

- **Exists Only When**: `LOSS > 0`
- **Never Exists For**: PROFIT (profit is withdrawn immediately)
- **Formula**: `Pending = LOSS × total_share_pct / 100`
- **Source**: From frozen `LossSnapshot.loss_amount`, never recalculated

### **Pending Calculation**

```python
def calculate_pending(client_exchange):
    """
    Calculate pending payments (what client owes)
    Uses frozen LOSS from LossSnapshot, never recalculated
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
    
    # Get frozen LOSS from snapshot (never recalculated)
    LOSS = loss_snapshot.loss_amount
    
    # Get frozen shares from snapshot
    my_share_pct = loss_snapshot.my_share_pct
    company_share_pct = loss_snapshot.company_share_pct
    total_share_pct = my_share_pct + company_share_pct
    
    # Calculate receivables (share space)
    client_payable = (LOSS * total_share_pct) / 100
    your_receivable = (LOSS * my_share_pct) / 100
    company_receivable = (LOSS * company_share_pct) / 100
    
    # Round to 2 decimals
    client_payable = client_payable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    your_receivable = your_receivable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    company_receivable = company_receivable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    return {
        "client_payable": client_payable,
        "your_receivable": your_receivable,
        "company_receivable": company_receivable,
        "loss_amount": LOSS
    }
```

### **Pending Display Rules**

1. **Show Pending Only When**: `LOSS > 0` and `LOSS >= ₹0.01`
2. **Hide Pending When**: 
   - `LOSS == 0`
   - `LOSS < ₹0.01` (auto-closed)
   - `PROFIT > 0` (profit case, not loss)
3. **Display Format**: 
   - "Client Payable: ₹X.XX"
   - "Your Receivable: ₹X.XX"
   - "Company Receivable: ₹X.XX" (for company clients)
4. **Source**: Always from frozen `LossSnapshot`, never live calculation

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

### **Share Freezing (Critical Rule)**

**Critical Rule**: Share percentages are **frozen at LOSS creation time**, not at settlement time.

- When `LossSnapshot` is created, it stores:
  - `my_share_pct` (frozen)
  - `company_share_pct` (frozen)
  - `total_share_pct` (frozen)
- All settlements use these frozen percentages
- Even if share config changes later, old LOSS uses old percentages
- This ensures historical correctness and prevents disputes

---

## 🖥️ HOW EVERYTHING IS DISPLAYED

### **1. Old Balance (CAPITAL)**
- **Source**: `ClientExchange.cached_old_balance` (cache)
- **True Source**: Ledger (`Σ(FUNDING) − Σ(CAPITAL_CLOSED)`)
- **Display**: "Old Balance: ₹X.XX"
- **Rounding**: 2 decimals
- **Update**: On funding, on settlement
- **Label**: "(from ledger)" in UI

### **2. Current Balance (CB)**
- **Source**: 
  - When LOSS exists: `loss_snapshot.balance_record.remaining_balance` (frozen)
  - When no LOSS: `ClientDailyBalance.remaining_balance` (latest)
- **Display**: "Current Balance: ₹X.XX"
- **Rounding**: 2 decimals
- **Update**: On balance record, on profit withdrawal
- **Label**: "(from snapshot)" when LOSS exists, "(live)" when no LOSS

### **3. Pending Amount**
- **Source**: Calculated from frozen `LossSnapshot.loss_amount`
- **Display**: 
  - "Client Payable: ₹X.XX (from LossSnapshot)"
  - "Your Receivable: ₹X.XX (from LossSnapshot)"
  - "Company Receivable: ₹X.XX (from LossSnapshot)" (if company client)
- **Show When**: `LOSS > 0` and `LOSS >= ₹0.01`
- **Hide When**: `LOSS == 0` or `LOSS < ₹0.01` or `PROFIT > 0`
- **Never Recalculated**: Always from frozen snapshot

### **4. Loss Amount**
- **Source**: `LossSnapshot.loss_amount` (frozen)
- **Display**: "Loss: ₹X.XX (frozen)"
- **Show When**: `LOSS > 0` and `LOSS >= ₹0.01`
- **Hide When**: `LOSS == 0` or `LOSS < ₹0.01`
- **Never Recalculated**: Always from snapshot

### **5. Profit Amount**
- **Source**: Calculated as `max(CB - CAPITAL, 0)`
- **Display**: "Profit: ₹X.XX" (rarely shown, withdrawn immediately)
- **Show When**: `PROFIT > 0` and not yet withdrawn
- **Hide When**: `PROFIT == 0` or withdrawn
- **Handling**: Atomic flag `profit_consumed` prevents double withdrawal

### **6. NET Movement**
- **Source**: `CB - CAPITAL`
- **Display**: "NET: ₹X.XX" (signed, positive = profit, negative = loss)
- **Usage**: Informational only, not used in business logic
- **Label**: "(informational only)"

### **Display Rules Summary Table**

| Value | Source | Display Format | Show When | Hide When | Label |
|-------|--------|----------------|-----------|-----------|-------|
| Old Balance | `cached_old_balance` (ledger) | "Old Balance: ₹X.XX" | Always | Never | "(from ledger)" |
| Current Balance | `loss_snapshot.balance_record` (if LOSS) or `remaining_balance` (if no LOSS) | "Current Balance: ₹X.XX" | Always | Never | "(from snapshot)" or "(live)" |
| Pending | `loss_snapshot.loss_amount` (frozen) | "Client Payable: ₹X.XX" | `LOSS > 0` and `>= ₹0.01` | `LOSS == 0` or `< ₹0.01` or `PROFIT > 0` | "(from LossSnapshot)" |
| Loss | `loss_snapshot.loss_amount` (frozen) | "Loss: ₹X.XX" | `LOSS > 0` and `>= ₹0.01` | `LOSS == 0` or `< ₹0.01` | "(frozen)" |
| Profit | `max(CB - CAPITAL, 0)` | "Profit: ₹X.XX" | `PROFIT > 0` and not withdrawn | `PROFIT == 0` or withdrawn | "(withdrawn immediately)" |
| NET | `CB - CAPITAL` | "NET: ₹X.XX" | Always | Never | "(informational only)" |

### **UI Display Rules**

1. **Causal Consistency**: CB shown from `loss_snapshot.balance_record` when LOSS exists
2. **Frozen Values**: LOSS and Pending always from snapshot, never recalculated
3. **Rounding**: All amounts rounded to 2 decimals for display
4. **Auto-Hide**: Values < ₹0.01 auto-hidden (treated as ₹0.00)
5. **Source Labeling**: UI labels show source (from ledger, from snapshot, live, etc.)
6. **Color Coding**: 
   - Red: Loss/Pending (client owes)
   - Green: Profit (you owe)
   - Black: Break-even

---

## 📖 COMPLETE EXAMPLES

### **Example 1: Simple Partial Payment**

**Initial State**:
- CAPITAL = ₹100 (from ledger)
- CB = ₹40 (frozen in LossSnapshot)
- LOSS = ₹60 (frozen in LossSnapshot)
- total_share_pct = 10% (frozen in LossSnapshot)
- ClientPayable = ₹6

**Client Pays ₹3 (Partial)**:
1. Payment = ₹3 (share space)
2. capital_closed = ₹3 × 100 / 10 = ₹30 (capital space)
3. loss_new = ₹60 - ₹30 = ₹30
4. CAPITAL_new = ₹40 + ₹30 = ₹70 (LOSS-first)
5. Your share = ₹30 × 1% / 100 = ₹0.30 (if company client)

**Final State**:
- CAPITAL = ₹70 (derived from ledger)
- CB = ₹40 (still frozen)
- LOSS = ₹30 (updated in LossSnapshot)
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
5. Auto-close: LOSS = ₹0 → `is_settled = True`

**Final State**:
- CAPITAL = ₹40
- CB = ₹40
- LOSS = ₹0
- ClientPayable = ₹0
- LossSnapshot: `is_settled = True`

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
- LossSnapshot: `is_settled = True`

### **Example 4: Company Client Share Split**

**Initial State**:
- CAPITAL = ₹100
- CB = ₹40
- LOSS = ₹60
- my_share_pct = 1% (frozen)
- company_share_pct = 9% (frozen)
- total_share_pct = 10% (frozen)
- ClientPayable = ₹6

**Client Pays ₹6 (Full)**:
- capital_closed = ₹60
- Your share = ₹60 × 1% / 100 = ₹0.60
- Company share = ₹60 × 9% / 100 = ₹5.40
- Total = ₹0.60 + ₹5.40 = ₹6.00 ✓

---

## 🎯 SUMMARY

### **Key Formulas**

```
LOSS = max(CAPITAL - CB, 0)  # Calculated once, then frozen
PROFIT = max(CB - CAPITAL, 0)
CAPITAL = Σ(FUNDING) − Σ(CAPITAL_CLOSED)  # Always derived from ledger
ClientPayable = LOSS × total_share_pct / 100  # From frozen LOSS
capital_closed = payment × 100 / total_share_pct  # Conversion
```

### **Key Rules**

1. **LOSS is Frozen** - Never recalculated, only from LossSnapshot
2. **CB is Causal** - From snapshot when LOSS exists
3. **LOSS-First Approach** - `CAPITAL = CB + LOSS` (LOSS is source of truth)
4. **Shares Frozen** - From snapshot, not live config
5. **Pending from Frozen LOSS** - Never live calculation
6. **Auto-Close** - LOSS < ₹0.01 automatically closed to ₹0.00
7. **Invariants Enforced** - All 6 checked before commit
8. **Deterministic Idempotency** - Hash-based settlement ID

### **Display Summary**

- **Old Balance**: CAPITAL (from ledger, cached)
- **Current Balance**: CB (from snapshot if LOSS exists, live if no LOSS)
- **Pending**: ClientPayable (from frozen LossSnapshot)
- **Loss**: LossSnapshot.loss_amount (frozen)
- **Profit**: `max(CB - CAPITAL, 0)` (withdrawn immediately)

### **Critical Principles**

1. **LOSS is the source of truth** - Everything derives from frozen LOSS
2. **CAPITAL is derived** - Never assigned, always from ledger
3. **Shares are frozen** - Historical correctness guaranteed
4. **Pending is stateless** - Calculated from frozen LOSS, never stored
5. **CB is causal** - From snapshot when LOSS exists, prevents drift

---

**Document Version**: 1.0  
**Last Updated**: 2026-01-05  
**Status**: ✅ Complete Pin-to-Pin Guide, All Formulas, All Display Rules, Production-Safe
