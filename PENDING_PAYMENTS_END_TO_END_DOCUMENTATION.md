# 📘 Pending Payments System - Complete End-to-End Documentation

## Table of Contents
1. [System Overview](#system-overview)
2. [Core Concepts & Fundamental Rules](#core-concepts--fundamental-rules)
3. [Old Balance Calculation](#old-balance-calculation)
4. [Current Balance Calculation](#current-balance-calculation)
5. [Net Profit/Loss Calculation](#net-profitloss-calculation)
6. [Share Calculations](#share-calculations)
7. [Pending Amount Calculation](#pending-amount-calculation)
8. [Partial Payment Logic](#partial-payment-logic)
9. [Complete Step-by-Step Examples](#complete-step-by-step-examples)
10. [All Formulas Reference](#all-formulas-reference)
11. [Critical Implementation Rules](#critical-implementation-rules)
12. [Common Pitfalls & Solutions](#common-pitfalls--solutions)

---

## System Overview

The Pending Payments system is a financial tracking system that calculates money owed between you (admin) and your clients based on exchange balance changes. It handles two types of clients:

- **My Clients**: You receive/pay 100% of the share (e.g., 10% of profit/loss)
- **Company Clients**: Share is split - You get 1%, Company gets 9% (total 10%)

### Key Components

1. **Old Balance** = Capital base (money you put in) adjusted for settlements
2. **Current Balance** = Actual exchange balance (reality from BALANCE_RECORD)
3. **Net Profit/Loss** = Current Balance - Old Balance
4. **Pending** = Your share of the net profit/loss (calculated statelessly)

### 🔒 Critical Separation

- **BALANCE_RECORD** = Exchange reality only (actual balance in exchange)
- **Old Balance** = Accounting baseline only (stored in `ClientExchange.cached_old_balance`)
- **Settlement moves Old Balance, NOT Current Balance**

---

## Core Concepts & Fundamental Rules

### 🔒 Core Truth (Cannot Be Broken)

**If Total Funding = Current Exchange Balance, then there is NO PROFIT and NO PAYMENT in either direction.**

This is the fundamental rule that governs the entire system.

### 🔒 Golden Rule

**When a payment (settlement) is recorded, Old Balance moves forward to reflect the settlement. Old Balance is stored in `ClientExchange.cached_old_balance` and is the PRIMARY source of truth.**

### Transaction Types

- **FUNDING**: Money you add to the exchange (increases capital base)
- **BALANCE_RECORD**: Records the actual exchange balance (reality check)
- **LOSS**: Exchange balance decreased (client owes you)
- **PROFIT**: Exchange balance increased (you owe client)
- **SETTLEMENT**: Payment recorded (moves Old Balance forward)

### 🔑 Key Rules

1. ✅ **Old Balance is NEVER set manually** - calculated automatically from transactions
2. ✅ **Only FUNDING and SETTLEMENT transactions affect Old Balance**
3. ✅ **LOSS, PROFIT, and BALANCE_RECORD do NOT affect Old Balance**
4. ✅ **Old Balance must NEVER cross Current Balance** (prevents fake profit/loss)
5. ✅ **Pending is calculated statelessly** - settlements are already reflected in Old Balance movement
6. ✅ **Round ONLY at the final step** - never round intermediate calculations

---

## Old Balance Calculation

### Definition

**Old Balance** = The capital base (money you put in) adjusted for settlements. This is stored in `ClientExchange.cached_old_balance` and is the PRIMARY source of truth.

### 🔑 Primary Source: `cached_old_balance`

The system uses `ClientExchange.cached_old_balance` as the PRIMARY source if:
- It exists (not None)
- It was updated within the last 24 hours

**Only if cache is missing or stale**, the system recalculates from funding and settlement history.

### Formula (No Settlement Exists)

```
Old Balance = SUM(All FUNDING transactions)
```

### Formula (Settlement Exists - Recalculation Fallback)

**Step 1: Start with funding up to last settlement**
```
Total Funding Up To Settlement = SUM(FUNDING where date <= last_settlement.date)
```

**Step 2: Apply each settlement in chronological order**

For each settlement (ordered by `date, created_at`):
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
Old Balance = Base Old Balance (after applying settlements) + Funding After Settlement
```

### 🔒 Critical Safety Rule: Old Balance Clamping

**Old Balance must NEVER cross Current Balance.**

**For Loss Case:**
```
Old Balance New = max(Old Balance - Capital Closed, Current Balance)
```

If Old Balance would go below Current Balance, it is clamped to Current Balance (fully paid).

**For Profit Case:**
```
Old Balance New = min(Old Balance + Capital Closed, Current Balance)
```

If Old Balance exceeds Current Balance after settlement, it is clamped to Current Balance (overpayment prevented).

### Important Rules

1. ✅ Old Balance is stored in `ClientExchange.cached_old_balance` (updated during settlement)
2. ✅ `cached_old_balance` is the PRIMARY source (not recalculated from funding unless cache is stale)
3. ✅ Only **FUNDING** and **SETTLEMENT** transactions affect Old Balance
4. ✅ **LOSS**, **PROFIT**, and **BALANCE_RECORD** do **NOT** affect Old Balance
5. ✅ Settlements are applied in chronological order (`ORDER BY date, created_at`)
6. ✅ Old Balance is clamped to Current Balance to prevent crossing

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

### Caching

Current Balance is cached in `ClientExchange.cached_current_balance` and refreshed:
- When a new BALANCE_RECORD is created
- If cache is older than 1 hour

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
- Old Balance = ₹70
- Current Balance = ₹60
- **Net Profit = ₹60 - ₹70 = -₹10** (LOSS - client owes you)

---

## Share Calculations

### My Clients

**My Share Percentage** = `my_share_pct` (e.g., 10%)

**My Share:**
```
My Share = (|Net Profit/Loss| × My Share %) / 100
```

**Company Share:** Always ₹0 (not applicable)

**Combined Share:**
```
Combined Share = My Share
```

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
- Net Loss = ₹10
- My Share % = 1%
- Company Share % = 9%

**Calculations:**
- My Share = (10 × 1) / 100 = ₹0.1
- Company Share = (10 × 9) / 100 = ₹0.9
- Combined Share = (10 × 10) / 100 = ₹1.0

---

## Pending Amount Calculation

### Definition

**Pending Amount** = The amount still owed (after all settlements).

### Key Principle

🚨 **CRITICAL:** Pending is calculated **statelessly** from Old Balance and Current Balance. Settlements are **already reflected** in Old Balance movement, so we **DO NOT** subtract settlements again.

### Formula

**Step 1: Calculate Net Profit/Loss (NO ROUNDING)**
```
Net Profit/Loss = Current Balance - Old Balance
```

**Step 2: Calculate Share (NO ROUNDING)**
```
Share = (|Net Profit/Loss| × Share Percentage) / 100
```

**Step 3: Pending = Share (NO ROUNDING)**
```
Pending = Share
```

**Step 4: Round ONLY at final step**
```
Pending = Pending.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
```

### 🚨 Critical: Rounding Rules

**NEVER round intermediate calculations!**

❌ **WRONG:**
```python
abs_profit = abs(current_balance - old_balance)
abs_profit = abs_profit.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)  # ❌ EARLY ROUND
share = (abs_profit * total_pct) / 100
```

✅ **CORRECT:**
```python
abs_profit = abs(current_balance - old_balance)  # NO rounding
share = (abs_profit * total_pct) / 100  # NO rounding
share = share.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)  # ONLY HERE
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
- Old Balance = ₹70
- Current Balance = ₹60
- Net Loss = ₹60 - ₹70 = -₹10
- Share % = 10%

**Calculation (with full precision):**
- Share = (10 × 10) / 100 = ₹1.0 (exact)
- **Pending = ₹1.0** (client owes you)

**If rounding too early:**
- If Old Balance = ₹64.6 (rounded), Current Balance = ₹60
- Net Loss = ₹4.6 (rounded early ❌)
- Share = (4.6 × 10) / 100 = ₹0.46 → rounded to ₹0.5 or ₹0.6 ❌

---

## Partial Payment Logic

### Overview

When a partial payment is recorded, the system:
1. Validates the payment
2. Converts payment to "capital closed"
3. Moves Old Balance forward (with clamping)
4. Recalculates Net Profit/Loss
5. Recalculates Pending
6. Updates `cached_old_balance`

### Loss Case (Client Pays You)

**Step 1: Get Current State (NO ROUNDING)**
```
Old Balance = get_old_balance_after_settlement()  # Uses cached_old_balance if available
Current Balance = get_exchange_balance()
Net Profit = Current Balance - Old Balance
```

**Step 2: Validate**
- Net Profit must be < 0 (loss case)
- Pending must be > 0.01
- Payment amount must be ≤ Pending

**Step 3: Convert Payment to Capital Closed (NO ROUNDING)**
```
Capital Closed = (Payment Amount × 100) / Share Percentage
```

**Step 4: Move Old Balance (DECREASES for loss, with clamping)**
```
Old Balance New = Old Balance - Capital Closed
Old Balance New = max(Old Balance New, Current Balance)  # Clamp to Current Balance
```

**Step 5: Recalculate Net Profit (NO ROUNDING)**
```
Net Profit New = Current Balance - Old Balance New
```

**Step 6: Recalculate Share (NO ROUNDING)**
```
Share New = (|Net Profit New| × Share Percentage) / 100
```

**Step 7: Pending New = Share New (NO ROUNDING)**
```
Pending New = Share New
```

**Step 8: Round ONLY at final step**
```
Pending New = Pending New.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
```

**Step 9: If Pending New = 0, align Old Balance with Current Balance**
```
If Pending New <= 0.01:
    Old Balance New = Current Balance
    Pending New = 0
```

**Step 10: Update Cache**
```
ClientExchange.cached_old_balance = Old Balance New
ClientExchange.balance_last_updated = timezone.now()
```

### Profit Case (You Pay Client)

**Step 1: Get Current State (NO ROUNDING)**
```
Old Balance = get_old_balance_after_settlement()  # Uses cached_old_balance if available
Current Balance = get_exchange_balance()
Net Profit = Current Balance - Old Balance
```

**Step 2: Validate**
- Net Profit must be > 0 (profit case)
- Pending must be > 0.01
- Payment amount must be ≤ Pending

**Step 3: Convert Payment to Capital Closed (NO ROUNDING)**
```
Capital Closed = (Payment Amount × 100) / Share Percentage
```

**Step 4: Move Old Balance (INCREASES for profit, with clamping)**
```
Old Balance New = Old Balance + Capital Closed
If Old Balance New > Current Balance:
    Old Balance New = Current Balance  # Clamp to Current Balance (overpayment prevented)
```

**Step 5: Recalculate Net Profit (NO ROUNDING)**
```
Net Profit New = Current Balance - Old Balance New
```

**Step 6: Recalculate Share (NO ROUNDING)**
```
Share New = (|Net Profit New| × Share Percentage) / 100
```

**Step 7: Pending New = Share New (NO ROUNDING)**
```
Pending New = Share New
```

**Step 8: Round ONLY at final step**
```
Pending New = Pending New.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
```

**Step 9: If Pending New = 0, align Old Balance with Current Balance**
```
If Pending New <= 0.01:
    Old Balance New = Current Balance
    Pending New = 0
```

**Step 10: Update Cache**
```
ClientExchange.cached_old_balance = Old Balance New
ClientExchange.balance_last_updated = timezone.now()
```

### Key Differences: Loss vs Profit

| Aspect | Loss Case | Profit Case |
|--------|-----------|-------------|
| Net Profit | < 0 (negative) | > 0 (positive) |
| Old Balance Movement | **DECREASES** (OB - capital_closed) | **INCREASES** (OB + capital_closed) |
| Clamping | `max(OB - CC, CB)` | `min(OB + CC, CB)` |
| Direction | Client pays you | You pay client |
| Section | "Clients Owe You" | "You Owe Clients" |

---

## Complete Step-by-Step Examples

### Example 1: Loss Case with Partial Payment (Realistic Scenario)

**Assumptions:**
- My Share % = 10%
- Client = My Client
- Exchange = diamond

**Transactions:**
1. **Dec 1 - Funding ₹100**
   - Old Balance = ₹100
   - Current Balance = —
   - Pending = ₹0

2. **Dec 1 - Balance Record ₹40**
   - Old Balance = ₹100
   - Current Balance = ₹40
   - Net Loss = ₹40 - ₹100 = -₹60
   - My Share = (60 × 10) / 100 = ₹6.0
   - **Pending = ₹6.0** (client owes you)

3. **Dec 2 - Settlement ₹3** (Client pays)
   - Capital Closed = (3 × 100) / 10 = ₹30.0
   - Old Balance New = ₹100 - ₹30 = ₹70.0
   - Old Balance New = max(₹70, ₹40) = ₹70 ✅ (no clamping needed)
   - Net Loss New = ₹40 - ₹70 = -₹10.0
   - My Share New = (10 × 10) / 100 = ₹1.0
   - **Pending New = ₹1.0**
   - `cached_old_balance = ₹70` ✅

4. **Dec 3 - Profit +₹20** (Balance Record ₹60)
   - Old Balance = ₹70 (from cache)
   - Current Balance = ₹60
   - Net Loss = ₹60 - ₹70 = -₹10.0
   - My Share = (10 × 10) / 100 = ₹1.0
   - **Pending = ₹1.0** ✅ (client still owes you - loss not fully recovered)

**Final State:**
- Old Balance = ₹70
- Current Balance = ₹60
- Net Loss = -₹10
- Pending = ₹1.0

✅ **This is CORRECT behavior** - the client made profit, but the loss is not fully recovered yet.

---

### Example 2: Loss Case with Full Payment

**Assumptions:**
- My Share % = 10%
- Client = My Client

**Transactions:**
1. **Dec 1 - Funding ₹100**
   - Old Balance = ₹100
   - Current Balance = —
   - Pending = ₹0

2. **Dec 1 - Balance Record ₹40**
   - Old Balance = ₹100
   - Current Balance = ₹40
   - Net Loss = -₹60
   - My Share = ₹6.0
   - **Pending = ₹6.0**

3. **Dec 2 - Settlement ₹6** (Client pays full)
   - Capital Closed = (6 × 100) / 10 = ₹60.0
   - Old Balance New = ₹100 - ₹60 = ₹40.0
   - Old Balance New = max(₹40, ₹40) = ₹40 ✅ (clamped to Current Balance)
   - Net Loss New = ₹40 - ₹40 = ₹0
   - My Share New = ₹0
   - **Pending New = ₹0** ✅ Case CLOSED

**Final State:**
- Old Balance = ₹40
- Current Balance = ₹40
- Net Loss = ₹0
- Pending = ₹0

---

### Example 3: Company Client with Loss and Partial Payment

**Assumptions:**
- My Share % = 1%
- Company Share % = 9%
- Combined Share % = 10%
- Client = Company Client

**Transactions:**
1. **Dec 1 - Funding ₹100**
   - Old Balance = ₹100
   - Current Balance = —
   - Pending = ₹0

2. **Dec 1 - Balance Record ₹40**
   - Old Balance = ₹100
   - Current Balance = ₹40
   - Net Loss = -₹60
   - Combined Share = (60 × 10) / 100 = ₹6.0
   - My Share = (60 × 1) / 100 = ₹0.6
   - Company Share = (60 × 9) / 100 = ₹5.4
   - **Pending = ₹6.0** (combined share - client owes you)

3. **Dec 2 - Settlement ₹3** (Client pays)
   - Capital Closed = (3 × 100) / 10 = ₹30.0
   - Old Balance New = ₹100 - ₹30 = ₹70.0
   - Net Loss New = ₹40 - ₹70 = -₹30.0
   - Combined Share New = (30 × 10) / 100 = ₹3.0
   - My Share New = (30 × 1) / 100 = ₹0.3
   - Company Share New = (30 × 9) / 100 = ₹2.7
   - **Pending New = ₹3.0** (combined share)

**Final State:**
- Old Balance = ₹70
- Current Balance = ₹40
- Net Loss = -₹30
- Pending = ₹3.0

---

### Example 4: Profit Case with Partial Payment

**Assumptions:**
- My Share % = 10%
- Client = My Client

**Transactions:**
1. **Dec 1 - Funding ₹100**
   - Old Balance = ₹100
   - Current Balance = —
   - Pending = ₹0

2. **Dec 1 - Balance Record ₹1000**
   - Old Balance = ₹100
   - Current Balance = ₹1000
   - Net Profit = ₹1000 - ₹100 = ₹900
   - My Share = (900 × 10) / 100 = ₹90.0
   - **Pending = ₹90.0** (you owe client)

3. **Dec 2 - Settlement ₹90** (You pay client full)
   - Capital Closed = (90 × 100) / 10 = ₹900.0
   - Old Balance New = ₹100 + ₹900 = ₹1000.0
   - Old Balance New = min(₹1000, ₹1000) = ₹1000 ✅ (clamped to Current Balance)
   - Net Profit New = ₹1000 - ₹1000 = ₹0
   - My Share New = ₹0
   - **Pending New = ₹0** ✅ Case CLOSED

**Final State:**
- Old Balance = ₹1000
- Current Balance = ₹1000
- Net Profit = ₹0
- Pending = ₹0

---

## All Formulas Reference

### Old Balance

**Primary Source:**
```
Old Balance = ClientExchange.cached_old_balance  # If available and recent (< 24 hours)
```

**Fallback (No Settlement):**
```
Old Balance = SUM(All FUNDING)
```

**Fallback (With Settlement):**
```
Old Balance = Base Old Balance (after applying settlements) + Funding After Settlement
```

**Settlement Application:**
```
Capital Closed = (Payment × 100) / Share Percentage

Loss Case:  Old Balance = max(Old Balance - Capital Closed, Current Balance)
Profit Case: Old Balance = min(Old Balance + Capital Closed, Current Balance)
```

### Current Balance

```
Current Balance = Latest BALANCE_RECORD.remaining_balance + BALANCE_RECORD.extra_adjustment
```

**Excludes:** Settlement adjustment records

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
Pending = Pending.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)  # Round ONLY at final step
```

**Important:** Pending is **stateless** - it's recalculated from Old Balance and Current Balance. Settlements are already reflected in Old Balance movement.

### Partial Payment

**Capital Closed:**
```
Capital Closed = (Payment Amount × 100) / Share Percentage
```

**Old Balance Movement:**
```
Loss Case:  Old Balance New = max(Old Balance - Capital Closed, Current Balance)
Profit Case: Old Balance New = min(Old Balance + Capital Closed, Current Balance)
```

**Recalculation (NO ROUNDING until final step):**
```
Net Profit New = Current Balance - Old Balance New
Share New = (|Net Profit New| × Share Percentage) / 100
Pending New = Share New.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)  # Round ONLY here
```

**Final Check:**
```
If Pending New <= 0.01:
    Old Balance New = Current Balance
    Pending New = 0
```

**Cache Update:**
```
ClientExchange.cached_old_balance = Old Balance New
ClientExchange.balance_last_updated = timezone.now()
```

---

## Critical Implementation Rules

### 1. Rounding Rules

🚨 **NEVER round intermediate calculations!**

✅ **CORRECT:**
```python
# Calculate with full precision
net_profit = current_balance - old_balance  # NO rounding
abs_profit = abs(net_profit)  # NO rounding
share = (abs_profit * total_pct) / Decimal(100)  # NO rounding
pending = share.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)  # Round ONLY here
```

❌ **WRONG:**
```python
# Rounding too early causes errors
net_profit = current_balance - old_balance
net_profit = net_profit.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)  # ❌ EARLY ROUND
abs_profit = abs(net_profit)
share = (abs_profit * total_pct) / Decimal(100)  # Error accumulates
```

### 2. Pending Calculation Rules

🚨 **NEVER subtract settlements from pending!**

✅ **CORRECT:**
```python
# Pending is stateless - settlements already reflected in Old Balance
pending = share  # That's it!
```

❌ **WRONG:**
```python
# This causes double counting
pending = share - settlements_sum  # ❌ WRONG - settlements already in Old Balance
```

### 3. Old Balance Cache Rules

🚨 **Always use cached_old_balance as PRIMARY source!**

✅ **CORRECT:**
```python
# Use cache if available and recent
if client_exchange.cached_old_balance and cache_age < 24_hours:
    old_balance = client_exchange.cached_old_balance
else:
    # Recalculate from history (fallback only)
    old_balance = recalculate_from_history()
```

### 4. Old Balance Clamping Rules

🚨 **Old Balance must NEVER cross Current Balance!**

✅ **CORRECT:**
```python
# Loss case
old_balance_new = old_balance - capital_closed
old_balance_new = max(old_balance_new, current_balance)  # Clamp to Current Balance

# Profit case
old_balance_new = old_balance + capital_closed
old_balance_new = min(old_balance_new, current_balance)  # Clamp to Current Balance
```

---

## Common Pitfalls & Solutions

### Pitfall 1: Rounding Too Early

**Symptom:** Pending shows ₹0.6 instead of ₹0.5

**Cause:** Rounding `abs_profit` or `net_profit` before calculating share

**Solution:** Calculate with full precision, round only at final step

```python
# ❌ WRONG
abs_profit = abs(current_balance - old_balance)
abs_profit = abs_profit.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)  # ❌
share = (abs_profit * total_pct) / 100

# ✅ CORRECT
abs_profit = abs(current_balance - old_balance)  # NO rounding
share = (abs_profit * total_pct) / 100  # NO rounding
share = share.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)  # Round ONLY here
```

### Pitfall 2: Stale cached_old_balance

**Symptom:** Old Balance shows wrong value after settlement

**Cause:** Using stale cache or not updating cache after settlement

**Solution:** Always update cache after settlement, check cache age

```python
# After settlement
client_exchange.cached_old_balance = old_balance_new
client_exchange.balance_last_updated = timezone.now()
client_exchange.save(update_fields=['cached_old_balance', 'balance_last_updated'])
```

### Pitfall 3: Double-Subtracting Settlements

**Symptom:** Pending decreases too much after settlement

**Cause:** Subtracting settlements from pending even though they're already in Old Balance

**Solution:** Pending is stateless - just recalculate from Old Balance and Current Balance

```python
# ❌ WRONG
pending = share - settlements_sum  # ❌ Double counting

# ✅ CORRECT
pending = share  # Settlements already reflected in Old Balance
```

### Pitfall 4: Old Balance Crossing Current Balance

**Symptom:** Profit flips to loss or vice versa after settlement

**Cause:** Not clamping Old Balance to Current Balance

**Solution:** Always clamp Old Balance to Current Balance

```python
# Loss case
old_balance_new = max(old_balance - capital_closed, current_balance)

# Profit case
old_balance_new = min(old_balance + capital_closed, current_balance)
```

---

## End of Documentation

This documentation covers the complete end-to-end logic for the Pending Payments system. All formulas, examples, and implementation rules are included.

For questions or clarifications, refer to the code in `core/views.py`:
- `get_old_balance_after_settlement()` - Old Balance calculation (uses `cached_old_balance` as primary source)
- `get_exchange_balance()` - Current Balance calculation
- `settle_payment()` - Partial payment logic (with Old Balance clamping and proper rounding)
- `pending_summary()` - Pending amount calculation and display (with proper rounding)

---

**Last Updated:** December 2025
**Version:** 3.0 (with proper rounding rules and comprehensive examples)





