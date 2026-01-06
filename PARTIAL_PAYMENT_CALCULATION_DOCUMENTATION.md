# Partial Payment Calculation - Formulas and Logic

## Overview

This document explains **exactly how partial payments are calculated**, including all formulas, step-by-step logic, and mathematical derivations. This is the technical reference for understanding the calculation engine.

---

## 🔑 Core Formula: Converting Payment to Capital Closed

### The Master Formula

```
capital_closed = payment × 100 / total_share_pct
```

**Where:**
- `payment` = Amount the client actually pays (e.g., ₹5)
- `total_share_pct` = Total share percentage (10% for company clients, or my_share_pct for my clients)
- `capital_closed` = The total loss/profit portion that this payment closes (e.g., ₹50)

### Mathematical Derivation

**Why this formula?**

If a client pays ₹5 and the share percentage is 10%, we need to find: "What total loss does ₹5 represent at 10%?"

**Derivation:**
```
Share Amount = (Total Loss × Share %) / 100
Payment = Share Amount
Payment = (Total Loss × Share %) / 100
Payment × 100 = Total Loss × Share %
Total Loss = (Payment × 100) / Share %
```

**Therefore:**
```
capital_closed = (payment × 100) / total_share_pct
```

**Example:**
- Payment = ₹5
- Total Share % = 10%
- `capital_closed = (5 × 100) / 10 = ₹50`

This means: **₹5 payment closes ₹50 of the total loss** (because 10% of ₹50 = ₹5)

---

## 📐 Complete Calculation Flow

### Step 1: Get Current State

```python
old_balance = get_old_balance_after_settlement(client_exchange)
current_balance = get_exchange_balance(client_exchange, use_cache=False)
net_profit = current_balance - old_balance
abs_profit = abs(net_profit)
```

**Formulas:**
- `net_profit = current_balance - old_balance`
- `abs_profit = |net_profit|`

**Example:**
- Old Balance = ₹100
- Current Balance = ₹10
- Net Profit = ₹10 - ₹100 = **-₹90** (loss)
- Abs Profit = ₹90

### Step 2: Get Share Percentages

```python
my_pct = client_exchange.my_share_pct  # e.g., 1%
if client_exchange.client.is_company_client:
    company_pct = client_exchange.company_share_pct  # e.g., 10%
    total_pct = company_pct  # For company clients: 10%
else:
    total_pct = my_pct  # For my clients: use my_share_pct
```

**Rules:**
- **My Clients:** `total_pct = my_share_pct`
- **Company Clients:** `total_pct = company_share_pct` (usually 10%)

### Step 3: Calculate Current Share Amount (Before Payment)

```python
share_amount = (abs_profit * total_pct) / Decimal(100)
share_amount = share_amount.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
```

**Formula:**
```
share_amount = (abs_profit × total_pct) / 100
```

**Example:**
- Abs Profit = ₹90
- Total Share % = 10%
- Share Amount = (₹90 × 10) / 100 = **₹9**

### Step 4: Calculate Settlements So Far

```python
if net_profit < 0:
    # LOSS CASE: Client pays you
    settlements_so_far = SUM(SETTLEMENT transactions where your_share_amount > 0)
else:
    # PROFIT CASE: You pay client
    settlements_so_far = SUM(SETTLEMENT transactions where client_share_amount > 0)
```

**Formula:**
```
settlements_so_far = Σ(previous_settlement_amounts)
```

**Example:**
- Previous payments: ₹2, ₹1
- Settlements So Far = ₹2 + ₹1 = **₹3**

### Step 5: Calculate Pending Before Payment

```python
pending_before = share_amount - settlements_so_far
pending_before = max(Decimal(0), pending_before)
```

**Formula:**
```
pending_before = share_amount - settlements_so_far
```

**Example:**
- Share Amount = ₹9
- Settlements So Far = ₹3
- Pending Before = ₹9 - ₹3 = **₹6**

### Step 6: Validate Payment

**Rule 1: Payment must be > 0**
```python
if amount <= 0:
    raise ValidationError("Payment must be greater than zero")
```

**Rule 2: Payment cannot exceed pending**
```python
if amount > pending_before:
    raise ValidationError(f"Payment ₹{amount} exceeds pending ₹{pending_before}")
```

**Rule 3: Share amount must be > 0**
```python
if share_amount <= 0:
    raise ValidationError("No pending amount to settle")
```

### Step 7: Calculate Capital Closed (THE KEY FORMULA)

```python
capital_closed = (amount * Decimal(100)) / total_pct
capital_closed = capital_closed.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
```

**Formula:**
```
capital_closed = (payment × 100) / total_share_pct
```

**Example:**
- Payment = ₹5
- Total Share % = 10%
- Capital Closed = (₹5 × 100) / 10 = **₹50**

**What this means:**
- Client pays ₹5 (which is 10% of some amount)
- That "some amount" = ₹50
- So ₹5 payment closes ₹50 of the total loss

### Step 8: Move Old Balance Forward

```python
if net_profit < 0:
    # LOSS CASE: old_balance_new = old_balance_old - capital_closed
    old_balance_new = old_balance - capital_closed
else:
    # PROFIT CASE: old_balance_new = old_balance_old + capital_closed
    old_balance_new = old_balance + capital_closed

old_balance_new = old_balance_new.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
```

**Formulas:**

**For LOSS:**
```
old_balance_new = old_balance_old - capital_closed
```

**For PROFIT:**
```
old_balance_new = old_balance_old + capital_closed
```

**Example (LOSS case):**
- Old Balance (old) = ₹100
- Capital Closed = ₹50
- Old Balance (new) = ₹100 - ₹50 = **₹50**

**Why this works:**
- Old Balance represents the capital base
- When client pays ₹5 (closing ₹50 of loss), the capital base reduces by ₹50
- New capital base = Old capital base - Capital closed

### Step 9: Recalculate Net Profit (After Old Balance Movement)

```python
net_profit_new = current_balance - old_balance_new
abs_profit_new = abs(net_profit_new)
```

**Formula:**
```
net_profit_new = current_balance - old_balance_new
abs_profit_new = |net_profit_new|
```

**Example:**
- Current Balance = ₹10 (unchanged)
- Old Balance (new) = ₹50
- Net Profit (new) = ₹10 - ₹50 = **-₹40** (loss)
- Abs Profit (new) = ₹40

### Step 10: Recalculate Share Amount (After Payment)

```python
share_new = (abs_profit_new * total_pct) / Decimal(100)
share_new = share_new.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
```

**Formula:**
```
share_new = (abs_profit_new × total_pct) / 100
```

**Example:**
- Abs Profit (new) = ₹40
- Total Share % = 10%
- Share (new) = (₹40 × 10) / 100 = **₹4**

### Step 11: Calculate New Pending Amount

```python
pending_new = share_new
pending_new = max(Decimal(0), pending_new)
```

**Formula:**
```
pending_new = share_new
```

**Critical Note:** We do **NOT** subtract settlements again because:
- Settlement is already reflected by moving Old Balance
- Old Balance movement → New loss → New share → That IS the pending

**Example:**
- Share (new) = ₹4
- Pending (new) = **₹4**

**Verification:**
- Pending (before) = ₹6
- Payment = ₹5
- Pending (new) = ₹4
- Check: ₹6 - ₹5 = ₹1 ❌ (Wrong - this would be wrong calculation)
- Check: ₹4 (correct - from new share calculation) ✅

### Step 12: Create Settlement Adjustment BALANCE_RECORD

```python
ClientDailyBalance.objects.create(
    client_exchange=client_exchange,
    date=settlement_date,
    remaining_balance=old_balance_new,
    extra_adjustment=Decimal(0),
    note=f"Settlement adjustment: Old Balance moved from ₹{old_balance} to ₹{old_balance_new} (capital_closed: ₹{capital_closed})"
)
```

**Purpose:**
- Stores the new Old Balance after settlement
- Used by `get_old_balance_after_settlement()` to find the correct Old Balance
- Ensures future calculations use the updated capital base

---

## 📊 Complete Example: Step-by-Step Calculation

### Initial State

- **Old Balance:** ₹100
- **Current Balance:** ₹10
- **Total Share %:** 10%
- **Previous Payments:** None

### Step 1: Calculate Initial Values

```
net_profit = 10 - 100 = -₹90 (loss)
abs_profit = ₹90
share_amount = (90 × 10) / 100 = ₹9
settlements_so_far = ₹0
pending_before = ₹9 - ₹0 = ₹9
```

### Step 2: Client Pays ₹5 (Partial Payment)

**Input:**
- Payment = ₹5

**Calculation:**

1. **Capital Closed:**
   ```
   capital_closed = (5 × 100) / 10 = ₹50
   ```

2. **New Old Balance:**
   ```
   old_balance_new = 100 - 50 = ₹50
   ```

3. **New Net Profit:**
   ```
   net_profit_new = 10 - 50 = -₹40 (loss)
   abs_profit_new = ₹40
   ```

4. **New Share:**
   ```
   share_new = (40 × 10) / 100 = ₹4
   ```

5. **New Pending:**
   ```
   pending_new = ₹4
   ```

### Final State After Payment

- **Old Balance:** ₹50 (moved from ₹100)
- **Current Balance:** ₹10 (unchanged)
- **Total Loss:** ₹40 (50 - 10)
- **Combined Share:** ₹4 (10% of ₹40)
- **Pending Amount:** ₹4
- **Payment Made:** ₹5
- **Capital Closed:** ₹50

### Verification

**Check 1: Payment closes correct capital**
- Payment = ₹5
- Capital Closed = ₹50
- 10% of ₹50 = ₹5 ✅

**Check 2: Pending reduced correctly**
- Pending (before) = ₹9
- Payment = ₹5
- Pending (new) = ₹4
- Remaining = ₹9 - ₹5 = ₹4 ✅

**Check 3: Old Balance moved correctly**
- Old Balance (before) = ₹100
- Capital Closed = ₹50
- Old Balance (new) = ₹50
- Reduction = ₹100 - ₹50 = ₹50 ✅

---

## 🔢 Multiple Partial Payments Example

### Scenario

- **Initial Old Balance:** ₹100
- **Current Balance:** ₹10
- **Total Share %:** 10%

### Payment 1: Client Pays ₹5

**Calculation:**
```
capital_closed_1 = (5 × 100) / 10 = ₹50
old_balance_1 = 100 - 50 = ₹50
net_profit_1 = 10 - 50 = -₹40
share_1 = (40 × 10) / 100 = ₹4
pending_1 = ₹4
```

**State After Payment 1:**
- Old Balance: ₹50
- Pending: ₹4

### Payment 2: Client Pays ₹2

**Calculation:**
```
capital_closed_2 = (2 × 100) / 10 = ₹20
old_balance_2 = 50 - 20 = ₹30
net_profit_2 = 10 - 30 = -₹20
share_2 = (20 × 10) / 100 = ₹2
pending_2 = ₹2
```

**State After Payment 2:**
- Old Balance: ₹30
- Pending: ₹2

### Payment 3: Client Pays ₹2 (Full Payment)

**Calculation:**
```
capital_closed_3 = (2 × 100) / 10 = ₹20
old_balance_3 = 30 - 20 = ₹10
net_profit_3 = 10 - 10 = ₹0
share_3 = (0 × 10) / 100 = ₹0
pending_3 = ₹0
```

**State After Payment 3:**
- Old Balance: ₹10 (equals Current Balance)
- Pending: ₹0 (fully paid)

---

## 🧮 Formula Summary

### Core Formulas

1. **Capital Closed:**
   ```
   capital_closed = (payment × 100) / total_share_pct
   ```

2. **New Old Balance (LOSS):**
   ```
   old_balance_new = old_balance_old - capital_closed
   ```

3. **New Old Balance (PROFIT):**
   ```
   old_balance_new = old_balance_old + capital_closed
   ```

4. **New Net Profit:**
   ```
   net_profit_new = current_balance - old_balance_new
   ```

5. **New Share:**
   ```
   share_new = (abs_profit_new × total_pct) / 100
   ```

6. **New Pending:**
   ```
   pending_new = share_new
   ```

### Derived Formulas

**Total Loss After Payment:**
```
total_loss_new = old_balance_new - current_balance
```

**Remaining Pending:**
```
remaining_pending = pending_before - payment
```

**Verification:**
```
remaining_pending should equal pending_new
```

---

## 🔍 Why These Formulas Work

### The Core Insight

**Partial payments don't just reduce pending - they close part of the capital base.**

**Traditional (Wrong) Approach:**
```
Pending = Share - Payments
```

**Correct Approach:**
```
Payment → Close Capital → Move Old Balance → Recalculate Loss → Recalculate Share → That IS Pending
```

### Mathematical Proof

**Given:**
- Old Balance = OB
- Current Balance = CB
- Total Share % = P%
- Payment = P

**Step 1: Calculate Capital Closed**
```
CC = (P × 100) / P%
```

**Step 2: Move Old Balance**
```
OB_new = OB - CC  (for loss case)
```

**Step 3: Recalculate Loss**
```
Loss_new = OB_new - CB
Loss_new = (OB - CC) - CB
Loss_new = OB - CB - CC
Loss_new = Loss_old - CC
```

**Step 4: Recalculate Share**
```
Share_new = (Loss_new × P%) / 100
Share_new = ((Loss_old - CC) × P%) / 100
Share_new = (Loss_old × P%) / 100 - (CC × P%) / 100
Share_new = Share_old - (CC × P%) / 100
```

**Step 5: Substitute CC**
```
CC = (P × 100) / P%
(CC × P%) / 100 = ((P × 100) / P%) × P% / 100
(CC × P%) / 100 = P
```

**Therefore:**
```
Share_new = Share_old - P
```

**This proves:** The new share equals the old share minus the payment, which is exactly what we want!

---

## ⚠️ Important Rules and Constraints

### Rule 1: Payment Cannot Exceed Pending

```python
if amount > pending_before:
    raise ValidationError("Payment exceeds pending amount")
```

**Why:** You cannot collect more than what's pending.

### Rule 2: Share Amount Must Be > 0

```python
if share_amount <= 0:
    raise ValidationError("No pending amount to settle")
```

**Why:** If there's no share, there's nothing to pay.

### Rule 3: Net Profit Cannot Be Zero

```python
if abs(net_profit) < Decimal("0.01"):
    raise ValidationError("No pending amount (net profit is zero)")
```

**Why:** If Old Balance = Current Balance, there's no profit/loss, hence no pending.

### Rule 4: Old Balance Never Goes Below Zero

```python
if old_balance_new < 0:
    old_balance_new = Decimal(0)
```

**Why:** Capital base cannot be negative.

### Rule 5: Pending Never Goes Below Zero

```python
pending_new = max(Decimal(0), pending_new)
```

**Why:** Pending amount cannot be negative.

---

## 🔄 State Transitions

### Before Payment

```
State_Before = {
    old_balance: OB,
    current_balance: CB,
    net_profit: CB - OB,
    share: (|CB - OB| × P%) / 100,
    pending: share - settlements_so_far
}
```

### After Payment

```
State_After = {
    old_balance: OB - CC,  (for loss)
    current_balance: CB,  (unchanged)
    net_profit: CB - (OB - CC),
    share: (|CB - (OB - CC)| × P%) / 100,
    pending: share_new
}
```

### Relationship

```
pending_after = pending_before - payment
```

This is automatically satisfied by the formula chain.

---

## 📝 Code Implementation Reference

### Function Location

**File:** `core/views.py`  
**Function:** `settle_payment(request)`  
**Section:** `payment_type == "client_pays"`

### Key Code Sections

#### 1. Calculate Capital Closed

```python
capital_closed = (amount * Decimal(100)) / total_pct
capital_closed = capital_closed.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
```

#### 2. Move Old Balance

```python
if net_profit < 0:
    old_balance_new = old_balance - capital_closed
else:
    old_balance_new = old_balance + capital_closed
old_balance_new = old_balance_new.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
```

#### 3. Recalculate Share

```python
net_profit_new = current_balance - old_balance_new
abs_profit_new = abs(net_profit_new)
share_new = (abs_profit_new * total_pct) / Decimal(100)
share_new = share_new.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
```

#### 4. Calculate New Pending

```python
pending_new = share_new
pending_new = max(Decimal(0), pending_new)
```

#### 5. Create Settlement Adjustment BALANCE_RECORD

```python
ClientDailyBalance.objects.create(
    client_exchange=client_exchange,
    date=settlement_date,
    remaining_balance=old_balance_new,
    extra_adjustment=Decimal(0),
    note=f"Settlement adjustment: Old Balance moved from ₹{old_balance} to ₹{old_balance_new} (capital_closed: ₹{capital_closed})"
)
```

---

## 🎯 Summary

**Partial payment calculation uses these core formulas:**

1. **`capital_closed = (payment × 100) / total_share_pct`** - Converts payment to capital closed
2. **`old_balance_new = old_balance_old - capital_closed`** - Moves Old Balance forward (loss case)
3. **`share_new = (abs_profit_new × total_pct) / 100`** - Recalculates share from new loss
4. **`pending_new = share_new`** - New pending is simply the new share

**Key Insight:** Partial payments close part of the capital base, which automatically reduces the loss and recalculates the pending amount. This ensures consistency and accuracy across all calculations.

---

## 🔗 Related Documentation

- `OLD_BALANCE_DOCUMENTATION.md` - How Old Balance is calculated and displayed
- `HOW_PARTIAL_PAYMENTS_WORK.md` - Overall partial payment process
- `PENDING_PAYMENTS_DOCUMENTATION.md` - Complete pending payments system

---

**Last Updated:** Based on implementation as of latest commit






