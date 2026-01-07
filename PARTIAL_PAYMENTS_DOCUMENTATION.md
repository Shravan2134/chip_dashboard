# PARTIAL PAYMENTS - FORMULAS, LOGIC & IMPLEMENTATION

**Version:** 1.0  
**Last Updated:** 2025-01-XX  
**Status:** Production Ready

---

## TABLE OF CONTENTS

1. [Overview](#1-overview)
2. [How Partial Payments Work](#2-how-partial-payments-work)
3. [Core Formula](#3-core-formula)
4. [Settlement Transaction Logic](#4-settlement-transaction-logic)
5. [Remaining Pending Calculation](#5-remaining-pending-calculation)
6. [Examples](#6-examples)
7. [Implementation Details](#7-implementation-details)

---

## 1. OVERVIEW

Partial payments allow clients to pay **any amount less than or equal to** the full pending amount. The system automatically tracks remaining balances and supports multiple partial payments until full settlement.

### Key Principles

- ✅ **Any Amount Allowed**: Client can pay any amount from ₹0.1 to full pending amount
- ✅ **Multiple Payments**: Supports unlimited partial payments until fully settled
- ✅ **Automatic Tracking**: Remaining pending is calculated automatically from ledger
- ✅ **No Manual Updates**: System handles all calculations - no manual balance updates needed
- ✅ **Ledger-Based**: All calculations come from transaction ledger (single source of truth)

---

## 2. HOW PARTIAL PAYMENTS WORK

### 2.1 Simple Flow

```
1. Client owes ₹50.00 (from LOSS transaction)
2. Client pays ₹30.00 (SETTLEMENT transaction created)
3. System calculates remaining: ₹50.00 - ₹30.00 = ₹20.00
4. Client can pay ₹20.00 later (or any amount ≤ ₹20.00)
5. When remaining = ₹0.00, client is fully settled
```

### 2.2 Core Concept

**Partial payments work because settlements are SUBTRACTED from the net tally.**

The system doesn't store "remaining pending" - it **calculates it dynamically** from:
- All LOSS transactions (what client owes)
- All PROFIT transactions (what you owe)
- **All SETTLEMENT transactions (payments made/received)**

---

## 3. CORE FORMULA

### 3.1 Net Client Tally Formula

The **single source of truth** for pending amounts:

```python
net_client_tally = (
    Σ(LOSS.your_share_amount)           # Income from losses
    - Σ(PROFIT.your_share_amount)        # Expense from profits  
    - Σ(SETTLEMENT.your_share_amount)    # Payments received (client pays you)
    + Σ(SETTLEMENT.client_share_amount)  # Payments made (you pay client)
)
```

### 3.2 Partial Payment Impact

When a partial payment is made:

```python
# BEFORE payment
net_client_tally = 50.00  # Client owes you ₹50

# Client pays ₹30 (SETTLEMENT created with your_share_amount=30)
# AFTER payment
net_client_tally = 50.00 - 30.00 = 20.00  # Remaining: ₹20
```

### 3.3 Multiple Partial Payments

```python
# Initial: Client owes ₹50
net_client_tally = 50.00

# Payment 1: ₹20
SETTLEMENT 1: your_share_amount = 20
net_client_tally = 50.00 - 20.00 = 30.00  # Remaining: ₹30

# Payment 2: ₹15
SETTLEMENT 2: your_share_amount = 15
net_client_tally = 50.00 - 20.00 - 15.00 = 15.00  # Remaining: ₹15

# Payment 3: ₹15 (full payment)
SETTLEMENT 3: your_share_amount = 15
net_client_tally = 50.00 - 20.00 - 15.00 - 15.00 = 0.00  # Fully settled
```

---

## 4. SETTLEMENT TRANSACTION LOGIC

### 4.1 Settlement Types

#### Client Pays You (Reduces What Client Owes)

```python
Transaction.objects.create(
    client_exchange=client_exchange,
    transaction_type=Transaction.TYPE_SETTLEMENT,
    amount=30.00,                    # Payment amount
    your_share_amount=30.00,         # You receive this amount
    client_share_amount=0,           # Client pays (not stored here)
    date=payment_date,
    note="Partial payment: ₹30.00"
)
```

**Formula Impact:**
- Subtracts from `net_client_tally`
- Reduces what client owes you
- `net_client_tally = net_client_tally - your_share_amount`

#### You Pay Client (Reduces What You Owe)

```python
Transaction.objects.create(
    client_exchange=client_exchange,
    transaction_type=Transaction.TYPE_SETTLEMENT,
    amount=20.00,                    # Payment amount
    your_share_amount=0,             # You pay (not stored here)
    client_share_amount=20.00,       # Client receives this amount
    date=payment_date,
    note="Partial payment to client: ₹20.00"
)
```

**Formula Impact:**
- Adds to `net_client_tally` (reduces negative balance)
- Reduces what you owe client
- `net_client_tally = net_client_tally + client_share_amount`

### 4.2 Settlement Processing

When a settlement is created:

```python
def settle_payment(request):
    # 1. Get payment amount from form
    amount = round_share(Decimal(str(amount_raw)))
    
    # 2. Create SETTLEMENT transaction
    Transaction.objects.create(
        client_exchange=client_exchange,
        transaction_type=Transaction.TYPE_SETTLEMENT,
        amount=amount,
        your_share_amount=amount if payment_type == 'client_pays' else 0,
        client_share_amount=amount if payment_type == 'admin_pays_profit' else 0,
        date=tx_date,
        note=note
    )
    
    # 3. System automatically recalculates pending on next view
    # No manual updates needed!
```

---

## 5. REMAINING PENDING CALCULATION

### 5.1 Calculation Function

The `calculate_net_tallies_from_transactions()` function handles all calculations:

```python
def calculate_net_tallies_from_transactions(client_exchange, as_of_date=None):
    """
    Calculate NET TALLIES from transactions.
    This is the SINGLE SOURCE OF TRUTH for pending amounts.
    """
    # Filter transactions
    tx_filter = {"client_exchange": client_exchange}
    if as_of_date:
        tx_filter["date__lte"] = as_of_date
    
    # Get all LOSS transactions
    your_share_from_losses = Transaction.objects.filter(
        **tx_filter,
        transaction_type=Transaction.TYPE_LOSS
    ).aggregate(total=Sum("your_share_amount"))["total"] or Decimal(0)
    
    # Get all PROFIT transactions
    your_share_from_profits = Transaction.objects.filter(
        **tx_filter,
        transaction_type=Transaction.TYPE_PROFIT
    ).aggregate(total=Sum("your_share_amount"))["total"] or Decimal(0)
    
    # Get settlements where client paid you
    client_payments = Transaction.objects.filter(
        **tx_filter,
        transaction_type=Transaction.TYPE_SETTLEMENT,
        your_share_amount__gt=0,
        client_share_amount=0
    ).aggregate(total=Sum("your_share_amount"))["total"] or Decimal(0)
    
    # Get settlements where you paid client
    admin_payments_to_client = Transaction.objects.filter(
        **tx_filter,
        transaction_type=Transaction.TYPE_SETTLEMENT,
        client_share_amount__gt=0,
        your_share_amount=0
    ).aggregate(total=Sum("client_share_amount"))["total"] or Decimal(0)
    
    # Calculate NET CLIENT TALLY
    net_client_tally_raw = (
        your_share_from_losses 
        - your_share_from_profits 
        - client_payments 
        + admin_payments_to_client
    )
    
    # Round DOWN (share-space rounding)
    net_client_tally = round_share(net_client_tally_raw)
    
    return {
        "net_client_tally": net_client_tally,
        "net_company_tally": Decimal(0),  # Always 0 for my clients
        "your_earnings": Decimal(0),
    }
```

### 5.2 Remaining Pending = Net Client Tally

**The remaining pending amount IS the net_client_tally.**

- If `net_client_tally > 0`: Client owes you this amount
- If `net_client_tally < 0`: You owe client this amount
- If `net_client_tally == 0`: Fully settled (no pending)

---

## 6. EXAMPLES

### Example 1: Single Partial Payment

**Scenario:**
- Client lost ₹500 (LOSS transaction)
- Your share % = 10%
- Client owes: ₹50.00
- Client pays: ₹30.00 (partial)

**Calculation:**

```python
# Step 1: Initial state
your_share_from_losses = 50.00
your_share_from_profits = 0.00
client_payments = 0.00
admin_payments_to_client = 0.00

net_client_tally = 50.00 - 0.00 - 0.00 + 0.00 = 50.00
# Client owes ₹50.00

# Step 2: After partial payment of ₹30
your_share_from_losses = 50.00  # Unchanged
your_share_from_profits = 0.00   # Unchanged
client_payments = 30.00          # ← NEW: Settlement added
admin_payments_to_client = 0.00  # Unchanged

net_client_tally = 50.00 - 0.00 - 30.00 + 0.00 = 20.00
# Remaining: ₹20.00
```

**Result:** Client still appears in "Clients Owe You" section with remaining pending ₹20.00

---

### Example 2: Multiple Partial Payments

**Scenario:**
- Client owes ₹100.00 (from losses)
- Payment 1: ₹40.00
- Payment 2: ₹35.00
- Payment 3: ₹25.00

**Calculation:**

```python
# Initial
net_client_tally = 100.00

# After Payment 1 (₹40)
SETTLEMENT 1: your_share_amount = 40.00
client_payments = 40.00
net_client_tally = 100.00 - 40.00 = 60.00  # Remaining: ₹60

# After Payment 2 (₹35)
SETTLEMENT 2: your_share_amount = 35.00
client_payments = 40.00 + 35.00 = 75.00
net_client_tally = 100.00 - 75.00 = 25.00  # Remaining: ₹25

# After Payment 3 (₹25) - Full payment
SETTLEMENT 3: your_share_amount = 25.00
client_payments = 40.00 + 35.00 + 25.00 = 100.00
net_client_tally = 100.00 - 100.00 = 0.00  # Fully settled!
```

**Result:** After Payment 3, client is fully settled and disappears from pending payments.

---

### Example 3: Partial Payment on Profit (You Owe Client)

**Scenario:**
- Client made ₹200 profit (PROFIT transaction)
- Your share % = 10%
- You owe: ₹20.00
- You pay: ₹12.00 (partial)

**Calculation:**

```python
# Step 1: Initial state
your_share_from_losses = 0.00
your_share_from_profits = 20.00
client_payments = 0.00
admin_payments_to_client = 0.00

net_client_tally = 0.00 - 20.00 - 0.00 + 0.00 = -20.00
# You owe client ₹20.00 (negative = you owe)

# Step 2: After partial payment of ₹12
your_share_from_losses = 0.00   # Unchanged
your_share_from_profits = 20.00 # Unchanged
client_payments = 0.00          # Unchanged
admin_payments_to_client = 12.00 # ← NEW: Settlement added

net_client_tally = 0.00 - 20.00 - 0.00 + 12.00 = -8.00
# Remaining: You still owe ₹8.00
```

**Result:** Client still appears in "You Owe Clients" section with remaining amount ₹8.00

---

### Example 4: Mixed Transactions with Partial Payments

**Scenario:**
- Loss 1: ₹100 (your share = ₹10)
- Profit 1: ₹50 (your share = ₹5)
- Payment 1: ₹3 (partial)
- Loss 2: ₹200 (your share = ₹20)
- Payment 2: ₹15 (partial)

**Calculation:**

```python
# After all transactions
your_share_from_losses = 10.00 + 20.00 = 30.00
your_share_from_profits = 5.00
client_payments = 3.00 + 15.00 = 18.00
admin_payments_to_client = 0.00

net_client_tally = 30.00 - 5.00 - 18.00 + 0.00 = 7.00
# Remaining: Client owes ₹7.00
```

**Result:** Client appears in "Clients Owe You" section with remaining pending ₹7.00

---

## 7. IMPLEMENTATION DETAILS

### 7.1 Settlement Creation

**Location:** `core/views.py` → `settle_payment()` function

**Key Steps:**
1. Validate payment amount (must be > 0)
2. Round amount using `round_share()` (rounds DOWN)
3. Create SETTLEMENT transaction
4. Redirect to pending summary (system recalculates automatically)

**Code:**
```python
@login_required
def settle_payment(request):
    if request.method == "POST":
        amount_raw = request.POST.get("amount", "0") or "0"
        amount = round_share(Decimal(str(amount_raw)))  # Round DOWN
        
        payment_type = request.POST.get("payment_type", "client_pays")
        
        Transaction.objects.create(
            client_exchange=client_exchange,
            transaction_type=Transaction.TYPE_SETTLEMENT,
            amount=amount,
            your_share_amount=amount if payment_type == 'client_pays' else 0,
            client_share_amount=amount if payment_type == 'admin_pays_profit' else 0,
            date=tx_date,
            note=note
        )
```

### 7.2 Pending Calculation

**Location:** `core/views.py` → `pending_summary()` function

**Key Steps:**
1. Get all client exchanges
2. For each exchange, call `calculate_net_tallies_from_transactions()`
3. Get `net_client_tally` (this is the remaining pending)
4. Route to appropriate section based on sign:
   - `net_client_tally > 0` → "Clients Owe You"
   - `net_client_tally < 0` → "You Owe Clients"
   - `net_client_tally == 0` → Skip (fully settled)

### 7.3 Rounding Rules

**Share-Space Rounding (ALWAYS ROUND DOWN):**
- Function: `round_share(amount, decimals=1)`
- Rule: Always rounds DOWN to prevent over-collection
- Examples:
  - `30.55 → 30.5`
  - `30.56 → 30.5`
  - `30.99 → 30.9`

**Why Round Down?**
- Prevents over-collection from clients
- Client-facing amounts must NEVER round up
- Ensures fairness in partial payments

### 7.4 Validation

**Frontend Validation:**
- Payment amount cannot exceed remaining pending
- Payment amount must be > 0
- Payment amount is validated against raw pending (before rounding)

**Backend Validation:**
- Amount is converted to Decimal (prevents float errors)
- Amount is rounded using `round_share()` (rounds DOWN)
- Transaction is created atomically (database transaction)

---

## 8. KEY TAKEAWAYS

### How Partial Payments Work

1. **Settlements Subtract from Net Tally**
   - Each SETTLEMENT transaction reduces the net_client_tally
   - Multiple settlements are automatically summed
   - No manual tracking needed

2. **Remaining Pending = Net Client Tally**
   - The remaining pending IS the net_client_tally
   - Calculated dynamically from all transactions
   - Always accurate, no drift possible

3. **Support for Unlimited Partial Payments**
   - Client can make as many partial payments as needed
   - Each payment reduces remaining pending
   - System handles all calculations automatically

4. **Single Source of Truth**
   - `calculate_net_tallies_from_transactions()` is the ONLY function that calculates pending
   - All settlements are stored as transactions
   - No stored "remaining balance" - always calculated fresh

### Formula Summary

```
net_client_tally = (
    Σ(LOSS.your_share_amount)           # What client owes from losses
    - Σ(PROFIT.your_share_amount)        # What you owe from profits
    - Σ(SETTLEMENT.your_share_amount)    # Payments received (partial or full)
    + Σ(SETTLEMENT.client_share_amount)  # Payments made (partial or full)
)

remaining_pending = abs(net_client_tally)
```

---

**End of Documentation**
