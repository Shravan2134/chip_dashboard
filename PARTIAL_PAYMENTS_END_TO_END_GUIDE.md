# Partial Payments & Record Payment Button - Complete End-to-End Guide

## 📋 Table of Contents

1. [Overview](#overview)
2. [Key Concepts](#key-concepts)
3. [UI Flow - Record Payment Button](#ui-flow---record-payment-button)
4. [Backend Flow - Settlement Processing](#backend-flow---settlement-processing)
5. [Partial Payment Logic](#partial-payment-logic)
6. [Full Payment Logic](#full-payment-logic)
7. [Database Updates](#database-updates)
8. [Verification & Safety Checks](#verification--safety-checks)
9. [Complete Example Walkthrough](#complete-example-walkthrough)
10. [Troubleshooting](#troubleshooting)

---

## Overview

This document explains the complete end-to-end flow of recording partial and full payments in the Transaction Hub system. It covers everything from clicking the "Record Share Settlement" button to database updates and verification.

### What This System Does

- **Records partial payments**: Client can pay any amount less than or equal to pending
- **Records full payments**: Client can pay the entire pending amount
- **Tracks loss settlement**: Each payment reduces the trading loss
- **Updates pending amounts**: Pending is always recalculated from remaining loss
- **Maintains audit trail**: All transactions are recorded with full details

---

## Key Concepts

### 1. Trading Loss (Capital Space)

- **What it is**: The difference between Capital (Old Balance) and Current Balance when CB < Capital
- **Formula**: `LOSS = max(CAPITAL - CB, 0)`
- **Frozen**: When a loss occurs, it's frozen in a `LossSnapshot` with the original amount
- **Immutable**: `LossSnapshot.loss_amount` never changes
- **Reduced by**: SETTLEMENT transactions only

### 2. Client Payable (Share Space)

- **What it is**: The share portion of the loss that the client must pay
- **Formula**: `Pending = (Remaining Loss × Total Share %) / 100`
- **Rounded**: Always rounded DOWN (share-space rounding)
- **Example**: If remaining loss = ₹900, share = 10%, then pending = ₹90.0

### 3. Capital Closed

- **What it is**: The amount of capital (loss) that is closed by a payment
- **Formula**: `Capital Closed = (Payment Amount × 100) / Total Share %`
- **Rounded**: Always rounded HALF-UP (capital-space rounding)
- **Example**: If payment = ₹10, share = 10%, then capital_closed = ₹100

### 4. Remaining Loss

- **What it is**: The loss amount still remaining after all settlements
- **Formula**: `Remaining Loss = Original Loss - SUM(All Capital Closed from Settlements)`
- **Derived**: Always calculated from database, never stored
- **Source of Truth**: `LossSnapshot.get_remaining_loss()` method

### 5. Old Balance (Capital)

- **What it is**: The accounting baseline for profit/loss calculation
- **Formula**: `CAPITAL = CB + LOSS` (when loss exists)
- **Derived**: Always calculated, never manually set
- **Updated**: After each settlement, CAPITAL = CB + Remaining Loss

---

## UI Flow - Record Payment Button

### Step 1: User Clicks "Record Share Settlement" Button

**Location**: `/pending/` page, in the "Clients Owe You" section

**Button HTML**:
```html
<button type="button" onclick="showSettlementForm(...)">
    Record Share Settlement
</button>
```

**What Happens**:
1. JavaScript function `showSettlementForm()` is called
2. Function receives these parameters:
   - `clientId`: Client ID
   - `clientExchangeId`: Client-Exchange ID
   - `clientName`: Client name (for display)
   - `exchangeName`: Exchange name (for display)
   - `pendingRaw`: Raw pending amount (before rounding)
   - `totalSharePct`: Total share percentage (e.g., 10%)

### Step 2: Modal Form Opens

**JavaScript Function**: `showSettlementForm()`

**What It Does**:
1. Sets form action URL based on client type:
   - My Clients → `/my-clients/settle-payment/`
   - Company Clients → `/company-clients/settle-payment/`
2. Populates form fields:
   - Client name (read-only)
   - Exchange name (read-only)
   - Amount input (editable, max = `pendingRaw`)
   - Date picker (defaults to today)
3. Sets validation attributes:
   - `data-raw-max`: Raw pending amount (for validation)
   - `data-combined-share`: Display pending amount
   - `max`: Raw pending amount (HTML5 validation)
4. Shows modal dialog

**Key Code**:
```javascript
// Set max amount to RAW pending (not rounded)
amountInput.max = pendingRawValue;
amountInput.setAttribute('data-raw-max', pendingRawValue);
amountInput.setAttribute('data-combined-share', pendingDisplayValue);
```

### Step 3: User Enters Payment Details

**User Actions**:
1. Enters payment amount (e.g., ₹10)
2. Selects payment date (defaults to today)
3. Optionally adds a note
4. Clicks "Record Payment" button

**Validation (Client-Side)**:
- Amount must be > 0
- Amount must be ≤ raw pending (not rounded)
- Date must be selected
- Client and exchange IDs must be present

**JavaScript Function**: `handleFormSubmit()`

**Validation Code**:
```javascript
// Validate against RAW pending (not rounded)
const rawMax = parseFloat(amountInput.getAttribute('data-raw-max')) || 0;
if (rawMax > 0 && enteredAmount > rawMax) {
    alert(`Payment amount exceeds pending amount`);
    return false; // Block submission
}
```

### Step 4: Form Submission

**What Happens**:
1. JavaScript validates all fields
2. Shows confirmation dialog: "Are you sure you want to record a payment of ₹X?"
3. If confirmed, form submits via POST to settlement URL
4. Form data sent:
   - `client_id`: Client ID
   - `client_exchange_id`: Client-Exchange ID
   - `amount`: Payment amount (e.g., "10")
   - `date`: Payment date (e.g., "2025-01-15")
   - `payment_type`: "client_pays"
   - `report_type`: Current report type filter
   - `client_type`: Current client type filter
   - `csrfmiddlewaretoken`: CSRF token

**JavaScript Code**:
```javascript
// Form will submit normally - don't prevent default
return true; // Allow form submission
```

---

## Backend Flow - Settlement Processing

### Step 1: Request Received

**View Function**: `settle_payment(request)`

**Location**: `core/views.py`

**What Happens**:
1. Extracts POST data
2. Converts amount to Decimal (CRITICAL: prevents int/float mixing)
3. Validates required fields

**Code**:
```python
# ✅ CRITICAL: Convert to Decimal immediately
amount_raw = request.POST.get("amount", "0") or "0"
amount = Decimal(str(amount_raw))  # Convert to Decimal FIRST
amount = round_share(amount)  # Then round (share-space: round DOWN)

tx_date = request.POST.get("date")
payment_type = request.POST.get("payment_type", "client_pays")
```

### Step 2: Enter Atomic Transaction Block

**Why Atomic**:
- Ensures all database updates happen together
- Prevents partial updates if something fails
- Locks database rows to prevent race conditions

**Code**:
```python
with db_transaction.atomic():
    # Lock the ClientExchange row
    locked_client_exchange = ClientExchange.objects.select_for_update().get(
        pk=client_exchange.pk
    )
```

### Step 3: Get Active Loss Snapshot

**What It Does**:
- Finds the active (unsettled) loss for this client-exchange
- Retrieves frozen values: original loss, share percentages, frozen balance

**Code**:
```python
loss_snapshot = LossSnapshot.objects.get(
    client_exchange=locked_client_exchange,
    is_settled=False
)
```

**If No Active Loss**:
- Shows error: "Cannot record payment: No active loss to settle"
- Redirects back to pending page

### Step 4: Get Frozen State

**Frozen Values** (Never Change):
- `original_loss`: The original loss amount (immutable)
- `current_balance`: Exchange balance at loss creation (frozen)
- `my_share_pct`: Your share percentage (frozen)
- `company_share_pct`: Company share percentage (frozen)

**Derived Values** (Calculated):
- `loss_current`: Remaining loss (derived from settlements)
- `old_balance`: Capital = CB + LOSS (derived)
- `total_pct`: Total share percentage (derived)

**Code**:
```python
# ✅ CRITICAL: Convert ALL values to Decimal
original_loss = Decimal(str(loss_snapshot.loss_amount))  # FROZEN
loss_current = loss_snapshot.get_remaining_loss()  # DERIVED
loss_current = Decimal(str(loss_current))  # Ensure Decimal

current_balance = Decimal(str(loss_snapshot.balance_record.remaining_balance))  # FROZEN
old_balance = current_balance + loss_current  # DERIVED: CAPITAL = CB + LOSS

my_share_pct_effective = Decimal(str(loss_snapshot.my_share_pct))  # FROZEN
company_share_pct = Decimal(str(loss_snapshot.company_share_pct))  # FROZEN

if locked_client_exchange.client.is_company_client:
    total_pct = my_share_pct_effective + company_share_pct  # Usually 10%
else:
    total_pct = my_share_pct_effective  # Usually 10%
total_pct = Decimal(str(total_pct))  # Ensure Decimal
```

### Step 5: Validate Payment

**Validations**:

1. **Amount > 0**:
   ```python
   if amount <= Decimal(0):
       messages.error(request, "Amount must be greater than zero")
       return redirect(...)
   ```

2. **Amount ≤ Raw Pending**:
   ```python
   pending_raw = (loss_current * total_pct) / Decimal(100)
   pending_display = round_share(pending_raw)  # For display only
   
   if amount > pending_raw:  # ✅ Validate against RAW, not rounded
       messages.error(request, f"Payment exceeds pending amount")
       return redirect(...)
   ```

3. **Loss Exists**:
   ```python
   if loss_current < AUTO_CLOSE_THRESHOLD:
       messages.error(request, "No loss to settle")
       return redirect(...)
   ```

4. **Share Percentage Valid**:
   ```python
   if total_pct <= 0:
       messages.error(request, "Invalid share percentage")
       return redirect(...)
   ```

### Step 6: Calculate Capital Closed

**Formula**:
```
Capital Closed = (Payment Amount × 100) / Total Share %
```

**Example**:
- Payment = ₹10
- Total Share % = 10%
- Capital Closed = (10 × 100) / 10 = ₹100

**Code**:
```python
capital_closed_raw = (amount * Decimal(100)) / total_pct

# Validate capital_closed doesn't exceed loss
if capital_closed_raw > loss_current:
    messages.error(request, "Capital closed exceeds loss")
    return redirect(...)

# Round AFTER validation (capital-space: ROUND_HALF_UP)
capital_closed = round_capital(capital_closed_raw)
```

### Step 7: Calculate Share Breakdown

**For Company Clients**:
- Split payment between your share (1%) and company share (9%)
- Use `calculate_share_split()` to prevent rounding leakage

**For My Clients**:
- Full payment goes to your share

**Code**:
```python
if locked_client_exchange.client.is_company_client:
    my_share_amount_raw = (amount * my_share_pct_effective) / total_pct
    my_share_amount = round_share(my_share_amount_raw)  # Round DOWN
    # Give remainder to company (NO rounding) to prevent leakage
    company_share_amount = amount - my_share_amount
else:
    my_share_amount = round_share(amount)  # Round DOWN
    company_share_amount = Decimal(0)
```

### Step 8: Create SETTLEMENT Transaction

**CRITICAL**: Transaction is created FIRST, before recalculating remaining loss

**Why First**:
- `get_remaining_loss()` queries the database for SETTLEMENT transactions
- If transaction doesn't exist yet, it won't be counted
- Creating it first ensures it's included in the recalculation

**Code**:
```python
settlement_date = datetime.strptime(tx_date, "%Y-%m-%d").date()

transaction = Transaction.objects.create(
    client_exchange=locked_client_exchange,
    date=settlement_date,  # ✅ CRITICAL: Date must be set
    transaction_type=Transaction.TYPE_SETTLEMENT,
    amount=amount,
    capital_closed=capital_closed,  # Audit trail
    client_share_amount=Decimal(0),  # Client pays
    your_share_amount=my_share_amount,  # Your share
    company_share_amount=company_share_amount,  # Company share (if applicable)
    note=note_text,
)
```

### Step 9: Recalculate Remaining Loss

**CRITICAL**: Re-read from database AFTER transaction is created

**Why Re-read**:
- `get_remaining_loss()` queries all SETTLEMENT transactions
- Our new transaction is now in the database
- This ensures accurate calculation

**Code**:
```python
# ✅ CRITICAL: Recalculate AFTER transaction is created
remaining_loss = loss_snapshot.get_remaining_loss()
remaining_loss = round_capital(remaining_loss)  # Round capital-space

# Guard against negative (should never happen)
if remaining_loss < 0:
    remaining_loss = Decimal(0)
```

### Step 10: Update LossSnapshot Status

**Rule**: Only mark as settled if remaining loss is effectively zero

**Code**:
```python
if remaining_loss <= AUTO_CLOSE_THRESHOLD:
    loss_snapshot.is_settled = True
    loss_snapshot.save(update_fields=['is_settled'])
    remaining_loss = Decimal(0)  # Normalize to zero
else:
    # ✅ CRITICAL: MUST remain False if loss still exists
    if loss_snapshot.is_settled:
        loss_snapshot.is_settled = False
        loss_snapshot.save(update_fields=['is_settled'])
```

### Step 11: Derive New Capital (Old Balance)

**Formula**: `CAPITAL = CB + LOSS`

**Code**:
```python
if remaining_loss > epsilon:
    # LOSS exists: CAPITAL = CB + LOSS
    old_balance_new = cb_snapshot + remaining_loss
else:
    # Full settlement: CAPITAL = CB
    old_balance_new = cb_snapshot
```

### Step 12: Calculate New Pending

**CRITICAL RULE**: Pending is ALWAYS derived from remaining loss, NEVER from payment

**Formula**: `Pending = (Remaining Loss × Total Share %) / 100`

**Code**:
```python
# ✅ CORRECT: Derive from remaining_loss
if remaining_loss >= AUTO_CLOSE_THRESHOLD:
    if locked_client_exchange.client.is_company_client:
        my_share_from_loss, company_share_from_loss, client_payable = calculate_share_split(
            loss=remaining_loss,
            my_pct=my_share_pct_effective,
            company_pct=company_share_pct,
        )
    else:
        client_payable_raw = (remaining_loss * total_pct) / Decimal(100)
        client_payable = round_share(client_payable_raw)  # Round DOWN
    
    pending_new = client_payable
else:
    # Fully settled
    pending_new = Decimal(0)
```

### Step 13: Update Cached Old Balance

**What It Is**: Performance cache (not source of truth)

**Code**:
```python
locked_client_exchange.cached_old_balance = old_balance_new
locked_client_exchange.balance_last_updated = timezone.now()
locked_client_exchange.save(update_fields=['cached_old_balance', 'balance_last_updated'])
```

### Step 14: Update Ledgers

**CRITICAL RULE**: Set to `pending_new` (derived from remaining_loss), NOT subtract payment

**For My Clients**:
```python
outstanding, _ = OutstandingAmount.objects.get_or_create(
    client_exchange=locked_client_exchange,
    defaults={"outstanding_amount": Decimal(0)}
)
# ✅ CORRECT: Set to pending_new (derived from remaining_loss)
outstanding.outstanding_amount = pending_new
outstanding.save()
```

**For Company Clients**:
```python
tally, _ = TallyLedger.objects.get_or_create(
    client_exchange=locked_client_exchange,
    defaults={...}
)
# ✅ CORRECT: Set to pending_new (derived from remaining_loss)
tally.client_owes_you = pending_new
tally.save()
```

### Step 15: Verify Settlement Worked

**CRITICAL**: Re-read from database to confirm loss decreased

**Why Verify**:
- Ensures transaction was created correctly
- Ensures date was set correctly
- Prevents fake success messages

**Code**:
```python
# ✅ CRITICAL: Verify settlement actually worked
remaining_loss_after = loss_snapshot.get_remaining_loss()
remaining_loss_after = Decimal(str(remaining_loss_after))

# ✅ VERIFICATION: Loss must have decreased
if remaining_loss_after > loss_current:
    raise RuntimeError(f"Settlement verification failed: Loss increased")

# ✅ VERIFICATION: If loss didn't decrease, settlement didn't work
if remaining_loss_after >= loss_current and remaining_loss_after > AUTO_CLOSE_THRESHOLD:
    raise RuntimeError(f"Settlement verification failed: Loss did not decrease")
```

### Step 16: Show Success Message

**Only After Verification Passes**:

**Code**:
```python
# ✅ CRITICAL: Success message ONLY after DB verification passes
if not locked_client_exchange.client.is_company_client:
    success_msg = f"Payment of ₹{amount} recorded for {client.name} - {exchange.name}. Remaining pending: ₹{pending_new}"
else:
    success_msg = f"Company payment of ₹{amount} recorded for {client.name} - {exchange.name}. Your share (1%): ₹{my_share_amount}. Remaining pending: ₹{pending_new}"

messages.success(request, success_msg)
```

### Step 17: Redirect

**Code**:
```python
redirect_url = f"?section=clients-owe&report_type={report_type}"
if client_type_filter and client_type_filter != 'all':
    redirect_url += f"&client_type={client_type_filter}"
return redirect(reverse("pending:summary") + redirect_url)
```

---

## Partial Payment Logic

### What Is a Partial Payment?

A partial payment is any payment amount less than the full pending amount.

**Example**:
- Pending: ₹90.0
- Payment: ₹10.0 (partial)
- Remaining Pending: ₹80.0

### How Partial Payments Work

1. **User enters partial amount** (e.g., ₹10)
2. **System calculates capital closed**:
   - Capital Closed = (10 × 100) / 10 = ₹100
3. **System creates SETTLEMENT transaction**:
   - `amount` = ₹10
   - `capital_closed` = ₹100
4. **System recalculates remaining loss**:
   - Remaining Loss = Original Loss - SUM(Capital Closed)
   - Example: 900 - 100 = ₹800
5. **System derives new pending**:
   - New Pending = (800 × 10) / 100 = ₹80.0
6. **System updates ledgers**:
   - Ledger = ₹80.0 (NOT ₹90 - ₹10 = ₹80)
7. **System verifies**:
   - Re-reads remaining loss from DB
   - Confirms loss decreased
   - Shows success message

### Key Rules for Partial Payments

1. **Pending is NEVER reduced by payment amount**
   - ❌ WRONG: `pending_new = pending_old - payment`
   - ✅ CORRECT: `pending_new = (remaining_loss × total_pct) / 100`

2. **Remaining loss is ALWAYS recalculated from database**
   - ❌ WRONG: `remaining_loss = remaining_loss - capital_closed`
   - ✅ CORRECT: `remaining_loss = loss_snapshot.get_remaining_loss()`

3. **is_settled is ONLY set when remaining_loss <= threshold**
   - ❌ WRONG: Set to True after any payment
   - ✅ CORRECT: Set to True only if `remaining_loss <= AUTO_CLOSE_THRESHOLD`

4. **All values MUST be Decimal**
   - ❌ WRONG: `amount = 10` (int)
   - ✅ CORRECT: `amount = Decimal("10")`

---

## Full Payment Logic

### What Is a Full Payment?

A full payment is when the payment amount equals (or is very close to) the pending amount.

**Example**:
- Pending: ₹90.0
- Payment: ₹90.0 (full)
- Remaining Pending: ₹0.0

### How Full Payments Work

1. **User enters full amount** (e.g., ₹90)
2. **System calculates capital closed**:
   - Capital Closed = (90 × 100) / 10 = ₹900
3. **System creates SETTLEMENT transaction**:
   - `amount` = ₹90
   - `capital_closed` = ₹900
4. **System recalculates remaining loss**:
   - Remaining Loss = 900 - 900 = ₹0
5. **System marks LossSnapshot as settled**:
   - `is_settled = True`
   - `remaining_loss = 0`
6. **System derives new pending**:
   - New Pending = (0 × 10) / 100 = ₹0.0
7. **System updates ledgers**:
   - Ledger = ₹0.0
8. **System verifies**:
   - Confirms remaining loss = 0
   - Shows success message

### Key Differences from Partial Payments

1. **LossSnapshot.is_settled = True**
   - Only happens when remaining loss <= threshold
   - Prevents further payments

2. **Pending becomes ₹0**
   - No more payments possible
   - Settlement button disappears

3. **Capital = Current Balance**
   - When loss = 0, CAPITAL = CB
   - Profit can now exist (if CB > CAPITAL)

---

## Database Updates

### Tables Updated

1. **Transaction**
   - New SETTLEMENT transaction created
   - Fields: `amount`, `capital_closed`, `date`, `your_share_amount`, `company_share_amount`

2. **LossSnapshot**
   - `is_settled` updated (if remaining_loss <= threshold)
   - `loss_amount` never changes (immutable)

3. **ClientExchange**
   - `cached_old_balance` updated (performance cache)
   - `balance_last_updated` timestamp updated

4. **OutstandingAmount** (My Clients)
   - `outstanding_amount` set to `pending_new`

5. **TallyLedger** (Company Clients)
   - `client_owes_you` set to `pending_new`

### Update Order

1. **Transaction created FIRST** (so it's included in remaining_loss calculation)
2. **Remaining loss recalculated** (from database)
3. **LossSnapshot updated** (if fully settled)
4. **ClientExchange updated** (cached_old_balance)
5. **Ledgers updated** (outstanding_amount or client_owes_you)

---

## Verification & Safety Checks

### Pre-Settlement Checks

1. **Active loss exists**
   - `LossSnapshot` with `is_settled=False` must exist

2. **Amount validation**
   - Amount > 0
   - Amount ≤ raw pending (not rounded)

3. **Loss validation**
   - Loss > threshold (not already settled)

4. **Share percentage validation**
   - Total share % > 0

5. **Capital closed validation**
   - Capital closed ≤ loss current

### Post-Settlement Verification

1. **Loss decreased**
   - `remaining_loss_after < loss_current`
   - Or `remaining_loss_after = 0` (if fully settled)

2. **Transaction exists**
   - SETTLEMENT transaction with correct `capital_closed` exists

3. **Date is set**
   - Transaction has a valid date (not NULL)

### Safety Checks

1. **Atomic transaction**
   - All updates happen together or not at all

2. **Row locking**
   - `select_for_update()` prevents race conditions

3. **Decimal safety**
   - All monetary values are Decimal (never int/float)

4. **Rounding consistency**
   - Share-space: ROUND_DOWN
   - Capital-space: ROUND_HALF_UP

---

## Complete Example Walkthrough

### Scenario

- **Client**: "Test Client"
- **Exchange**: "Test Exchange"
- **Original Loss**: ₹900
- **Share Percentage**: 10%
- **Initial Pending**: ₹90.0

### Payment 1: Partial Payment of ₹10

**Step 1: User Clicks Button**
- Button shows: "Record Share Settlement"
- Modal opens with pending: ₹90.0

**Step 2: User Enters Amount**
- Amount: ₹10
- Date: 2025-01-15
- Clicks "Record Payment"

**Step 3: Backend Processing**
```
1. Get active loss snapshot
   - original_loss = ₹900 (frozen)
   - loss_current = ₹900 (no settlements yet)

2. Validate payment
   - amount = ₹10 > 0 ✅
   - pending_raw = (900 × 10) / 100 = ₹90.0
   - amount (₹10) ≤ pending_raw (₹90.0) ✅

3. Calculate capital closed
   - capital_closed = (10 × 100) / 10 = ₹100

4. Create transaction
   - Transaction: amount=₹10, capital_closed=₹100, date=2025-01-15

5. Recalculate remaining loss
   - remaining_loss = 900 - 100 = ₹800

6. Update LossSnapshot
   - is_settled = False (loss still exists)

7. Derive new capital
   - old_balance_new = CB + 800

8. Calculate new pending
   - pending_new = (800 × 10) / 100 = ₹80.0

9. Update ledgers
   - outstanding_amount = ₹80.0

10. Verify
    - remaining_loss_after = ₹800 ✅ (decreased from ₹900)

11. Show success
    - "Payment of ₹10 recorded. Remaining pending: ₹80.0"
```

**Result**:
- Remaining Loss: ₹800
- Pending: ₹80.0
- Transaction created: ₹10 payment, ₹100 capital closed

### Payment 2: Another Partial Payment of ₹20

**Step 1: User Clicks Button**
- Button shows: "Record Share Settlement"
- Modal opens with pending: ₹80.0

**Step 2: User Enters Amount**
- Amount: ₹20
- Date: 2025-01-16
- Clicks "Record Payment"

**Step 3: Backend Processing**
```
1. Get active loss snapshot
   - original_loss = ₹900 (still frozen)
   - loss_current = ₹800 (from previous settlement)

2. Validate payment
   - amount = ₹20 > 0 ✅
   - pending_raw = (800 × 10) / 100 = ₹80.0
   - amount (₹20) ≤ pending_raw (₹80.0) ✅

3. Calculate capital closed
   - capital_closed = (20 × 100) / 10 = ₹200

4. Create transaction
   - Transaction: amount=₹20, capital_closed=₹200, date=2025-01-16

5. Recalculate remaining loss
   - remaining_loss = 900 - (100 + 200) = ₹600

6. Update LossSnapshot
   - is_settled = False (loss still exists)

7. Derive new capital
   - old_balance_new = CB + 600

8. Calculate new pending
   - pending_new = (600 × 10) / 100 = ₹60.0

9. Update ledgers
   - outstanding_amount = ₹60.0

10. Verify
    - remaining_loss_after = ₹600 ✅ (decreased from ₹800)

11. Show success
    - "Payment of ₹20 recorded. Remaining pending: ₹60.0"
```

**Result**:
- Remaining Loss: ₹600
- Pending: ₹60.0
- Total Settlements: ₹30 (₹10 + ₹20)
- Total Capital Closed: ₹300 (₹100 + ₹200)

### Payment 3: Full Payment of ₹60

**Step 1: User Clicks Button**
- Button shows: "Record Share Settlement"
- Modal opens with pending: ₹60.0

**Step 2: User Enters Amount**
- Amount: ₹60
- Date: 2025-01-17
- Clicks "Record Payment"

**Step 3: Backend Processing**
```
1. Get active loss snapshot
   - original_loss = ₹900 (still frozen)
   - loss_current = ₹600 (from previous settlements)

2. Validate payment
   - amount = ₹60 > 0 ✅
   - pending_raw = (600 × 10) / 100 = ₹60.0
   - amount (₹60) ≤ pending_raw (₹60.0) ✅

3. Calculate capital closed
   - capital_closed = (60 × 100) / 10 = ₹600

4. Create transaction
   - Transaction: amount=₹60, capital_closed=₹600, date=2025-01-17

5. Recalculate remaining loss
   - remaining_loss = 900 - (100 + 200 + 600) = ₹0

6. Update LossSnapshot
   - is_settled = True ✅ (loss fully settled)
   - remaining_loss = ₹0

7. Derive new capital
   - old_balance_new = CB (loss = 0)

8. Calculate new pending
   - pending_new = (0 × 10) / 100 = ₹0.0

9. Update ledgers
   - outstanding_amount = ₹0.0

10. Verify
    - remaining_loss_after = ₹0 ✅ (fully settled)

11. Show success
    - "Payment of ₹60 recorded. Remaining pending: ₹0.0"
```

**Result**:
- Remaining Loss: ₹0
- Pending: ₹0.0
- LossSnapshot.is_settled: True
- Settlement Complete ✅

---

## Troubleshooting

### Issue: "No active loss to settle"

**Cause**: No `LossSnapshot` with `is_settled=False` exists

**Solution**:
- Check if loss was already fully settled
- Check if loss snapshot exists at all
- Verify `is_settled` flag is not incorrectly set to True

### Issue: "Payment exceeds pending amount"

**Cause**: Payment amount > raw pending

**Solution**:
- Check if user entered amount correctly
- Verify raw pending calculation: `(remaining_loss × total_pct) / 100`
- Ensure UI validation uses raw pending (not rounded)

### Issue: "Settlement verification failed"

**Cause**: Loss did not decrease after settlement

**Possible Reasons**:
1. Transaction date is NULL (not counted in `get_remaining_loss()`)
2. Transaction not created correctly
3. Database transaction rolled back

**Solution**:
- Check transaction has valid date
- Check transaction was created successfully
- Check database transaction didn't roll back

### Issue: Pending shows ₹0 but loss still exists

**Cause**: `is_settled` was set to True too early

**Solution**:
- Check `is_settled` is only set when `remaining_loss <= AUTO_CLOSE_THRESHOLD`
- Verify `remaining_loss` calculation is correct
- Check for rounding errors

### Issue: "int object has no attribute 'quantize'"

**Cause**: int or float value passed to rounding function

**Solution**:
- Ensure all values are converted to Decimal: `Decimal(str(value))`
- Check POST data conversion
- Verify all calculations use Decimal

---

## Summary

### Key Takeaways

1. **Pending is ALWAYS derived from remaining loss**
   - Never calculated from payment amount
   - Formula: `(remaining_loss × total_pct) / 100`

2. **Remaining loss is ALWAYS recalculated from database**
   - Never stored or updated directly
   - Formula: `original_loss - SUM(capital_closed from settlements)`

3. **Transaction is created FIRST**
   - Before recalculating remaining loss
   - Ensures it's included in the calculation

4. **All values MUST be Decimal**
   - Prevents int/float mixing errors
   - Ensures accurate calculations

5. **Verification is CRITICAL**
   - Re-reads from database
   - Confirms loss decreased
   - Prevents fake success messages

6. **Atomic transactions ensure consistency**
   - All updates happen together
   - Prevents partial updates

### Flow Diagram

```
User Clicks Button
    ↓
Modal Opens (showSettlementForm)
    ↓
User Enters Amount & Date
    ↓
Form Validation (handleFormSubmit)
    ↓
POST to settle_payment view
    ↓
Enter Atomic Block
    ↓
Get Active Loss Snapshot
    ↓
Get Frozen State
    ↓
Validate Payment
    ↓
Calculate Capital Closed
    ↓
Calculate Share Breakdown
    ↓
Create SETTLEMENT Transaction (FIRST)
    ↓
Recalculate Remaining Loss (from DB)
    ↓
Update LossSnapshot (if fully settled)
    ↓
Derive New Capital
    ↓
Calculate New Pending (from remaining_loss)
    ↓
Update Cached Old Balance
    ↓
Update Ledgers (set to pending_new)
    ↓
Verify Settlement Worked
    ↓
Show Success Message
    ↓
Redirect to Pending Page
```

---

## End of Document

This document covers the complete end-to-end flow of partial and full payments in the Transaction Hub system. All critical rules, formulas, and safety checks are documented to ensure accurate and reliable payment processing.

