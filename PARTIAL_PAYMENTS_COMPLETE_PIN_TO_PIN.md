# PARTIAL PAYMENTS - COMPLETE PIN TO PIN GUIDE

**Everything You Need: How It Works, All Formulas, Display Rules**

---

## 📋 TABLE OF CONTENTS

1. [Core Definitions](#core-definitions)
2. [Fundamental Formulas](#fundamental-formulas)
3. [Partial Payment Logic](#partial-payment-logic)
4. [Pending Payments Calculation](#pending-payments-calculation)
5. [Share Calculations](#share-calculations)
6. [How Values Are Displayed](#how-values-are-displayed)
7. [Complete Examples](#complete-examples)

---

## 🔑 CORE DEFINITIONS

### **CAPITAL (C) / Old Balance (OB)**
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

### **LOSS**
- **Formula**: `LOSS = max(CAPITAL - CB, 0)`
- **Meaning**: Client's receivable (money client owes you)
- **When It Exists**: Only when `CAPITAL > CB`
- **Source**: From `LossSnapshot` tied to `BalanceRecord` (frozen at balance time)
- **Auto-Close**: If `LOSS < ₹0.01`, auto-closed to ₹0.00 (with settlement event)
- **Display**: Used to calculate pending amounts

### **PROFIT**
- **Formula**: `PROFIT = max(CB - CAPITAL, 0)`
- **Meaning**: Your liability (money you owe client)
- **When It Exists**: Only when `CB > CAPITAL`
- **Handling**: Withdrawn immediately when detected (no pending profit state)
- **Auto-Close**: If `PROFIT < ₹0.01`, auto-closed to ₹0.00 (with adjustment event)
- **Display**: Shown in "You Owe Clients" section

---

## 📐 FUNDAMENTAL FORMULAS

### **🧠 GOLDEN FORMULAS**

```python
# Core calculations (exact, 2 decimals)
LOSS = max(CAPITAL - CB, 0)
PROFIT = max(CB - CAPITAL, 0)

# CAPITAL (always derived from ledger, never assigned)
CAPITAL = Σ(FUNDING) − Σ(CAPITAL_CLOSED)

# Receivables (share space)
ClientPayable = LOSS × total_share_pct / 100
YourReceivable = LOSS × my_share_pct / 100
CompanyReceivable = LOSS × company_share_pct / 100

# Auto-close threshold
AUTO_CLOSE_THRESHOLD = Decimal("0.01")
```

---

## 🔄 PARTIAL PAYMENT LOGIC

### **Complete Step-by-Step Flow**

```python
# STEP 1: Lock for concurrency
client_exchange = ClientExchange.objects.select_for_update().get(pk=client_exchange_id)

# STEP 2: Generate unique settlement ID (UUID)
settlement_id = str(uuid.uuid4())

# STEP 3: Check idempotency
if Transaction.objects.filter(settlement_id=settlement_id).exists():
    return "duplicate"

# STEP 4: Get balance record
balance_record = BalanceRecord.objects.get(pk=balance_record_id)

# STEP 5: Get loss snapshot (LOSS from snapshot, not global CAPITAL)
loss_snapshot = LossSnapshot.objects.get(balance_record=balance_record)
loss_current = loss_snapshot.loss_amount  # ✅ From snapshot

# STEP 6: Validate loss exists and not settled
if loss_current == 0 or loss_snapshot.is_settled:
    REJECT  # No loss to settle

# STEP 7: Get share % from snapshot (frozen at creation)
my_share_pct = loss_snapshot.my_share_pct
company_share_pct = loss_snapshot.company_share_pct
total_share_pct = my_share_pct + company_share_pct

# STEP 8: Calculate ClientPayable (share space)
client_payable = (loss_current * total_share_pct) / 100

# STEP 9: Validate payment in share space
if payment > client_payable:
    REJECT  # Payment exceeds ClientPayable

# STEP 10: Convert to capital space
capital_closed_raw = (payment * 100) / total_share_pct

# STEP 11: Validate capital_closed does not exceed LOSS
if capital_closed_raw > loss_current:
    REJECT  # Cannot close more capital than loss

# STEP 12: Check if this would make CAPITAL negative
total_funding = get_total_funding(client_exchange)
total_capital_closed = get_total_capital_closed(client_exchange)
if total_capital_closed + capital_closed_raw > total_funding:
    REJECT  # Would make CAPITAL negative

# STEP 13: Round AFTER validation
capital_closed = capital_closed_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

# STEP 14: Reduce LOSS
loss_new = loss_current - capital_closed

# STEP 15: Guard against negative LOSS
if loss_new < 0:
    REJECT

# STEP 16: Apply auto-close (deterministic, no mutation)
if loss_new < Decimal("0.01"):
    capital_closed = loss_current  # Close entire loss deterministically
    loss_new = Decimal(0)

# STEP 17: Calculate shares (even for auto-close)
your_share_amount = (capital_closed * my_share_pct) / 100
company_share_amount = (capital_closed * company_share_pct) / 100

# STEP 18: Create settlement event
Transaction.objects.create(
    transaction_type=Transaction.TYPE_SETTLEMENT,
    settlement_id=settlement_id,
    amount=payment,
    capital_closed=capital_closed,
    your_share_amount=your_share_amount,
    company_share_amount=company_share_amount,
    balance_record_id=balance_record_id
)

# STEP 19: Update loss snapshot
loss_snapshot.loss_amount = loss_new
if loss_new == 0:
    loss_snapshot.is_settled = True
loss_snapshot.save()

# STEP 20: Enforce invariants
enforce_invariants(client_exchange)
```

---

## 📊 PENDING PAYMENTS CALCULATION

### **For MY CLIENTS**

```python
# Step 1: Get active loss snapshot
active_loss = LossSnapshot.objects.filter(
    client_exchange=client_exchange,
    is_settled=False
).first()

if not active_loss:
    return None  # No pending

# Step 2: Get LOSS from snapshot
loss = active_loss.loss_amount  # ✅ From snapshot

# Step 3: Apply auto-close
if loss < Decimal("0.01"):
    loss = Decimal("0.00")
    return None  # No pending

# Step 4: Calculate receivables
my_share_pct = active_loss.my_share_pct  # e.g., 10%
ClientPayable = (loss * my_share_pct) / 100
YourReceivable = ClientPayable  # Full share
CompanyReceivable = Decimal(0)

# Round to 2 decimals
ClientPayable = ClientPayable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
YourReceivable = YourReceivable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

**Formula Summary**:
```
LOSS = loss_snapshot.loss_amount (from snapshot)
ClientPayable = (LOSS × my_share_pct) / 100
YourReceivable = ClientPayable
```

### **For COMPANY CLIENTS**

```python
# Step 1: Get active loss snapshot
active_loss = LossSnapshot.objects.filter(
    client_exchange=client_exchange,
    is_settled=False
).first()

if not active_loss:
    return None  # No pending

# Step 2: Get LOSS from snapshot
loss = active_loss.loss_amount  # ✅ From snapshot

# Step 3: Apply auto-close
if loss < Decimal("0.01"):
    loss = Decimal("0.00")
    return None  # No pending

# Step 4: Calculate receivables
total_share_pct = 10  # Always 10% for company clients
ClientPayable = (loss * 10) / 100
YourReceivable = (loss * 1) / 100   # 1% for you
CompanyReceivable = (loss * 9) / 100  # 9% for company

# Round to 2 decimals
ClientPayable = ClientPayable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
YourReceivable = YourReceivable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
CompanyReceivable = CompanyReceivable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

**Formula Summary**:
```
LOSS = loss_snapshot.loss_amount (from snapshot)
ClientPayable = (LOSS × 10) / 100
YourReceivable = (LOSS × 1) / 100
CompanyReceivable = (LOSS × 9) / 100
```

---

## 🧮 SHARE CALCULATIONS

### **My Share (for MY CLIENTS)**
```
My Share = (LOSS × my_share_pct) / 100
```
- **Example**: LOSS = 60.00, my_share_pct = 10% → My Share = 6.00
- **Full share goes to you**
- **Display**: Shown as "Your Receivable" in UI

### **My Share (for COMPANY CLIENTS)**
```
My Share = (LOSS × 1) / 100
```
- **Always 1% of loss**
- **Example**: LOSS = 60.00 → My Share = 0.60
- **Display**: Shown as "Your Receivable" in UI

### **Company Share (for COMPANY CLIENTS)**
```
Company Share = (LOSS × 9) / 100
```
- **Always 9% of loss**
- **Example**: LOSS = 60.00 → Company Share = 5.40
- **Display**: Shown as "Company Receivable" in UI

### **Combined Share (for COMPANY CLIENTS)**
```
Combined Share = My Share + Company Share
Combined Share = (LOSS × 10) / 100
```
- **Always 10% of loss (1% + 9%)**
- **Example**: LOSS = 60.00 → Combined Share = 6.00
- **Display**: Shown as "Pending Amount" if `combine_shares = True`

---

## 🖥️ HOW VALUES ARE DISPLAYED IN UI

### **"Clients Owe You" Section**

#### **When to Show**
- Only when `LOSS >= ₹0.01` (after auto-close)
- Only when `loss_snapshot.is_settled = False`

#### **What to Display**

**For MY CLIENTS**:
```
┌─────────────────────────────────────────────┐
│ Client: [Client Name]                        │
│ Exchange: [Exchange Name]                    │
│                                              │
│ Pending Amount: ₹[ClientPayable]            │
│   Formula: (LOSS × my_share_pct) / 100      │
│   Example: (60.00 × 10) / 100 = ₹6.00        │
│   Source: LossSnapshot                       │
│   Display: Rounded to 2 decimals             │
│                                              │
│ Your Receivable: ₹[YourReceivable]            │
│   Same as Pending (full share)               │
│   Display: Rounded to 2 decimals             │
│                                              │
│ Old Balance: ₹[CAPITAL]                      │
│   Formula: Σ(FUNDING) − Σ(CAPITAL_CLOSED)    │
│   Source: Ledger (derived)                   │
│   Display: Rounded to 2 decimals             │
│                                              │
│ Current Balance: ₹[CB]                       │
│   Source: loss_snapshot.balance_record      │
│   (Causal CB, not latest)                    │
│   Display: Rounded to 2 decimals             │
│                                              │
│ Total Loss: ₹[LOSS]                          │
│   Source: LossSnapshot.loss_amount            │
│   Display: Rounded to 2 decimals             │
└─────────────────────────────────────────────┘
```

**For COMPANY CLIENTS**:
```
┌─────────────────────────────────────────────┐
│ Client: [Client Name]                        │
│ Exchange: [Exchange Name]                    │
│                                              │
│ Pending Amount: ₹[ClientPayable]            │
│   If combine_shares = True:                  │
│     Show: (LOSS × 10) / 100 = ₹6.00          │
│   If combine_shares = False:                 │
│     My Share: ₹0.60                          │
│     Company Share: ₹5.40                     │
│   Display: Rounded to 2 decimals             │
│                                              │
│ Your Receivable: ₹[YourReceivable]           │
│   Formula: (LOSS × 1) / 100                  │
│   Example: (60.00 × 1) / 100 = ₹0.60         │
│   Display: Rounded to 2 decimals             │
│                                              │
│ Company Receivable: ₹[CompanyReceivable]     │
│   Formula: (LOSS × 9) / 100                  │
│   Example: (60.00 × 9) / 100 = ₹5.40         │
│   Display: Rounded to 2 decimals             │
│                                              │
│ Old Balance: ₹[CAPITAL]                      │
│ Current Balance: ₹[CB]                       │
│ Total Loss: ₹[LOSS]                          │
│ All displayed rounded to 2 decimals          │
└─────────────────────────────────────────────┘
```

### **"You Owe Clients" Section**

#### **When to Show**
- Only when `PROFIT >= ₹0.01` (after auto-close)
- PROFIT is withdrawn immediately, so this section is rarely shown

#### **What to Display**
```
┌─────────────────────────────────────────────┐
│ Client: [Client Name]                        │
│ Exchange: [Exchange Name]                    │
│                                              │
│ Profit Amount: ₹[PROFIT]                     │
│   Formula: CB - CAPITAL                      │
│   Example: 120.00 - 100.00 = ₹20.00          │
│   Display: Rounded to 2 decimals             │
│                                              │
│ Your Share: ₹[Your Share of Profit]          │
│   What you owe to client                     │
│   Display: Rounded to 2 decimals             │
│                                              │
│ Old Balance: ₹[CAPITAL]                      │
│ Current Balance: ₹[CB]                       │
│ Both displayed rounded to 2 decimals        │
└─────────────────────────────────────────────┘
```

---

## 📝 COMPLETE EXAMPLES

### **Example 1: Simple Partial Payment (My Client)**

#### **Initial State**
```
Funding: ₹100.00
CAPITAL = 100.00 (from ledger: Σ(FUNDING) = 100.00)
CB = 100.00
LOSS = 0.00
ClientPayable = 0.00
```

**UI Display**: No pending shown

#### **After Trading Loss**
```
Balance Record Created:
  date = 2026-01-05
  remaining_balance = 40.00
  capital_at_balance_time = 100.00
  loss_at_balance_time = 60.00

LossSnapshot Created:
  balance_record = (above)
  loss_amount = 60.00
  my_share_pct = 10%
  company_share_pct = 0%
  is_settled = False

CAPITAL = 100.00 (unchanged, from ledger)
CB = 40.00 (from balance record)
LOSS = 60.00 (from snapshot)
ClientPayable = (60.00 × 10) / 100 = 6.00
YourReceivable = 6.00
```

**UI Display**:
- Pending Amount: ₹6.00
- Your Receivable: ₹6.00
- Old Balance: ₹100.00
- Current Balance: ₹40.00
- Total Loss: ₹60.00

#### **Partial Payment: ₹3.00**
```
payment = 3.00
loss_snapshot = LossSnapshot.objects.get(balance_record=balance_record)
loss_current = 60.00 (from snapshot)

# Validate in share space
client_payable = (60.00 × 10) / 100 = 6.00
if 3.00 > 6.00: REJECT  # ✅ Passes

# Convert to capital space
capital_closed_raw = (3.00 × 100) / 10 = 30.00
capital_closed = 30.00

# Reduce LOSS
loss_new = 60.00 - 30.00 = 30.00

# Create settlement event
Transaction.objects.create(
    transaction_type=Transaction.TYPE_SETTLEMENT,
    settlement_id=uuid.uuid4(),
    amount=3.00,
    capital_closed=30.00,
    your_share_amount=3.00,
    company_share_amount=0.00
)

# Update loss snapshot
loss_snapshot.loss_amount = 30.00
loss_snapshot.save()

# CAPITAL is now: 100.00 - 30.00 = 70.00 (from ledger)
CAPITAL_new = 70.00
CB = 40.00 (unchanged)

# Verify
LOSS_new = 30.00 (from updated snapshot) ✅
ClientPayable_new = (30.00 × 10) / 100 = 3.00 ✅
```

**UI Display After Payment**:
- Pending Amount: ₹3.00
- Your Receivable: ₹3.00
- Old Balance: ₹70.00
- Current Balance: ₹40.00
- Total Loss: ₹30.00

### **Example 2: Company Client with Combined Share**

#### **Initial State**
```
Balance Record:
  remaining_balance = 40.00
  capital_at_balance_time = 100.00
  loss_at_balance_time = 60.00

LossSnapshot:
  loss_amount = 60.00
  my_share_pct = 1%
  company_share_pct = 9%
  is_settled = False

CAPITAL = 100.00
CB = 40.00
LOSS = 60.00
ClientPayable = (60.00 × 10) / 100 = 6.00
YourReceivable = (60.00 × 1) / 100 = 0.60
CompanyReceivable = (60.00 × 9) / 100 = 5.40
```

**UI Display (combine_shares = True)**:
- Pending Amount: ₹6.00 (Combined Share)
- Old Balance: ₹100.00
- Current Balance: ₹40.00
- Total Loss: ₹60.00

**UI Display (combine_shares = False)**:
- My Share: ₹0.60
- Company Share: ₹5.40
- Old Balance: ₹100.00
- Current Balance: ₹40.00
- Total Loss: ₹60.00

#### **Partial Payment: ₹3.00**
```
payment = 3.00
loss_current = 60.00 (from snapshot)

# Validate in share space
client_payable = 6.00
if 3.00 > 6.00: REJECT  # ✅ Passes

# Convert to capital space
capital_closed = 30.00

# Calculate shares
your_share_amount = (30.00 × 1) / 100 = 0.30
company_share_amount = (30.00 × 9) / 100 = 2.70

# Create settlement
Transaction.objects.create(
    amount=3.00,
    capital_closed=30.00,
    your_share_amount=0.30,
    company_share_amount=2.70
)

# Update snapshot
loss_snapshot.loss_amount = 30.00
loss_snapshot.save()

# State after Payment
CAPITAL = 70.00 (from ledger)
CB = 40.00
LOSS = 30.00 (from updated snapshot)
ClientPayable = 3.00
YourReceivable = 0.30
CompanyReceivable = 2.70
```

**UI Display After Payment**:
- Pending Amount: ₹3.00
- Your Receivable: ₹0.30
- Company Receivable: ₹2.70
- Old Balance: ₹70.00
- Current Balance: ₹40.00
- Total Loss: ₹30.00

---

## 🎯 FORMULA QUICK REFERENCE

### **Core Formulas**
```
CAPITAL = Σ(FUNDING) − Σ(CAPITAL_CLOSED)  (always derived from ledger)
LOSS = loss_snapshot.loss_amount  (from snapshot, not CAPITAL - CB)
PROFIT = max(CB - CAPITAL, 0)  (withdrawn immediately)
```

### **Receivables**
```
ClientPayable = LOSS × total_share_pct / 100
YourReceivable = LOSS × my_share_pct / 100
CompanyReceivable = LOSS × company_share_pct / 100
```

### **Partial Payment**
```
# Validate in share space
if payment > ClientPayable: REJECT

# Convert to capital space
capital_closed = (payment × 100) / total_share_pct

# Validate in capital space
if capital_closed > LOSS: REJECT

# Reduce LOSS
loss_new = loss_current - capital_closed

# Update snapshot
loss_snapshot.loss_amount = loss_new
```

### **Auto-Close**
```
if LOSS < 0.01: LOSS = 0.00 (with settlement event, shares allocated)
if PROFIT < 0.01: PROFIT = 0.00 (with adjustment event)
```

---

## 📊 DISPLAY SUMMARY

### **What Shows in UI**

| Value | Formula | Source | When Shown | Display Format |
|-------|---------|--------|------------|----------------|
| Pending Amount | `(LOSS × total_share_pct) / 100` | LossSnapshot | LOSS >= ₹0.01 | ₹X.XX |
| Your Receivable | `(LOSS × my_share_pct) / 100` | LossSnapshot | LOSS >= ₹0.01 | ₹X.XX |
| Company Receivable | `(LOSS × 9) / 100` | LossSnapshot | LOSS >= ₹0.01, Company | ₹X.XX |
| Old Balance | `CAPITAL` (from ledger) | Ledger | Always | ₹X.XX |
| Current Balance | `CB` (from loss snapshot) | LossSnapshot.balance_record | Always | ₹X.XX |
| Total Loss | `loss_snapshot.loss_amount` | LossSnapshot | LOSS >= ₹0.01 | ₹X.XX |
| Profit Amount | `CB - CAPITAL` | Calculated | PROFIT >= ₹0.01 | ₹X.XX |

---

## 🔒 CRITICAL RULES

### **State Management Rules**
```
✅ Trading BLOCKED when LOSS exists
✅ Funding BLOCKED when LOSS exists
✅ Only ONE active LossSnapshot per client
✅ LOSS is frozen in snapshot (trading blocked)
✅ CB shown from loss snapshot (causal consistency)
```

### **Validation Rules**
```
✅ Payment validated in share space first (ClientPayable)
✅ Then validated in capital space (capital_closed <= LOSS)
✅ CAPITAL cannot go negative (hard validation)
✅ Settlement IDs are UUID-based (collision-safe)
```

### **Display Rules**
```
✅ All values rounded to 2 decimals
✅ CB from loss snapshot (not latest balance)
✅ Pending shown only when LOSS >= ₹0.01
✅ Profit shown only when PROFIT >= ₹0.01
```

---

**Document Version**: Final  
**Last Updated**: 2026-01-05  
**Status**: ✅ Complete Pin-to-Pin Documentation with All Fixes
