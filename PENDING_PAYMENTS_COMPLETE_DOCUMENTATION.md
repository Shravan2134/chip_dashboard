# 📘 Pending Payments System - Complete End-to-End Documentation

## Table of Contents
1. [System Overview](#system-overview)
2. [Core Concepts](#core-concepts)
3. [Old Balance Calculation](#old-balance-calculation)
4. [Current Balance Calculation](#current-balance-calculation)
5. [Net Profit/Loss Calculation](#net-profitloss-calculation)
6. [Share Calculations](#share-calculations)
7. [Pending Amount Calculation](#pending-amount-calculation)
8. [Partial Payment Logic](#partial-payment-logic)
9. [Complete Examples](#complete-examples)
10. [Formulas Summary](#formulas-summary)

---

## System Overview

The Pending Payments system tracks money owed between you and your clients based on exchange balance changes. It handles two types of clients:

- **My Clients**: You receive/pay 100% of the share (e.g., 10% of profit/loss)
- **Company Clients**: Share is split - You get 1%, Company gets 9% (total 10%)

### Key Principles

1. **Old Balance** = Capital base (money you put in)
2. **Current Balance** = Actual exchange balance (reality)
3. **Net Profit/Loss** = Current Balance - Old Balance
4. **Pending** = Your share of the net profit/loss (after settlements)

---

## Core Concepts

### 🔒 Core Truth (Cannot Be Broken)

**If Total Funding = Current Exchange Balance, then there is NO PROFIT and NO PAYMENT in either direction.**

### 🔒 Golden Rule

**When a payment (settlement) is recorded, Old Balance RESETS to reflect the settlement.**

### Transaction Types

- **FUNDING**: Money you add to the exchange (increases capital base)
- **BALANCE_RECORD**: Records the actual exchange balance (reality check)
- **LOSS**: Exchange balance decreased (client owes you)
- **PROFIT**: Exchange balance increased (you owe client)
- **SETTLEMENT**: Payment recorded (moves Old Balance forward)

---

## Old Balance Calculation

### Definition

**Old Balance** = The capital base (money you put in) adjusted for settlements.

### Formula (No Settlement Exists)

```
Old Balance = SUM(All FUNDING transactions)
```

### Formula (Settlement Exists)

**Step 1: Start with funding up to last settlement**
```
Total Funding Up To Settlement = SUM(FUNDING where date <= last_settlement.date)
```

**Step 2: Apply each settlement in chronological order**

For each settlement:
- **If client pays you (loss case)**:
  ```
  Capital Closed = (Payment Amount × 100) / Share Percentage
  Old Balance = Old Balance - Capital Closed
  ```

- **If you pay client (profit case)**:
  ```
  Capital Closed = (Payment Amount × 100) / Share Percentage
  Old Balance = Old Balance + Capital Closed
  ```

**Step 3: Add funding after settlement**
```
Funding After Settlement = SUM(FUNDING where date > last_settlement.date)
```

**Final Old Balance:**
```
Old Balance = Base Old Balance (after settlements) + Funding After Settlement
```

### Important Rules

1. ✅ Old Balance is **NEVER** set manually - calculated automatically
2. ✅ Only **FUNDING** and **SETTLEMENT** transactions affect Old Balance
3. ✅ **LOSS**, **PROFIT**, and **BALANCE_RECORD** do **NOT** affect Old Balance
4. ✅ Settlements are applied in chronological order (`ORDER BY date, created_at`)

### Example: Old Balance Calculation

**Scenario:**
- Dec 1: Funding ₹100
- Dec 2: Balance Record ₹40 (loss of ₹60)
- Dec 3: Settlement ₹8 (client pays)
- Dec 4: Settlement ₹1 (client pays)
- Dec 5: Funding ₹200

**Calculation:**
1. Total Funding Up To Last Settlement = ₹100
2. Apply Settlement ₹8:
   - Capital Closed = (8 × 100) / 10 = ₹80
   - Old Balance = 100 - 80 = ₹20
3. Apply Settlement ₹1:
   - Capital Closed = (1 × 100) / 10 = ₹10
   - Old Balance = 20 - 10 = ₹10
4. Funding After Settlement = ₹200
5. **Final Old Balance = ₹10 + ₹200 = ₹210**

---

## Current Balance Calculation

### Definition

**Current Balance** = The actual exchange balance (reality) from the latest BALANCE_RECORD.

### Formula

```
Current Balance = Latest BALANCE_RECORD.remaining_balance + BALANCE_RECORD.extra_adjustment
```

**Important:** Settlement adjustment records are **EXCLUDED** (they contain Old Balance, not Current Balance).

### Fallback

If no BALANCE_RECORD exists:
```
Current Balance = SUM(All FUNDING transactions)
```

### Example: Current Balance

**Scenario:**
- Latest BALANCE_RECORD: remaining_balance = ₹1000, extra_adjustment = ₹0
- **Current Balance = ₹1000**

---

## Net Profit/Loss Calculation

### Formula

```
Net Profit/Loss = Current Balance - Old Balance
```

### Interpretation

- **If Net Profit/Loss > 0**: **PROFIT** (you owe client)
- **If Net Profit/Loss < 0**: **LOSS** (client owes you)
- **If Net Profit/Loss = 0**: **BALANCED** (no pending)

### Example: Net Profit/Loss

**Scenario:**
- Old Balance = ₹960
- Current Balance = ₹1000
- **Net Profit = ₹1000 - ₹960 = ₹40** (PROFIT - you owe client)

---

## Share Calculations

### My Clients

**My Share Percentage** = `my_share_pct` (e.g., 10%)

**My Share:**
```
My Share = (|Net Profit/Loss| × My Share %) / 100
```

**Company Share:** Always ₹0 (not applicable)

### Company Clients

**My Share Percentage** = 1% (fixed)
**Company Share Percentage** = 9% (fixed)
**Combined Share Percentage** = 10% (1% + 9%)

**My Share:**
```
My Share = (|Net Profit/Loss| × 1%) / 100
```

**Company Share:**
```
Company Share = (|Net Profit/Loss| × 9%) / 100
```

**Combined Share:**
```
Combined Share = (|Net Profit/Loss| × 10%) / 100
```

### Example: Share Calculations

**Scenario (Company Client):**
- Net Profit = ₹40
- My Share % = 1%
- Company Share % = 9%

**Calculations:**
- My Share = (40 × 1) / 100 = ₹0.4
- Company Share = (40 × 9) / 100 = ₹3.6
- Combined Share = (40 × 10) / 100 = ₹4.0

---

## Pending Amount Calculation

### Definition

**Pending Amount** = The amount still owed (after all settlements).

### Key Principle

🚨 **CRITICAL:** Pending is calculated **statelessly** from Old Balance and Current Balance. Settlements are **already reflected** in Old Balance movement, so we **DO NOT** subtract settlements again.

### Formula

**Step 1: Calculate Net Profit/Loss**
```
Net Profit/Loss = Current Balance - Old Balance
```

**Step 2: Calculate Share**
```
Share = (|Net Profit/Loss| × Share Percentage) / 100
```

**Step 3: Pending = Share** (no subtraction needed!)

```
Pending = Share
```

### For Loss Case (Client Owes You)

- Net Profit/Loss < 0 (negative)
- Pending = Share (positive value)
- Shown in "Clients Owe You" section

### For Profit Case (You Owe Client)

- Net Profit/Loss > 0 (positive)
- Pending = Share (positive value, but direction is "you owe")
- Shown in "You Owe Clients" section

### Example: Pending Amount

**Scenario:**
- Old Balance = ₹960
- Current Balance = ₹1000
- Net Profit = ₹40
- Share % = 10%

**Calculation:**
- Share = (40 × 10) / 100 = ₹4
- **Pending = ₹4** (you owe client)

---

## Partial Payment Logic

### Overview

When a partial payment is recorded, the system:
1. Converts payment to "capital closed"
2. Moves Old Balance forward
3. Recalculates Net Profit/Loss
4. Recalculates Pending

### Loss Case (Client Pays You)

**Step 1: Get Current State**
```
Old Balance = get_old_balance_after_settlement()
Current Balance = get_exchange_balance()
Net Profit = Current Balance - Old Balance
```

**Step 2: Validate**
- Net Profit must be < 0 (loss case)
- Pending must be > 0
- Payment amount must be ≤ Pending

**Step 3: Convert Payment to Capital Closed**
```
Capital Closed = (Payment Amount × 100) / Share Percentage
```

**Step 4: Move Old Balance (DECREASES for loss)**
```
Old Balance New = Old Balance - Capital Closed
```

**Step 5: Recalculate Net Profit**
```
Net Profit New = Current Balance - Old Balance New
```

**Step 6: Recalculate Share**
```
Share New = (|Net Profit New| × Share Percentage) / 100
```

**Step 7: Pending New = Share New**
```
Pending New = Share New
```

**Step 8: If Pending New = 0, align Old Balance with Current Balance**
```
If Pending New <= 0.01:
    Old Balance New = Current Balance
    Pending New = 0
```

### Profit Case (You Pay Client)

**Step 1: Get Current State**
```
Old Balance = get_old_balance_after_settlement()
Current Balance = get_exchange_balance()
Net Profit = Current Balance - Old Balance
```

**Step 2: Validate**
- Net Profit must be > 0 (profit case)
- Pending must be > 0
- Payment amount must be ≤ Pending

**Step 3: Convert Payment to Capital Closed**
```
Capital Closed = (Payment Amount × 100) / Share Percentage
```

**Step 4: Move Old Balance (INCREASES for profit)**
```
Old Balance New = Old Balance + Capital Closed
```

**Step 5: Recalculate Net Profit**
```
Net Profit New = Current Balance - Old Balance New
```

**Step 6: Recalculate Share**
```
Share New = (|Net Profit New| × Share Percentage) / 100
```

**Step 7: Pending New = Share New**
```
Pending New = Share New
```

**Step 8: If Pending New = 0, align Old Balance with Current Balance**
```
If Pending New <= 0.01:
    Old Balance New = Current Balance
    Pending New = 0
```

### Key Differences: Loss vs Profit

| Aspect | Loss Case | Profit Case |
|--------|-----------|-------------|
| Net Profit | < 0 (negative) | > 0 (positive) |
| Old Balance Movement | **DECREASES** (OB - capital_closed) | **INCREASES** (OB + capital_closed) |
| Direction | Client pays you | You pay client |
| Section | "Clients Owe You" | "You Owe Clients" |

---

## Complete Examples

### Example 1: Loss Case with Partial Payments

**Assumptions:**
- My Share % = 10%
- Client = My Client
- Exchange = diamond

**Transactions:**
1. **Dec 29 - Funding ₹100**
   - Old Balance = ₹100
   - Current Balance = —
   - Pending = ₹0

2. **Dec 29 - Balance Record ₹10**
   - Old Balance = ₹100
   - Current Balance = ₹10
   - Net Loss = ₹100 - ₹10 = ₹90
   - My Share = (90 × 10) / 100 = ₹9
   - **Pending = ₹9**

3. **Dec 29 - Settlement ₹8** (Client pays)
   - Capital Closed = (8 × 100) / 10 = ₹80
   - Old Balance New = ₹100 - ₹80 = ₹20
   - Net Loss New = ₹20 - ₹10 = ₹10
   - My Share New = (10 × 10) / 100 = ₹1
   - **Pending New = ₹1**

4. **Dec 29 - Settlement ₹1** (Client pays remaining)
   - Capital Closed = (1 × 100) / 10 = ₹10
   - Old Balance New = ₹20 - ₹10 = ₹10
   - Net Loss New = ₹10 - ₹10 = ₹0
   - My Share New = (0 × 10) / 100 = ₹0
   - **Pending New = ₹0** ✅ Case CLOSED

**Final State:**
- Old Balance = ₹10
- Current Balance = ₹10
- Net Loss = ₹0
- Pending = ₹0

---

### Example 2: Profit Case with Partial Payment

**Assumptions:**
- My Share % = 10%
- Client = My Client
- Exchange = diamond

**Transactions:**
1. **Dec 29 - Funding ₹100**
   - Old Balance = ₹100
   - Current Balance = —
   - Pending = ₹0

2. **Dec 29 - Balance Record ₹1000**
   - Old Balance = ₹100
   - Current Balance = ₹1000
   - Net Profit = ₹1000 - ₹100 = ₹900
   - My Share = (900 × 10) / 100 = ₹90
   - **Pending = ₹90** (you owe client)

3. **Dec 29 - Settlement ₹95** (You pay client)
   - Capital Closed = (95 × 100) / 10 = ₹950
   - Old Balance New = ₹100 + ₹950 = ₹1050
   - Net Profit New = ₹1000 - ₹1050 = -₹50 ❌ **INVALID!**

   **Wait! This is wrong. Let me recalculate...**

   Actually, the correct calculation should be:
   - Capital Closed = (95 × 100) / 10 = ₹950
   - Old Balance New = ₹100 + ₹950 = ₹1050
   - Net Profit New = ₹1000 - ₹1050 = -₹50

   But this creates a negative profit, which means Old Balance crossed Current Balance. This should be prevented by validation.

   **Correct scenario:** If you pay ₹90 (full pending):
   - Capital Closed = (90 × 100) / 10 = ₹900
   - Old Balance New = ₹100 + ₹900 = ₹1000
   - Net Profit New = ₹1000 - ₹1000 = ₹0
   - My Share New = ₹0
   - **Pending New = ₹0** ✅ Case CLOSED

**Final State:**
- Old Balance = ₹1000
- Current Balance = ₹1000
- Net Profit = ₹0
- Pending = ₹0

---

### Example 3: Company Client with Loss and Partial Payment

**Assumptions:**
- My Share % = 1%
- Company Share % = 9%
- Combined Share % = 10%
- Client = Company Client
- Exchange = diamond

**Transactions:**
1. **Dec 29 - Funding ₹100**
   - Old Balance = ₹100
   - Current Balance = —
   - Pending = ₹0

2. **Dec 29 - Balance Record ₹10**
   - Old Balance = ₹100
   - Current Balance = ₹10
   - Net Loss = ₹100 - ₹10 = ₹90
   - Combined Share = (90 × 10) / 100 = ₹9
   - My Share = (90 × 1) / 100 = ₹0.9
   - Company Share = (90 × 9) / 100 = ₹8.1
   - **Pending = ₹9** (combined share - client owes you)

3. **Dec 29 - Settlement ₹8** (Client pays)
   - Capital Closed = (8 × 100) / 10 = ₹80
   - Old Balance New = ₹100 - ₹80 = ₹20
   - Net Loss New = ₹20 - ₹10 = ₹10
   - Combined Share New = (10 × 10) / 100 = ₹1
   - My Share New = (10 × 1) / 100 = ₹0.1
   - Company Share New = (10 × 9) / 100 = ₹0.9
   - **Pending New = ₹1** (combined share)

4. **Dec 29 - Settlement ₹1** (Client pays remaining)
   - Capital Closed = (1 × 100) / 10 = ₹10
   - Old Balance New = ₹20 - ₹10 = ₹10
   - Net Loss New = ₹10 - ₹10 = ₹0
   - Combined Share New = ₹0
   - **Pending New = ₹0** ✅ Case CLOSED

**Final State:**
- Old Balance = ₹10
- Current Balance = ₹10
- Net Loss = ₹0
- Pending = ₹0

---

### Example 4: Company Client with Profit and Partial Payment

**Assumptions:**
- My Share % = 1%
- Company Share % = 9%
- Combined Share % = 10%
- Client = Company Client
- Exchange = diamond

**Transactions:**
1. **Dec 29 - Funding ₹100**
   - Old Balance = ₹100
   - Current Balance = —
   - Pending = ₹0

2. **Dec 29 - Balance Record ₹1000**
   - Old Balance = ₹100
   - Current Balance = ₹1000
   - Net Profit = ₹1000 - ₹100 = ₹900
   - Combined Share = (900 × 10) / 100 = ₹90
   - My Share = (900 × 1) / 100 = ₹9
   - Company Share = (900 × 9) / 100 = ₹81
   - **Pending = ₹90** (combined share - you owe client)

3. **Dec 29 - Settlement ₹95** (You pay client)
   - Capital Closed = (95 × 100) / 10 = ₹950
   - Old Balance New = ₹100 + ₹950 = ₹1050
   - Net Profit New = ₹1000 - ₹1050 = -₹50 ❌ **INVALID!**

   **Validation should prevent this!** Payment cannot exceed pending.

   **Correct scenario:** If you pay ₹90 (full pending):
   - Capital Closed = (90 × 100) / 10 = ₹900
   - Old Balance New = ₹100 + ₹900 = ₹1000
   - Net Profit New = ₹1000 - ₹1000 = ₹0
   - Combined Share New = ₹0
   - **Pending New = ₹0** ✅ Case CLOSED

**Final State:**
- Old Balance = ₹1000
- Current Balance = ₹1000
- Net Profit = ₹0
- Pending = ₹0

---

## Formulas Summary

### Old Balance

**No Settlement:**
```
Old Balance = SUM(All FUNDING)
```

**With Settlement:**
```
Old Balance = Base Old Balance (after applying settlements) + Funding After Settlement
```

**Settlement Application:**
```
Capital Closed = (Payment × 100) / Share Percentage

Loss Case:  Old Balance = Old Balance - Capital Closed
Profit Case: Old Balance = Old Balance + Capital Closed
```

### Current Balance

```
Current Balance = Latest BALANCE_RECORD.remaining_balance + BALANCE_RECORD.extra_adjustment
```

### Net Profit/Loss

```
Net Profit/Loss = Current Balance - Old Balance
```

### Share Calculations

**My Clients:**
```
My Share = (|Net Profit/Loss| × My Share %) / 100
Company Share = 0
Combined Share = My Share
```

**Company Clients:**
```
My Share = (|Net Profit/Loss| × 1%) / 100
Company Share = (|Net Profit/Loss| × 9%) / 100
Combined Share = (|Net Profit/Loss| × 10%) / 100
```

### Pending Amount

```
Pending = Share (calculated from current Old Balance and Current Balance)
```

**Important:** Pending is **stateless** - it's recalculated from Old Balance and Current Balance. Settlements are already reflected in Old Balance movement.

### Partial Payment

**Capital Closed:**
```
Capital Closed = (Payment Amount × 100) / Share Percentage
```

**Old Balance Movement:**
```
Loss Case:  Old Balance New = Old Balance - Capital Closed
Profit Case: Old Balance New = Old Balance + Capital Closed
```

**Recalculation:**
```
Net Profit New = Current Balance - Old Balance New
Share New = (|Net Profit New| × Share Percentage) / 100
Pending New = Share New
```

**Final Check:**
```
If Pending New <= 0.01:
    Old Balance New = Current Balance
    Pending New = 0
```

---

## Validation Rules

### Settlement Validation

1. **Pending Check:**
   - Pending must be > 0.01
   - Cannot record payment if no pending amount

2. **Amount Check:**
   - Payment amount must be ≤ Pending
   - Cannot exceed pending amount

3. **Direction Check:**
   - Loss case: Must use "client_pays" (net_profit < 0)
   - Profit case: Must use "admin_pays_profit" (net_profit > 0)

4. **Old Balance Check:**
   - Old Balance New must NOT cross Current Balance
   - Prevents fake profit/loss creation

### Display Rules

1. **Clients Owe You:**
   - Show only when Net Profit/Loss < 0 (loss case)
   - Pending = Share (positive value)

2. **You Owe Clients:**
   - Show only when Net Profit/Loss > 0 (profit case)
   - Pending = Share (positive value, but direction is "you owe")

3. **No Pending:**
   - Hide when Net Profit/Loss = 0
   - Hide when Pending = 0

---

## Key Takeaways

1. ✅ **Old Balance** is the capital base, adjusted for settlements
2. ✅ **Current Balance** is the exchange reality
3. ✅ **Net Profit/Loss** = Current Balance - Old Balance
4. ✅ **Pending** is calculated statelessly from Old Balance and Current Balance
5. ✅ **Settlements move Old Balance** - they don't subtract from pending
6. ✅ **Loss case**: Old Balance decreases when client pays
7. ✅ **Profit case**: Old Balance increases when you pay client
8. ✅ **Partial payments** work by moving Old Balance forward and recalculating

---

## End of Documentation

This documentation covers the complete end-to-end logic for the Pending Payments system. All formulas, examples, and validation rules are included.

For questions or clarifications, refer to the code in `core/views.py`:
- `get_old_balance_after_settlement()` - Old Balance calculation
- `get_exchange_balance()` - Current Balance calculation
- `settle_payment()` - Partial payment logic
- `pending_summary()` - Pending amount calculation and display

