# PARTIAL PAYMENTS & PENDING PAYMENTS - FINAL COMPLETE GUIDE

**Pin-to-Pin Documentation: All Formulas, Logic, Display Rules, and Examples**

---

## 📋 TABLE OF CONTENTS

1. [Core Definitions](#core-definitions)
2. [Fundamental Formulas (Golden Rules)](#fundamental-formulas-golden-rules)
3. [Partial Payment Logic (LOSS-First Approach)](#partial-payment-logic-loss-first-approach)
4. [Pending Payments Calculation](#pending-payments-calculation)
5. [Share Calculations](#share-calculations)
6. [Display Rules & UI Logic](#display-rules--ui-logic)
7. [Step-by-Step Examples](#step-by-step-examples)
8. [Validation Rules](#validation-rules)
9. [Database Storage](#database-storage)

---

## 🔑 CORE DEFINITIONS

### **CAPITAL (C) / Old Balance (OB)**
- **Definition**: Total money you have put into the exchange that is not yet settled
- **Database Field**: `ClientExchange.cached_old_balance`
- **Key Rule**: 
  - If LOSS > 0: `CAPITAL = CB + LOSS`
  - If PROFIT > 0: `CAPITAL < CB`
- **When It Changes**:
  - ✅ On settlement (for loss) - recomputed as `CB + LOSS_new`
  - ✅ On funding - `CAPITAL += funding_amount`
  - ❌ NEVER on profit withdrawal (only affects CB)

### **Current Balance (CB)**
- **Definition**: Actual exchange balance from latest `BALANCE_RECORD`
- **Database Field**: `ClientDailyBalance.remaining_balance`
- **When It Changes**:
  - ✅ On new `BALANCE_RECORD` creation
  - ✅ On profit withdrawal (decreases CB)
  - ✅ On funding (when auto-credited) - `CB += funding_amount`

### **LOSS**
- **Formula**: `LOSS = max(CAPITAL - CB, 0)`
- **Meaning**: Client's receivable (money client owes you)
- **When It Exists**: Only when `CAPITAL > CB`
- **Precision**: 1 decimal place (0.1)

### **PROFIT**
- **Formula**: `PROFIT = max(CB - CAPITAL, 0)`
- **Meaning**: Your liability (money you owe client)
- **When It Exists**: Only when `CB > CAPITAL`
- **Precision**: 1 decimal place (0.1)

### **NET Movement (NET)**
- **Formula**: `NET = CB - CAPITAL`
- **Purpose**: Informational only
- **Values**: `NET < 0` = Loss, `NET > 0` = Profit, `NET = 0` = Break-even

---

## 📐 FUNDAMENTAL FORMULAS (GOLDEN RULES)

### **🧠 FINAL GOLDEN FORMULA (PIN THIS)**

```
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

**Key Rules**:
- All calculations use 1 decimal place precision (0.1)
- Single epsilon (0.1) for all comparisons
- CAPITAL = CB + LOSS only when LOSS > 0

---

## 🔄 PARTIAL PAYMENT LOGIC (LOSS-FIRST APPROACH)

### **Complete Correct Flow**

```python
# Step 1: Setup
epsilon = Decimal("0.1")  # Single epsilon, 1 decimal place

# Step 2: Calculate current LOSS
loss_current = max(CAPITAL - CB, 0)
loss_current = loss_current.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

# Step 3: Validate LOSS exists
if loss_current <= epsilon:
    REJECT  # No loss to settle

# Step 4: Calculate capital_closed
capital_closed = (payment × 100) / total_share_pct
capital_closed = capital_closed.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

# Step 5: Validate against LOSS
if capital_closed > loss_current + epsilon:
    REJECT  # Cannot close more capital than loss

# Step 6: Reduce LOSS
loss_new = max(loss_current - capital_closed, 0)
loss_new = loss_new.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

# Step 7: Re-derive CAPITAL (only when LOSS exists)
if loss_new > epsilon:
    CAPITAL_new = CB + loss_new  # Partial settlement
else:
    loss_new = Decimal(0)
    CAPITAL_new = CB  # Full settlement

# Step 8: Validate direction
if loss_new > epsilon and CAPITAL_new < CB:
    REJECT  # LOSS settlement must not create profit
```

### **Example: Partial Payment**

**Before Payment**:
```
CAPITAL = 100.0
CB = 40.0
LOSS = max(100.0 - 40.0, 0) = 60.0
total_share_pct = 10%
ClientPayable = (60.0 × 10) / 100 = 6.0
```

**Client Pays ₹3.0**:
```
payment = 3.0
capital_closed = (3.0 × 100) / 10 = 30.0

loss_current = 60.0
loss_new = max(60.0 - 30.0, 0) = 30.0
CAPITAL_new = 40.0 + 30.0 = 70.0

# Verify
LOSS_new = max(70.0 - 40.0, 0) = 30.0 ✅
ClientPayable_new = (30.0 × 10) / 100 = 3.0 ✅
```

**After Payment**:
```
CAPITAL = 70.0
CB = 40.0
LOSS = 30.0
ClientPayable = 3.0
```

---

## 📊 PENDING PAYMENTS CALCULATION

### **For MY CLIENTS**

```python
# Step 1: Get CAPITAL and CB
old_balance = get_old_balance_after_settlement(client_exchange)
current_balance = get_exchange_balance(client_exchange)

# Step 2: Calculate LOSS (always clamped)
epsilon = Decimal("0.1")
loss = max(old_balance - current_balance, 0)
loss = loss.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

# Step 3: Skip if no loss
if loss <= epsilon:
    continue  # No pending

# Step 4: Calculate receivables
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

### **Key Rules**
1. **Pending is NEVER stored** - always calculated statelessly
2. **Pending exists ONLY when LOSS > 0** - never shown for profit
3. **Use single epsilon (0.1)** - no mixed precision
4. **Separate receivables** - ClientPayable, YourReceivable, CompanyReceivable
5. **✅ ERROR 3 FIX: Epsilon = 0.1 is business rule** - We intentionally ignore amounts below ₹0.1
6. **✅ ERROR 4 FIX: CB must be locked** - Settlement must lock CB snapshot to prevent race conditions
7. **✅ ERROR 7 FIX: Share % frozen** - Share percentages are frozen at transaction start, never recalculated
8. **✅ ERROR 8 FIX: Same normalization** - Use same normalization for LOSS and PROFIT (break-even check)

---

## 🧮 SHARE CALCULATIONS

### **My Share (for MY CLIENTS)**
```
My Share = (LOSS × my_share_pct) / 100
```
- Example: LOSS = 60.0, my_share_pct = 10% → My Share = 6.0
- Full share goes to you

### **My Share (for COMPANY CLIENTS)**
```
My Share = (LOSS × 1) / 100
```
- Always 1% of loss
- Example: LOSS = 60.0 → My Share = 0.6

### **Company Share (for COMPANY CLIENTS)**
```
Company Share = (LOSS × 9) / 100
```
- Always 9% of loss
- Example: LOSS = 60.0 → Company Share = 5.4

### **Combined Share (for COMPANY CLIENTS)**
```
Combined Share = My Share + Company Share
Combined Share = (LOSS × 10) / 100
```
- Always 10% of loss (1% + 9%)
- Example: LOSS = 60.0 → Combined Share = 6.0

### **Total Share Percentage**
```
total_share_pct = my_share_pct  # For MY CLIENTS (e.g., 10%)
total_share_pct = 10  # For COMPANY CLIENTS (always 10%)
```

---

## 🖥️ DISPLAY RULES & UI LOGIC

### **"Clients Owe You" Section**

#### **When to Show**
- Only when `CAPITAL > CB` (loss case)
- Only when `loss > epsilon` (epsilon = 0.1)

#### **What to Display**

**For MY CLIENTS**:
- **Client Name**
- **Exchange Name**
- **Pending Amount**: `ClientPayable = (LOSS × my_share_pct) / 100`
- **Your Receivable**: Same as Pending (full share)
- **Old Balance**: CAPITAL
- **Current Balance**: CB
- **Total Loss**: `CAPITAL - CB`

**For COMPANY CLIENTS**:
- **Client Name**
- **Exchange Name**
- **Pending Amount**: 
  - If `combine_shares = True`: `Combined Share = (LOSS × 10) / 100`
  - If `combine_shares = False`: Show separately
    - **My Share**: `(LOSS × 1) / 100`
    - **Company Share**: `(LOSS × 9) / 100`
- **Old Balance**: CAPITAL
- **Current Balance**: CB
- **Total Loss**: `CAPITAL - CB`

### **"You Owe Clients" Section**

#### **When to Show**
- Only when `CB > CAPITAL` (profit case)
- Only when `profit > epsilon` (epsilon = 0.1)

#### **What to Display**
- **Client Name**
- **Exchange Name**
- **Profit Amount**: `CB - CAPITAL`
- **Your Share**: What you owe
- **Old Balance**: CAPITAL
- **Current Balance**: CB

#### **Important**
- **NO PENDING shown for profit** - pending exists only for loss
- Profit withdrawal affects only CB, never CAPITAL

---

## 📝 STEP-BY-STEP EXAMPLES

### **Example 1: Simple Partial Payment**

#### **Initial State**
```
Funding: ₹100.0
CAPITAL = 100.0
CB = 100.0
LOSS = 0.0
ClientPayable = 0.0
```

#### **After Trading Loss**
```
Balance Record: ₹40.0
CAPITAL = 100.0
CB = 40.0
LOSS = max(100.0 - 40.0, 0) = 60.0
ClientPayable = (60.0 × 10) / 100 = 6.0
```

#### **Partial Payment: ₹3.0**
```
payment = 3.0
capital_closed = (3.0 × 100) / 10 = 30.0

loss_current = 60.0
loss_new = max(60.0 - 30.0, 0) = 30.0
CAPITAL_new = 40.0 + 30.0 = 70.0

# Verify
LOSS_new = max(70.0 - 40.0, 0) = 30.0 ✅
ClientPayable_new = (30.0 × 10) / 100 = 3.0 ✅
```

#### **Final State**
```
CAPITAL = 70.0
CB = 40.0
LOSS = 30.0
ClientPayable = 3.0
```

### **Example 2: Multiple Partial Payments**

#### **Initial State**
```
CAPITAL = 100.0
CB = 40.0
LOSS = 60.0
ClientPayable = 6.0
```

#### **Payment 1: ₹2.0**
```
payment = 2.0
capital_closed = 20.0

loss_current = 60.0
loss_new = 40.0
CAPITAL_new = 40.0 + 40.0 = 80.0

# State after Payment 1
CAPITAL = 80.0
CB = 40.0
LOSS = 40.0
ClientPayable = 4.0
```

#### **Payment 2: ₹1.5**
```
payment = 1.5
capital_closed = 15.0

loss_current = 40.0
loss_new = 25.0
CAPITAL_new = 40.0 + 25.0 = 65.0

# State after Payment 2
CAPITAL = 65.0
CB = 40.0
LOSS = 25.0
ClientPayable = 2.5
```

#### **Payment 3: ₹2.5 (Full Settlement)**
```
payment = 2.5
capital_closed = 25.0

loss_current = 25.0
loss_new = 0.0
CAPITAL_new = 40.0  # Full settlement

# State after Payment 3
CAPITAL = 40.0
CB = 40.0
LOSS = 0.0
ClientPayable = 0.0
```

### **Example 3: Company Client with Combined Share**

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

#### **Partial Payment: ₹3.0**
```
payment = 3.0
capital_closed = (3.0 × 100) / 10 = 30.0

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

### **Example 4: Profit Withdrawal**

#### **Initial State**
```
CAPITAL = 100.0
CB = 120.0
PROFIT = max(120.0 - 100.0, 0) = 20.0
```

#### **Withdraw ₹10.0**
```
withdrawal = 10.0  # Direct amount, NOT capital_closed

# Validate
if withdrawal > profit_current + epsilon:
    REJECT  # Cannot withdraw more than profit

# Update CB
CB_new = 120.0 - 10.0 = 110.0
CAPITAL_new = 100.0  # Unchanged

# Verify
PROFIT_new = max(110.0 - 100.0, 0) = 10.0 ✅
```

#### **Final State**
```
CAPITAL = 100.0
CB = 110.0
PROFIT = 10.0
```

---

## ✅ VALIDATION RULES

### **Settlement Validation**

#### **1. Payment Amount Validation**
```python
if amount <= Decimal(0):
    REJECT  # Payment must be positive
```

#### **2. LOSS Exists Validation (✅ ERROR 1 FIX)**
```python
epsilon = Decimal("0.1")
loss_current = max(old_balance - current_balance, 0)
loss_current = loss_current.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

# ✅ ERROR 1 FIX: Only reject if loss is negative (never block based on epsilon)
# This allows valid final settlements even when loss <= epsilon
if loss_current < 0:
    REJECT  # Invalid loss (negative)
```

#### **3. Capital Closed Validation (✅ ERROR 2 FIX)**
```python
# ✅ ERROR 2 FIX: Validate raw value BEFORE rounding (prevents false rejections)
capital_closed_raw = (payment × 100) / total_share_pct

if capital_closed_raw > loss_current + epsilon:
    REJECT  # Cannot close more capital than loss

# ✅ ERROR 2 FIX: Round AFTER validation
capital_closed = capital_closed_raw.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
```

#### **4. Direction Validation**
```python
# Only check LOSS exists, not NET direction
# The invariant check is sufficient
if loss_new > epsilon and CAPITAL_new < CB:
    REJECT  # LOSS settlement must not create profit
```

#### **5. CAPITAL Non-Negative Validation (✅ ERROR 6 FIX)**
```python
# ✅ ERROR 6 FIX: Normalize CAPITAL aggressively (prevent zombie balances)
if CAPITAL_new < epsilon:
    CAPITAL_new = Decimal(0)

if CAPITAL_new < 0:
    REJECT  # CAPITAL cannot be negative
```

### **Profit Withdrawal Validation**

```python
epsilon = Decimal("0.1")
profit_current = max(current_balance - old_balance, 0)
profit_current = profit_current.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

# Profit withdrawals do NOT use capital_closed
withdrawal = amount  # Direct amount

if withdrawal > profit_current + epsilon:
    REJECT  # Cannot withdraw more than profit

CB_new = current_balance - withdrawal
if CB_new < old_balance - epsilon:
    REJECT  # Withdrawal cannot create fake loss
```

---

## 💾 DATABASE STORAGE

### **ClientExchange Model**

#### **cached_old_balance (CAPITAL)**
- **Type**: `DecimalField(max_digits=14, decimal_places=2)`
- **Precision**: 1 decimal place (0.1)
- **Updated**: On settlement, on funding

#### **cached_current_balance (CB)**
- **Type**: `DecimalField(max_digits=14, decimal_places=2)`
- **Precision**: 1 decimal place (0.1)
- **Updated**: Via signals when `BALANCE_RECORD` is created

### **Transaction Model**

#### **amount**
- **Type**: `DecimalField(max_digits=14, decimal_places=2)`
- **Precision**: 1 decimal place (0.1)
- Payment amount (in share space)

#### **your_share_amount**
- **Type**: `DecimalField(max_digits=14, decimal_places=2)`
- **Precision**: 1 decimal place (0.1)
- Your share amount

#### **company_share_amount**
- **Type**: `DecimalField(max_digits=14, decimal_places=2)**
- **Precision**: 1 decimal place (0.1)
- Company share amount

---

## 🔒 CRITICAL INVARIANTS

### **1. CAPITAL Invariant**
```
CAPITAL >= 0  (always)
If LOSS > 0: CAPITAL = CB + LOSS
If PROFIT > 0: CAPITAL < CB
```

### **2. LOSS/PROFIT Mutually Exclusive**
```
LOSS = max(CAPITAL - CB, 0)
PROFIT = max(CB - CAPITAL, 0)
```
- Only one can be > 0 at a time

### **3. Pending Exists Only for Loss**
```
IF LOSS > epsilon:
    ClientPayable = (LOSS × total_share_pct) / 100
ELSE:
    ClientPayable = 0
```

### **4. Settlement Invariant**
```
After settlement:
    if loss_new > epsilon:
        CAPITAL_new = CB + loss_new
    else:
        CAPITAL_new = CB
```

### **5. Funding Invariant (✅ ERROR 5 FIX)**
```
After funding:
    CAPITAL_new = CAPITAL_old + funding_amount
    CB_new = CB_old + funding_amount
    (CAPITAL - CB) remains unchanged
    
✅ ERROR 5 FIX: Funding keeps LOSS unchanged,
BUT LOSS and receivables MUST be recalculated after funding
(UI must refresh to show correct pending)
```

### **6. Profit Withdrawal Invariant**
```
After profit withdrawal:
    CAPITAL_new = CAPITAL_old  (unchanged)
    CB_new = CB_old - withdrawal_amount
    PROFIT_new = max(CB_new - CAPITAL_new, 0)
```

---

## 🎯 SUMMARY

### **Key Takeaways**

1. **LOSS-First Approach**: Always reduce LOSS first, then re-derive CAPITAL
2. **Pending is Stateless**: Never stored, always calculated from CAPITAL and CB
3. **Single Epsilon**: Use 0.1 (1 decimal place) for all comparisons
4. **Separate Receivables**: ClientPayable, YourReceivable, CompanyReceivable
5. **Precision Consistency**: All calculations use 0.1 precision
6. **CAPITAL Rule**: `CAPITAL = CB + LOSS` only when LOSS > 0
7. **✅ ERROR 1 FIX**: Never block settlement based on epsilon (only reject if loss < 0)
8. **✅ ERROR 2 FIX**: Validate capital_closed_raw BEFORE rounding
9. **✅ ERROR 3 FIX**: Epsilon = 0.1 is explicit business rule (ignore amounts < ₹0.1)
10. **✅ ERROR 4 FIX**: Lock CB snapshot during settlement (prevent race conditions)
11. **✅ ERROR 5 FIX**: Recalculate LOSS after funding (UI must refresh)
12. **✅ ERROR 6 FIX**: Normalize CAPITAL aggressively (prevent zombie balances)
13. **✅ ERROR 7 FIX**: Freeze share_pct at transaction start (never recalculate)
14. **✅ ERROR 8 FIX**: Use same normalization for LOSS and PROFIT (break-even check)

### **Formulas Quick Reference**

```
epsilon = Decimal("0.1")  # Single epsilon, 1 decimal place

LOSS = max(CAPITAL - CB, 0)
PROFIT = max(CB - CAPITAL, 0)

If LOSS > 0: CAPITAL = CB + LOSS
If PROFIT > 0: CAPITAL < CB

ClientPayable = LOSS × total_share_pct / 100
YourReceivable = LOSS × my_share_pct / 100
CompanyReceivable = LOSS × company_share_pct / 100

# LOSS Settlement
capital_closed = (payment × 100) / total_share_pct
loss_new = max(loss_current - capital_closed, 0)
loss_new = loss_new.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
if loss_new <= epsilon:
    CAPITAL_new = CB  # Full settlement
else:
    CAPITAL_new = CB + loss_new  # Partial settlement

# Profit Withdrawal (does NOT use capital_closed)
withdrawal = amount  # Direct amount
CB_new = CB - withdrawal
CAPITAL_new = CAPITAL_old  # Unchanged
```

---

**Document Version**: 3.0  
**Last Updated**: 2026-01-04  
**Status**: ✅ Complete, All 8 Errors Fixed, 1 Decimal Place Precision

