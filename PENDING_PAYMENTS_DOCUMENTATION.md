# Pending Payments System Documentation

## Overview

This document explains how the pending payments system calculates all financial values, including Old Balance, Current Balance, Total Loss/Profit, Shares, and Percentages for both My Clients and Company Clients.

---

## Table of Contents

1. [Core Concepts](#core-concepts)
2. [Old Balance Calculation](#old-balance-calculation)
3. [Current Balance Calculation](#current-balance-calculation)
4. [Net Profit / Total Loss Calculation](#net-profit--total-loss-calculation)
5. [Share Calculations](#share-calculations)
6. [Share Percentages](#share-percentages)
7. [Pending Amount Calculation](#pending-amount-calculation)
8. [Examples](#examples)
9. [Business Rules](#business-rules)

---

## Core Concepts

### Key Principles

1. **Old Balance and Current Balance define reality** - Everything else is derived from these two values
2. **Net Profit is the ONLY source of truth** - All share calculations come from Net Profit
3. **Shares are stateless** - They are recalculated fresh every time from Net Profit
4. **Pending is stateful** - It depends on settlements made (Pending = Share Amount - Settlements)
5. **Settlement resets Old Balance** - When a settlement occurs, Old Balance moves forward

---

## Old Balance Calculation

### Definition

**Old Balance** = The exchange balance immediately BEFORE the current profit/loss situation. This represents the original capital invested (after accounting for settlements).

### Formula

```
IF settlement exists:
    Old Balance = Current Balance AT settlement date + Funding AFTER settlement
ELSE:
    Old Balance = SUM of ALL FUNDING transactions
```

### Detailed Logic

#### Step 1: Check for Settlements

The system first checks if any SETTLEMENT transactions exist for the client-exchange pair.

#### Step 2A: If Settlement Exists

1. Find the **last SETTLEMENT transaction** (most recent date)
2. Get **Current Balance AT the settlement date** using `get_exchange_balance(client_exchange, as_of_date=last_settlement.date)`
3. Get all **FUNDING transactions AFTER the last settlement** (date > settlement date)
4. Calculate: `Old Balance = balance_at_settlement + funding_after_settlement`

**Why this works:**
- Settlement closes part of the loss
- The balance at settlement becomes the new base
- Only funding after settlement counts toward new capital

#### Step 2B: If No Settlement Exists

1. Get all **FUNDING transactions** (no date filter)
2. Calculate: `Old Balance = SUM(all_funding_amounts)`

**Why this works:**
- No settlement means no capital reset
- Total funding = original capital base

### Important Rules

✅ **DO:**
- Always respect settlements when calculating Old Balance
- Use balance_at_settlement as the new base after settlement
- Only count funding that came AFTER the last settlement

❌ **DON'T:**
- Never use `sum(all_funding)` if a settlement exists
- Never override Old Balance with total_funding after settlement
- Never include funding that came before settlement in the new base

### Example

**Scenario:**
- Dec 1: FUNDING ₹100
- Dec 1: BALANCE_RECORD ₹10 (loss of ₹90)
- Dec 2: SETTLEMENT ₹9 (client paid 10% share)
- Dec 3: FUNDING ₹100

**Calculation:**
1. Settlement exists → Use settlement-aware logic
2. Balance at settlement (Dec 2) = ₹10
3. Funding after settlement = ₹100
4. **Old Balance = ₹10 + ₹100 = ₹110**

**Without settlement-aware logic (WRONG):**
- Old Balance = ₹100 + ₹100 = ₹200 ❌ (double-counts pre-settlement funding)

---

## Current Balance Calculation

### Definition

**Current Balance** = The latest exchange balance recorded in the system. This is the actual current state of the client's account.

### Formula

```
Current Balance = Latest BALANCE_RECORD transaction amount
```

### Detailed Logic

1. Query all **BALANCE_RECORD transactions** for the client-exchange pair
2. Order by date (descending) and created_at (descending)
3. Take the **most recent** balance record
4. Use its `amount` field as Current Balance

### Important Rules

✅ **DO:**
- Always use the latest BALANCE_RECORD
- Consider both date and created_at for ordering

❌ **DON'T:**
- Never use FUNDING, LOSS, or PROFIT transactions for current balance
- Never use cached values if they might be stale

### Example

**Scenario:**
- Dec 1: BALANCE_RECORD ₹100
- Dec 5: BALANCE_RECORD ₹50
- Dec 10: BALANCE_RECORD ₹75

**Current Balance = ₹75** (latest record)

---

## Net Profit / Total Loss Calculation

### Definition

**Net Profit** = The difference between Current Balance and Old Balance. This is the ONLY source of truth for all share calculations.

### Formula

```
net_profit = current_balance - old_balance

IF net_profit < 0:
    Total Loss = abs(net_profit)
    Total Profit = 0
ELSE IF net_profit > 0:
    Total Loss = 0
    Total Profit = net_profit
ELSE:
    Total Loss = 0
    Total Profit = 0
```

### Interpretation

- **Net Profit < 0** → Client is in LOSS (client owes you)
- **Net Profit > 0** → Client is in PROFIT (you owe client)
- **Net Profit = 0** → Break-even (no pending)

### Important Rules

✅ **DO:**
- Always calculate Net Profit first
- Use Net Profit as the single source of truth
- Derive Total Loss/Profit from Net Profit

❌ **DON'T:**
- Never mix loss and profit in one variable
- Never use transaction tallies instead of Net Profit
- Never accumulate losses/profits from individual transactions

### Example

**Scenario:**
- Old Balance = ₹100
- Current Balance = ₹10

**Calculation:**
- net_profit = ₹10 - ₹100 = -₹90
- net_profit < 0 → Loss case
- **Total Loss = ₹90**
- **Total Profit = ₹0**

---

## Share Calculations

### Definition

**Shares** = The portion of Total Loss or Total Profit that belongs to you (My Share) and the company (Company Share).

### Key Principle

**Shares are STATELESS** - They are recalculated fresh every time from Net Profit. They do NOT accumulate or store state.

### Formula

```
# Step 1: Calculate Net Profit (see above)
net_profit = current_balance - old_balance

# Step 2: Calculate share amounts (stateless)
abs_net_profit = abs(net_profit)

My Share Amount = abs_net_profit × (my_share_pct / 100)
Company Share Amount = abs_net_profit × (company_share_pct / 100)
Combined Share Amount = My Share Amount + Company Share Amount
```

### For My Clients

- **My Share %** = Percentage from `ClientExchange.my_share_pct`
- **Company Share %** = 0 (not applicable)
- **My Share Amount** = `abs_net_profit × my_share_pct / 100`
- **Company Share Amount** = 0
- **Combined Share Amount** = My Share Amount

### For Company Clients

- **My Share %** = 1% (typically, from `ClientExchange.my_share_pct`)
- **Company Share %** = 9% (typically, from `ClientExchange.company_share_pct`)
- **My Share Amount** = `abs_net_profit × 1%`
- **Company Share Amount** = `abs_net_profit × 9%`
- **Combined Share Amount** = My Share Amount + Company Share Amount

### Important Rules

✅ **DO:**
- Always calculate shares from Net Profit
- Recalculate shares fresh every time (stateless)
- Use the same formula for both My Clients and Company Clients

❌ **DON'T:**
- Never accumulate shares from individual transactions
- Never store share amounts in database (they're derived)
- Never use transaction tallies for shares

### Example

**Scenario (My Client):**
- Old Balance = ₹100
- Current Balance = ₹10
- My Share % = 10%

**Calculation:**
- net_profit = ₹10 - ₹100 = -₹90
- abs_net_profit = ₹90
- **My Share Amount = ₹90 × 10% = ₹9**
- **Company Share Amount = ₹0**
- **Combined Share Amount = ₹9**

**Scenario (Company Client):**
- Old Balance = ₹100
- Current Balance = ₹10
- My Share % = 1%
- Company Share % = 9%

**Calculation:**
- net_profit = ₹10 - ₹100 = -₹90
- abs_net_profit = ₹90
- **My Share Amount = ₹90 × 1% = ₹0.9**
- **Company Share Amount = ₹90 × 9% = ₹8.1**
- **Combined Share Amount = ₹0.9 + ₹8.1 = ₹9**

---

## Share Percentages

### My Share Percentage

**Definition:** Your share of profits/losses (as a percentage).

**Source:** Stored in `ClientExchange.my_share_pct` field.

**For My Clients:**
- Typically ranges from 5% to 30%
- This is your full share (no company split)

**For Company Clients:**
- Typically 1% (your cut from the company's 10% share)
- The remaining 9% goes to the company

### Company Share Percentage

**Definition:** Company's share of profits/losses (as a percentage).

**Source:** Stored in `ClientExchange.company_share_pct` field.

**For My Clients:**
- Always 0% (not applicable)

**For Company Clients:**
- Typically 9% (company's portion of the 10% share)
- Combined with your 1% = 10% total share

### Combined Share Percentage

**Definition:** Total share percentage (My Share % + Company Share %).

**Formula:**
```
Combined Share % = my_share_pct + company_share_pct
```

**For My Clients:**
- Combined Share % = My Share % (company_share_pct = 0)

**For Company Clients:**
- Combined Share % = 1% + 9% = 10% (typically)

### Important Rules

✅ **DO:**
- Always fetch percentages from `ClientExchange` model
- Use `my_share_pct` and `company_share_pct` fields
- Calculate combined percentage by addition

❌ **DON'T:**
- Never hardcode percentages
- Never calculate percentages from transaction amounts
- Never assume percentages are the same for all clients

---

## Pending Amount Calculation

### Definition

**Pending Amount** = The remaining amount that needs to be paid (either by client to you, or by you to client).

### Key Principle

**Pending is STATEFUL** - It depends on settlements made. It's calculated as: Share Amount - Settlements.

### Formula

```
# Step 1: Calculate Share Amount (stateless, from Net Profit)
share_amount = abs(net_profit) × share_pct / 100

# Step 2: Get settlements made
IF net_profit < 0 (loss case):
    settlements = SUM of SETTLEMENT transactions where client paid you
    (your_share_amount > 0)
ELSE IF net_profit > 0 (profit case):
    settlements = SUM of SETTLEMENT transactions where you paid client
    (client_share_amount > 0 AND your_share_amount = 0)

# Step 3: Calculate Pending (stateful)
pending = share_amount - settlements

# Ensure pending is never negative
pending = max(0, pending)
```

### For Loss Case (Client Owes You)

**My Share Pending:**
```
my_share_pending = my_share_amount - client_payments_to_you
```

**Company Share Pending:**
```
company_share_pending = company_share_amount - client_payments_to_company
```

**Combined Share Pending:**
```
combined_share_pending = combined_share_amount - total_client_payments
```

### For Profit Case (You Owe Client)

**My Share Pending:**
```
my_share_pending = my_share_amount - your_payments_to_client
```

**Company Share Pending:**
```
company_share_pending = company_share_amount - your_payments_to_client
```

**Combined Share Pending:**
```
combined_share_pending = combined_share_amount - total_your_payments
```

### Important Rules

✅ **DO:**
- Always subtract settlements from share amounts
- Ensure pending is never negative (use max(0, pending))
- Track settlements separately for My Share and Company Share

❌ **DON'T:**
- Never accumulate pending from previous calculations
- Never ignore settlements when calculating pending
- Never mix loss and profit settlements

### Example

**Scenario (Loss Case):**
- Old Balance = ₹100
- Current Balance = ₹10
- My Share % = 10%
- Client paid ₹3 (settlement)

**Calculation:**
- net_profit = ₹10 - ₹100 = -₹90
- my_share_amount = ₹90 × 10% = ₹9
- settlements = ₹3
- **My Share Pending = ₹9 - ₹3 = ₹6**

---

## Examples

### Example 1: My Client - Simple Loss

**Transactions:**
- FUNDING: ₹100
- BALANCE_RECORD: ₹10
- My Share %: 10%

**Calculations:**
1. **Old Balance:** No settlement → ₹100 (sum of funding)
2. **Current Balance:** ₹10 (latest balance record)
3. **Net Profit:** ₹10 - ₹100 = -₹90
4. **Total Loss:** ₹90
5. **My Share Amount:** ₹90 × 10% = ₹9
6. **Company Share Amount:** ₹0 (not applicable)
7. **Combined Share Amount:** ₹9
8. **Pending:** ₹9 - ₹0 = ₹9 (no settlements)

---

### Example 2: Company Client - Loss with Settlement

**Transactions:**
- FUNDING: ₹100
- BALANCE_RECORD: ₹10
- SETTLEMENT: ₹9 (client paid)
- My Share %: 1%
- Company Share %: 9%

**Calculations:**
1. **Old Balance:** Settlement exists → Balance at settlement (₹10) + Funding after (₹0) = ₹10
2. **Current Balance:** ₹10 (latest balance record)
3. **Net Profit:** ₹10 - ₹10 = ₹0
4. **Total Loss:** ₹0 (settlement closed the loss)
5. **My Share Amount:** ₹0 × 1% = ₹0
6. **Company Share Amount:** ₹0 × 9% = ₹0
7. **Combined Share Amount:** ₹0
8. **Pending:** ₹0 (fully settled)

---

### Example 3: My Client - Profit Case

**Transactions:**
- FUNDING: ₹100
- BALANCE_RECORD: ₹200
- My Share %: 10%

**Calculations:**
1. **Old Balance:** No settlement → ₹100
2. **Current Balance:** ₹200
3. **Net Profit:** ₹200 - ₹100 = ₹100
4. **Total Profit:** ₹100
5. **My Share Amount:** ₹100 × 10% = ₹10
6. **Pending:** ₹10 (you owe client ₹10)

---

### Example 4: Company Client - Partial Settlement

**Transactions:**
- FUNDING: ₹100
- BALANCE_RECORD: ₹40
- SETTLEMENT: ₹3 (client paid)
- My Share %: 1%
- Company Share %: 9%

**Calculations:**
1. **Old Balance:** Settlement exists → Balance at settlement (₹40) + Funding after (₹0) = ₹40
2. **Current Balance:** ₹40
3. **Net Profit:** ₹40 - ₹40 = ₹0
4. **Total Loss:** ₹0 (settlement closed the loss)
5. **My Share Amount:** ₹0 × 1% = ₹0
6. **Company Share Amount:** ₹0 × 9% = ₹0
7. **Combined Share Amount:** ₹0
8. **Pending:** ₹0

**Note:** The settlement of ₹3 closed ₹30 of loss (₹3 / 10% = ₹30), which moved Old Balance from ₹100 to ₹40.

---

## Business Rules

### Rule 1: Settlement Resets Old Balance

When a settlement occurs, Old Balance must move forward to the balance at settlement date. This prevents double-counting of losses.

**Formula:**
```
Old Balance (after settlement) = balance_at_settlement + funding_after_settlement
```

### Rule 2: Net Profit is Single Source of Truth

All share calculations must come from Net Profit. Never use transaction tallies or accumulated values.

**Formula:**
```
net_profit = current_balance - old_balance
share_amount = abs(net_profit) × share_pct / 100
```

### Rule 3: Shares are Stateless

Shares are recalculated fresh every time from Net Profit. They do not store or accumulate state.

### Rule 4: Pending is Stateful

Pending depends on settlements made. It's calculated as Share Amount minus Settlements.

**Formula:**
```
pending = share_amount - settlements_made
```

### Rule 5: Break-Even Rule

If Old Balance equals Current Balance, there is no profit, no loss, and no pending.

**Formula:**
```
IF old_balance == current_balance:
    net_profit = 0
    share_amount = 0
    pending = 0
```

### Rule 6: Unified Logic for All Clients

Both My Clients and Company Clients use the same calculation logic:
- Same Old Balance calculation (settlement-aware)
- Same Net Profit calculation
- Same Share calculation (from Net Profit)
- Only difference: Company Clients have two percentages (1% + 9%)

### Rule 7: Never Override Old Balance

Once Old Balance is calculated using settlement-aware logic, never override it with `sum(all_funding)`. This breaks the settlement reset mechanism.

---

## Technical Implementation

### Key Functions

1. **`get_old_balance_after_settlement(client_exchange, as_of_date=None)`**
   - Calculates Old Balance using settlement-aware logic
   - Returns: Decimal (Old Balance amount)

2. **`get_exchange_balance(client_exchange, as_of_date=None, use_cache=True)`**
   - Gets Current Balance from latest BALANCE_RECORD
   - Returns: Decimal (Current Balance amount)

3. **`calculate_client_profit_loss(client_exchange)`**
   - Calculates profit/loss data
   - Returns: dict with exchange_balance and client_profit_loss

### Data Sources

- **Old Balance:** `Transaction` model (TYPE_FUNDING, TYPE_SETTLEMENT)
- **Current Balance:** `ClientDailyBalance` or `Transaction` model (TYPE_BALANCE_RECORD)
- **Share Percentages:** `ClientExchange` model (my_share_pct, company_share_pct)
- **Settlements:** `Transaction` model (TYPE_SETTLEMENT)

---

## Summary

The pending payments system uses a unified, settlement-aware approach:

1. **Old Balance** = balance_at_settlement + funding_after (if settlement exists) OR sum(all_funding) (if no settlement)
2. **Current Balance** = latest BALANCE_RECORD
3. **Net Profit** = current_balance - old_balance (single source of truth)
4. **Shares** = abs(net_profit) × share_pct (stateless, recalculated fresh)
5. **Pending** = share_amount - settlements (stateful, depends on payments made)

This ensures accuracy, prevents double-counting, and maintains consistency across all client types.

---

**Last Updated:** 2025-12-28
**Version:** 1.0


