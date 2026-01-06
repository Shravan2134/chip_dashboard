# PARTIAL PAYMENTS - COMPLETE DOCUMENTATION

**Everything You Need to Know: UI, Recording, Formulas, Logic, Code**

---

## 📋 TABLE OF CONTENTS

1. [What Are Partial Payments?](#what-are-partial-payments)
2. [UI Flow - How to Record](#ui-flow)
3. [Step-by-Step Recording Process](#recording-process)
4. [Core Formulas](#formulas)
5. [Rounding Rules (CRITICAL)](#rounding-rules)
6. [Backend Logic Explained](#backend-logic)
7. [Code Walkthrough](#code-walkthrough)
8. [Complete Examples](#examples)
9. [Validation Rules](#validation-rules)
10. [Troubleshooting](#troubleshooting)

---

## 🎯 WHAT ARE PARTIAL PAYMENTS?

### Definition

**Partial Payments** allow clients to pay a portion of their pending loss amount instead of paying the full amount at once. The system automatically:
- Converts the payment amount to "capital closed"
- Reduces the frozen Loss amount
- Re-derives the Old Balance (CAPITAL)
- Recalculates the remaining pending amount
- Updates all ledgers and displays

### Key Concepts (CRITICAL)

1. **Loss (FROZEN)**: Stored in `LossSnapshot` model - NEVER recalculated
   - Set when loss is first detected
   - Only reduced by SETTLEMENT transactions
   - Never recalculated from `Old Balance - Current Balance`
   - **IMMUTABLE**: `loss_amount` is the original loss, never changed
   - **DERIVED**: `remaining_loss` = `original_loss - sum(capital_closed from settlements)`

2. **Current Balance (CB)**: Frozen when loss exists
   - When active LossSnapshot exists: CB is frozen from `LossSnapshot.balance_record`
   - When no loss: CB is live from latest balance record
   - New balance records don't affect loss calculations when loss exists

3. **Old Balance (CAPITAL)**: Always DERIVED, never a source of truth
   - Formula: `CAPITAL = CB + LOSS`
   - Never used to derive Loss
   - Updated after every settlement

4. **Pending Amount**: Calculated from FROZEN Loss
   - Formula: `Pending = (Loss × Share %) / 100`
   - Always from `LossSnapshot.get_remaining_loss()`, never recalculated
   - **ROUNDED DOWN** to prevent over-collection

5. **Capital Closed**: Amount of loss that gets closed
   - Formula: `Capital Closed = (Payment × 100) / Share %`
   - This is what reduces the frozen Loss
   - Stored in `Transaction.capital_closed` for audit trail

### 🔒 CRITICAL RULES (NON-NEGOTIABLE)

1. **LOSS is FROZEN** - Stored in LossSnapshot, never recalculated
2. **CAPITAL is DERIVED** - Always `CB + LOSS`, never source of truth
3. **PROFIT exists ONLY when LOSS = 0** - Cannot have profit while loss exists
4. **LOSS reduced ONLY by SETTLEMENT** - Balance recovery never reduces loss
5. **CB is FROZEN when LOSS exists** - New balance records ignored
6. **Pending from FROZEN LOSS** - Always from LossSnapshot
7. **SHARE-SPACE ALWAYS ROUNDS DOWN** - Prevents over-collection

---

## 🖥️ UI FLOW - HOW TO RECORD

### Step 1: Navigate to Pending Payments Page

1. Open your browser and go to: `http://localhost:8000/pending/`
2. You'll see two main sections:
   - **"Clients Owe You"** - Shows clients with pending losses (this is where you record payments)
   - **"You Owe Clients"** - Shows clients in profit (rare, for profit payouts)

### Step 2: Find the Client in the Table

In the **"Clients Owe You"** section, you'll see a table with columns:

| Column | Description |
|--------|-------------|
| Client Name | Name of the client |
| Exchange | Exchange name |
| Old Balance | Capital base (derived: CB + Loss) |
| Current Balance | Frozen balance from LossSnapshot |
| Trading Loss (Capital) | Frozen loss amount from LossSnapshot |
| My Share | Your share of the loss (1% for company clients, 10% for my clients) |
| Company Share | Company share (9% for company clients, 0 for my clients) |
| Client Payable (Share) | **What client owes (this is what you can collect)** |
| Action | **"Record Share Settlement"** button |

### Step 3: Click "Record Share Settlement" Button

1. Find the client you want to record payment for
2. Click the **"Record Share Settlement"** button in the Action column
3. A modal form will pop up with payment details

### Step 4: Payment Modal Form

The modal shows:

```
┌─────────────────────────────────────────┐
│  Record Share Settlement               │
├─────────────────────────────────────────┤
│  Client: [Client Name] (read-only)     │
│  Exchange: [Exchange Name] (read-only) │
│                                         │
│  Client Payable (Share): ₹6.00        │
│  (Pre-filled with pending amount)      │
│                                         │
│  Amount: [₹6.00]                       │
│  (Default: Full pending amount)         │
│  (For partial: Change to any ≤ pending)│
│                                         │
│  Date: [2026-01-05]                     │
│  (Default: Today's date)               │
│                                         │
│  Note: [Optional text field]           │
│                                         │
│  Share Breakdown:                      │
│  - My Share: ₹0.60                      │
│  - Company Share: ₹5.40                 │
│  - Combined Share: ₹6.00                │
│                                         │
│  [Cancel]  [Record Share Settlement]    │
└─────────────────────────────────────────┘
```

### Step 5: Enter Payment Details

1. **Amount Field**:
   - **Default**: Pre-filled with the full pending amount (e.g., ₹6.00)
   - **For Partial Payment**: Change it to any amount ≤ pending amount
   - **Example**: If pending is ₹6, you can enter ₹3 for partial payment
   - **Validation**: System prevents entering amount > pending
   - **Max Value**: Automatically set to pending amount

2. **Date Field**:
   - **Default**: Today's date
   - **Change**: You can select a different date if needed

3. **Note Field** (Optional):
   - Add any notes about this payment
   - Example: "Partial payment - first installment"
   - Example: "Payment via bank transfer"

### Step 6: Submit the Form

1. Click **"Record Share Settlement"** button
2. The system will:
   - Validate the payment
   - Process the settlement
   - Update LossSnapshot (mark as settled if loss = 0)
   - Re-derive Old Balance
   - Recalculate pending amount
   - Create SETTLEMENT transaction with `capital_closed`
   - Show success message
   - Redirect back to pending payments page

### UI Code Location

**File**: `core/templates/core/pending/summary.html`

**Key JavaScript Functions**:
- `showSettlementForm()` - Opens the payment modal and populates fields
- `handleFormSubmit()` - Validates and submits the form
- `validateAmount()` - Ensures payment ≤ pending amount

---

## 📝 STEP-BY-STEP RECORDING PROCESS

### What Happens Behind the Scenes?

Let's trace through a complete example:

#### **Initial State**:
```
Original Loss (FROZEN in LossSnapshot) = ₹60
Current Balance (FROZEN in LossSnapshot) = ₹40
Old Balance (CAPITAL) = CB + Loss = ₹40 + ₹60 = ₹100 (DERIVED)
Share % = 10% (FROZEN in LossSnapshot)
Pending Amount = ₹60 × 10% = ₹6 (from frozen Loss, ROUNDED DOWN)
```

#### **User Action**: Client pays ₹3 (Partial Payment)

### **Step 1: Get Current State (from FROZEN LossSnapshot)**

**Code**:
```python
# Get active loss snapshot (frozen values)
loss_snapshot = LossSnapshot.objects.get(
    client_exchange=client_exchange,
    is_settled=False
)

# LOSS is FROZEN - original loss is immutable
original_loss = loss_snapshot.loss_amount  # ₹60 (FROZEN, IMMUTABLE)

# Remaining loss is DERIVED from settlements
loss_current = loss_snapshot.get_remaining_loss()  # ₹60 (DERIVED)

# CB is FROZEN when loss exists
current_balance = loss_snapshot.balance_record.remaining_balance  # ₹40 (FROZEN)

# CAPITAL is DERIVED from frozen values
old_balance = current_balance + loss_current  # ₹40 + ₹60 = ₹100 (DERIVED)

# Share percentages are FROZEN at loss creation time
my_share_pct = loss_snapshot.my_share_pct  # FROZEN
company_share_pct = loss_snapshot.company_share_pct  # FROZEN
```

**Result**:
- `original_loss = ₹60` (frozen, immutable)
- `loss_current = ₹60` (derived from original_loss - settlements)
- `current_balance = ₹40` (frozen)
- `old_balance = ₹100` (derived)

### **Step 2: Validate Payment**

**Code**:
```python
from core.utils.money import AUTO_CLOSE_THRESHOLD

# Check if active loss snapshot exists
if not loss_snapshot or loss_snapshot.is_settled:
    ERROR: "No active loss to settle"

# Check if loss exists (from frozen snapshot)
if loss_current < AUTO_CLOSE_THRESHOLD:
    ERROR: "No loss to settle"

# Check if payment is valid
if amount <= 0:
    ERROR: "Amount must be greater than zero"

# ✅ FIX ISSUE 3: Validate against RAW pending, not rounded (prevents blocking valid payments)
# Calculate raw pending for validation (display uses rounded)
total_share_pct = my_share_pct + company_share_pct  # 10%
pending_raw = (loss_current * total_share_pct) / 100  # ₹6.00 (RAW)
pending_display = round_share(pending_raw)  # ₹6.0 (ROUNDED DOWN, for display only)

# Validate payment against RAW pending (prevents blocking valid payments like ₹3.05 when raw is ₹3.09)
if amount > pending_raw:
    ERROR: "Payment exceeds pending amount"
```

**Result**: Validation passes ✓

### **Step 3: Convert Payment to Capital Closed**

**Code**:
```python
from core.utils.money import round_capital

# Formula: capital_closed = payment × 100 / share_pct
capital_closed_raw = (amount * Decimal(100)) / total_share_pct
capital_closed_raw = (₹3 × 100) / 10 = ₹30.00

# Validate capital_closed doesn't exceed loss
if capital_closed_raw > loss_current:
    ERROR: "Capital closed exceeds loss"

# Round to 2 decimal places (capital-space: ROUND_HALF_UP)
capital_closed = round_capital(capital_closed_raw)  # ₹30.00
```

**Result**: `capital_closed = ₹30.00`

### **Step 4: Reduce Loss (LOSS-First Approach)**

**Code**:
```python
from core.utils.money import round_capital, AUTO_CLOSE_THRESHOLD

# Reduce DERIVED loss by capital closed
loss_new = loss_current - capital_closed
loss_new = ₹60 - ₹30 = ₹30

# Guard against negative loss
if loss_new < 0:
    ERROR: "Settlement would create negative loss"

# Clamp to zero (safety check)
loss_new = max(loss_new, 0)

# Round to 2 decimal places (capital-space: ROUND_HALF_UP)
loss_new = round_capital(loss_new)  # ₹30.00

# Auto-close if below threshold
if loss_new < AUTO_CLOSE_THRESHOLD:
    loss_new = Decimal(0)
    loss_snapshot.is_settled = True
```

**Result**: `loss_new = ₹30.00`

### **Step 5: Update LossSnapshot (IMMUTABLE)**

**Code**:
```python
# 🚨 CRITICAL: LossSnapshot.loss_amount is IMMUTABLE
# DO NOT mutate loss_snapshot.loss_amount - it's a historical snapshot
# Remaining loss is DERIVED from settlements, not stored

# Only update is_settled flag if loss is fully closed
if loss_new < AUTO_CLOSE_THRESHOLD:
    loss_snapshot.is_settled = True
    loss_snapshot.save(update_fields=['is_settled'])
```

**Result**: LossSnapshot remains immutable, `is_settled` updated if needed

### **Step 6: Re-derive CAPITAL**

**Code**:
```python
# CAPITAL is ALWAYS derived: CAPITAL = CB + LOSS
if loss_new >= AUTO_CLOSE_THRESHOLD:
    # Partial settlement: CAPITAL = CB (frozen) + LOSS (updated)
    old_balance_new = current_balance + loss_new
    old_balance_new = ₹40 + ₹30 = ₹70
else:
    # Full settlement: CAPITAL = CB (frozen)
    old_balance_new = current_balance
    loss_new = Decimal(0)
```

**Result**: `old_balance_new = ₹70` (derived)

### **Step 7: Recalculate Pending (from Remaining Loss)**

**Code**:
```python
from core.utils.money import round_share

if loss_new >= AUTO_CLOSE_THRESHOLD:
    # Calculate pending from updated remaining Loss (share-space: round DOWN)
    client_payable_raw = (loss_new * total_pct) / Decimal(100)
    client_payable_raw = (₹30 × 10) / 100 = ₹3.00
    client_payable = round_share(client_payable_raw)  # ₹3.0 (ROUNDED DOWN)
    
    pending_new = client_payable
else:
    # Fully settled
    pending_new = Decimal(0)
```

**Result**: `pending_new = ₹3.0` (rounded down)

### **Step 8: Create SETTLEMENT Transaction**

**Code**:
```python
from core.utils.money import round_share

# ✅ CORRECT IMPLEMENTATION: Split payment to prevent leakage
# Algorithm: Round ONE side, give remainder to other (NO rounding on remainder)
if client_exchange.client.is_company_client:
    # Company clients: Split payment between my share (1%) and company share (9%)
    my_share_amount_raw = (amount * my_share_pct) / total_pct
    my_share_amount_raw = (₹3 × 1) / 10 = ₹0.30
    my_share_amount = round_share(my_share_amount_raw)  # ₹0.3 (ROUNDED DOWN)
    
    # Give remainder to company (NO rounding) to prevent leakage
    company_share_amount = amount - my_share_amount  # ₹3 - ₹0.3 = ₹2.7 (NO rounding)
    # Total always equals amount: ₹0.3 + ₹2.7 = ₹3.0 ✅
else:
    # My clients: Full payment goes to my share
    my_share_amount = round_share(amount)  # ₹3.0 (ROUNDED DOWN)
    company_share_amount = Decimal(0)

# Create SETTLEMENT transaction
transaction = Transaction.objects.create(
    client_exchange=client_exchange,
    date=settlement_date,
    transaction_type=Transaction.TYPE_SETTLEMENT,
    amount=amount,  # ₹3.0
    capital_closed=capital_closed,  # ₹30.00 (audit trail)
    client_share_amount=Decimal(0),  # Client pays
    your_share_amount=my_share_amount,  # ₹0.3 or ₹3.0
    company_share_amount=company_share_amount,  # ₹2.7 or ₹0
    note=f"Share settlement: ₹{amount} (capital_closed: ₹{capital_closed})"
)
```

**Result**: SETTLEMENT transaction created with `capital_closed = ₹30.00`

### **Step 9: Update Cached Old Balance**

**Code**:
```python
# Update cached_old_balance in ClientExchange (this is the source of truth)
locked_client_exchange.cached_old_balance = old_balance_new  # ₹70
locked_client_exchange.balance_last_updated = timezone.now()
locked_client_exchange.save(update_fields=['cached_old_balance', 'balance_last_updated'])
```

**Result**: `cached_old_balance = ₹70` (updated)

### **Final State After Partial Payment**:
```
Original Loss (FROZEN, IMMUTABLE) = ₹60
Remaining Loss (DERIVED) = ₹60 - ₹30 = ₹30
Current Balance (FROZEN) = ₹40
Old Balance (CAPITAL, DERIVED) = ₹40 + ₹30 = ₹70
Pending Amount = ₹30 × 10% = ₹3.0 (ROUNDED DOWN)
Capital Closed = ₹30.00 (stored in Transaction)
```

---

## 📐 CORE FORMULAS

### Formula 1: Capital Closed

**Purpose**: Convert payment amount to capital (loss) amount

**Formula**:
```
Capital Closed = (Payment × 100) / Share %
```

**Example**:
- Payment = ₹3
- Share % = 10%
- Capital Closed = (₹3 × 100) / 10 = ₹30

**Code**:
```python
from core.utils.money import round_capital

capital_closed_raw = (amount * Decimal(100)) / total_share_pct
capital_closed = round_capital(capital_closed_raw)  # Capital-space: ROUND_HALF_UP
```

### Formula 2: Remaining Loss

**Purpose**: Calculate remaining loss after settlement

**Formula**:
```
Remaining Loss = Original Loss - Sum(Capital Closed from all Settlements)
```

**Example**:
- Original Loss = ₹60
- Capital Closed = ₹30
- Remaining Loss = ₹60 - ₹30 = ₹30

**Code**:
```python
# In LossSnapshot model
def get_remaining_loss(self):
    """
    ✅ FIX ISSUE 1: Uses transaction date (not created_at) to handle backdated settlements.
    This is CRITICAL - backdated settlements are very common in accounting.
    """
    from .models import Transaction
    from django.db.models import Sum
    
    total_capital_closed = Transaction.objects.filter(
        client_exchange=self.client_exchange,
        transaction_type=Transaction.TYPE_SETTLEMENT,
        capital_closed__isnull=False,
        date__gte=self.balance_record.date  # ✅ Use transaction date, not created_at
    ).aggregate(total=Sum("capital_closed"))["total"] or Decimal(0)
    return max(self.loss_amount - total_capital_closed, Decimal(0))
```

### Formula 3: Old Balance (CAPITAL)

**Purpose**: Calculate capital base (always derived)

**Formula**:
```
CAPITAL = Current Balance + Remaining Loss
```

**Example**:
- Current Balance = ₹40
- Remaining Loss = ₹30
- CAPITAL = ₹40 + ₹30 = ₹70

**Code**:
```python
from core.utils.money import round_capital

old_balance = current_balance + loss_current
old_balance = round_capital(old_balance, decimals=1)  # Capital-space: ROUND_HALF_UP
```

### Formula 4: Pending Amount

**Purpose**: Calculate what client owes (share of loss)

**Formula**:
```
Pending = (Remaining Loss × Share %) / 100
```

**Example**:
- Remaining Loss = ₹30
- Share % = 10%
- Pending = (₹30 × 10) / 100 = ₹3.0

**Code**:
```python
from core.utils.money import round_share

pending_raw = (loss_current * total_share_pct) / Decimal(100)
pending = round_share(pending_raw)  # Share-space: ROUND DOWN
```

### Formula 5: Share Breakdown

**Purpose**: Split payment between my share and company share

**For Company Clients**:
```
My Share = (Payment × My Share %) / Total Share % (ROUNDED DOWN)
Company Share = Payment - My Share (NO ROUNDING - prevents leakage)
```

**For My Clients**:
```
My Share = Payment (ROUNDED DOWN)
Company Share = 0
```

**Code**:
```python
from core.utils.money import round_share

# ✅ FIX ISSUE 4: Prevent share split leakage
# Compute one side (my_share), give remainder to other (company_share)
# This ensures: my_share + company_share = amount (always)
if client_exchange.client.is_company_client:
    my_share_amount_raw = (amount * my_share_pct) / total_pct
    my_share_amount = round_share(my_share_amount_raw)  # ROUND DOWN
    # Give remainder to company (NO rounding) to prevent leakage
    company_share_amount = amount - my_share_amount  # Total always equals amount
else:
    my_share_amount = round_share(amount)  # ROUND DOWN
    company_share_amount = Decimal(0)
```

**Why This Matters**:
- If both sides round down: `my_share + company_share < amount` (money "disappears")
- By computing one side and giving remainder: `my_share + company_share = amount` (always)

---

## 🔢 ROUNDING RULES (CRITICAL)

### Centralized Rounding Utilities

**File**: `core/utils/money.py`

### Rule 1: Share-Space Rounding (ALWAYS ROUND DOWN)

**Purpose**: Prevent over-collection from clients

**Function**: `round_share(amount, decimals=1)`

**Rule**:
- **ALWAYS round DOWN**
- **NEVER round up**
- Prevents clients from paying more than their actual share

**Examples**:
- `8.55 → 8.5` (rounds down)
- `8.56 → 8.5` (rounds down)
- `8.88 → 8.8` (rounds down)
- `9.00 → 9.0` (no change)

**Used For**:
- `client_payable` (pending amount)
- `my_share_amount`
- `company_share_amount`
- Any amount the client pays
- Any amount shown in Pending / Settlement UI

**Code**:
```python
from core.utils.money import round_share

client_payable = round_share(loss * total_share_pct / 100)
my_share = round_share(loss * my_share_pct / 100)
company_share = round_share(loss * company_share_pct / 100)
```

### Rule 2: Capital-Space Rounding (ROUND_HALF_UP)

**Purpose**: Standard accounting rounding

**Function**: `round_capital(amount, decimals=2)`

**Rule**:
- **ROUND_HALF_UP** is allowed (standard accounting)
- Used for ledger values and capital calculations

**Examples**:
- `8.555 → 8.56` (rounds up)
- `8.554 → 8.55` (rounds down)
- `8.555 → 8.56` (rounds up)

**Used For**:
- `capital` (old balance)
- `loss` (capital)
- `capital_closed`
- Ledger values

**Code**:
```python
from core.utils.money import round_capital

capital_closed = round_capital((payment * 100) / total_share_pct)
loss_new = round_capital(original_loss - total_capital_closed)
old_balance = round_capital(current_balance + loss_new)
```

### Rule 3: UI Does NOT Round Again

**Rule**: All rounding happens in backend, never in template or JS

**❌ WRONG** (double rounding):
```django
₹{{ item.company_amount|floatformat:1 }}
```

**✅ CORRECT** (backend already rounded):
```django
₹{{ item.company_amount }}
```

**Reason**: Backend already rounded, UI just displays

---

## 🧠 BACKEND LOGIC EXPLAINED

### LOSS-First Approach

**Principle**: LOSS is the source of truth, CAPITAL is derived

**Flow**:
1. **LOSS is FROZEN** at creation time (stored in LossSnapshot)
2. **LOSS is REDUCED** only by SETTLEMENT transactions
3. **CAPITAL is RE-DERIVED** after every settlement: `CAPITAL = CB + LOSS`
4. **PENDING is CALCULATED** from remaining Loss: `Pending = (Loss × Share %) / 100`

**Why This Approach?**
- Prevents loss from disappearing when balance recovers
- Allows partial payments to work correctly
- Maintains audit trail of original loss

### Immutability of LossSnapshot

**Principle**: `LossSnapshot.loss_amount` is IMMUTABLE

**What This Means**:
- `loss_amount` stores the **original loss** at creation time
- It is **NEVER changed** after creation
- `remaining_loss` is **DERIVED** from `original_loss - sum(capital_closed)`

**Code**:
```python
# ❌ WRONG - Never do this
loss_snapshot.loss_amount = loss_new  # BREAKS AUDITABILITY

# ✅ CORRECT - Only update is_settled flag
if loss_new < AUTO_CLOSE_THRESHOLD:
    loss_snapshot.is_settled = True
    loss_snapshot.save(update_fields=['is_settled'])

# ✅ CORRECT - Derive remaining loss
remaining_loss = loss_snapshot.get_remaining_loss()
```

### Atomic Transactions

**Principle**: All settlement operations happen atomically

**Why?**
- Prevents race conditions
- Ensures data consistency
- Maintains invariants

**Code**:
```python
from django.db import transaction as db_transaction

with db_transaction.atomic():
    # Lock the ClientExchange row
    locked_client_exchange = ClientExchange.objects.select_for_update().get(pk=client_exchange.pk)
    
    # Get loss snapshot
    loss_snapshot = LossSnapshot.objects.get(
        client_exchange=locked_client_exchange,
        is_settled=False
    )
    
    # Calculate capital closed
    capital_closed = round_capital((amount * 100) / total_pct)
    
    # Reduce loss
    loss_new = loss_current - capital_closed
    
    # Re-derive CAPITAL
    old_balance_new = current_balance + loss_new
    
    # Create SETTLEMENT transaction
    transaction = Transaction.objects.create(...)
    
    # Update cached old balance
    locked_client_exchange.cached_old_balance = old_balance_new
    locked_client_exchange.save()
```

### Invariant Checks

**Principle**: System validates invariants after every settlement

**Invariants**:
1. `CAPITAL >= CB` (CAPITAL cannot be less than Current Balance)
2. `LOSS = CAPITAL - CB` (Loss must equal CAPITAL minus CB)
3. `CAPITAL = CB + LOSS` (CAPITAL must equal CB plus LOSS)

**Code**:
```python
# Invariant 1: CAPITAL >= CB
if old_balance_new < current_balance:
    ERROR: "Settlement invariant violation"

# Invariant 2: LOSS = CAPITAL - CB
loss_verify = old_balance_new - current_balance
if abs(loss_new - loss_verify) > AUTO_CLOSE_THRESHOLD:
    ERROR: "Loss invariant violation"

# Invariant 3: CAPITAL = CB + LOSS
capital_verify = current_balance + loss_new
if abs(old_balance_new - capital_verify) > AUTO_CLOSE_THRESHOLD:
    ERROR: "Capital invariant violation"
```

---

## 💻 CODE WALKTHROUGH

### Main Function: `settle_payment()`

**Location**: `core/views.py`, line 1384

**Purpose**: Handle settlement requests (partial or full payments)

**Flow**:
1. Parse request parameters
2. Validate payment type
3. Get locked ClientExchange (atomic)
4. Get active LossSnapshot
5. Validate payment amount
6. Calculate capital closed
7. Reduce loss
8. Re-derive CAPITAL
9. Create SETTLEMENT transaction
10. Update cached old balance
11. Update ledgers

**Key Code Sections**:

#### Section 1: Get Frozen State
```python
# Get active loss snapshot (frozen values)
loss_snapshot = LossSnapshot.objects.get(
    client_exchange=locked_client_exchange,
    is_settled=False
)

# LOSS is FROZEN - original loss is immutable
original_loss = loss_snapshot.loss_amount  # FROZEN (immutable)

# Remaining loss is DERIVED from settlements
loss_current = loss_snapshot.get_remaining_loss()  # DERIVED

# CB is FROZEN when loss exists
current_balance = loss_snapshot.balance_record.remaining_balance  # FROZEN

# CAPITAL is DERIVED from frozen values
old_balance = current_balance + loss_current  # DERIVED
```

#### Section 2: Validate Payment
```python
# Check if payment is valid
if amount <= Decimal(0):
    ERROR: "Amount must be greater than zero"

# Check if loss exists
if loss_current < AUTO_CLOSE_THRESHOLD:
    ERROR: "No loss to settle"

# Check if payment doesn't exceed pending
total_share_pct = my_share_pct + company_share_pct
pending_before_raw = (loss_current * total_share_pct) / 100
pending_before = round_share(pending_before_raw)  # ROUND DOWN
if amount > pending_before:
    ERROR: "Payment exceeds pending amount"
```

#### Section 3: Calculate Capital Closed
```python
from core.utils.money import round_capital

# Formula: capital_closed = payment × 100 / share_pct
capital_closed_raw = (amount * Decimal(100)) / total_pct

# Validate capital_closed doesn't exceed loss
if capital_closed_raw > loss_current:
    ERROR: "Capital closed exceeds loss"

# Round to 2 decimal places (capital-space: ROUND_HALF_UP)
capital_closed = round_capital(capital_closed_raw)
```

#### Section 4: Reduce Loss
```python
from core.utils.money import round_capital, AUTO_CLOSE_THRESHOLD

# Reduce DERIVED loss by capital closed
loss_new = loss_current - capital_closed

# Guard against negative loss
if loss_new < 0:
    ERROR: "Settlement would create negative loss"

# Clamp to zero
loss_new = max(loss_new, 0)

# Round to 2 decimal places (capital-space: ROUND_HALF_UP)
loss_new = round_capital(loss_new)

# Auto-close if below threshold
if loss_new < AUTO_CLOSE_THRESHOLD:
    loss_new = Decimal(0)
    loss_snapshot.is_settled = True
```

#### Section 5: Re-derive CAPITAL
```python
# CAPITAL is ALWAYS derived: CAPITAL = CB + LOSS
if loss_new >= AUTO_CLOSE_THRESHOLD:
    # Partial settlement: CAPITAL = CB (frozen) + LOSS (updated)
    old_balance_new = current_balance + loss_new
else:
    # Full settlement: CAPITAL = CB (frozen)
    old_balance_new = current_balance
    loss_new = Decimal(0)
```

#### Section 6: Recalculate Pending
```python
from core.utils.money import round_share

if loss_new >= AUTO_CLOSE_THRESHOLD:
    # Calculate pending from updated remaining Loss (share-space: round DOWN)
    client_payable_raw = (loss_new * total_pct) / Decimal(100)
    client_payable = round_share(client_payable_raw)  # ROUND DOWN
    pending_new = client_payable
else:
    # Fully settled
    pending_new = Decimal(0)
```

#### Section 7: Create SETTLEMENT Transaction
```python
from core.utils.money import round_share

# Calculate share breakdown (share-space: round DOWN)
if client_exchange.client.is_company_client:
    my_share_amount_raw = (amount * my_share_pct) / total_pct
    my_share_amount = round_share(my_share_amount_raw)  # ROUND DOWN
    company_share_amount_raw = amount - my_share_amount
    company_share_amount = round_share(company_share_amount_raw)  # ROUND DOWN
else:
    my_share_amount = round_share(amount)  # ROUND DOWN
    company_share_amount = Decimal(0)

# Create SETTLEMENT transaction
transaction = Transaction.objects.create(
    client_exchange=locked_client_exchange,
    date=settlement_date,
    transaction_type=Transaction.TYPE_SETTLEMENT,
    amount=amount,
    capital_closed=capital_closed,  # Audit trail
    client_share_amount=Decimal(0),
    your_share_amount=my_share_amount,
    company_share_amount=company_share_amount,
    note=f"Share settlement: ₹{amount} (capital_closed: ₹{capital_closed})"
)
```

#### Section 8: Update Cached Old Balance
```python
# Update cached_old_balance in ClientExchange (DISPLAY CACHE, not source of truth)
# ✅ FIX ISSUE 5: cached_old_balance is a performance cache, ledger is source of truth
locked_client_exchange.cached_old_balance = old_balance_new
locked_client_exchange.balance_last_updated = timezone.now()
locked_client_exchange.save(update_fields=['cached_old_balance', 'balance_last_updated'])
```

### Helper Function: `LossSnapshot.get_remaining_loss()`

**Location**: `core/models.py`

**Purpose**: Derive remaining loss from original loss and settlements

**✅ CRITICAL FIX (ISSUE 1)**: Uses transaction `date` (not `created_at`) to handle backdated settlements

**Code**:
```python
def get_remaining_loss(self):
    """
    ✅ FIX ISSUE 1: Uses transaction date (not created_at) to handle backdated settlements.
    This is CRITICAL - backdated settlements are very common in accounting.
    """
    from .models import Transaction
    from django.db.models import Sum
    
    total_capital_closed = Transaction.objects.filter(
        client_exchange=self.client_exchange,
        transaction_type=Transaction.TYPE_SETTLEMENT,
        capital_closed__isnull=False,
        date__gte=self.balance_record.date  # ✅ Use transaction date, not created_at
    ).aggregate(total=Sum("capital_closed"))["total"] or Decimal(0)
    return max(self.loss_amount - total_capital_closed, Decimal(0))
```

**Why This Matters**:
- `created_at` = when transaction was entered in system
- `date` = when transaction actually occurred (can be backdated)
- Using `created_at` would ignore backdated settlements, causing incorrect remaining loss

### Helper Function: `calculate_share_split()`

**Location**: `core/utils/money.py`

**Purpose**: Calculate share split from loss amount with guaranteed no leakage

**✅ CORRECT IMPLEMENTATION**: This is the ONLY correct way to split shares

**Code**:
```python
def calculate_share_split(
    loss: Decimal,
    my_pct: Decimal,
    company_pct: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    """
    Returns: (my_amount, company_amount, total_payable)
    
    Algorithm:
    1. Calculate RAW share-space amounts
    2. Round TOTAL first (client-facing amount)
    3. Round ONLY ONE SIDE (my_amount)
    4. Give remainder to the other side (NO ROUNDING)
    
    Guarantees:
    - total_payable is rounded DOWN
    - my_amount is rounded DOWN
    - company_amount absorbs remainder
    - my_amount + company_amount == total_payable (ALWAYS)
    """
    total_pct = my_pct + company_pct
    raw_total = (loss * total_pct) / Decimal(100)
    raw_my = (loss * my_pct) / Decimal(100)
    
    total_payable = round_share(raw_total)  # Round TOTAL first
    my_amount = round_share(raw_my)  # Round ONE side
    company_amount = total_payable - my_amount  # Remainder (NO rounding)
    
    return my_amount, company_amount, total_payable
```

**Example**:
```python
loss = Decimal("95")
my_pct = Decimal("1")
company_pct = Decimal("9")

my, company, total = calculate_share_split(loss, my_pct, company_pct)
# Returns: (0.9, 8.6, 9.5)
# Verification: 0.9 + 8.6 = 9.5 ✅
```

**Why This Matters**:
- Prevents money "disappearing" due to double rounding
- Ensures ledger safety: `my + company == total` (always)
- Used for all loss-based share calculations

---

## 📊 COMPLETE EXAMPLES

### Example 1: Full Payment

**Initial State**:
- Original Loss = ₹60
- Current Balance = ₹40
- Share % = 10%
- Pending = ₹6.0

**User Action**: Client pays ₹6.0 (full payment)

**Process**:
1. Capital Closed = (₹6 × 100) / 10 = ₹60
2. Remaining Loss = ₹60 - ₹60 = ₹0
3. CAPITAL = ₹40 + ₹0 = ₹40
4. Pending = ₹0 × 10% = ₹0
5. LossSnapshot.is_settled = True

**Final State**:
- Original Loss = ₹60 (frozen, immutable)
- Remaining Loss = ₹0 (derived)
- Current Balance = ₹40 (frozen)
- CAPITAL = ₹40 (derived)
- Pending = ₹0

### Example 2: Partial Payment (50%)

**Initial State**:
- Original Loss = ₹60
- Current Balance = ₹40
- Share % = 10%
- Pending = ₹6.0

**User Action**: Client pays ₹3.0 (50% payment)

**Process**:
1. Capital Closed = (₹3 × 100) / 10 = ₹30
2. Remaining Loss = ₹60 - ₹30 = ₹30
3. CAPITAL = ₹40 + ₹30 = ₹70
4. Pending = ₹30 × 10% = ₹3.0 (rounded down)
5. LossSnapshot.is_settled = False

**Final State**:
- Original Loss = ₹60 (frozen, immutable)
- Remaining Loss = ₹30 (derived)
- Current Balance = ₹40 (frozen)
- CAPITAL = ₹70 (derived)
- Pending = ₹3.0

### Example 3: Multiple Partial Payments

**Initial State**:
- Original Loss = ₹100
- Current Balance = ₹50
- Share % = 10%
- Pending = ₹10.0

**Payment 1**: Client pays ₹3.0
- Capital Closed = ₹30
- Remaining Loss = ₹70
- CAPITAL = ₹80
- Pending = ₹7.0

**Payment 2**: Client pays ₹4.0
- Capital Closed = ₹40
- Remaining Loss = ₹30
- CAPITAL = ₹60
- Pending = ₹3.0

**Payment 3**: Client pays ₹3.0
- Capital Closed = ₹30
- Remaining Loss = ₹0
- CAPITAL = ₹50
- Pending = ₹0
- LossSnapshot.is_settled = True

**Final State**:
- Original Loss = ₹100 (frozen, immutable)
- Remaining Loss = ₹0 (derived)
- Current Balance = ₹50 (frozen)
- CAPITAL = ₹50 (derived)
- Pending = ₹0

---

## ✅ VALIDATION RULES

### Rule 1: Payment Must Be Positive
```python
if amount <= Decimal(0):
    ERROR: "Amount must be greater than zero"
```

### Rule 2: Active Loss Must Exist
```python
if not loss_snapshot or loss_snapshot.is_settled:
    ERROR: "No active loss to settle"
```

**✅ FIX ISSUE 6**: Also validated at model level in `Transaction.clean()`:
```python
def clean(self):
    if self.transaction_type == Transaction.TYPE_SETTLEMENT:
        if not LossSnapshot.objects.filter(
            client_exchange=self.client_exchange,
            is_settled=False
        ).exists():
            raise ValidationError("Cannot create SETTLEMENT without active loss")
```

### Rule 3: Loss Must Be Above Threshold
```python
if loss_current < AUTO_CLOSE_THRESHOLD:
    ERROR: "No loss to settle"
```

### Rule 4: Payment Cannot Exceed Pending (RAW Validation)
```python
# ✅ FIX ISSUE 3: Validate against RAW pending, not rounded
pending_raw = (loss_current * total_pct) / 100
pending_display = round_share(pending_raw)  # For display only
if amount > pending_raw:  # Validate against RAW, not rounded
    ERROR: "Payment exceeds pending amount"
```

**Why This Matters**:
- Example: Raw pending = ₹3.09, Rounded pending = ₹3.0
- Client tries to pay ₹3.05
- ❌ WRONG: Validate against ₹3.0 → Rejected (incorrect)
- ✅ CORRECT: Validate against ₹3.09 → Accepted (correct)

### Rule 5: Capital Closed Cannot Exceed Loss
```python
capital_closed_raw = (amount * 100) / total_pct
if capital_closed_raw > loss_current:
    ERROR: "Capital closed exceeds loss"
```

### Rule 6: Loss Cannot Become Negative
```python
loss_new = loss_current - capital_closed
if loss_new < 0:
    ERROR: "Settlement would create negative loss"
```

### Rule 7: CAPITAL Must Be >= CB
```python
if old_balance_new < current_balance:
    ERROR: "Settlement invariant violation"
```

### Rule 8: Share Percentage Must Be Valid
```python
if total_pct <= 0:
    ERROR: "Invalid share percentage"
```

---

## 🔧 TROUBLESHOOTING

### Issue 1: "Payment exceeds pending amount"

**Cause**: User entered amount > pending amount

**Solution**: 
- Check pending amount in UI
- Enter amount ≤ pending amount
- System validates this automatically

### Issue 2: "No active loss to settle"

**Cause**: No active LossSnapshot exists

**Solution**:
- Check if loss exists
- LossSnapshot may be marked as settled
- Create new loss by recording balance change

### Issue 3: "Capital closed exceeds loss"

**Cause**: Payment would close more loss than exists

**Solution**:
- Check remaining loss amount
- Reduce payment amount
- System validates this automatically

### Issue 4: "Settlement invariant violation"

**Cause**: Mathematical inconsistency detected

**Solution**:
- This is a system error
- Check database for corruption
- Contact support

### Issue 5: Pending amount shows incorrect value

**Cause**: Pending calculated from wrong source

**Solution**:
- Pending must come from `LossSnapshot.get_remaining_loss()`
- Never recalculate from `CAPITAL - CB`
- Check that LossSnapshot is not mutated

---

## 📚 KEY FILES

### Backend Files:
- `core/views.py` - Main settlement logic (`settle_payment()`)
- `core/models.py` - LossSnapshot model, `get_remaining_loss()` method, Transaction validation
- `core/utils/money.py` - Rounding utilities (`round_share()`, `round_capital()`, `AUTO_CLOSE_THRESHOLD`, `calculate_share_split()`)

### Frontend Files:
- `core/templates/core/pending/summary.html` - UI and JavaScript

### Database Models:
- `LossSnapshot` - Stores frozen loss values (immutable `loss_amount`)
- `Transaction` - Stores SETTLEMENT transactions with `capital_closed` (has `clean()` validation)
- `ClientExchange` - Stores `cached_old_balance` (DISPLAY CACHE, not source of truth)

### Recent Critical Fixes (Applied):

1. **ISSUE 1**: `get_remaining_loss()` now uses `date__gte=self.balance_record.date` (handles backdated settlements)
2. **ISSUE 2**: `AUTO_CLOSE_THRESHOLD` defined once in `core/utils/money.py` (single source of truth)
3. **ISSUE 3**: Pending validation uses RAW value, not rounded (prevents blocking valid payments)
4. **ISSUE 4**: Share split prevents leakage (company_share = amount - my_share, no rounding)
5. **ISSUE 5**: Documentation clarifies `cached_old_balance` is cache, not source of truth
6. **ISSUE 6**: Transaction model has `clean()` method preventing SETTLEMENT without active loss

---

## 🎯 SUMMARY

### Key Takeaways:

1. **LOSS is FROZEN** - Never recalculated, only reduced by settlements
2. **CAPITAL is DERIVED** - Always `CB + LOSS`, never source of truth
3. **SHARE-SPACE ROUNDS DOWN** - Prevents over-collection
4. **CAPITAL-SPACE ROUNDS HALF_UP** - Standard accounting
5. **IMMUTABLE LossSnapshot** - `loss_amount` never changes, `remaining_loss` is derived
6. **ATOMIC TRANSACTIONS** - All operations happen atomically
7. **INVARIANT CHECKS** - System validates mathematical consistency

### Formula Summary:

```
Capital Closed = (Payment × 100) / Share %
Remaining Loss = Original Loss - Sum(Capital Closed)
CAPITAL = Current Balance + Remaining Loss
Pending = (Remaining Loss × Share %) / 100 (ROUNDED DOWN)
```

---

**Last Updated**: 2025-01-05
**Version**: 2.2 (with correct share split implementation)

### Recent Updates:
- ✅ Fixed `get_remaining_loss()` to use transaction date (handles backdated settlements)
- ✅ Single source of truth for `AUTO_CLOSE_THRESHOLD`
- ✅ Pending validation uses RAW value (prevents blocking valid payments)
- ✅ **NEW**: `calculate_share_split()` function prevents share leakage (guaranteed: my + company = total)
- ✅ Share split for payments: Round ONE side, give remainder to other (no rounding on remainder)
- ✅ Clarified `cached_old_balance` is cache, not source of truth
- ✅ Added Transaction validation to prevent SETTLEMENT without active loss

### Share Split Implementation:
- **For LOSS-based shares**: Use `calculate_share_split(loss, my_pct, company_pct)`
  - Algorithm: Round TOTAL first → Round ONE side → Give remainder to other
  - Example: Loss=95, My=1%, Company=9% → My=0.9, Company=8.6, Total=9.5 ✅
- **For PAYMENT splitting**: Round ONE side, give remainder to other (NO rounding on remainder)
  - Ensures: `my_share + company_share == payment_amount` (always)
