# PENDING PAYMENTS - FORMULAS, LOGIC & IMPLEMENTATION

**Version:** 1.0  
**Last Updated:** 2025-01-XX  
**Status:** Production Ready

---

## TABLE OF CONTENTS

1. [Overview](#1-overview)
2. [Core Concepts](#2-core-concepts)
3. [PIN-TO-PIN Formula](#3-pin-to-pin-formula)
4. [Net Tally Calculation](#4-net-tally-calculation)
5. [Rounding Rules](#5-rounding-rules)
6. [Implementation Flow](#6-implementation-flow)
7. [Code Structure](#7-code-structure)
8. [Examples](#8-examples)

---

## 1. OVERVIEW

The Pending Payments system calculates what clients owe you and what you owe clients based on a **ledger-based approach** that tracks all transactions (losses, profits, and settlements).

### Key Principles

- ✅ **Single Source of Truth**: Pending amounts come ONLY from transaction ledger calculations
- ✅ **No Stored Pending**: Pending is always calculated dynamically, never stored
- ✅ **Two Separate Sections**: 
  - **Clients Owe You** (net_share > 0)
  - **You Owe Clients** (net_share < 0)
- ✅ **Share-Space Rounding**: Always rounds DOWN to prevent over-collection

---

## 2. CORE CONCEPTS

### 2.1 Two Spaces

The system operates in **two distinct spaces**:

#### **Capital-Space** (What Happened)
- **Funding**: Total money given to client = `Σ(FUNDING.amount)`
- **Exchange Balance**: Current balance in exchange (from latest balance record)
- **Client PnL**: `Exchange Balance - Funding`
- **Purpose**: Shows WHAT happened in trading

#### **Share-Space** (What Is Still Payable)
- **Net Share**: Amount still owed (from ledger calculations)
- **Purpose**: Shows WHAT is still payable after settlements
- **Source**: Calculated from transactions ONLY

### 2.2 Golden Rule

> **Capital-space tells WHAT happened. Share-space tells WHAT is still payable. Ledger settles share-space only.**

---

## 3. PIN-TO-PIN FORMULA

The pending payments system uses a **PIN-TO-PIN** formula that ensures accuracy and prevents drift.

### 3.1 Formula Steps

For each `ClientExchange`:

```python
# Step 1: Get the two stored values
funding = client_exchange.cached_total_funding or Decimal(0)
exchange_balance = client_exchange.cached_current_balance or Decimal(0)

# Step 2: Calculate NET (capital-space) - for display only
NET = exchange_balance - funding

# Step 3: Get net_share from ledger (share-space) - ONLY source for pending
net_tallies = calculate_net_tallies_from_transactions(client_exchange)
net_share = net_tallies["net_client_tally"]

# Step 4: Determine section based on net_share (not NET)
if net_share > 0:
    section = "Clients Need To Pay Me"
elif net_share < 0:
    section = "I Need To Pay Clients"
else:
    skip  # Fully settled
```

### 3.2 Critical Rules

- ❌ **NO** `capital_closed`
- ❌ **NO** `old_balance` recalculation
- ❌ **NO** recalculated pending from NET
- ❌ **NO** drift possible
- ✅ Pending comes from **ONE function only**: `calculate_net_tallies_from_transactions()`

---

## 4. NET TALLY CALCULATION

The `calculate_net_tallies_from_transactions()` function is the **single source of truth** for pending amounts.

### 4.1 Function Signature

```python
def calculate_net_tallies_from_transactions(client_exchange, as_of_date=None):
    """
    Calculate NET TALLIES from transactions (not from stored pending amounts).
    
    Returns:
        dict with:
        - net_client_tally: Net amount (positive = client owes you, negative = you owe client)
        - net_company_tally: Net amount (always 0 for my clients)
        - your_earnings: Your earnings from company split (1% of losses + 1% of profits)
    """
```

### 4.2 Calculation Formula

```python
# Get all LOSS transactions
your_share_from_losses = Σ(LOSS.your_share_amount)

# Get all PROFIT transactions
your_share_from_profits = Σ(PROFIT.your_share_amount)

# Get settlements where client paid you (reduces what client owes you)
client_payments = Σ(SETTLEMENT.your_share_amount WHERE client_share_amount=0 AND your_share_amount>0)

# Get settlements where you paid client (reduces what you owe client)
admin_payments_to_client = Σ(SETTLEMENT.client_share_amount WHERE client_share_amount>0 AND your_share_amount=0)

# Calculate NET CLIENT TALLY
net_client_tally_raw = (
    your_share_from_losses 
    - your_share_from_profits 
    - client_payments 
    + admin_payments_to_client
)

# Round DOWN (share-space rounding)
net_client_tally = round_share(net_client_tally_raw)
```

### 4.3 Formula Breakdown

**Net Client Tally** = (Income from Losses) - (Expense from Profits) - (Payments Received) + (Payments Made)

Where:
- **Income from Losses**: Your share amount from all LOSS transactions
- **Expense from Profits**: Your share amount from all PROFIT transactions (negative because you owe)
- **Payments Received**: Settlements where client paid you (reduces what they owe)
- **Payments Made**: Settlements where you paid client (reduces what you owe)

### 4.4 Sign Convention

- **Positive `net_client_tally`**: Client owes you (show in "Clients Owe You" section)
- **Negative `net_client_tally`**: You owe client (show in "You Owe Clients" section)
- **Zero `net_client_tally`**: Fully settled (skip, don't show)

---

## 5. ROUNDING RULES

### 5.1 Share-Space Rounding (ALWAYS ROUND DOWN)

**Function**: `round_share(amount, decimals=1)`

**Rule**: 
- ALWAYS round DOWN
- NEVER round up
- Prevents over-collection from clients

**Examples**:
- `8.55 → 8.5`
- `8.56 → 8.5`
- `8.88 → 8.8`
- `9.00 → 9.0`

**Usage**: All pending amounts, shares, and payable amounts

### 5.2 Capital-Space Rounding (ROUND HALF UP)

**Function**: `round_capital(amount, decimals=2)`

**Rule**:
- Standard accounting rounding (ROUND_HALF_UP)
- Used for ledger values and capital calculations

**Examples**:
- `8.555 → 8.56`
- `8.554 → 8.55`
- `8.555 → 8.56` (rounds up)

**Usage**: Loss amounts, profit amounts, capital calculations

### 5.3 Why Different Rounding?

- **Share-space**: Client-facing amounts must NEVER round up (prevents over-collection)
- **Capital-space**: Internal calculations use standard accounting rules

---

## 6. IMPLEMENTATION FLOW

### 6.1 Pending Summary Function Flow

```python
def pending_summary(request):
    # 1. Setup: Get date ranges, filters, settings
    # 2. Get all active client exchanges
    # 3. For each client_exchange:
    for client_exchange in client_exchanges:
        # 3a. Get cached values (capital-space)
        funding = client_exchange.cached_total_funding or Decimal(0)
        exchange_balance = client_exchange.cached_current_balance or Decimal(0)
        NET = exchange_balance - funding  # For display only
        
        # 3b. Calculate net_share (share-space) - ONLY source for pending
        net_tallies = calculate_net_tallies_from_transactions(client_exchange)
        net_share = net_tallies["net_client_tally"]
        
        # 3c. Route to appropriate section
        if net_share > 0:
            # Add to "Clients Owe You" list
            clients_owe_list.append({...})
        elif net_share < 0:
            # Add to "You Owe Clients" list
            you_owe_list.append({...})
        # else: skip (fully settled)
    
    # 4. Sort lists by absolute net_share (largest first)
    # 5. Calculate totals
    # 6. Render template
```

### 6.2 Transaction Types

The system tracks three main transaction types:

1. **FUNDING**: Money given to client
   - Increases `cached_total_funding`
   - Used for capital-space calculations

2. **LOSS**: Client lost money
   - Creates `LOSS` transaction with `your_share_amount`
   - Increases what client owes you

3. **PROFIT**: Client made money
   - Creates `PROFIT` transaction with `your_share_amount`
   - Increases what you owe client

4. **SETTLEMENT**: Payment recorded
   - **Client pays you**: `SETTLEMENT` with `your_share_amount > 0`, `client_share_amount = 0`
   - **You pay client**: `SETTLEMENT` with `client_share_amount > 0`, `your_share_amount = 0`
   - Reduces pending amounts

---

## 7. CODE STRUCTURE

### 7.1 Key Functions

#### `calculate_net_tallies_from_transactions(client_exchange, as_of_date=None)`
- **Location**: `core/views.py` (line ~1002)
- **Purpose**: Calculate net tallies from transaction ledger
- **Returns**: Dict with `net_client_tally`, `net_company_tally`, `your_earnings`

#### `pending_summary(request)`
- **Location**: `core/views.py` (line ~1118)
- **Purpose**: Main view function for pending payments page
- **Flow**: Gets client exchanges → calculates net tallies → routes to sections → renders

#### `round_share(amount, decimals=1)`
- **Location**: `core/utils/money.py` (line ~20)
- **Purpose**: Round share-space amounts DOWN
- **Usage**: All pending amounts, shares, payable amounts

#### `round_capital(amount, decimals=2)`
- **Location**: `core/utils/money.py` (line ~57)
- **Purpose**: Round capital-space amounts (ROUND_HALF_UP)
- **Usage**: Loss amounts, profit amounts, capital calculations

### 7.2 Data Flow

```
ClientExchange
    ↓
cached_total_funding (capital-space)
cached_current_balance (capital-space)
    ↓
calculate_net_tallies_from_transactions()
    ↓
Transaction.objects.filter(...)
    ├─ LOSS transactions → your_share_from_losses
    ├─ PROFIT transactions → your_share_from_profits
    └─ SETTLEMENT transactions → client_payments, admin_payments_to_client
    ↓
net_client_tally = (losses - profits - payments_received + payments_made)
    ↓
round_share(net_client_tally)
    ↓
Route to section (clients_owe_list or you_owe_list)
```

---

## 8. EXAMPLES

### Example 1: Client in Loss (Client Owes You)

**Scenario**:
- Client received ₹1000 funding
- Client lost ₹500 (LOSS transaction created)
- Your share % = 10%
- No settlements yet

**Calculation**:
```python
# Step 1: Get cached values
funding = 1000
exchange_balance = 500  # (1000 - 500)

# Step 2: Calculate NET (for display)
NET = 500 - 1000 = -500  # Loss

# Step 3: Calculate net_share from ledger
your_share_from_losses = 500 * 10% = 50
your_share_from_profits = 0
client_payments = 0
admin_payments_to_client = 0

net_client_tally = 50 - 0 - 0 + 0 = 50

# Step 4: Route to section
net_share = 50 > 0 → "Clients Owe You" section
```

**Result**: Client appears in "Clients Owe You" section with pending amount ₹50.00

---

### Example 2: Client in Profit (You Owe Client)

**Scenario**:
- Client received ₹1000 funding
- Client made ₹200 profit (PROFIT transaction created)
- Your share % = 10%
- No settlements yet

**Calculation**:
```python
# Step 1: Get cached values
funding = 1000
exchange_balance = 1200  # (1000 + 200)

# Step 2: Calculate NET (for display)
NET = 1200 - 1000 = 200  # Profit

# Step 3: Calculate net_share from ledger
your_share_from_losses = 0
your_share_from_profits = 200 * 10% = 20
client_payments = 0
admin_payments_to_client = 0

net_client_tally = 0 - 20 - 0 + 0 = -20

# Step 4: Route to section
net_share = -20 < 0 → "You Owe Clients" section
```

**Result**: Client appears in "You Owe Clients" section with amount ₹20.00

---

### Example 3: Partial Payment (Settlement)

**Scenario**:
- Client owes ₹50 (from Example 1)
- Client pays ₹30 (SETTLEMENT transaction created)
- Remaining pending?

**Calculation**:
```python
# Step 1: Get cached values (unchanged)
funding = 1000
exchange_balance = 500

# Step 2: Calculate NET (unchanged)
NET = -500

# Step 3: Calculate net_share from ledger (UPDATED)
your_share_from_losses = 50
your_share_from_profits = 0
client_payments = 30  # ← NEW: Settlement payment
admin_payments_to_client = 0

net_client_tally = 50 - 0 - 30 + 0 = 20

# Step 4: Route to section
net_share = 20 > 0 → Still in "Clients Owe You" section
```

**Result**: Client still appears in "Clients Owe You" section with remaining pending ₹20.00

---

### Example 4: Fully Settled

**Scenario**:
- Client owes ₹50 (from Example 1)
- Client pays ₹50 (SETTLEMENT transaction created)
- Fully settled?

**Calculation**:
```python
# Step 3: Calculate net_share from ledger
your_share_from_losses = 50
your_share_from_profits = 0
client_payments = 50  # Full payment
admin_payments_to_client = 0

net_client_tally = 50 - 0 - 50 + 0 = 0

# Step 4: Route to section
net_share = 0 → Skip (fully settled)
```

**Result**: Client does NOT appear in pending payments (fully settled)

---

## 9. SETTLEMENT TRANSACTIONS

### 9.1 Settlement Types

#### Client Pays You (Reduces What Client Owes)
```python
Transaction.objects.create(
    client_exchange=client_exchange,
    transaction_type=Transaction.TYPE_SETTLEMENT,
    your_share_amount=30,  # You receive
    client_share_amount=0,  # Client pays
    ...
)
```

#### You Pay Client (Reduces What You Owe)
```python
Transaction.objects.create(
    client_exchange=client_exchange,
    transaction_type=Transaction.TYPE_SETTLEMENT,
    your_share_amount=0,  # You pay
    client_share_amount=20,  # Client receives
    ...
)
```

### 9.2 Settlement Impact

Settlements **directly reduce** the net tally:

- **Client payment**: Subtracts from `net_client_tally` (reduces what client owes)
- **Admin payment**: Adds to `net_client_tally` (reduces what you owe)

---

## 10. EDGE CASES

### 10.1 Zero Net Share

If `net_share == 0`:
- Client is fully settled
- Skip adding to any list
- Don't show in pending payments

### 10.2 Negative Exchange Balance

If `exchange_balance < funding`:
- Client is in loss
- `NET` will be negative
- But `net_share` determines which section (not `NET`)

### 10.3 Multiple Settlements

Multiple settlements are automatically summed:
```python
client_payments = Σ(all SETTLEMENT.your_share_amount WHERE client_share_amount=0)
```

---

## 11. VALIDATION RULES

### 11.1 Data Integrity

- ✅ Pending is **always calculated**, never stored
- ✅ Single source of truth: `calculate_net_tallies_from_transactions()`
- ✅ No drift possible (ledger-based calculation)

### 11.2 Rounding Validation

- ✅ All share-space amounts use `round_share()` (round DOWN)
- ✅ All capital-space amounts use `round_capital()` (round HALF UP)
- ✅ No mixing of rounding methods

---

## 12. SUMMARY

### Key Takeaways

1. **Pending = Net Tally from Ledger**: Calculated from transactions, never stored
2. **Two Sections**: Clients owe you (positive) vs You owe clients (negative)
3. **Share-Space Rounding**: Always round DOWN to prevent over-collection
4. **Settlements Reduce Net**: Payments directly reduce the net tally
5. **Single Source of Truth**: `calculate_net_tallies_from_transactions()` is the ONLY function that calculates pending

### Formula Summary

```
net_client_tally = (
    Σ(LOSS.your_share_amount) 
    - Σ(PROFIT.your_share_amount) 
    - Σ(SETTLEMENT.your_share_amount WHERE client_pays) 
    + Σ(SETTLEMENT.client_share_amount WHERE admin_pays)
)

net_share = round_share(net_client_tally)

if net_share > 0:
    → "Clients Owe You"
elif net_share < 0:
    → "You Owe Clients"
else:
    → Fully settled (skip)
```

---

**End of Documentation**

