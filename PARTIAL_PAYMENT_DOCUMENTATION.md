# Partial Payment Documentation

## Overview

This document explains how **Old Balance** is calculated and displayed after a **partial payment** (settlement). Understanding this is crucial because partial payments reset the capital base, which affects all future profit/loss calculations.

---

## Table of Contents

1. [What is a Partial Payment?](#what-is-a-partial-payment)
2. [How Partial Payment Affects Old Balance](#how-partial-payment-affects-old-balance)
3. [Old Balance Calculation After Partial Payment](#old-balance-calculation-after-partial-payment)
4. [Step-by-Step Examples](#step-by-step-examples)
5. [Visual Timeline Examples](#visual-timeline-examples)
6. [Common Scenarios](#common-scenarios)
7. [Important Rules](#important-rules)

---

## What is a Partial Payment?

A **partial payment** (also called a **settlement**) occurs when:
- A client pays you **less than the full pending amount**
- Example: Pending = ₹10, Client pays = ₹3 (partial payment of 30%)

### Key Characteristics

- **Payment Amount** = What the client actually paid (e.g., ₹3)
- **My Share %** = Your percentage share (e.g., 10%)
- **Loss Settled** = The total loss that this payment closes (e.g., ₹30)

### Formula

```
Loss Settled = Payment Amount / My Share %

Example:
Payment = ₹3
My Share % = 10%
Loss Settled = ₹3 / 10% = ₹3 / 0.10 = ₹30
```

**Why this formula?**
- If you get 10% of a loss, and you receive ₹3, that means the total loss closed was ₹30
- ₹30 × 10% = ₹3 ✓

---

## How Partial Payment Affects Old Balance

### The Core Principle

**Settlement is a capital reset** - When a partial payment occurs, it closes part of the loss and moves the Old Balance forward.

### Before Partial Payment

```
Old Balance = ₹100 (original funding)
Current Balance = ₹40
Total Loss = ₹100 - ₹40 = ₹60
My Share (10%) = ₹60 × 10% = ₹6
Pending = ₹6
```

### After Partial Payment

When client pays ₹3 (partial payment):

```
Loss Settled = ₹3 / 10% = ₹30
New Old Balance = ₹100 - ₹30 = ₹70
Remaining Loss = ₹70 - ₹40 = ₹30
New My Share (10%) = ₹30 × 10% = ₹3
New Pending = ₹3 - ₹0 = ₹3
```

**Key Insight:** The Old Balance moved from ₹100 to ₹70, reflecting that ₹30 of loss was closed.

---

## Old Balance Calculation After Partial Payment

### The Correct Formula

```
IF settlement exists:
    Old Balance = Current Balance AT settlement date + Funding AFTER settlement
ELSE:
    Old Balance = SUM of ALL FUNDING transactions
```

### Detailed Steps

#### Step 1: Find Last Settlement

Find the most recent SETTLEMENT transaction for the client-exchange pair.

#### Step 2: Get Balance at Settlement Date

Get the Current Balance **at the exact date of the settlement**. This is the balance after the settlement closed part of the loss.

```
balance_at_settlement = get_exchange_balance(client_exchange, as_of_date=settlement.date)
```

#### Step 3: Get Funding After Settlement

Get all FUNDING transactions that occurred **AFTER** the settlement date.

```
funding_after_settlement = SUM of all FUNDING where date > settlement.date
```

#### Step 4: Calculate New Old Balance

```
Old Balance = balance_at_settlement + funding_after_settlement
```

### Why This Works

1. **Balance at settlement** = The new base after loss was closed
2. **Funding after settlement** = New capital added after the reset
3. **Sum of both** = The correct Old Balance going forward

---

## Step-by-Step Examples

### Example 1: Simple Partial Payment

**Initial State:**
- Dec 1: FUNDING ₹100
- Dec 1: BALANCE_RECORD ₹40 (loss of ₹60)
- My Share %: 10%

**Before Payment:**
- Old Balance = ₹100
- Current Balance = ₹40
- Total Loss = ₹60
- My Share = ₹6
- Pending = ₹6

**Transaction:**
- Dec 2: SETTLEMENT ₹3 (client pays partial amount)

**After Payment - Calculation:**

1. **Find Last Settlement:** Dec 2, ₹3
2. **Get Balance at Settlement Date:**
   - Balance on Dec 2 = ₹40 (same as current, no change yet)
3. **Get Funding After Settlement:**
   - Funding after Dec 2 = ₹0 (no new funding)
4. **Calculate Old Balance:**
   - Old Balance = ₹40 + ₹0 = ₹40

**After Payment - New State:**
- Old Balance = ₹40 ✅
- Current Balance = ₹40
- Total Loss = ₹40 - ₹40 = ₹0 ✅
- My Share = ₹0
- Pending = ₹0

**Verification:**
- Loss Settled = ₹3 / 10% = ₹30
- Original Old Balance = ₹100
- Loss Closed = ₹30
- New Old Balance = ₹100 - ₹30 = ₹70 ❌ (WRONG - this is the old method)

**Correct Method:**
- Balance at settlement = ₹40
- Funding after = ₹0
- New Old Balance = ₹40 + ₹0 = ₹40 ✅

---

### Example 2: Partial Payment with New Funding

**Initial State:**
- Dec 1: FUNDING ₹100
- Dec 1: BALANCE_RECORD ₹40 (loss of ₹60)
- My Share %: 10%

**Transaction:**
- Dec 2: SETTLEMENT ₹3 (client pays partial)
- Dec 3: FUNDING ₹50 (new capital added)

**After Payment - Calculation:**

1. **Find Last Settlement:** Dec 2, ₹3
2. **Get Balance at Settlement Date:**
   - Balance on Dec 2 = ₹40
3. **Get Funding After Settlement:**
   - Funding after Dec 2 = ₹50 (Dec 3 funding)
4. **Calculate Old Balance:**
   - Old Balance = ₹40 + ₹50 = ₹90

**After Payment - New State:**
- Old Balance = ₹90 ✅
- Current Balance = ₹40
- Total Loss = ₹90 - ₹40 = ₹50
- My Share = ₹50 × 10% = ₹5
- Pending = ₹5 - ₹0 = ₹5

**Why ₹90?**
- Settlement closed ₹30 of loss (₹3 / 10%)
- Balance at settlement = ₹40
- New funding = ₹50
- Old Balance = ₹40 + ₹50 = ₹90

---

### Example 3: Multiple Partial Payments

**Initial State:**
- Dec 1: FUNDING ₹100
- Dec 1: BALANCE_RECORD ₹40 (loss of ₹60)
- My Share %: 10%

**Transactions:**
- Dec 2: SETTLEMENT ₹3 (first partial payment)
- Dec 5: SETTLEMENT ₹2 (second partial payment)
- Dec 8: FUNDING ₹20 (new capital)

**After All Payments - Calculation:**

1. **Find Last Settlement:** Dec 5, ₹2 (most recent)
2. **Get Balance at Settlement Date:**
   - Balance on Dec 5 = ₹40 (assuming no balance change)
3. **Get Funding After Settlement:**
   - Funding after Dec 5 = ₹20 (Dec 8 funding)
4. **Calculate Old Balance:**
   - Old Balance = ₹40 + ₹20 = ₹60

**After All Payments - New State:**
- Old Balance = ₹60 ✅
- Current Balance = ₹40
- Total Loss = ₹60 - ₹40 = ₹20
- My Share = ₹20 × 10% = ₹2
- Pending = ₹2 - ₹0 = ₹2

**Verification:**
- First payment: ₹3 / 10% = ₹30 loss closed
- Second payment: ₹2 / 10% = ₹20 loss closed
- Total loss closed = ₹30 + ₹20 = ₹50
- Original Old Balance = ₹100
- Loss closed = ₹50
- Remaining base = ₹100 - ₹50 = ₹50
- But we use: Balance at last settlement (₹40) + Funding after (₹20) = ₹60

**Note:** The system uses the balance at the **last settlement date**, not the original balance minus all losses. This ensures accuracy.

---

## Visual Timeline Examples

### Timeline 1: Single Partial Payment

```
Time    Transaction          Old Balance    Current Balance    Loss      Pending
─────────────────────────────────────────────────────────────────────────────────
T0      FUNDING ₹100         ₹100          -                  -         -
T1      BALANCE_RECORD ₹40   ₹100          ₹40                ₹60       ₹6
T2      SETTLEMENT ₹3        ₹40 ✅        ₹40                ₹0        ₹0
```

**At T2 (After Settlement):**
- Old Balance = Balance at T2 (₹40) + Funding after T2 (₹0) = ₹40
- Current Balance = ₹40
- Loss = ₹40 - ₹40 = ₹0
- Pending = ₹0

---

### Timeline 2: Partial Payment + New Funding

```
Time    Transaction          Old Balance    Current Balance    Loss      Pending
─────────────────────────────────────────────────────────────────────────────────
T0      FUNDING ₹100         ₹100          -                  -         -
T1      BALANCE_RECORD ₹40   ₹100          ₹40                ₹60       ₹6
T2      SETTLEMENT ₹3        ₹40           ₹40                ₹0        ₹0
T3      FUNDING ₹50          ₹90 ✅         ₹40                ₹50       ₹5
```

**At T3 (After New Funding):**
- Old Balance = Balance at T2 (₹40) + Funding after T2 (₹50) = ₹90
- Current Balance = ₹40
- Loss = ₹90 - ₹40 = ₹50
- Pending = ₹50 × 10% = ₹5

---

### Timeline 3: Multiple Partial Payments

```
Time    Transaction          Old Balance    Current Balance    Loss      Pending
─────────────────────────────────────────────────────────────────────────────────
T0      FUNDING ₹100         ₹100          -                  -         -
T1      BALANCE_RECORD ₹40   ₹100          ₹40                ₹60       ₹6
T2      SETTLEMENT ₹3        ₹40           ₹40                ₹0        ₹0
T3      SETTLEMENT ₹2         ₹40           ₹40                ₹0        ₹0
T4      FUNDING ₹20          ₹60 ✅         ₹40                ₹20       ₹2
```

**At T4 (After All Transactions):**
- Last Settlement = T3 (₹2)
- Old Balance = Balance at T3 (₹40) + Funding after T3 (₹20) = ₹60
- Current Balance = ₹40
- Loss = ₹60 - ₹40 = ₹20
- Pending = ₹20 × 10% = ₹2

---

## Common Scenarios

### Scenario 1: Full Payment After Partial Payment

**State:**
- Old Balance = ₹100
- Current Balance = ₹40
- Pending = ₹6
- Client pays ₹3 (partial), then ₹3 (full)

**After First Payment (₹3):**
- Old Balance = ₹40
- Current Balance = ₹40
- Pending = ₹0

**After Second Payment (₹3):**
- Old Balance = ₹40 (unchanged - no new settlement affects it differently)
- Current Balance = ₹40
- Pending = ₹0

**Note:** The second payment of ₹3 is actually overpayment since pending was already ₹0. This would be handled as advance payment or adjustment.

---

### Scenario 2: Partial Payment When Balance Changes

**State:**
- Dec 1: FUNDING ₹100
- Dec 1: BALANCE_RECORD ₹40
- Dec 2: SETTLEMENT ₹3
- Dec 3: BALANCE_RECORD ₹50 (profit of ₹10)

**After Settlement (Dec 2):**
- Old Balance = ₹40 (balance at Dec 2)
- Current Balance = ₹40
- Loss = ₹0

**After Balance Change (Dec 3):**
- Old Balance = ₹40 (unchanged - based on last settlement)
- Current Balance = ₹50 (new balance record)
- Net Profit = ₹50 - ₹40 = ₹10 (profit!)
- My Share = ₹10 × 10% = ₹1 (you owe client)

**Key Point:** Old Balance stays at ₹40 (from settlement), but Current Balance changes to ₹50, creating a profit situation.

---

### Scenario 3: Partial Payment with Multiple Funding Rounds

**State:**
- Dec 1: FUNDING ₹100
- Dec 1: BALANCE_RECORD ₹40
- Dec 2: SETTLEMENT ₹3
- Dec 3: FUNDING ₹50
- Dec 4: FUNDING ₹30

**After All Transactions:**
- Last Settlement = Dec 2
- Balance at Dec 2 = ₹40
- Funding after Dec 2 = ₹50 + ₹30 = ₹80
- **Old Balance = ₹40 + ₹80 = ₹120**

**Current State:**
- Old Balance = ₹120
- Current Balance = ₹40
- Total Loss = ₹120 - ₹40 = ₹80
- My Share = ₹80 × 10% = ₹8
- Pending = ₹8 - ₹3 = ₹5

---

## Important Rules

### Rule 1: Settlement Resets the Base

When a settlement occurs, Old Balance is reset to the balance at the settlement date. This prevents double-counting of losses.

✅ **CORRECT:**
```
Old Balance = balance_at_settlement + funding_after_settlement
```

❌ **WRONG:**
```
Old Balance = original_funding - loss_settled + funding_after
```

### Rule 2: Use Balance at Settlement Date

Always use the balance **at the exact settlement date**, not the current balance or original balance.

✅ **CORRECT:**
```
balance_at_settlement = get_exchange_balance(client_exchange, as_of_date=settlement.date)
```

❌ **WRONG:**
```
balance_at_settlement = current_balance  # May have changed since settlement
```

### Rule 3: Only Count Funding After Settlement

Only funding that came **AFTER** the last settlement counts toward new Old Balance.

✅ **CORRECT:**
```
funding_after = SUM of FUNDING where date > last_settlement.date
```

❌ **WRONG:**
```
funding_after = SUM of ALL FUNDING  # Includes pre-settlement funding
```

### Rule 4: Last Settlement Wins

If multiple settlements exist, only the **last settlement** matters for Old Balance calculation. Previous settlements are already reflected in the balance at the last settlement date.

✅ **CORRECT:**
```
Old Balance = balance_at_last_settlement + funding_after_last_settlement
```

❌ **WRONG:**
```
Old Balance = balance_at_first_settlement - all_losses_settled + all_funding_after
```

### Rule 5: Never Override with Total Funding

Once a settlement exists, never override Old Balance with `sum(all_funding)`. This breaks the settlement reset mechanism.

✅ **CORRECT:**
```
Old Balance = balance_at_settlement + funding_after_settlement
```

❌ **WRONG:**
```
Old Balance = sum(all_funding)  # Ignores settlement reset
```

---

## Summary

### Key Takeaways

1. **Partial payment resets Old Balance** to the balance at the settlement date
2. **Old Balance formula:** `balance_at_settlement + funding_after_settlement`
3. **Only the last settlement matters** - previous settlements are already reflected
4. **Funding after settlement** is added to the new base
5. **Never use sum(all_funding)** once a settlement exists

### Formula Summary

```
IF settlement exists:
    Old Balance = Current Balance AT settlement date + Funding AFTER settlement
ELSE:
    Old Balance = SUM of ALL FUNDING transactions
```

### Example Summary

**Before Partial Payment:**
- Old Balance = ₹100
- Current Balance = ₹40
- Loss = ₹60
- Pending = ₹6

**After Partial Payment (₹3):**
- Old Balance = ₹40 (balance at settlement)
- Current Balance = ₹40
- Loss = ₹0
- Pending = ₹0

**After New Funding (₹50):**
- Old Balance = ₹40 + ₹50 = ₹90
- Current Balance = ₹40
- Loss = ₹50
- Pending = ₹5

---

**Last Updated:** 2025-12-28
**Version:** 1.0


