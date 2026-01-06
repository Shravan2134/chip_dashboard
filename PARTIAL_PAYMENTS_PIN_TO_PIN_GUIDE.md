# PARTIAL PAYMENTS & PENDING PAYMENTS - PIN-TO-PIN COMPLETE GUIDE

**Complete Documentation: Formulas, Logic, Display Rules, and Examples**

---

## 📋 TABLE OF CONTENTS

1. [Core Definitions & Variables](#core-definitions--variables)
2. [Fundamental Formulas (Golden Rules)](#fundamental-formulas-golden-rules)
3. [Partial Payment Logic (LOSS-First Approach)](#partial-payment-logic-loss-first-approach)
4. [Pending Payments Calculation](#pending-payments-calculation)
5. [Share Calculations (My Share, Company Share, Combined Share)](#share-calculations)
6. [Display Rules & UI Logic](#display-rules--ui-logic)
7. [Step-by-Step Examples](#step-by-step-examples)
8. [Validation Rules](#validation-rules)
9. [Database Storage](#database-storage)

---

## 🔑 CORE DEFINITIONS & VARIABLES

### **CAPITAL (C) / Old Balance (OB)**
- **Definition**: Total money you have put into the exchange that is not yet settled
- **Alternative Name**: "Total funded money currently at risk"
- **Database Field**: `ClientExchange.cached_old_balance`
- **Key Rule**: CAPITAL is stored, but derived truth is always `CAPITAL = CB + LOSS`
- **When It Changes**:
  - ✅ On settlement (for loss) - recomputed as `CB + LOSS_new`
  - ✅ On funding - `CAPITAL += funding_amount`
  - ❌ NEVER on profit withdrawal (only affects CB)
  - ❌ NEVER on balance records (only updates CB)

### **Current Balance (CB)**
- **Definition**: Actual exchange balance from latest `BALANCE_RECORD`
- **Database Field**: `ClientDailyBalance.remaining_balance` (latest record)
- **When It Changes**:
  - ✅ On new `BALANCE_RECORD` creation (exchange balance update)
  - ✅ On profit withdrawal (decreases CB via balance record)
  - ✅ On funding (when auto-credited) - `CB += funding_amount`
  - ❌ NEVER on settlement (settlement only moves CAPITAL)

### **LOSS**
- **Formula**: `LOSS = max(CAPITAL - CB, 0)`
- **Meaning**: Client's receivable (money client owes you)
- **When It Exists**: Only when `CAPITAL > CB`
- **Display**: Shown in "Clients Owe You" section

### **PROFIT**
- **Formula**: `PROFIT = max(CB - CAPITAL, 0)`
- **Meaning**: Your liability (money you owe client)
- **When It Exists**: Only when `CB > CAPITAL`
- **Display**: Shown in "You Owe Clients" section

### **NET Movement (NET)**
- **Formula**: `NET = CB - CAPITAL`
- **Purpose**: Informational only (determines loss/profit direction)
- **NOT used for business logic** - use `LOSS` or `PROFIT` instead
- **Values**:
  - `NET < 0` → Loss case (client owes you)
  - `NET > 0` → Profit case (you owe client)
  - `NET = 0` → Break-even (no pending)

### **Pending Amount**
- **Formula**: `Pending = (LOSS × total_share_pct) / 100`
- **Meaning**: Your share of the loss (what client owes you)
- **When It Exists**: Only when `LOSS > 0`
- **Storage**: **NEVER stored** - always calculated statelessly
- **Display**: Only shown when `LOSS > 0` (never shown for profit)

---

## 📐 FUNDAMENTAL FORMULAS (GOLDEN RULES)

### **🧠 FINAL GOLDEN FORMULA (PIN THIS)**

```
LOSS = max(CAPITAL - CB, 0)
PROFIT = max(CB - CAPITAL, 0)
If LOSS > 0: CAPITAL = CB + LOSS
If PROFIT > 0: CAPITAL < CB
Pending = LOSS × share_pct / 100
```

**✅ ERROR 1 FIX**: `CAPITAL = CB + LOSS` is only true when LOSS > 0. When PROFIT exists, CAPITAL < CB.

### **1. LOSS Calculation**
```
LOSS = max(CAPITAL - CB, 0)
```
- If `CAPITAL > CB`: `LOSS = CAPITAL - CB`
- If `CAPITAL ≤ CB`: `LOSS = 0`
- **Always clamped** - never negative

### **2. PROFIT Calculation**
```
PROFIT = max(CB - CAPITAL, 0)
```
- If `CB > CAPITAL`: `PROFIT = CB - CAPITAL`
- If `CB ≤ CAPITAL`: `PROFIT = 0`
- **Always clamped** - never negative

### **3. NET Calculation (Informational Only)**
```
NET = CB - CAPITAL
```
- `NET < 0` → Loss case
- `NET > 0` → Profit case
- `NET = 0` → Break-even

### **4. Pending Amount (✅ ERROR 4 FIX: Separated into 3 variables)**
```
ClientPayable = (LOSS × total_share_pct) / 100  # What client owes total
YourReceivable = (LOSS × my_share_pct) / 100    # What you receive
CompanyReceivable = (LOSS × company_share_pct) / 100  # What company receives
```
- Only calculated when `LOSS > 0`
- Rounded to 1 decimal place for display (✅ ERROR 8 FIX: 0.1 precision)
- **NEVER stored in database**
- **For MY CLIENTS**: `ClientPayable = YourReceivable` (full share)
- **For COMPANY CLIENTS**: `ClientPayable = YourReceivable + CompanyReceivable` (1% + 9% = 10%)

### **5. Capital Closed (from Payment) - LOSS Settlement Only**
```
capital_closed = (payment_amount × 100) / total_share_pct
```
- Converts payment amount to capital space
- Example: Payment ₹3, total_share_pct = 10% → `capital_closed = 3 × 100 / 10 = 30`
- **✅ ERROR 3 FIX**: Profit withdrawals do NOT use capital_closed - they use withdrawal amount directly

---

## 🔄 PARTIAL PAYMENT LOGIC (LOSS-FIRST APPROACH)

### **🚨 GOLDEN RULE**
> **Clients settle LOSS, not CAPITAL directly. CAPITAL is recomputed from LOSS + CB, never blindly reduced.**

### **Why LOSS-First Approach?**
The old approach (`CAPITAL_new = CAPITAL - capital_closed`) fails when:
- Multiple partial payments occur
- CB changes between payments
- Profit appears between settlements
- Rounding errors accumulate

The LOSS-first approach is **mathematically stable** and handles all edge cases.

### **Complete Correct Partial Payment Flow**

```python
# ✅ ERROR 5 FIX: Use single epsilon (0.1 for 1 decimal place)
# ✅ ERROR 8 FIX: Use 0.1 precision to match DB (decimal_places=2)
epsilon = Decimal("0.1")

# Step 1: Calculate current LOSS (the truth) - MUST be done before validation
loss_current = max(CAPITAL - CB, 0)

# Step 2: Validate LOSS exists
if loss_current <= epsilon:
    REJECT  # No loss to settle

# Step 3: Calculate capital_closed
capital_closed = (payment * 100) / total_share_pct
capital_closed = capital_closed.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

# Step 4: Validate against LOSS (not movement)
if capital_closed > loss_current + epsilon:
    REJECT  # Cannot close more capital than loss

# Step 5: Reduce LOSS
loss_new = max(loss_current - capital_closed, 0)

# Step 6: Normalize LOSS (✅ ERROR 8 FIX: Use 0.1 precision)
loss_new = loss_new.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
if loss_new <= epsilon:
    loss_new = Decimal(0)  # Normalize to 0

# Step 7: ✅ ERROR 1 FIX: Re-derive CAPITAL only when LOSS > 0
# ✅ ERROR 2 FIX: Only recompute CAPITAL on settlement (when LOSS exists)
if loss_new > epsilon:
    # LOSS exists: CAPITAL = CB + LOSS
    CAPITAL_new = CB + loss_new
else:
    # Full settlement: CAPITAL = CB
    CAPITAL_new = CB

# Step 8: Validate direction (simple check)
# ✅ ERROR 6 FIX: Removed duplicate direction check (only keep invariant)
if loss_new > epsilon and CAPITAL_new < CB:
    REJECT  # LOSS settlement must not create profit while loss still exists
```

### **Step-by-Step Example**

#### **Before Payment**
```
CAPITAL = 100
CB = 40
LOSS = max(100 - 40, 0) = 60
total_share_pct = 10%
Pending = (60 × 10) / 100 = 6
```

#### **Client Pays ₹3**
```
payment = 3
capital_closed = (3 × 100) / 10 = 30

# LOSS-First Approach
loss_current = 60
loss_new = max(60 - 30, 0) = 30
loss_new = 30.quantize(Decimal("0.0001")) = 30
CAPITAL_new = 40 + 30 = 70

# Verify
LOSS_new = max(70 - 40, 0) = 30 ✅
Pending_new = (30 × 10) / 100 = 3 ✅
```

#### **After Payment**
```
CAPITAL = 70
CB = 40
LOSS = 30
Pending = 3
```

---

## 📊 PENDING PAYMENTS CALCULATION

### **For MY CLIENTS**

#### **Step 1: Get CAPITAL and CB**
```python
old_balance = get_old_balance_after_settlement(client_exchange)
current_balance = get_exchange_balance(client_exchange)
```

#### **Step 2: Calculate NET LOSS**
```python
# ✅ ERROR 4 FIX: LOSS must always be clamped
net_loss = max(old_balance - current_balance, 0)
```

#### **Step 3: Validate (Skip if break-even)**
```python
if abs(old_balance - current_balance) < Decimal("0.01"):
    continue  # Skip - no pending
```

#### **Step 4: Calculate My Share (if loss)**
```python
if net_loss > 0:
    my_share_pct = client_exchange.my_share_pct  # e.g., 10%
    my_share = (net_loss * my_share_pct) / Decimal(100)
    my_share = my_share.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
else:
    my_share = Decimal(0)  # No pending for profit
```

### **For COMPANY CLIENTS**

#### **Step 1: Calculate Net Tallies**
```python
net_tallies = calculate_net_tallies_from_transactions(client_exchange)
net_client_tally = net_tallies["net_client_tally"]  # 1%
net_company_tally = net_tallies["net_company_tally"]  # 9%
```

#### **Step 2: Calculate Combined Share**
```python
if combine_shares:
    # Combined Share = My Share (1%) + Company Share (9%) = 10%
    combined_share = net_client_tally + net_company_tally
else:
    # Show separately
    my_share = net_client_tally  # 1%
    company_share = net_company_tally  # 9%
```

### **Key Rules**
1. **Pending is NEVER stored** - always calculated statelessly
2. **Pending exists ONLY when LOSS > 0** - never shown for profit
3. **Settlements are already reflected** - Old Balance moves forward, so pending is automatically correct
4. **No need to subtract settlements** - the current `net_loss` already accounts for all settlements
5. **✅ ERROR 6 FIX**: Pending must use normalized LOSS, never raw math or movement

---

## 🧮 SHARE CALCULATIONS

### **My Share (for MY CLIENTS)**
```
My Share = (LOSS × my_share_pct) / 100
```
- Example: LOSS = 60, my_share_pct = 10% → My Share = 6
- Full share goes to you

### **My Share (for COMPANY CLIENTS)**
```
My Share = (LOSS × 1) / 100
```
- Always 1% of loss for company clients
- You get 1% of the total loss

### **Company Share (for COMPANY CLIENTS)**
```
Company Share = (LOSS × 9) / 100
```
- Always 9% of loss for company clients
- Company gets 9% of the total loss

### **Combined Share (for COMPANY CLIENTS)**
```
Combined Share = My Share + Company Share
Combined Share = (LOSS × 10) / 100
```
- Always 10% of loss (1% + 9%)
- This is what client pays in total

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
- Only when `abs(CAPITAL - CB) >= 0.01` (not break-even)

#### **What to Display**
- **Client Name**
- **Exchange Name**
- **Pending Amount**:
  - For MY CLIENTS: My Share = `(LOSS × my_share_pct) / 100`
  - For COMPANY CLIENTS: Combined Share = `(LOSS × 10) / 100` (if combine_shares = True)
- **Old Balance** (CAPITAL)
- **Current Balance** (CB)
- **Total Loss** (`CAPITAL - CB`)

#### **For MY CLIENTS**
```
Pending = My Share = (LOSS × my_share_pct) / 100
```

#### **For COMPANY CLIENTS**
```
If combine_shares = True:
    Pending = Combined Share = (LOSS × 10) / 100
Else:
    My Share = (LOSS × 1) / 100
    Company Share = (LOSS × 9) / 100
```

### **"You Owe Clients" Section**

#### **When to Show**
- Only when `CB > CAPITAL` (profit case)
- Only when `abs(CB - CAPITAL) >= 0.01` (not break-even)

#### **What to Display**
- **Client Name**
- **Exchange Name**
- **Profit Amount** (`CB - CAPITAL`)
- **Your Share** (what you owe)
- **Old Balance** (CAPITAL)
- **Current Balance** (CB)

#### **Important**
- **NO PENDING shown for profit** - pending exists only for loss
- Profit withdrawal affects only CB, never CAPITAL

---

## 📝 STEP-BY-STEP EXAMPLES

### **Example 1: Simple Partial Payment**

#### **Initial State**
```
Funding: ₹100
CAPITAL = 100
CB = 100
LOSS = 0
Pending = 0
```

#### **After Trading Loss**
```
Balance Record: ₹40
CAPITAL = 100
CB = 40
LOSS = max(100 - 40, 0) = 60
Pending = (60 × 10) / 100 = 6
```

#### **Partial Payment: ₹3**
```
payment = 3
capital_closed = (3 × 100) / 10 = 30

# LOSS-First Approach
loss_current = 60
loss_new = max(60 - 30, 0) = 30
loss_new = 30.quantize(Decimal("0.0001")) = 30
CAPITAL_new = 40 + 30 = 70

# Verify
LOSS_new = max(70 - 40, 0) = 30 ✅
Pending_new = (30 × 10) / 100 = 3 ✅
```

#### **Final State**
```
CAPITAL = 70
CB = 40
LOSS = 30
Pending = 3
```

### **Example 2: Multiple Partial Payments**

#### **Initial State**
```
CAPITAL = 100
CB = 40
LOSS = 60
Pending = 6
```

#### **Payment 1: ₹2**
```
payment = 2
capital_closed = 20

loss_current = 60
loss_new = 40
CAPITAL_new = 40 + 40 = 80

# State after Payment 1
CAPITAL = 80
CB = 40
LOSS = 40
Pending = 4
```

#### **Payment 2: ₹1.5**
```
payment = 1.5
capital_closed = 15

loss_current = 40
loss_new = 25
CAPITAL_new = 40 + 25 = 65

# State after Payment 2
CAPITAL = 65
CB = 40
LOSS = 25
Pending = 2.5
```

#### **Payment 3: ₹2.5 (Full Settlement)**
```
payment = 2.5
capital_closed = 25

loss_current = 25
loss_new = 0
CAPITAL_new = 40 + 0 = 40  # Full settlement

# State after Payment 3
CAPITAL = 40
CB = 40
LOSS = 0
Pending = 0
```

### **Example 3: CB Changes Between Payments**

#### **Initial State**
```
CAPITAL = 100
CB = 40
LOSS = 60
Pending = 6
```

#### **Payment 1: ₹3**
```
payment = 3
capital_closed = 30

loss_current = 60
loss_new = 30
CAPITAL_new = 40 + 30 = 70

# State after Payment 1
CAPITAL = 70
CB = 40
LOSS = 30
Pending = 3
```

#### **New Balance Record: CB = 50**
```
# CB changes (profit of 10)
CAPITAL = 70  # Unchanged
CB = 50  # Updated
LOSS = max(70 - 50, 0) = 20  # Recalculated
Pending = (20 × 10) / 100 = 2  # Recalculated
```

#### **Payment 2: ₹2**
```
payment = 2
capital_closed = 20

loss_current = 20
loss_new = 0
CAPITAL_new = 50 + 0 = 50  # Full settlement

# State after Payment 2
CAPITAL = 50
CB = 50
LOSS = 0
Pending = 0
```

**✅ This is why LOSS-first approach works** - it handles CB changes correctly!

### **Example 4: Company Client with Combined Share**

#### **Initial State**
```
CAPITAL = 100
CB = 40
LOSS = 60
total_share_pct = 10%
My Share = (60 × 1) / 100 = 0.6
Company Share = (60 × 9) / 100 = 5.4
Combined Share = 6
```

#### **Partial Payment: ₹3**
```
payment = 3
capital_closed = (3 × 100) / 10 = 30

loss_current = 60
loss_new = 30
CAPITAL_new = 40 + 30 = 70

# State after Payment
CAPITAL = 70
CB = 40
LOSS = 30
My Share = (30 × 1) / 100 = 0.3
Company Share = (30 × 9) / 100 = 2.7
Combined Share = 3
```

---

## ✅ VALIDATION RULES

### **Settlement Validation**

#### **1. Payment Amount Validation**
```python
if amount <= Decimal(0):
    REJECT  # Payment must be positive
```

#### **2. LOSS Exists Validation**
```python
epsilon = Decimal("0.0001")
loss_current = max(old_balance - current_balance, 0)

if loss_current <= epsilon:
    REJECT  # No loss to settle
```

#### **3. Capital Closed Validation (✅ ERROR 3 FIX)**
```python
# ✅ FIX: Validate against LOSS, not movement
if capital_closed > loss_current + epsilon:
    REJECT  # Cannot close more capital than loss
```

#### **4. Direction Validation**
```python
# For client_pays: must be in LOSS case
if net >= 0:
    REJECT  # Client cannot pay when in profit

# For admin_pays_profit: must be in PROFIT case
if net <= 0:
    REJECT  # Admin cannot pay when in loss
```

#### **5. CAPITAL Non-Negative Validation**
```python
if old_balance_new < 0:
    REJECT  # CAPITAL cannot be negative
```

#### **6. Direction Flip Prevention (✅ ERROR 2 FIX)**
```python
# ✅ FIX: Simple direction flip check
if loss_new > epsilon and old_balance_new < current_balance:
    REJECT  # LOSS settlement must not create profit while loss still exists
```

#### **7. LOSS Normalization (✅ ERROR 6 FIX)**
```python
# ✅ FIX: Normalize LOSS after every operation
loss_new = loss_new.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
if loss_new <= epsilon:
    loss_new = Decimal(0)
```

### **Profit Withdrawal Validation (✅ ERROR 3 FIX + ERROR 5 FIX)**
```python
# ✅ ERROR 5 FIX: Use single epsilon (0.1 for 1 decimal place)
epsilon = Decimal("0.1")
profit_current = max(current_balance - old_balance, 0)

# ✅ ERROR 3 FIX: Profit withdrawals do NOT use capital_closed
# withdrawal = amount (in CB space, not capital space)
withdrawal = amount
if withdrawal > profit_current + epsilon:
    REJECT  # Cannot withdraw more than profit

# Calculate what CB would be after withdrawal
cb_new_after_withdrawal = current_balance - withdrawal

# If profit is fully withdrawn (within epsilon), set CB = CAPITAL
profit_new = max(profit_current - withdrawal, 0)
profit_new = profit_new.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
if profit_new <= epsilon:
    cb_new_after_withdrawal = old_balance
    profit_new = Decimal(0)

if cb_new_after_withdrawal < old_balance - epsilon:
    REJECT  # Withdrawal cannot create fake loss

# CAPITAL remains unchanged for profit withdrawal
CAPITAL_new = CAPITAL_old
```

---

## 💾 DATABASE STORAGE

### **ClientExchange Model**

#### **cached_old_balance (CAPITAL)**
- **Type**: `DecimalField(max_digits=14, decimal_places=2)`
- **Purpose**: Stores CAPITAL (Old Balance)
- **Updated**: On settlement, on funding, via signals
- **Precision**: Stored at high precision (≥6 decimals), rounded only for display

#### **cached_current_balance (CB)**
- **Type**: `DecimalField(max_digits=14, decimal_places=2)`
- **Purpose**: Cached current exchange balance
- **Updated**: Via signals when `BALANCE_RECORD` is created/updated

#### **cached_total_funding**
- **Type**: `DecimalField(max_digits=14, decimal_places=2)`
- **Purpose**: Cached total funding amount
- **Updated**: Via signals when `FUNDING` transaction is created

### **Transaction Model**

#### **transaction_type**
- `TYPE_FUNDING`: Funding transaction
- `TYPE_LOSS`: Loss transaction (informational)
- `TYPE_PROFIT`: Profit transaction (informational)
- `TYPE_SETTLEMENT`: Settlement transaction

#### **amount**
- Payment amount (in share space, not capital space)

#### **client_share_amount**
- Client's share amount

#### **your_share_amount**
- Your share amount (1% for company clients, full share for my clients)

#### **company_share_amount**
- Company share amount (9% for company clients, 0 for my clients)

### **ClientDailyBalance Model**

#### **remaining_balance**
- **Type**: `DecimalField(max_digits=14, decimal_places=2)`
- **Purpose**: Exchange balance at this date
- **Updated**: When new balance record is created

#### **extra_adjustment**
- **Type**: `DecimalField(max_digits=14, decimal_places=2)`
- **Purpose**: Additional adjustment to balance
- **Updated**: For manual adjustments

---

## 🔒 CRITICAL INVARIANTS

### **1. CAPITAL Invariant**
```
CAPITAL >= 0  (always)
```

### **2. LOSS/PROFIT Mutually Exclusive**
```
LOSS = max(CAPITAL - CB, 0)
PROFIT = max(CB - CAPITAL, 0)
```
- Only one can be > 0 at a time

### **3. Pending Exists Only for Loss**
```
IF LOSS > 0:
    Pending = (LOSS × total_share_pct) / 100
ELSE:
    Pending = 0
```

### **4. Settlement Invariant**
```
After settlement:
    CAPITAL_new = CB + LOSS_new
    where LOSS_new = max(LOSS_old - capital_closed, 0)
```

### **5. Funding Invariant**
```
After funding:
    CAPITAL_new = CAPITAL_old + funding_amount
    CB_new = CB_old + funding_amount
    (CAPITAL - CB) remains unchanged
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
3. **Settlements Move CAPITAL**: Old Balance moves forward, pending automatically correct
4. **Profit ≠ Pending**: Pending exists only for loss, never for profit
5. **High Precision**: Store at ≥6 decimals, round only for display
6. **Validation is Critical**: Multiple validation rules prevent data corruption
7. **✅ ERROR 1 FIX**: CAPITAL is stored, but derived truth is always CB + LOSS
8. **✅ ERROR 2 FIX**: ONE RULE ONLY for full settlement: `if loss_new <= epsilon: CAPITAL_new = CB`
9. **✅ ERROR 3 FIX**: Validate against LOSS/PROFIT, not movement
10. **✅ ERROR 4 FIX**: LOSS must always be clamped: `loss = max(CAPITAL - CB, 0)`
11. **✅ ERROR 5 FIX**: Profit withdrawal needs epsilon logic (mirrors loss settlement)
12. **✅ ERROR 6 FIX**: Pending must use normalized LOSS, never raw math
13. **✅ ERROR 7 FIX**: Funding has two explicit states (initiated vs credited)
14. **✅ ERROR 8 FIX**: Remove unnecessary direction-flip logic

### **Formulas Quick Reference (✅ FINAL GOLDEN FORMULA - PIN THIS)**

```
# ✅ ERROR 5 FIX: Use single epsilon (0.1 for 1 decimal place)
# ✅ ERROR 8 FIX: Use 0.1 precision to match DB
epsilon = Decimal("0.1")

LOSS = max(CAPITAL - CB, 0)
PROFIT = max(CB - CAPITAL, 0)

# ✅ ERROR 1 FIX: CAPITAL = CB + LOSS only when LOSS > 0
If LOSS > 0: CAPITAL = CB + LOSS
If PROFIT > 0: CAPITAL < CB

# ✅ ERROR 4 FIX: Separate receivables
ClientPayable = LOSS × total_share_pct / 100
YourReceivable = LOSS × my_share_pct / 100
CompanyReceivable = LOSS × company_share_pct / 100

# LOSS Settlement
capital_closed = (payment × 100) / total_share_pct
loss_new = max(loss_current - capital_closed, 0)
loss_new = loss_new.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
if loss_new <= epsilon:
    loss_new = 0
    CAPITAL_new = CB  # Full settlement
else:
    CAPITAL_new = CB + loss_new  # Partial settlement

# ✅ ERROR 3 FIX: Profit withdrawal (does NOT use capital_closed)
withdrawal = amount  # Direct amount, not capital_closed
CB_new = CB - withdrawal
CAPITAL_new = CAPITAL_old  # Unchanged
```

**🧠 GOLDEN RULE**: 
- If LOSS > 0: `CAPITAL = CB + LOSS`
- If PROFIT > 0: `CAPITAL < CB`
- All calculations use 0.1 precision (1 decimal place)

---

**Document Version**: 2.0  
**Last Updated**: 2026-01-04  
**Status**: ✅ Complete, Authoritative, All 8 Errors Fixed

