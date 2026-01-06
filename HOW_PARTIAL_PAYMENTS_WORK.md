# How Partial Payments Are Recorded - Complete Guide

## Overview

This document explains **exactly how partial payments are recorded** in the Transaction Hub system. It covers the step-by-step process, formulas, and examples with real numbers.

---

## Table of Contents

1. [What is a Partial Payment?](#what-is-a-partial-payment)
2. [The Payment Recording Process](#the-payment-recording-process)
3. [Step-by-Step Algorithm](#step-by-step-algorithm)
4. [How Old Balance is Updated](#how-old-balance-is-updated)
5. [How Pending Amount is Calculated](#how-pending-amount-is-calculated)
6. [Complete Examples](#complete-examples)
7. [Key Rules and Formulas](#key-rules-and-formulas)

---

## What is a Partial Payment?

A **partial payment** (also called a **settlement**) occurs when:
- A client pays you **less than the full pending amount**
- Example: Pending = ₹10, Client pays = ₹3 (30% payment)

### Key Terms

- **Payment Amount**: What the client actually pays (e.g., ₹3)
- **My Share %**: Your percentage share (e.g., 10%)
- **Total Share %**: For My Clients = My Share %, For Company Clients = Company Share % (e.g., 10%)
- **Capital Closed**: The total loss/profit portion that this payment closes (e.g., ₹30)
- **Old Balance**: The baseline balance before profit/loss calculations

---

## The Payment Recording Process

When you click "Record Payment" and enter an amount, here's what happens:

### 1. User Action
- User clicks "Record Payment" button
- Enters payment amount (e.g., ₹3)
- Selects date
- Submits form

### 2. System Processing
The system performs these steps in order:

1. **Get Current State**: Calculate Old Balance, Current Balance, Net Profit
2. **Validate Payment**: Check if payment is allowed
3. **Convert Payment to Capital Closed**: Calculate how much loss/profit is closed
4. **Update Old Balance**: Move Old Balance forward
5. **Recalculate Pending**: Calculate new pending amount
6. **Create Transaction**: Record SETTLEMENT transaction
7. **Update Ledgers**: Update Outstanding or TallyLedger

---

## Step-by-Step Algorithm

### Step 1: Get Current State

```python
old_balance = get_old_balance_after_settlement(client_exchange)
current_balance = get_exchange_balance(client_exchange)
net_profit = current_balance - old_balance
abs_profit = abs(net_profit)
```

**Example:**
- Old Balance = ₹100
- Current Balance = ₹40
- Net Profit = ₹40 - ₹100 = **-₹60** (loss)
- Abs Profit = ₹60

### Step 2: Get Share Percentages

```python
my_share_pct = client_exchange.my_share_pct  # e.g., 10%
if is_company_client:
    total_pct = company_share_pct  # e.g., 10%
else:
    total_pct = my_share_pct  # e.g., 10%
```

**Example:**
- My Share % = 10%
- Total Share % = 10% (for My Clients)

### Step 3: Calculate Share Amount (Stateless)

```python
share_amount = (abs_profit * total_pct) / 100
```

**Example:**
- Share Amount = (₹60 × 10%) / 100 = **₹6**

### Step 4: Calculate Settlements So Far

```python
if net_profit < 0:  # Loss case
    settlements_so_far = SUM of SETTLEMENT transactions where your_share_amount > 0
else:  # Profit case
    settlements_so_far = SUM of SETTLEMENT transactions where client_share_amount > 0
```

**Example (First Payment):**
- Settlements So Far = ₹0 (no previous payments)

### Step 5: Calculate Pending Before Payment

```python
pending_before = share_amount - settlements_so_far
pending_before = max(0, pending_before)
```

**Example:**
- Pending Before = ₹6 - ₹0 = **₹6**

### Step 6: Validate Payment

```python
# Rule 1: Share amount must be > 0
if share_amount <= 0:
    ERROR: "No pending amount to settle"

# Rule 2: Payment cannot exceed pending
if amount > pending_before:
    ERROR: "Amount exceeds pending amount"
```

**Example:**
- Payment Amount = ₹3
- Pending Before = ₹6
- ✅ Valid: ₹3 ≤ ₹6

### Step 7: Convert Payment to Capital Closed

```python
capital_closed = (payment_amount * 100) / total_pct
```

**Example:**
- Capital Closed = (₹3 × 100) / 10% = ₹3 × 10 = **₹30**

**Why this formula?**
- If you get 10% of a loss, and you receive ₹3, that means the total loss closed was ₹30
- ₹30 × 10% = ₹3 ✓

### Step 8: Update Old Balance

```python
if net_profit < 0:  # Loss case
    old_balance_new = old_balance - capital_closed
else:  # Profit case
    old_balance_new = old_balance + capital_closed
```

**Example (Loss Case):**
- Old Balance New = ₹100 - ₹30 = **₹70**

**Why subtract?**
- In loss case, capital_closed represents loss that was closed
- Old Balance moves forward (decreases) by the amount of loss closed

### Step 9: Recalculate Net Profit (After Reset)

```python
net_profit_new = current_balance - old_balance_new
abs_profit_new = abs(net_profit_new)
```

**Example:**
- Net Profit New = ₹40 - ₹70 = **-₹30** (loss)
- Abs Profit New = ₹30

### Step 10: Recalculate Share (Stateless)

```python
share_new = (abs_profit_new * total_pct) / 100
```

**Example:**
- Share New = (₹30 × 10%) / 100 = **₹3**

### Step 11: Calculate New Pending

```python
# 🚨 CRITICAL: Settlement is already reflected by moving Old Balance
# So pending is simply the new share amount - DO NOT subtract settlement again
pending_new = share_new
pending_new = max(0, pending_new)
```

**Example:**
- Pending New = ₹3

**Why not subtract settlement?**
- The settlement is already accounted for by moving Old Balance
- Old Balance moved from ₹100 to ₹70, which reduced the loss from ₹60 to ₹30
- The new share (₹3) IS the new pending amount

### Step 12: Hard Reset Rule

```python
if pending_new <= 0.01:
    old_balance_new = current_balance
    pending_new = 0
```

**Example:**
- If Pending New = ₹0, then Old Balance = Current Balance (₹40)

### Step 13: Create Balance Record

```python
ClientDailyBalance.objects.create(
    client_exchange=client_exchange,
    date=settlement_date,
    remaining_balance=old_balance_new,
    extra_adjustment=0,
    note="Settlement adjustment: Old Balance moved from ₹100 to ₹70"
)
```

**Purpose:**
- This balance record stores the new Old Balance
- Future calculations will use this as the baseline

### Step 14: Create Settlement Transaction

```python
Transaction.objects.create(
    client_exchange=client_exchange,
    date=settlement_date,
    transaction_type=Transaction.TYPE_SETTLEMENT,
    amount=payment_amount,
    client_share_amount=0,  # Client pays
    your_share_amount=payment_amount,  # You receive
    company_share_amount=0,
    note="Client payment: ₹3"
)
```

### Step 15: Update Ledgers

**For My Clients:**
```python
outstanding.outstanding_amount = pending_new
outstanding.save()
```

**For Company Clients:**
```python
tally.client_owes_you = max(0, tally.client_owes_you - payment_amount)
tally.save()
```

---

## How Old Balance is Updated

### The Golden Rule

**When a payment is recorded, Old Balance RESETS to reflect the capital that was closed.**

### Formula

```
IF payment is for LOSS:
    Old Balance New = Old Balance Old - Capital Closed

IF payment is for PROFIT:
    Old Balance New = Old Balance Old + Capital Closed
```

### Why This Works

1. **Loss Case Example:**
   - Old Balance = ₹100 (original funding)
   - Current Balance = ₹40
   - Loss = ₹60
   - Client pays ₹3 (10% share)
   - Capital Closed = ₹30 (₹3 / 10%)
   - **Old Balance New = ₹100 - ₹30 = ₹70**
   - New Loss = ₹70 - ₹40 = ₹30 ✓

2. **Profit Case Example:**
   - Old Balance = ₹100
   - Current Balance = ₹150
   - Profit = ₹50
   - You pay client ₹5 (10% share)
   - Capital Closed = ₹50 (₹5 / 10%)
   - **Old Balance New = ₹100 + ₹50 = ₹150**
   - New Profit = ₹150 - ₹150 = ₹0 ✓

### Storage

The new Old Balance is stored in a `ClientDailyBalance` record with:
- `date` = Settlement date
- `remaining_balance` = New Old Balance
- `note` = "Settlement adjustment: Old Balance moved from X to Y"

---

## How Pending Amount is Calculated

### After Payment

Pending amount is **recalculated from scratch** using the new Old Balance:

```python
# Step 1: Get new Old Balance (already updated)
old_balance_new = old_balance - capital_closed  # Loss case

# Step 2: Calculate new net profit
net_profit_new = current_balance - old_balance_new

# Step 3: Calculate new share
share_new = (abs(net_profit_new) * total_pct) / 100

# Step 4: Pending = New Share (stateless calculation)
pending_new = share_new
```

### Important: No Subtraction

**DO NOT subtract the payment amount from pending!**

❌ **WRONG:**
```python
pending_new = share_new - payment_amount  # WRONG!
```

✅ **CORRECT:**
```python
pending_new = share_new  # Settlement already reflected in Old Balance
```

**Why?**
- The payment is already accounted for by moving Old Balance
- Moving Old Balance automatically reduces the loss/profit
- The new share calculation already reflects the payment

---

## Complete Examples

### Example 1: First Partial Payment (Loss Case)

**Initial State:**
- Dec 1: FUNDING ₹100
- Dec 1: BALANCE_RECORD ₹40 (loss occurred)
- My Share %: 10%

**Before Payment:**
- Old Balance = ₹100
- Current Balance = ₹40
- Net Profit = ₹40 - ₹100 = **-₹60** (loss)
- Share Amount = ₹60 × 10% = **₹6**
- Pending = ₹6

**User Action:**
- Records payment: ₹3
- Date: Dec 2

**System Processing:**

1. **Get Current State:**
   - Old Balance = ₹100
   - Current Balance = ₹40
   - Net Profit = -₹60

2. **Calculate Capital Closed:**
   - Capital Closed = (₹3 × 100) / 10% = **₹30**

3. **Update Old Balance:**
   - Old Balance New = ₹100 - ₹30 = **₹70**

4. **Recalculate Net Profit:**
   - Net Profit New = ₹40 - ₹70 = **-₹30**

5. **Recalculate Share:**
   - Share New = ₹30 × 10% = **₹3**

6. **Calculate Pending:**
   - Pending New = ₹3

7. **Create Balance Record:**
   - Date: Dec 2
   - Remaining Balance: ₹70
   - Note: "Settlement adjustment: Old Balance moved from ₹100 to ₹70"

8. **Create Transaction:**
   - Type: SETTLEMENT
   - Amount: ₹3
   - Your Share Amount: ₹3

9. **Update Outstanding:**
   - Outstanding Amount: ₹3

**After Payment:**
- Old Balance = **₹70** ✅
- Current Balance = ₹40
- Net Profit = -₹30
- Share = ₹3
- Pending = **₹3** ✅

---

### Example 2: Second Partial Payment

**State After First Payment:**
- Old Balance = ₹70
- Current Balance = ₹40
- Pending = ₹3

**User Action:**
- Records payment: ₹2
- Date: Dec 5

**System Processing:**

1. **Get Current State:**
   - Old Balance = ₹70
   - Current Balance = ₹40
   - Net Profit = -₹30

2. **Calculate Capital Closed:**
   - Capital Closed = (₹2 × 100) / 10% = **₹20**

3. **Update Old Balance:**
   - Old Balance New = ₹70 - ₹20 = **₹50**

4. **Recalculate Net Profit:**
   - Net Profit New = ₹40 - ₹50 = **-₹10**

5. **Recalculate Share:**
   - Share New = ₹10 × 10% = **₹1**

6. **Calculate Pending:**
   - Pending New = ₹1

7. **Create Balance Record:**
   - Date: Dec 5
   - Remaining Balance: ₹50
   - Note: "Settlement adjustment: Old Balance moved from ₹70 to ₹50"

8. **Create Transaction:**
   - Type: SETTLEMENT
   - Amount: ₹2
   - Your Share Amount: ₹2

9. **Update Outstanding:**
   - Outstanding Amount: ₹1

**After Second Payment:**
- Old Balance = **₹50** ✅
- Current Balance = ₹40
- Net Profit = -₹10
- Share = ₹1
- Pending = **₹1** ✅

---

### Example 3: Full Payment (Final Settlement)

**State After Second Payment:**
- Old Balance = ₹50
- Current Balance = ₹40
- Pending = ₹1

**User Action:**
- Records payment: ₹1
- Date: Dec 8

**System Processing:**

1. **Get Current State:**
   - Old Balance = ₹50
   - Current Balance = ₹40
   - Net Profit = -₹10

2. **Calculate Capital Closed:**
   - Capital Closed = (₹1 × 100) / 10% = **₹10**

3. **Update Old Balance:**
   - Old Balance New = ₹50 - ₹10 = **₹40**

4. **Recalculate Net Profit:**
   - Net Profit New = ₹40 - ₹40 = **₹0**

5. **Recalculate Share:**
   - Share New = ₹0 × 10% = **₹0**

6. **Hard Reset Rule:**
   - Since Pending New ≤ 0.01:
   - Old Balance New = Current Balance = **₹40**
   - Pending New = **₹0**

7. **Create Balance Record:**
   - Date: Dec 8
   - Remaining Balance: ₹40
   - Note: "Settlement adjustment: Old Balance moved from ₹50 to ₹40"

8. **Create Transaction:**
   - Type: SETTLEMENT
   - Amount: ₹1
   - Your Share Amount: ₹1

9. **Update Outstanding:**
   - Outstanding Amount: ₹0

**After Full Payment:**
- Old Balance = **₹40** ✅ (equals Current Balance)
- Current Balance = ₹40
- Net Profit = ₹0
- Share = ₹0
- Pending = **₹0** ✅

---

### Example 4: Partial Payment with New Funding After

**Initial State:**
- Dec 1: FUNDING ₹100
- Dec 1: BALANCE_RECORD ₹40
- Old Balance = ₹100
- Current Balance = ₹40
- Pending = ₹6

**User Action:**
- Records payment: ₹3
- Date: Dec 2

**After Payment:**
- Old Balance = ₹70
- Current Balance = ₹40
- Pending = ₹3

**New Transaction:**
- Dec 3: FUNDING ₹50

**After New Funding:**
- Old Balance = **₹70 + ₹50 = ₹90** ✅
- Current Balance = ₹40 + ₹50 = ₹90
- Net Profit = ₹90 - ₹90 = ₹0
- Pending = ₹0

**Why?**
- Old Balance = Balance at last settlement (₹70) + Funding after settlement (₹50) = ₹90
- Current Balance = Previous balance (₹40) + New funding (₹50) = ₹90
- No profit, no loss → Pending = ₹0

---

## Key Rules and Formulas

### Rule 1: Capital Closed Formula

```
Capital Closed = (Payment Amount × 100) / Total Share %
```

**Example:**
- Payment = ₹3
- Total Share % = 10%
- Capital Closed = (₹3 × 100) / 10 = ₹30

### Rule 2: Old Balance Update (Loss Case)

```
Old Balance New = Old Balance Old - Capital Closed
```

**Example:**
- Old Balance Old = ₹100
- Capital Closed = ₹30
- Old Balance New = ₹100 - ₹30 = ₹70

### Rule 3: Old Balance Update (Profit Case)

```
Old Balance New = Old Balance Old + Capital Closed
```

**Example:**
- Old Balance Old = ₹100
- Capital Closed = ₹50
- Old Balance New = ₹100 + ₹50 = ₹150

### Rule 4: Pending Calculation (After Payment)

```
Pending New = (Abs(Current Balance - Old Balance New) × Total Share %) / 100
```

**DO NOT subtract payment amount!**

**Example:**
- Current Balance = ₹40
- Old Balance New = ₹70
- Net Profit = -₹30
- Total Share % = 10%
- Pending New = (₹30 × 10%) / 100 = ₹3

### Rule 5: Hard Reset Rule

```
IF Pending New ≤ 0.01:
    Old Balance New = Current Balance
    Pending New = 0
```

**Example:**
- Current Balance = ₹40
- Old Balance New = ₹40
- Pending New = ₹0

### Rule 6: Funding After Settlement

```
Old Balance = Balance at Last Settlement + Funding After Settlement
```

**Example:**
- Balance at Last Settlement = ₹70
- Funding After = ₹50
- Old Balance = ₹70 + ₹50 = ₹120

---

## Summary

### The Complete Flow

1. **User records payment** → System gets current state
2. **Calculate capital closed** → Payment × 100 / Share %
3. **Update Old Balance** → Old Balance ± Capital Closed
4. **Recalculate pending** → From new Old Balance (stateless)
5. **Create records** → Balance record + Transaction
6. **Update ledgers** → Outstanding or TallyLedger

### Key Principles

1. **Settlement resets Old Balance** - It moves forward/backward by capital closed
2. **Pending is stateless** - Always calculated from current Old Balance
3. **No double-counting** - Payment is reflected in Old Balance, not subtracted from pending
4. **Funding after settlement** - Added to Old Balance at last settlement

### Formula Summary

```
Capital Closed = (Payment × 100) / Share %

Old Balance New = Old Balance Old ± Capital Closed
  (Loss: subtract, Profit: add)

Pending New = (Abs(Current - Old Balance New) × Share %) / 100
```

---

**Last Updated:** 2025-12-29  
**Version:** 2.0






