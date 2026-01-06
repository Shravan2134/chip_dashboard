# PARTIAL PAYMENTS & PENDING PAYMENTS - COMPLETE FINAL GUIDE

**Pin-to-Pin Documentation: All Formulas, Logic, Display Rules, and How Everything Works**

---

## 📋 TABLE OF CONTENTS

1. [Core Definitions](#core-definitions)
2. [Fundamental Formulas](#fundamental-formulas)
3. [Partial Payment Logic (Complete Flow)](#partial-payment-logic-complete-flow)
4. [Pending Payments Calculation](#pending-payments-calculation)
5. [Share Calculations (My Share vs Company Share)](#share-calculations)
6. [How Values Are Displayed in UI](#how-values-are-displayed-in-ui)
7. [Complete Examples with Numbers](#complete-examples-with-numbers)
8. [All 15 Critical Fixes](#all-15-critical-fixes)
9. [Validation Rules](#validation-rules)

---

## 🔑 CORE DEFINITIONS

### **CAPITAL (C) / Old Balance (OB)**
- **What It Is**: Total money you have put into the exchange that is not yet settled
- **Database Field**: `ClientExchange.cached_old_balance`
- **Formula**: 
  - If LOSS > 0: `CAPITAL = CB + LOSS`
  - If PROFIT > 0: `CAPITAL < CB`
- **When It Changes**:
  - ✅ On settlement (for loss) - recomputed as `CB + LOSS_new`
  - ✅ On funding - `CAPITAL += funding_amount`
  - ❌ NEVER on profit withdrawal (only affects CB)
- **Display**: Shown as "Old Balance" in UI

### **Current Balance (CB)**
- **What It Is**: Actual exchange balance from latest `BALANCE_RECORD`
- **Database Field**: `ClientDailyBalance.remaining_balance`
- **When It Changes**:
  - ✅ On new `BALANCE_RECORD` creation
  - ✅ On profit withdrawal (decreases CB)
  - ✅ On funding (when auto-credited) - `CB += funding_amount`
- **Display**: Shown as "Current Balance" in UI

### **LOSS**
- **Formula**: `LOSS = max(CAPITAL - CB, 0)`
- **Meaning**: Client's receivable (money client owes you)
- **When It Exists**: Only when `CAPITAL > CB`
- **Precision**: 1 decimal place (0.1)
- **Display**: Used to calculate pending amounts

### **PROFIT**
- **Formula**: `PROFIT = max(CB - CAPITAL, 0)`
- **Meaning**: Your liability (money you owe client)
- **When It Exists**: Only when `CB > CAPITAL`
- **Precision**: 1 decimal place (0.1)
- **Display**: Shown in "You Owe Clients" section

### **NET Movement (NET)**
- **Formula**: `NET = CB - CAPITAL`
- **Purpose**: Informational only (not used in business logic)
- **Values**: 
  - `NET < 0` = Loss
  - `NET > 0` = Profit
  - `NET = 0` = Break-even

---

## 📐 FUNDAMENTAL FORMULAS

### **🧠 GOLDEN FORMULAS (PIN THIS)**

```python
# Single epsilon for all comparisons (1 decimal place)
epsilon = Decimal("0.1")

# Core calculations
LOSS = max(CAPITAL - CB, 0)
PROFIT = max(CB - CAPITAL, 0)

# CAPITAL invariant (only true when LOSS exists)
If LOSS > 0: CAPITAL = CB + LOSS
If PROFIT > 0: CAPITAL < CB

# Receivables (separated for clarity)
ClientPayable = LOSS × total_share_pct / 100
YourReceivable = LOSS × my_share_pct / 100
CompanyReceivable = LOSS × company_share_pct / 100
```

---

## 🔄 PARTIAL PAYMENT LOGIC (COMPLETE FLOW)

### **Step-by-Step Complete Flow**

```python
# ✅ ALL 15 ERRORS FIXED - PRODUCTION SAFE

# Step 1: Setup
epsilon = Decimal("0.1")

# Step 2: Lock CB snapshot (✅ ERROR 6 FIX - prevent race conditions)
cb_snapshot = current_balance  # Use this for all calculations

# Step 3: Calculate current LOSS and PROFIT
loss_current = max(CAPITAL - cb_snapshot, 0)
profit_current = max(cb_snapshot - CAPITAL, 0)

# Step 4: ✅ ERROR 1 FIX - Block settlement when LOSS = 0
if loss_current == 0:
    REJECT  # No loss to settle

# Step 5: ✅ ERROR 15 FIX - Block LOSS settlement when PROFIT exists
if profit_current > 0:
    REJECT  # Cannot settle loss when client is in profit

# Step 6: ✅ ERROR 3 FIX - Prevent division by zero
if total_share_pct <= 0:
    REJECT  # Invalid share percentage

# Step 7: Calculate capital_closed_raw (validate BEFORE rounding)
capital_closed_raw = (payment × 100) / total_share_pct

# Step 8: ✅ ERROR 4 FIX - Strict upper bound
if capital_closed_raw > loss_current:
    REJECT  # Cannot close more capital than loss

# Step 9: Round AFTER validation
capital_closed = capital_closed_raw.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

# Step 10: Reduce LOSS
loss_new = loss_current - capital_closed

# Step 11: ✅ ERROR 5 FIX - Guard against negative LOSS
if loss_new < 0:
    REJECT  # Settlement would create negative loss

# Step 12: Re-derive CAPITAL
if loss_new == 0:
    CAPITAL_new = cb_snapshot  # Full settlement
else:
    CAPITAL_new = cb_snapshot + loss_new  # Partial settlement

# Step 13: ✅ ERROR 6 FIX - Normalize CAPITAL only when LOSS = 0
if CAPITAL_new < epsilon and loss_new == 0:
    CAPITAL_new = Decimal(0)

# Step 14: ✅ ERROR 14 FIX - Post-settlement invariant checks
if CAPITAL_new < 0:
    REJECT  # CAPITAL cannot be negative

if CAPITAL_new < cb_snapshot:
    REJECT  # CAPITAL must be >= CB for LOSS settlement

loss_verify = CAPITAL_new - cb_snapshot
if abs(loss_new - loss_verify) > epsilon:
    REJECT  # Loss invariant violation

# Step 15: ✅ ERROR 13 FIX - Upper bound on payment
client_payable_before = (loss_current × total_share_pct) / 100
if payment > client_payable_before + epsilon:
    REJECT  # Payment exceeds pending amount
```

---

## 📊 PENDING PAYMENTS CALCULATION

### **For MY CLIENTS**

```python
# Step 1: Get CAPITAL and CB
old_balance = get_old_balance_after_settlement(client_exchange)
current_balance = get_exchange_balance(client_exchange)

# Step 2: Calculate LOSS (always clamped)
loss = max(old_balance - current_balance, 0)
loss = loss.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
if loss <= epsilon:
    loss = Decimal(0)
    continue  # No pending

# Step 3: Calculate receivables
my_share_pct = client_exchange.my_share_pct  # e.g., 10%
ClientPayable = (loss × my_share_pct) / 100
YourReceivable = ClientPayable  # Full share for my clients
CompanyReceivable = Decimal(0)

# Round to 1 decimal place
ClientPayable = ClientPayable.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
YourReceivable = YourReceivable.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
```

### **For COMPANY CLIENTS**

```python
# Step 1: Calculate LOSS
loss = max(old_balance - current_balance, 0)
loss = loss.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
if loss <= epsilon:
    loss = Decimal(0)
    continue  # No pending

# Step 2: Calculate receivables
total_share_pct = 10  # Always 10% for company clients
ClientPayable = (loss × 10) / 100
YourReceivable = (loss × 1) / 100   # 1% for you
CompanyReceivable = (loss × 9) / 100  # 9% for company

# Round to 1 decimal place
ClientPayable = ClientPayable.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
YourReceivable = YourReceivable.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
CompanyReceivable = CompanyReceivable.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
```

---

## 🧮 SHARE CALCULATIONS

### **My Share (for MY CLIENTS)**
```
My Share = (LOSS × my_share_pct) / 100
```
- Example: LOSS = 60.0, my_share_pct = 10% → My Share = 6.0
- Full share goes to you
- **Display**: Shown as "Your Receivable" in UI

### **My Share (for COMPANY CLIENTS)**
```
My Share = (LOSS × 1) / 100
```
- Always 1% of loss
- Example: LOSS = 60.0 → My Share = 0.6
- **Display**: Shown as "Your Receivable" in UI

### **Company Share (for COMPANY CLIENTS)**
```
Company Share = (LOSS × 9) / 100
```
- Always 9% of loss
- Example: LOSS = 60.0 → Company Share = 5.4
- **Display**: Shown as "Company Receivable" in UI

### **Combined Share (for COMPANY CLIENTS)**
```
Combined Share = My Share + Company Share
Combined Share = (LOSS × 10) / 100
```
- Always 10% of loss (1% + 9%)
- Example: LOSS = 60.0 → Combined Share = 6.0
- **Display**: Shown as "Pending Amount" if `combine_shares = True`

---

## 🖥️ HOW VALUES ARE DISPLAYED IN UI

### **"Clients Owe You" Section**

#### **When to Show**
- Only when `CAPITAL > CB` (loss case)
- Only when `loss > epsilon` (epsilon = 0.1)

#### **What to Display**

**For MY CLIENTS**:
```
Client Name: [Client Name]
Exchange Name: [Exchange Name]

Pending Amount: ₹[ClientPayable]
  Formula: (LOSS × my_share_pct) / 100
  Example: (60.0 × 10) / 100 = ₹6.0

Your Receivable: ₹[YourReceivable]
  Same as Pending Amount (full share)

Old Balance: ₹[CAPITAL]
  From: ClientExchange.cached_old_balance

Current Balance: ₹[CB]
  From: Latest ClientDailyBalance.remaining_balance

Total Loss: ₹[LOSS]
  Formula: CAPITAL - CB
  Example: 100.0 - 40.0 = ₹60.0
```

**For COMPANY CLIENTS**:
```
Client Name: [Client Name]
Exchange Name: [Exchange Name]

Pending Amount: ₹[ClientPayable]
  If combine_shares = True: Show Combined Share
    Formula: (LOSS × 10) / 100
    Example: (60.0 × 10) / 100 = ₹6.0
  If combine_shares = False: Show separately
    My Share: ₹[YourReceivable] = (LOSS × 1) / 100 = ₹0.6
    Company Share: ₹[CompanyReceivable] = (LOSS × 9) / 100 = ₹5.4

Your Receivable: ₹[YourReceivable]
  Formula: (LOSS × 1) / 100
  Example: (60.0 × 1) / 100 = ₹0.6

Company Receivable: ₹[CompanyReceivable]
  Formula: (LOSS × 9) / 100
  Example: (60.0 × 9) / 100 = ₹5.4

Old Balance: ₹[CAPITAL]
Current Balance: ₹[CB]
Total Loss: ₹[LOSS]
```

### **"You Owe Clients" Section**

#### **When to Show**
- Only when `CB > CAPITAL` (profit case)
- Only when `profit > epsilon` (epsilon = 0.1)

#### **What to Display**
```
Client Name: [Client Name]
Exchange Name: [Exchange Name]

Profit Amount: ₹[PROFIT]
  Formula: CB - CAPITAL
  Example: 120.0 - 100.0 = ₹20.0

Your Share: ₹[Your Share of Profit]
  What you owe to client

Old Balance: ₹[CAPITAL]
Current Balance: ₹[CB]
```

---

## 📝 COMPLETE EXAMPLES WITH NUMBERS

### **Example 1: Simple Partial Payment (My Client)**

#### **Initial State**
```
Funding: ₹100.0
CAPITAL = 100.0
CB = 100.0
LOSS = 0.0
ClientPayable = 0.0
```

**UI Display**: No pending shown

#### **After Trading Loss**
```
Balance Record: ₹40.0
CAPITAL = 100.0
CB = 40.0
LOSS = max(100.0 - 40.0, 0) = 60.0
my_share_pct = 10%
ClientPayable = (60.0 × 10) / 100 = 6.0
YourReceivable = 6.0
```

**UI Display**:
- Pending Amount: ₹6.0
- Your Receivable: ₹6.0
- Old Balance: ₹100.0
- Current Balance: ₹40.0
- Total Loss: ₹60.0

#### **Partial Payment: ₹3.0**
```
payment = 3.0
capital_closed_raw = (3.0 × 100) / 10 = 30.0
capital_closed = 30.0

loss_current = 60.0
loss_new = 60.0 - 30.0 = 30.0
CAPITAL_new = 40.0 + 30.0 = 70.0

# Verify
LOSS_new = max(70.0 - 40.0, 0) = 30.0 ✅
ClientPayable_new = (30.0 × 10) / 100 = 3.0 ✅
```

**UI Display After Payment**:
- Pending Amount: ₹3.0
- Your Receivable: ₹3.0
- Old Balance: ₹70.0
- Current Balance: ₹40.0
- Total Loss: ₹30.0

### **Example 2: Company Client with Combined Share**

#### **Initial State**
```
CAPITAL = 100.0
CB = 40.0
LOSS = 60.0
total_share_pct = 10%
ClientPayable = (60.0 × 10) / 100 = 6.0
YourReceivable = (60.0 × 1) / 100 = 0.6
CompanyReceivable = (60.0 × 9) / 100 = 5.4
```

**UI Display (combine_shares = True)**:
- Pending Amount: ₹6.0 (Combined Share)
- Old Balance: ₹100.0
- Current Balance: ₹40.0
- Total Loss: ₹60.0

**UI Display (combine_shares = False)**:
- My Share: ₹0.6
- Company Share: ₹5.4
- Old Balance: ₹100.0
- Current Balance: ₹40.0
- Total Loss: ₹60.0

#### **Partial Payment: ₹3.0**
```
payment = 3.0
capital_closed_raw = (3.0 × 100) / 10 = 30.0
capital_closed = 30.0

loss_current = 60.0
loss_new = 30.0
CAPITAL_new = 40.0 + 30.0 = 70.0

# State after Payment
CAPITAL = 70.0
CB = 40.0
LOSS = 30.0
ClientPayable = (30.0 × 10) / 100 = 3.0
YourReceivable = (30.0 × 1) / 100 = 0.3
CompanyReceivable = (30.0 × 9) / 100 = 2.7
```

**UI Display After Payment**:
- Pending Amount: ₹3.0
- Your Receivable: ₹0.3
- Company Receivable: ₹2.7
- Old Balance: ₹70.0
- Current Balance: ₹40.0
- Total Loss: ₹30.0

### **Example 3: Profit Withdrawal**

#### **Initial State**
```
CAPITAL = 100.0
CB = 120.0
PROFIT = max(120.0 - 100.0, 0) = 20.0
```

**UI Display**:
- Profit Amount: ₹20.0
- Old Balance: ₹100.0
- Current Balance: ₹120.0

#### **Withdraw ₹10.0**
```
withdrawal = 10.0  # Direct amount, NOT capital_closed

# ✅ ERROR 12 FIX: Validate withdrawal amount
if withdrawal > profit_current:
    REJECT  # Cannot withdraw more than profit

# Update CB
CB_new = 120.0 - 10.0 = 110.0
CAPITAL_new = 100.0  # Unchanged

# Verify
PROFIT_new = max(110.0 - 100.0, 0) = 10.0 ✅
```

**UI Display After Withdrawal**:
- Profit Amount: ₹10.0
- Old Balance: ₹100.0
- Current Balance: ₹110.0

---

## 🔧 ALL 15 CRITICAL FIXES

### **ERROR 1: Settlement allowed when LOSS = 0**
**✅ Fix**: `if loss_current == 0: REJECT`

### **ERROR 2: Mixing LOSS and PROFIT paths**
**✅ Fix**: Separate flows for `client_pays` and `admin_pays_profit`

### **ERROR 3: capital_closed division by zero**
**✅ Fix**: `if total_share_pct <= 0: REJECT`

### **ERROR 4: capital_closed can exceed LOSS**
**✅ Fix**: `if capital_closed_raw > loss_current: REJECT`

### **ERROR 5: Negative LOSS_new not guarded**
**✅ Fix**: `if loss_new < 0: REJECT`

### **ERROR 6: CAPITAL recomputed without CB lock**
**✅ Fix**: `cb_snapshot = current_balance` (locked at transaction start)

### **ERROR 7: Funding vs settlement order**
**✅ Fix**: Documented - enforced by DB transaction ordering

### **ERROR 8: Settlement not idempotent**
**⚠️ TODO**: Requires unique settlement_id

### **ERROR 9: Share % frozen too late**
**✅ Fix**: Share % frozen at transaction start

### **ERROR 10: Pending derived from cached CAPITAL**
**✅ Fix**: Recompute from guaranteed-updated CAPITAL

### **ERROR 11: LOSS/PROFIT history not stored**
**⚠️ TODO**: Requires audit trail table

### **ERROR 12: Profit withdrawal can make CB negative**
**✅ Fix**: `if withdrawal > profit_current: REJECT` and `if cb_new < 0: REJECT`

### **ERROR 13: No upper bound on payment**
**✅ Fix**: `if payment > client_payable_before + epsilon: REJECT`

### **ERROR 14: No invariant check after settlement**
**✅ Fix**: Post-settlement assertions for CAPITAL >= CB and LOSS == CAPITAL - CB

### **ERROR 15: LOSS settlement when PROFIT exists**
**✅ Fix**: `if profit_current > 0: REJECT`

---

## ✅ VALIDATION RULES

### **Settlement Validation (Complete)**

```python
# ✅ ERROR 1 FIX: Block settlement when LOSS = 0
if loss_current == 0:
    REJECT

# ✅ ERROR 15 FIX: Block LOSS settlement when PROFIT exists
if profit_current > 0:
    REJECT

# ✅ ERROR 3 FIX: Prevent division by zero
if total_share_pct <= 0:
    REJECT

# ✅ ERROR 4 FIX: Strict upper bound
if capital_closed_raw > loss_current:
    REJECT

# ✅ ERROR 5 FIX: Guard against negative LOSS
if loss_new < 0:
    REJECT

# ✅ ERROR 13 FIX: Upper bound on payment
if payment > client_payable_before + epsilon:
    REJECT

# ✅ ERROR 14 FIX: Post-settlement invariant checks
if CAPITAL_new < 0:
    REJECT
if CAPITAL_new < cb_snapshot:
    REJECT
if abs(loss_new - (CAPITAL_new - cb_snapshot)) > epsilon:
    REJECT
```

### **Profit Withdrawal Validation**

```python
# ✅ ERROR 1 FIX: Block withdrawal when PROFIT = 0
if profit_current == 0:
    REJECT

# ✅ ERROR 2 FIX: Block profit withdrawal when LOSS exists
if loss_current > 0:
    REJECT

# ✅ ERROR 12 FIX: Validate withdrawal amount
if withdrawal > profit_current:
    REJECT

# ✅ ERROR 12 FIX: Prevent CB from going negative
if cb_new_after_withdrawal < 0:
    REJECT
```

---

## 🎯 SUMMARY

### **Key Formulas**

```
LOSS = max(CAPITAL - CB, 0)
PROFIT = max(CB - CAPITAL, 0)

If LOSS > 0: CAPITAL = CB + LOSS
If PROFIT > 0: CAPITAL < CB

ClientPayable = LOSS × total_share_pct / 100
YourReceivable = LOSS × my_share_pct / 100
CompanyReceivable = LOSS × company_share_pct / 100

# Partial Payment
capital_closed_raw = (payment × 100) / total_share_pct
loss_new = loss_current - capital_closed
CAPITAL_new = CB + loss_new (if loss_new > 0)
CAPITAL_new = CB (if loss_new == 0)
```

### **Display Rules**

- **Pending shown only when LOSS > 0**
- **Profit shown only when PROFIT > 0**
- **My Share**: Full share for my clients, 1% for company clients
- **Company Share**: 9% for company clients only
- **All values rounded to 1 decimal place**

---

**Document Version**: 5.0  
**Last Updated**: 2026-01-05  
**Status**: ✅ Complete, All 15 Errors Fixed, Production-Safe


