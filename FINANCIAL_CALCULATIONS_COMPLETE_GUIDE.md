# Financial Calculations - Complete Guide

## 📋 Table of Contents

1. [Overview](#overview)
2. [Core Concepts](#core-concepts)
3. [Current Balance (CB) Calculation](#current-balance-cb-calculation)
4. [Capital (Old Balance) Calculation](#capital-old-balance-calculation)
5. [Trading Loss Calculation](#trading-loss-calculation)
6. [Share Calculations](#share-calculations)
7. [Pending Payments Calculation](#pending-payments-calculation)
8. [Loss Percentage Calculation](#loss-percentage-calculation)
9. [Complete Example Walkthrough](#complete-example-walkthrough)
10. [Data Flow Diagrams](#data-flow-diagrams)
11. [Code References](#code-references)

---

## Overview

This document explains how the Transaction Hub system calculates all financial values:
- **Current Balance (CB)**: The actual exchange balance
- **Capital (Old Balance)**: The accounting baseline
- **Trading Loss**: The frozen loss amount
- **My Share**: Your portion of the loss/profit
- **Company Share**: Company's portion of the loss/profit
- **Pending Payments**: What the client owes you
- **Loss Percentage**: The share percentage applied to losses

---

## Core Concepts

### 1. Two Spaces: Capital vs Share

**Capital Space** (Old Balance, Loss):
- Uses **ROUND_HALF_UP** rounding (2 decimal places)
- Represents the full capital base
- Example: ₹1000.00, ₹990.00

**Share Space** (Pending, My Share, Company Share):
- Uses **ROUND_DOWN** rounding (1 decimal place)
- Represents the share portion of capital
- Example: ₹99.0, ₹9.9

### 2. Frozen vs Derived Values

**Frozen Values** (Immutable):
- `LossSnapshot.loss_amount`: Original loss (never changes)
- `LossSnapshot.balance_record.remaining_balance`: CB at loss creation (frozen)
- `LossSnapshot.my_share_pct`: Your share % at loss creation (frozen)
- `LossSnapshot.company_share_pct`: Company share % at loss creation (frozen)

**Derived Values** (Calculated):
- `remaining_loss`: Original loss - settlements (calculated from DB)
- `current_balance`: Frozen balance + funding after loss
- `capital`: CB + remaining_loss
- `pending`: (remaining_loss × total_share_pct) / 100

### 3. Data Sources

**Source of Truth**:
- **Ledger**: All transactions (FUNDING, LOSS, SETTLEMENT, etc.)
- **LossSnapshot**: Frozen loss state at creation time
- **ClientDailyBalance**: Exchange balance records

**Performance Cache** (Not Source of Truth):
- `ClientExchange.cached_current_balance`: Cached CB
- `ClientExchange.cached_old_balance`: Cached Capital

---

## Current Balance (CB) Calculation

### Definition

**Current Balance (CB)** is the actual exchange balance at any point in time. It includes:
1. Base balance (from balance records)
2. Funding transactions
3. Adjustments for extra amounts

### Formula

```
CB = Base Balance + Extra Adjustment + Funding After Loss (if loss exists)
```

### When Loss Exists (Active LossSnapshot)

**CRITICAL RULE**: When an active `LossSnapshot` exists, CB is calculated as:

```
CB = Frozen Balance (at loss creation) + Funding After Loss
```

**Code Implementation**:
```python
def get_exchange_balance(client_exchange, as_of_date=None, use_cache=True):
    # Check for active loss snapshot
    active_loss = LossSnapshot.objects.filter(
        client_exchange=client_exchange,
        is_settled=False
    ).first()
    
    if active_loss:
        # ✅ CORRECT: CB = Frozen Balance + Funding After Loss
        frozen_balance = active_loss.balance_record.remaining_balance
        
        # Get funding transactions AFTER loss creation date
        funding_after_loss = Transaction.objects.filter(
            client_exchange=client_exchange,
            transaction_type=Transaction.TYPE_FUNDING,
            date__gt=active_loss.balance_record.date
        ).aggregate(total=Sum("amount"))["total"] or Decimal(0)
        
        return frozen_balance + funding_after_loss
    
    # No active loss - use latest balance record
    latest_balance_record = ClientDailyBalance.objects.filter(
        client_exchange=client_exchange
    ).exclude(
        note__icontains="Settlement adjustment"
    ).order_by("-date", "-created_at").first()
    
    if latest_balance_record:
        return latest_balance_record.remaining_balance + (
            latest_balance_record.extra_adjustment or Decimal(0)
        )
    
    # Fallback: sum of all funding
    total_funding = Transaction.objects.filter(
        client_exchange=client_exchange,
        transaction_type=Transaction.TYPE_FUNDING
    ).aggregate(total=Sum("amount"))["total"] or Decimal(0)
    
    return total_funding
```

### Example

**Scenario**:
- Dec 1: Funding ₹1000
- Dec 2: Balance Record ₹10 (loss detected, LossSnapshot created)
- Dec 3: Funding ₹100

**Calculation**:
```
Frozen Balance = ₹10 (from LossSnapshot.balance_record)
Funding After Loss = ₹100 (Dec 3 funding)
CB = ₹10 + ₹100 = ₹110
```

### Key Rules

1. **Funding After Loss MUST be included**: Even if loss exists, funding increases CB
2. **Frozen Balance is Base**: CB starts from the balance at loss creation
3. **Never Recalculate**: CB is never recalculated from transactions when loss exists

---

## Capital (Old Balance) Calculation

### Definition

**Capital (Old Balance)** is the accounting baseline used for profit/loss calculations. It represents the capital base that the client started with.

### Formula

**When Loss Exists**:
```
CAPITAL = CB + LOSS
```

**When No Loss**:
```
CAPITAL = SUM(FUNDING) - SUM(CAPITAL_CLOSED from SETTLEMENTS)
```

### Code Implementation

```python
def get_old_balance_after_settlement(client_exchange, as_of_date=None):
    """
    Calculate Capital (Old Balance) from transactions.
    
    Rules:
    1. If no settlements: CAPITAL = SUM(FUNDING)
    2. If settlements exist: CAPITAL = CB + LOSS (derived)
    """
    # Get active loss snapshot
    active_loss = LossSnapshot.objects.filter(
        client_exchange=client_exchange,
        is_settled=False
    ).first()
    
    if active_loss:
        # ✅ CORRECT: CAPITAL = CB + LOSS
        current_balance = get_exchange_balance(client_exchange)
        remaining_loss = active_loss.get_remaining_loss()
        capital = current_balance + remaining_loss
        return round_capital(capital)  # Capital-space rounding
    
    # No active loss - calculate from funding and settlements
    total_funding = Transaction.objects.filter(
        client_exchange=client_exchange,
        transaction_type=Transaction.TYPE_FUNDING
    ).aggregate(total=Sum("amount"))["total"] or Decimal(0)
    
    # Subtract capital closed from settlements
    total_capital_closed = Transaction.objects.filter(
        client_exchange=client_exchange,
        transaction_type=Transaction.TYPE_SETTLEMENT
    ).aggregate(total=Sum("capital_closed"))["total"] or Decimal(0)
    
    capital = total_funding - total_capital_closed
    return round_capital(capital)  # Capital-space rounding
```

### Example

**Scenario**:
- Dec 1: Funding ₹1000
- Dec 2: Balance Record ₹10 (loss detected)
- LossSnapshot: loss_amount = ₹990, frozen_balance = ₹10
- Dec 3: Funding ₹100

**Calculation**:
```
CB = ₹10 (frozen) + ₹100 (funding) = ₹110
LOSS = ₹990 (frozen, from LossSnapshot)
CAPITAL = ₹110 + ₹990 = ₹1100
```

### Key Rules

1. **CAPITAL is Derived**: Never set manually, always calculated
2. **When Loss Exists**: CAPITAL = CB + LOSS
3. **When No Loss**: CAPITAL = SUM(FUNDING) - SUM(CAPITAL_CLOSED)
4. **Settlements Reduce Capital**: Each settlement closes capital

---

## Trading Loss Calculation

### Definition

**Trading Loss** is the amount by which the capital base exceeds the current balance. It represents the client's trading loss.

### Formula

**CRITICAL RULE**: Loss is **FROZEN** in `LossSnapshot`, not recalculated.

```
LOSS = LossSnapshot.loss_amount (FROZEN, immutable)
Remaining Loss = Original Loss - SUM(Capital Closed from Settlements)
```

### Code Implementation

```python
# ✅ CORRECT: Get loss from LossSnapshot (frozen)
active_loss_snapshot = LossSnapshot.objects.filter(
    client_exchange=client_exchange,
    is_settled=False
).first()

if active_loss_snapshot:
    # ✅ CORRECT: Use frozen loss_amount (immutable)
    original_loss = Decimal(str(active_loss_snapshot.loss_amount))  # FROZEN
    
    # ✅ CORRECT: Calculate remaining_loss from settlements (derived)
    remaining_loss = active_loss_snapshot.get_remaining_loss()
    remaining_loss = Decimal(str(remaining_loss))  # Ensure Decimal
    
    # Use remaining_loss for calculations
    total_loss = remaining_loss
else:
    # No active loss - calculate from OB and CB (for display only)
    total_loss = max(old_balance - current_balance, 0)
```

### LossSnapshot.get_remaining_loss() Method

```python
def get_remaining_loss(self):
    """
    Calculate remaining loss from settlements.
    
    Formula: Original Loss - SUM(Capital Closed from Settlements)
    """
    # Get all SETTLEMENT transactions for this loss
    settlements = Transaction.objects.filter(
        client_exchange=self.client_exchange,
        transaction_type=Transaction.TYPE_SETTLEMENT,
        date__gte=self.balance_record.date,  # ✅ CRITICAL: Only settlements after loss creation
        date__isnull=False  # ✅ CRITICAL: Must have valid date
    ).aggregate(total=Sum("capital_closed"))["total"] or Decimal(0)
    
    # Remaining loss = original - settled
    remaining = self.loss_amount - settlements
    
    # Guard against negative (should never happen)
    if remaining < 0:
        remaining = Decimal(0)
    
    return round_capital(remaining)  # Capital-space rounding
```

### Example

**Scenario**:
- Dec 2: Loss detected, LossSnapshot created
  - `loss_amount` = ₹990 (FROZEN)
  - `balance_record.remaining_balance` = ₹10 (FROZEN)
- Dec 3: Settlement payment ₹10
  - `capital_closed` = ₹100 (calculated: 10 × 100 / 10%)

**Calculation**:
```
Original Loss = ₹990 (FROZEN)
Capital Closed = ₹100 (from settlement)
Remaining Loss = ₹990 - ₹100 = ₹890
```

### Key Rules

1. **Loss is FROZEN**: `LossSnapshot.loss_amount` never changes
2. **Never Recalculate**: Loss is NOT `CAPITAL - CB`
3. **Remaining Loss is Derived**: Calculated from original loss minus settlements
4. **Settlements Reduce Loss**: Each settlement closes capital, reducing remaining loss

---

## Share Calculations

### Definition

**Shares** represent the proportional distribution of loss/profit between you and the company.

### Share Percentages

**For Company Clients**:
- **My Share %**: 1% (you get 1% of loss/profit)
- **Company Share %**: 9% (company gets 9% of loss/profit)
- **Total Share %**: 10% (1% + 9%)

**For My Clients**:
- **My Share %**: 10% (you get full 10%)
- **Company Share %**: 0% (no company share)
- **Total Share %**: 10%

### Formula

**For Loss**:
```
My Share = (Remaining Loss × My Share %) / 100
Company Share = (Remaining Loss × Company Share %) / 100
Combined Share = My Share + Company Share = (Remaining Loss × Total Share %) / 100
```

**For Profit**:
```
My Share = (Profit × My Share %) / 100
Company Share = (Profit × Company Share %) / 100
Combined Share = My Share + Company Share = (Profit × Total Share %) / 100
```

### Code Implementation

```python
from core.utils.money import calculate_share_split, round_share

# ✅ CORRECT: Use calculate_share_split to prevent rounding leakage
if client_exchange.client.is_company_client:
    my_share_from_loss, company_share_from_loss, combined_share_from_loss = calculate_share_split(
        loss=remaining_loss,
        my_pct=Decimal(1),  # 1% for company clients
        company_pct=Decimal(9),  # 9% for company clients
    )
    
    my_share = round_share(my_share_from_loss)  # Round DOWN (share-space)
    company_share = round_share(company_share_from_loss)  # Round DOWN (share-space)
    combined_share = round_share(combined_share_from_loss)  # Round DOWN (share-space)
else:
    # My clients: full share
    total_share_pct = my_share_pct  # Usually 10%
    combined_share_raw = (remaining_loss * total_share_pct) / Decimal(100)
    combined_share = round_share(combined_share_raw)  # Round DOWN (share-space)
    my_share = combined_share
    company_share = Decimal(0)
```

### calculate_share_split() Function

```python
def calculate_share_split(
    loss: Decimal,
    my_pct: Decimal,
    company_pct: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    """
    Split loss/profit into shares without rounding leakage.
    
    ✅ CRITICAL: Round ONE side, give remainder to other (NO rounding on remainder)
    """
    # Convert to Decimal if needed
    if not isinstance(loss, Decimal):
        loss = Decimal(str(loss))
    if not isinstance(my_pct, Decimal):
        my_pct = Decimal(str(my_pct))
    if not isinstance(company_pct, Decimal):
        company_pct = Decimal(str(company_pct))
    
    total_pct = my_pct + company_pct
    if total_pct <= 0:
        raise ValueError("Invalid share percentage: total_pct must be > 0")
    
    # Calculate raw amounts
    raw_total = (loss * total_pct) / Decimal("100")
    raw_my = (loss * my_pct) / Decimal("100")
    
    # Round total and my share (share-space: ROUND_DOWN)
    total_payable = round_share(raw_total)
    my_amount = round_share(raw_my)
    
    # ✅ CRITICAL: Give remainder to company (NO rounding) to prevent leakage
    company_amount = total_payable - my_amount
    
    return my_amount, company_amount, total_payable
```

### Example

**Scenario**:
- Remaining Loss: ₹990
- My Share %: 1%
- Company Share %: 9%
- Total Share %: 10%

**Calculation**:
```
Raw Total = (990 × 10) / 100 = ₹99.0
Raw My = (990 × 1) / 100 = ₹9.9

Total Payable = round_down(99.0) = ₹99.0
My Share = round_down(9.9) = ₹9.9
Company Share = ₹99.0 - ₹9.9 = ₹89.1 (NO rounding, remainder)
```

### Key Rules

1. **Share-Space Rounding**: Always ROUND_DOWN (1 decimal place)
2. **No Rounding Leakage**: Round one side, give remainder to other
3. **Frozen Percentages**: Share percentages are frozen at loss creation
4. **Total Share = My + Company**: Always true (no rounding errors)

---

## Pending Payments Calculation

### Definition

**Pending Payments** is the amount the client owes you. It represents the share portion of the remaining loss.

### Formula

**CRITICAL RULE**: Pending is **ALWAYS derived from remaining loss**, never from payment amounts.

```
Pending = (Remaining Loss × Total Share %) / 100
```

### Code Implementation

```python
# ✅ CORRECT: Derive pending from remaining_loss
if remaining_loss >= AUTO_CLOSE_THRESHOLD:
    if client_exchange.client.is_company_client:
        # Use calculate_share_split for company clients
        my_share_from_loss, company_share_from_loss, client_payable = calculate_share_split(
            loss=remaining_loss,
            my_pct=my_share_pct_effective,
            company_pct=company_share_pct,
        )
        pending_new = client_payable  # Combined share
    else:
        # My clients: simple calculation
        client_payable_raw = (remaining_loss * total_pct) / Decimal(100)
        client_payable = round_share(client_payable_raw)  # Round DOWN
        pending_new = client_payable
else:
    # Fully settled
    pending_new = Decimal(0)
```

### Example

**Scenario**:
- Remaining Loss: ₹990
- Total Share %: 10%

**Calculation**:
```
Pending Raw = (990 × 10) / 100 = ₹99.0
Pending = round_down(99.0) = ₹99.0
```

**After Partial Payment**:
- Payment: ₹10
- Capital Closed: ₹100 (10 × 100 / 10%)
- Remaining Loss: ₹990 - ₹100 = ₹890

**New Pending**:
```
Pending Raw = (890 × 10) / 100 = ₹89.0
Pending = round_down(89.0) = ₹89.0
```

### Key Rules

1. **Pending is Derived**: Always from remaining_loss, never from payment
2. **Never Subtract Payment**: Pending ≠ Old Pending - Payment
3. **Share-Space Rounding**: Always ROUND_DOWN (1 decimal place)
4. **Auto-Close Threshold**: If remaining_loss ≤ ₹0.01, pending = ₹0

---

## Loss Percentage Calculation

### Definition

**Loss Percentage** is the share percentage applied to losses. It determines how much of the loss is payable.

### Share Percentage Structure

**For Company Clients**:
```
My Share % = 1%
Company Share % = 9%
Total Share % = 10% (1% + 9%)
```

**For My Clients**:
```
My Share % = 10%
Company Share % = 0%
Total Share % = 10%
```

### Code Implementation

```python
# Determine share percentages
my_share_pct = client_exchange.my_share_pct or Decimal(0)

if client_exchange.client.is_company_client:
    # ✅ CORRECT: For company clients, ALWAYS use total_share_pct = 10
    total_share_pct = Decimal(10)  # ALWAYS 10 for company clients
    my_share_pct_effective = Decimal(1)  # you get 1%
    company_share_pct = Decimal(9)  # company gets 9%
else:
    # My clients: use my_share_pct
    total_share_pct = my_share_pct  # usually 10
    my_share_pct_effective = my_share_pct  # you get full share
    company_share_pct = Decimal(0)
```

### Display in UI

**Template Code**:
```django
<td class="share-cell combined-share-pct-cell" 
    data-total-share-pct="{{ item.total_share_pct|default:10 }}">
    {% if item.total_share_pct is not None and item.total_share_pct > 0 %}
        <span>{{ item.total_share_pct }}%</span>
    {% endif %}
</td>
```

### Example

**Company Client**:
- My Share %: 1%
- Company Share %: 9%
- **Total Share %: 10%** (displayed in UI)

**My Client**:
- My Share %: 10%
- Company Share %: 0%
- **Total Share %: 10%** (displayed in UI)

### Key Rules

1. **Total Share % = My % + Company %**: Always true
2. **Company Clients**: Always 10% total (1% + 9%)
3. **My Clients**: Usually 10% total (10% + 0%)
4. **Frozen at Loss Creation**: Percentages are frozen in LossSnapshot

---

## Complete Example Walkthrough

### Scenario Setup

**Transactions**:
- Dec 1: Funding ₹1000
- Dec 2: Balance Record ₹10 (loss detected)
- Dec 3: Funding ₹100
- Dec 4: Settlement payment ₹10

**LossSnapshot Created (Dec 2)**:
- `loss_amount` = ₹990 (FROZEN)
- `balance_record.remaining_balance` = ₹10 (FROZEN)
- `my_share_pct` = 1% (FROZEN, for company client)
- `company_share_pct` = 9% (FROZEN, for company client)

### Step-by-Step Calculations

#### Step 1: Calculate Current Balance (CB)

```
Frozen Balance = ₹10 (from LossSnapshot.balance_record)
Funding After Loss = ₹100 (Dec 3 funding, after loss creation)
CB = ₹10 + ₹100 = ₹110
```

#### Step 2: Calculate Remaining Loss

```
Original Loss = ₹990 (FROZEN, from LossSnapshot.loss_amount)
Capital Closed = ₹100 (from Dec 4 settlement: 10 × 100 / 10%)
Remaining Loss = ₹990 - ₹100 = ₹890
```

#### Step 3: Calculate Capital (Old Balance)

```
CAPITAL = CB + LOSS
CAPITAL = ₹110 + ₹890 = ₹1000
```

#### Step 4: Calculate Share Percentages

```
My Share % = 1%
Company Share % = 9%
Total Share % = 10% (1% + 9%)
```

#### Step 5: Calculate Shares

```
Raw Total = (890 × 10) / 100 = ₹89.0
Raw My = (890 × 1) / 100 = ₹8.9

Total Payable = round_down(89.0) = ₹89.0
My Share = round_down(8.9) = ₹8.9
Company Share = ₹89.0 - ₹8.9 = ₹80.1 (remainder, no rounding)
```

#### Step 6: Calculate Pending Payment

```
Pending = Total Payable = ₹89.0
```

### Final State

| Field | Value | Source |
|-------|-------|--------|
| Current Balance (CB) | ₹110 | Frozen ₹10 + Funding ₹100 |
| Trading Loss (Capital) | ₹890 | Original ₹990 - Settled ₹100 |
| Capital (Old Balance) | ₹1000 | CB ₹110 + Loss ₹890 |
| My Share | ₹8.9 | (₹890 × 1%) / 100, rounded DOWN |
| Company Share | ₹80.1 | Total ₹89.0 - My ₹8.9 |
| Combined Share | ₹89.0 | My ₹8.9 + Company ₹80.1 |
| Client Payable (Pending) | ₹89.0 | (₹890 × 10%) / 100 |
| Total Share % | 10% | My 1% + Company 9% |

---

## Data Flow Diagrams

### Current Balance Calculation Flow

```
┌─────────────────────────────────────────────────────────┐
│              get_exchange_balance()                      │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │ Active LossSnapshot?  │
            └───────────────────────┘
                        │
            ┌───────────┴───────────┐
            │                       │
            YES                    NO
            │                       │
            ▼                       ▼
    ┌───────────────┐      ┌───────────────┐
    │ Frozen Balance │      │ Latest Balance│
    │   (₹10)        │      │     Record    │
    └───────────────┘      └───────────────┘
            │                       │
            ▼                       │
    ┌───────────────┐              │
    │ Funding After │              │
    │ Loss (₹100)   │              │
    └───────────────┘              │
            │                       │
            └───────────┬───────────┘
                        │
                        ▼
                ┌───────────────┐
                │   CB = ₹110   │
                └───────────────┘
```

### Capital Calculation Flow

```
┌─────────────────────────────────────────────────────────┐
│        get_old_balance_after_settlement()               │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │ Active LossSnapshot?  │
            └───────────────────────┘
                        │
            ┌───────────┴───────────┐
            │                       │
            YES                    NO
            │                       │
            ▼                       ▼
    ┌───────────────┐      ┌───────────────┐
    │ Get CB        │      │ SUM(FUNDING)  │
    │ Get Remaining │      │ - SUM(CAPITAL │
    │ Loss          │      │   CLOSED)     │
    └───────────────┘      └───────────────┘
            │                       │
            ▼                       │
    ┌───────────────┐              │
    │ CAPITAL =     │              │
    │ CB + LOSS     │              │
    └───────────────┘              │
            │                       │
            └───────────┬───────────┘
                        │
                        ▼
                ┌───────────────┐
                │ CAPITAL =     │
                │ ₹1000         │
                └───────────────┘
```

### Loss Calculation Flow

```
┌─────────────────────────────────────────────────────────┐
│              LossSnapshot.get_remaining_loss()          │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │ Original Loss (FROZEN)│
            │   ₹990                │
            └───────────────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │ Get SETTLEMENT        │
            │ transactions after    │
            │ loss creation date    │
            └───────────────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │ SUM(capital_closed)    │
            │   ₹100                 │
            └───────────────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │ Remaining Loss =       │
            │ Original - Settled     │
            │ ₹990 - ₹100 = ₹890     │
            └───────────────────────┘
```

### Pending Payment Calculation Flow

```
┌─────────────────────────────────────────────────────────┐
│              Calculate Pending Payment                 │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │ Get Remaining Loss    │
            │   ₹890                │
            └───────────────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │ Get Total Share %     │
            │   10%                 │
            └───────────────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │ Pending Raw =         │
            │ (890 × 10) / 100      │
            │ = ₹89.0               │
            └───────────────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │ Pending =             │
            │ round_down(89.0)      │
            │ = ₹89.0               │
            └───────────────────────┘
```

---

## Code References

### Key Functions

1. **`get_exchange_balance()`** (`core/views.py:19`)
   - Calculates Current Balance (CB)
   - Handles frozen balance + funding after loss

2. **`get_old_balance_after_settlement()`** (`core/views.py:82`)
   - Calculates Capital (Old Balance)
   - Handles settlements and funding

3. **`LossSnapshot.get_remaining_loss()`** (`core/models.py`)
   - Calculates remaining loss from settlements
   - Uses frozen original loss

4. **`calculate_share_split()`** (`core/utils/money.py`)
   - Splits loss/profit into shares
   - Prevents rounding leakage

5. **`pending_summary()`** (`core/views.py:2552`)
   - Main view for pending payments
   - Uses all calculation functions

### Key Models

1. **`LossSnapshot`** (`core/models.py`)
   - Stores frozen loss state
   - `loss_amount`: Original loss (immutable)
   - `balance_record`: Frozen balance at loss creation
   - `my_share_pct`, `company_share_pct`: Frozen percentages

2. **`Transaction`** (`core/models.py`)
   - All financial transactions
   - `TYPE_FUNDING`: Adds to balance
   - `TYPE_SETTLEMENT`: Closes capital
   - `capital_closed`: Amount of capital closed

3. **`ClientExchange`** (`core/models.py`)
   - Cached values (performance only)
   - `cached_current_balance`: Cached CB
   - `cached_old_balance`: Cached Capital

---

## Summary

### Key Formulas

1. **Current Balance (CB)**:
   ```
   CB = Frozen Balance + Funding After Loss (if loss exists)
   ```

2. **Capital (Old Balance)**:
   ```
   CAPITAL = CB + LOSS (if loss exists)
   CAPITAL = SUM(FUNDING) - SUM(CAPITAL_CLOSED) (if no loss)
   ```

3. **Trading Loss**:
   ```
   LOSS = LossSnapshot.loss_amount (FROZEN)
   Remaining Loss = Original Loss - SUM(Capital Closed)
   ```

4. **Shares**:
   ```
   My Share = (Loss × My Share %) / 100
   Company Share = (Loss × Company Share %) / 100
   Combined Share = (Loss × Total Share %) / 100
   ```

5. **Pending Payment**:
   ```
   Pending = (Remaining Loss × Total Share %) / 100
   ```

### Critical Rules

1. **Loss is FROZEN**: Never recalculated from CAPITAL - CB
2. **CB includes funding after loss**: Frozen balance + funding
3. **Pending is derived**: Always from remaining_loss, never from payment
4. **Share-space rounding**: Always ROUND_DOWN (1 decimal)
5. **Capital-space rounding**: Always ROUND_HALF_UP (2 decimals)
6. **No rounding leakage**: Round one side, give remainder to other

---

## End of Document

This document covers all financial calculations in the Transaction Hub system. All formulas, code references, and examples are provided for complete understanding.

