# PARTIAL PAYMENTS - COMPLETE PIN-TO-PIN GUIDE

**Everything You Need to Know: Formulas, Logic, Display Rules**

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
- **Definition**: Total money you have put into the exchange that is not yet settled
- **Formula**: `CAPITAL = Σ(FUNDING) − Σ(CAPITAL_CLOSED)`
- **Database**: `ClientExchange.cached_old_balance`
- **When It Changes**:
  - ✅ On settlement (recomputed from ledger)
  - ✅ On funding (added to ledger)
  - ❌ NEVER on profit withdrawal
- **Display**: Shown as "Old Balance" in UI

### **Current Balance (CB)**
- **Definition**: Actual exchange balance from latest `BALANCE_RECORD`
- **Database**: `ClientDailyBalance.remaining_balance`
- **When It Changes**:
  - ✅ On new `BALANCE_RECORD` creation
  - ✅ On profit withdrawal (decreases CB)
  - ✅ On funding (when auto-credited)
- **Display**: Shown as "Current Balance" in UI

### **LOSS**
- **Formula**: `LOSS = max(CAPITAL - CB, 0)`
- **Meaning**: Client's receivable (money client owes you)
- **When It Exists**: Only when `CAPITAL > CB`
- **Auto-Close**: If `LOSS < ₹0.01`, auto-closed to ₹0.00 (with settlement event)
- **Display**: Used to calculate pending amounts

### **PROFIT**
- **Formula**: `PROFIT = max(CB - CAPITAL, 0)`
- **Meaning**: Your liability (money you owe client)
- **When It Exists**: Only when `CB > CAPITAL`
- **Auto-Close**: If `PROFIT < ₹0.01`, auto-closed to ₹0.00 (with adjustment event)
- **Display**: Shown in "You Owe Clients" section

---

## 📐 FUNDAMENTAL FORMULAS

### **🧠 GOLDEN FORMULAS**

```python
# Core calculations (exact, 2 decimals)
LOSS = max(CAPITAL - CB, 0)
PROFIT = max(CB - CAPITAL, 0)

# CAPITAL (always derived from ledger)
CAPITAL = Σ(FUNDING) − Σ(CAPITAL_CLOSED)

# Receivables
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

# STEP 2: Check idempotency
settlement_id = generate_unique_id(client_exchange_id, tx_date, payment)
if Transaction.objects.filter(settlement_id=settlement_id).exists():
    return "duplicate"

# STEP 3: Get CAPITAL from ledger (derived, not cached)
capital = get_capital(client_exchange)  # Σ(FUNDING) − Σ(CAPITAL_CLOSED)

# STEP 4: Snapshot CB
cb_snapshot = get_exchange_balance(client_exchange, use_cache=False)

# STEP 5: Calculate LOSS and PROFIT (exact)
loss_current = max(capital - cb_snapshot, 0)
profit_current = max(cb_snapshot - capital, 0)

# STEP 6: Apply auto-close (with events)
if loss_current < Decimal("0.01"):
    # Create settlement event
    Transaction.objects.create(
        transaction_type=Transaction.TYPE_SETTLEMENT,
        amount=Decimal(0),
        capital_closed=loss_current,
        note="Auto-close: LOSS < ₹0.01"
    )
    loss_current = Decimal(0)

# STEP 7: Validate LOSS exists
if loss_current == 0:
    REJECT  # No loss to settle

# STEP 8: Validate PROFIT does not exist
if profit_current > 0:
    REJECT  # Cannot settle loss when profit exists

# STEP 9: Get share % from LOSS snapshot (frozen at creation)
loss_snapshot = LossSnapshot.objects.get(
    client_exchange=client_exchange,
    balance_record_id=balance_record_id
)
total_share_pct = loss_snapshot.my_share_pct + loss_snapshot.company_share_pct

# STEP 10: Calculate capital_closed
capital_closed_raw = (payment × 100) / total_share_pct

# STEP 11: Validate capital_closed does not exceed LOSS
if capital_closed_raw > loss_current:
    REJECT  # Cannot close more capital than loss

# STEP 12: Round AFTER validation
capital_closed = capital_closed_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

# STEP 13: Reduce LOSS
loss_new = loss_current - capital_closed

# STEP 14: Guard against negative LOSS
if loss_new < 0:
    REJECT

# STEP 15: Apply auto-close to new LOSS
if loss_new < Decimal("0.01"):
    capital_closed += loss_new  # Close remaining
    loss_new = Decimal(0)

# STEP 16: Create settlement event
Transaction.objects.create(
    transaction_type=Transaction.TYPE_SETTLEMENT,
    settlement_id=settlement_id,
    amount=payment,
    capital_closed=capital_closed,
    balance_record_id=balance_record_id
)

# STEP 17: Re-verify CB before commit
current_cb = get_exchange_balance(client_exchange, use_cache=False)
if current_cb != cb_snapshot:
    raise ValueError("CB changed during settlement. Retry required.")

# STEP 18: Enforce invariants
enforce_invariants(client_exchange)
```

---

## 📊 PENDING PAYMENTS CALCULATION

### **For MY CLIENTS**

```python
# Step 1: Get CAPITAL and CB
old_balance = get_capital(client_exchange)  # From ledger
current_balance = get_exchange_balance(client_exchange)

# Step 2: Calculate LOSS (exact)
loss = max(old_balance - current_balance, 0)

# Step 3: Apply auto-close
if loss < Decimal("0.01"):
    loss = Decimal("0.00")
    continue  # No pending

# Step 4: Calculate receivables
my_share_pct = client_exchange.my_share_pct  # e.g., 10%
ClientPayable = (loss × my_share_pct) / 100
YourReceivable = ClientPayable  # Full share
CompanyReceivable = Decimal(0)

# Round to 2 decimals
ClientPayable = ClientPayable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
YourReceivable = YourReceivable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

**Formula Summary**:
```
LOSS = max(CAPITAL - CB, 0)
ClientPayable = (LOSS × my_share_pct) / 100
YourReceivable = ClientPayable
```

### **For COMPANY CLIENTS**

```python
# Step 1: Calculate LOSS (exact)
loss = max(old_balance - current_balance, 0)

# Step 2: Apply auto-close
if loss < Decimal("0.01"):
    loss = Decimal("0.00")
    continue  # No pending

# Step 3: Calculate receivables
total_share_pct = 10  # Always 10% for company clients
ClientPayable = (loss × 10) / 100
YourReceivable = (loss × 1) / 100   # 1% for you
CompanyReceivable = (loss × 9) / 100  # 9% for company

# Round to 2 decimals
ClientPayable = ClientPayable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
YourReceivable = YourReceivable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
CompanyReceivable = CompanyReceivable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

**Formula Summary**:
```
LOSS = max(CAPITAL - CB, 0)
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
- Only when `CAPITAL > CB` (loss case)
- Only when `loss >= ₹0.01` (after auto-close)

#### **What to Display**

**For MY CLIENTS**:
```
┌─────────────────────────────────────┐
│ Client: [Client Name]               │
│ Exchange: [Exchange Name]            │
│                                      │
│ Pending Amount: ₹[ClientPayable]     │
│   Formula: (LOSS × my_share_pct) / 100│
│   Example: (60.00 × 10) / 100 = ₹6.00│
│                                      │
│ Your Receivable: ₹[YourReceivable]   │
│   Same as Pending (full share)       │
│                                      │
│ Old Balance: ₹[CAPITAL]              │
│ Current Balance: ₹[CB]               │
│ Total Loss: ₹[LOSS]                  │
│   Formula: CAPITAL - CB              │
└─────────────────────────────────────┘
```

**For COMPANY CLIENTS**:
```
┌─────────────────────────────────────┐
│ Client: [Client Name]               │
│ Exchange: [Exchange Name]            │
│                                      │
│ Pending Amount: ₹[ClientPayable]    │
│   If combine_shares = True:          │
│     Show: (LOSS × 10) / 100          │
│   If combine_shares = False:         │
│     My Share: ₹0.60                  │
│     Company Share: ₹5.40              │
│                                      │
│ Your Receivable: ₹[YourReceivable]   │
│   Formula: (LOSS × 1) / 100          │
│                                      │
│ Company Receivable: ₹[CompanyReceivable]│
│   Formula: (LOSS × 9) / 100          │
│                                      │
│ Old Balance: ₹[CAPITAL]               │
│ Current Balance: ₹[CB]                │
│ Total Loss: ₹[LOSS]                  │
└─────────────────────────────────────┘
```

### **"You Owe Clients" Section**

#### **When to Show**
- Only when `CB > CAPITAL` (profit case)
- Only when `profit >= ₹0.01` (after auto-close)

#### **What to Display**
```
┌─────────────────────────────────────┐
│ Client: [Client Name]               │
│ Exchange: [Exchange Name]            │
│                                      │
│ Profit Amount: ₹[PROFIT]            │
│   Formula: CB - CAPITAL              │
│   Example: 120.00 - 100.00 = ₹20.00 │
│                                      │
│ Your Share: ₹[Your Share of Profit] │
│   What you owe to client             │
│                                      │
│ Old Balance: ₹[CAPITAL]              │
│ Current Balance: ₹[CB]               │
└─────────────────────────────────────┘
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
Balance Record: ₹40.00
CAPITAL = 100.00 (unchanged, from ledger)
CB = 40.00
LOSS = max(100.00 - 40.00, 0) = 60.00
my_share_pct = 10%
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
capital_closed_raw = (3.00 × 100) / 10 = 30.00
capital_closed = 30.00

loss_current = 60.00
loss_new = 60.00 - 30.00 = 30.00

# Create settlement event
Transaction.objects.create(
    transaction_type=Transaction.TYPE_SETTLEMENT,
    amount=3.00,
    capital_closed=30.00
)

# CAPITAL is now derived: 100.00 - 30.00 = 70.00
CAPITAL_new = 70.00 (from ledger)
CB = 40.00 (unchanged)

# Verify
LOSS_new = max(70.00 - 40.00, 0) = 30.00 ✅
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
CAPITAL = 100.00
CB = 40.00
LOSS = 60.00
total_share_pct = 10%
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
capital_closed_raw = (3.00 × 100) / 10 = 30.00
capital_closed = 30.00

loss_current = 60.00
loss_new = 30.00

# Create settlement event
Transaction.objects.create(
    transaction_type=Transaction.TYPE_SETTLEMENT,
    amount=3.00,
    capital_closed=30.00
)

# CAPITAL is now: 100.00 - 30.00 = 70.00
CAPITAL_new = 70.00
CB = 40.00

# State after Payment
LOSS = 30.00
ClientPayable = (30.00 × 10) / 100 = 3.00
YourReceivable = (30.00 × 1) / 100 = 0.30
CompanyReceivable = (30.00 × 9) / 100 = 2.70
```

**UI Display After Payment**:
- Pending Amount: ₹3.00
- Your Receivable: ₹0.30
- Company Receivable: ₹2.70
- Old Balance: ₹70.00
- Current Balance: ₹40.00
- Total Loss: ₹30.00

### **Example 3: Auto-Close Rule**

#### **Initial State**
```
CAPITAL = 100.00
CB = 99.995  # Stored as 100.00 or 99.99
LOSS = 0.005
```

**Apply Auto-Close Rule**:
```
LOSS = 0.005 < 0.01 → auto-close

# Create settlement event
Transaction.objects.create(
    transaction_type=Transaction.TYPE_SETTLEMENT,
    amount=Decimal(0),
    capital_closed=Decimal("0.005"),
    note="Auto-close: LOSS < ₹0.01"
)

# CAPITAL is now: 100.00 - 0.005 = 99.995 ≈ 100.00
LOSS = 0.00
```

**UI Display**:
- No pending shown
- LOSS = ₹0.00
- CAPITAL ≈ CB = ₹100.00

---

## 🎯 FORMULA QUICK REFERENCE

### **Core Formulas**
```
CAPITAL = Σ(FUNDING) − Σ(CAPITAL_CLOSED)  (always derived)
LOSS = max(CAPITAL - CB, 0)
PROFIT = max(CB - CAPITAL, 0)
```

### **Receivables**
```
ClientPayable = LOSS × total_share_pct / 100
YourReceivable = LOSS × my_share_pct / 100
CompanyReceivable = LOSS × company_share_pct / 100
```

### **Partial Payment**
```
capital_closed_raw = (payment × 100) / total_share_pct
loss_new = loss_current - capital_closed
CAPITAL_new = Σ(FUNDING) − Σ(CAPITAL_CLOSED)  (recomputed from ledger)
```

### **Auto-Close**
```
if LOSS < 0.01: LOSS = 0.00 (with settlement event)
if PROFIT < 0.01: PROFIT = 0.00 (with adjustment event)
```

---

## 📊 DISPLAY SUMMARY

### **What Shows in UI**

| Value | Formula | When Shown | Display Format |
|-------|---------|------------|----------------|
| Pending Amount | `(LOSS × total_share_pct) / 100` | LOSS >= ₹0.01 | ₹X.XX |
| Your Receivable | `(LOSS × my_share_pct) / 100` | LOSS >= ₹0.01 | ₹X.XX |
| Company Receivable | `(LOSS × 9) / 100` | LOSS >= ₹0.01, Company Client | ₹X.XX |
| Old Balance | `CAPITAL` (from ledger) | Always | ₹X.XX |
| Current Balance | `CB` (from balance record) | Always | ₹X.XX |
| Total Loss | `CAPITAL - CB` | LOSS >= ₹0.01 | ₹X.XX |
| Profit Amount | `CB - CAPITAL` | PROFIT >= ₹0.01 | ₹X.XX |

---

**Document Version**: Final  
**Last Updated**: 2026-01-05  
**Status**: ✅ Complete Pin-to-Pin Documentation


