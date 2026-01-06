# PARTIAL PAYMENTS - COMPLETE GUIDE

**Everything You Need to Know: UI, Recording, Formulas, Logic, Code**

---

## 📋 TABLE OF CONTENTS

1. [What Are Partial Payments?](#what-are-partial-payments)
2. [UI Flow - How to Record](#ui-flow)
3. [Step-by-Step Recording Process](#recording-process)
4. [Core Formulas](#formulas)
5. [Backend Logic Explained](#backend-logic)
6. [Code Walkthrough](#code-walkthrough)
7. [Complete Examples](#examples)
8. [Validation Rules](#validation-rules)
9. [Troubleshooting](#troubleshooting)

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
   - Always from `LossSnapshot.loss_amount`, never recalculated

5. **Capital Closed**: Amount of loss that gets closed
   - Formula: `Capital Closed = (Payment × 100) / Share %`
   - This is what reduces the frozen Loss

### 🔒 CRITICAL RULES (NON-NEGOTIABLE)

1. **LOSS is FROZEN** - Stored in LossSnapshot, never recalculated
2. **CAPITAL is DERIVED** - Always `CB + LOSS`, never source of truth
3. **PROFIT exists ONLY when LOSS = 0** - Cannot have profit while loss exists
4. **LOSS reduced ONLY by SETTLEMENT** - Balance recovery never reduces loss
5. **CB is FROZEN when LOSS exists** - New balance records ignored
6. **Pending from FROZEN LOSS** - Always from LossSnapshot

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
| Total Loss | Frozen loss amount from LossSnapshot |
| My Share | Your share of the loss (1% for company clients, 10% for my clients) |
| Company Share | Company share (9% for company clients, 0 for my clients) |
| Combined Share | Total share (10% for company clients, 10% for my clients) |
| **Pending** | **What client owes (this is what you can collect)** |
| Action | **"Record Payment"** button |

### Step 3: Click "Record Payment" Button

1. Find the client you want to record payment for
2. Click the **"Record Payment"** button in the Action column
3. A modal form will pop up with payment details

### Step 4: Payment Modal Form

The modal shows:

```
┌─────────────────────────────────────────┐
│  Record Payment                        │
├─────────────────────────────────────────┤
│  Client: [Client Name] (read-only)     │
│  Exchange: [Exchange Name] (read-only) │
│                                         │
│  Amount to Pay: [₹6.00]                │
│  (Pre-filled with pending amount)      │
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
│  [Cancel]  [Record Payment]             │
└─────────────────────────────────────────┘
```

### Step 5: Enter Payment Details

1. **Amount Field**:
   - **Default**: Pre-filled with the full pending amount (e.g., ₹6.00)
   - **For Partial Payment**: Change it to any amount ≤ pending amount
   - **Example**: If pending is ₹6, you can enter ₹3 for partial payment
   - **Validation**: System prevents entering amount > pending

2. **Date Field**:
   - **Default**: Today's date
   - **Change**: You can select a different date if needed

3. **Note Field** (Optional):
   - Add any notes about this payment
   - Example: "Partial payment - first installment"
   - Example: "Payment via bank transfer"

### Step 6: Submit the Form

1. Click **"Record Payment"** button
2. The system will:
   - Validate the payment
   - Process the settlement
   - Update LossSnapshot (reduce frozen Loss)
   - Re-derive Old Balance
   - Recalculate pending amount
   - Create SETTLEMENT transaction
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
Loss (FROZEN in LossSnapshot) = ₹60
Current Balance (FROZEN in LossSnapshot) = ₹40
Old Balance (CAPITAL) = CB + Loss = ₹40 + ₹60 = ₹100 (DERIVED)
Share % = 10% (FROZEN in LossSnapshot)
Pending Amount = ₹60 × 10% = ₹6 (from frozen Loss)
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

# LOSS is FROZEN - never recalculated
loss_current = loss_snapshot.loss_amount  # ₹60 (FROZEN)

# CB is FROZEN when loss exists
current_balance = loss_snapshot.balance_record.remaining_balance  # ₹40 (FROZEN)

# CAPITAL is DERIVED from frozen values
old_balance = current_balance + loss_current  # ₹40 + ₹60 = ₹100 (DERIVED)

# Share percentages are FROZEN at loss creation time
my_share_pct = loss_snapshot.my_share_pct  # FROZEN
company_share_pct = loss_snapshot.company_share_pct  # FROZEN
```

**Result**:
- `loss_current = ₹60` (frozen)
- `current_balance = ₹40` (frozen)
- `old_balance = ₹100` (derived)

### **Step 2: Validate Payment**

**Code**:
```python
# Check if active loss snapshot exists
if not loss_snapshot or loss_snapshot.is_settled:
    ERROR: "No active loss to settle"

# Check if loss exists (from frozen snapshot)
AUTO_CLOSE_THRESHOLD = Decimal("0.01")
if loss_current < AUTO_CLOSE_THRESHOLD:
    ERROR: "No loss to settle"

# Check if payment is valid
if amount <= 0:
    ERROR: "Amount must be greater than zero"

# Check if payment doesn't exceed pending (from frozen loss)
total_share_pct = my_share_pct + company_share_pct  # 10%
pending_before = (loss_current * total_share_pct) / 100  # ₹6 (from frozen Loss)
if amount > pending_before:
    ERROR: "Payment exceeds pending amount"
```

**Result**: Validation passes ✓

### **Step 3: Convert Payment to Capital Closed**

**Code**:
```python
# Formula: capital_closed = payment × 100 / share_pct
capital_closed_raw = (amount * Decimal(100)) / total_share_pct
capital_closed_raw = (₹3 × 100) / 10 = ₹30

# Validate capital_closed doesn't exceed loss
if capital_closed_raw > loss_current:
    ERROR: "Capital closed exceeds loss"

# Round to 2 decimal places
capital_closed = capital_closed_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
capital_closed = ₹30.00
```

**Result**: `capital_closed = ₹30`

### **Step 4: Reduce Loss (LOSS-First Approach)**

**Code**:
```python
# Reduce FROZEN loss by capital closed
loss_new = loss_current - capital_closed
loss_new = ₹60 - ₹30 = ₹30

# Guard against negative loss
if loss_new < 0:
    ERROR: "Settlement would create negative loss"

# Clamp to zero (safety check)
loss_new = max(loss_new, 0)

# Round to 2 decimal places
loss_new = loss_new.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

# Auto-close if below threshold
AUTO_CLOSE_THRESHOLD = Decimal("0.01")
if loss_new < AUTO_CLOSE_THRESHOLD:
    loss_new = Decimal(0)
    loss_snapshot.is_settled = True
```

**Result**: `loss_new = ₹30`

### **Step 5: Update LossSnapshot**

**Code**:
```python
# Update FROZEN loss in snapshot
loss_snapshot.loss_amount = loss_new  # ₹30 (update frozen value)
if loss_new < AUTO_CLOSE_THRESHOLD:
    loss_snapshot.is_settled = True
loss_snapshot.save()
```

**Result**: LossSnapshot updated with `loss_amount = ₹30`

### **Step 6: Re-derive Old Balance**

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

**Result**: `old_balance_new = ₹70`

### **Step 7: Validate Invariants**

**Code**:
```python
# Invariant 1: CAPITAL = CB + LOSS (always true by definition)
capital_verify = current_balance + loss_new
capital_verify = ₹40 + ₹30 = ₹70
if abs(old_balance_new - capital_verify) > AUTO_CLOSE_THRESHOLD:
    ERROR: "Capital invariant violation"

# Invariant 2: Old Balance >= Current Balance (when loss exists)
if loss_new >= AUTO_CLOSE_THRESHOLD and old_balance_new < current_balance:
    ERROR: "Settlement would create profit while loss still exists"

# Invariant 3: Old Balance >= 0
if old_balance_new < 0:
    ERROR: "Old Balance would become negative"
```

**Result**: All invariants pass ✓

### **Step 8: Recalculate Pending (from FROZEN Loss)**

**Code**:
```python
# Pending is ALWAYS calculated from frozen Loss, never recalculated from CAPITAL - CB
if loss_new >= AUTO_CLOSE_THRESHOLD:
    # Calculate pending from updated frozen Loss
    pending_new = (loss_new * total_share_pct) / 100
    pending_new = (₹30 × 10) / 100 = ₹3
else:
    # Fully settled
    pending_new = Decimal(0)
```

**Result**: `pending_new = ₹3`

### **Step 9: Update Database**

**Code**:
```python
# Update cached Old Balance (display-only cache, ledger is truth)
client_exchange.cached_old_balance = old_balance_new  # ₹70
client_exchange.balance_last_updated = timezone.now()
client_exchange.save()

# Create SETTLEMENT transaction
Transaction.objects.create(
    client_exchange=client_exchange,
    date=settlement_date,
    transaction_type=Transaction.TYPE_SETTLEMENT,
    amount=₹3,  # Payment amount
    your_share_amount=₹0.3,  # 1% if company client
    company_share_amount=₹2.7,  # 9% if company client
    note="Partial payment: ₹3"
)
```

**Result**: Database updated, transaction created

### **Final State**:
```
Loss (FROZEN in LossSnapshot) = ₹30 (updated)
Current Balance (FROZEN in LossSnapshot) = ₹40 (unchanged)
Old Balance (CAPITAL) = CB + Loss = ₹40 + ₹30 = ₹70 (DERIVED)
Pending Amount = ₹30 × 10% = ₹3 (from frozen Loss)
```

---

## 📐 CORE FORMULAS

### 1. Loss (FROZEN - NEVER RECALCULATED)

```python
# ❌ WRONG - NEVER DO THIS:
# Loss = max(Old Balance - Current Balance, 0)

# ✅ CORRECT - Loss is FROZEN in LossSnapshot:
loss_snapshot = LossSnapshot.objects.get(
    client_exchange=client_exchange,
    is_settled=False
)
Loss = loss_snapshot.loss_amount  # FROZEN value
```

**Example**:
- Loss (frozen in LossSnapshot) = ₹60
- This value is set when loss is first detected and NEVER recalculated
- Only SETTLEMENT transactions can reduce this frozen value

### 2. Pending Amount Calculation (from FROZEN Loss)

```python
# Pending is ALWAYS calculated from frozen Loss, never recalculated
loss_snapshot = LossSnapshot.objects.get(
    client_exchange=client_exchange,
    is_settled=False
)
Loss = loss_snapshot.loss_amount  # FROZEN
total_share_pct = loss_snapshot.my_share_pct + loss_snapshot.company_share_pct
Pending = (Loss × total_share_pct) / 100
```

**Example**:
- Loss (frozen) = ₹60
- Total Share % = 10% (frozen in LossSnapshot)
- Pending = (₹60 × 10) / 100 = ₹6

### 3. Capital Closed Conversion

```python
# Convert payment (share space) to capital closed (capital space)
Capital Closed = (Payment Amount × 100) / Share Percentage
```

**Example**:
- Payment = ₹3
- Share % = 10%
- Capital Closed = (₹3 × 100) / 10 = ₹30

**Why this formula?**
- Client pays ₹3 (which is 10% of the loss share)
- This ₹3 represents 10% of the total share
- To find how much capital this closes: reverse the percentage
- Capital Closed = Payment × (100 / Share %)

### 4. New Loss After Payment

```python
# Reduce FROZEN loss by capital closed
Loss New = Loss Current - Capital Closed
```

**Example**:
- Loss Current (frozen) = ₹60
- Capital Closed = ₹30
- Loss New = ₹60 - ₹30 = ₹30

### 5. New Old Balance After Payment (DERIVED)

```python
# Old Balance (CAPITAL) is ALWAYS derived, never a source of truth
# Formula: CAPITAL = CB + LOSS
Old Balance New = Current Balance (frozen) + Loss New (updated in snapshot)
```

**Example**:
- Current Balance (frozen) = ₹40
- Loss New (updated in LossSnapshot) = ₹30
- Old Balance New = ₹40 + ₹30 = ₹70 (DERIVED)

### 6. Share Breakdown (Company Clients) - from FROZEN Loss

```python
# All shares calculated from FROZEN Loss
loss_snapshot = LossSnapshot.objects.get(...)
Loss = loss_snapshot.loss_amount  # FROZEN
my_share_pct = loss_snapshot.my_share_pct  # FROZEN (1%)
company_share_pct = loss_snapshot.company_share_pct  # FROZEN (9%)

# Total share (what client pays)
Total Share = (Loss × Total Share %) / 100
Total Share = (Loss × 10%) / 100

# Your share (1% for company clients)
Your Share = (Loss × 1%) / 100

# Company share (9% for company clients)
Company Share = (Loss × 9%) / 100
```

**Example**:
- Loss (frozen) = ₹60
- Total Share % (frozen) = 10%
- Your Share = (₹60 × 1%) / 100 = ₹0.6
- Company Share = (₹60 × 9%) / 100 = ₹5.4
- Total Share = ₹0.6 + ₹5.4 = ₹6.0 ✓

---

## ⚙️ BACKEND LOGIC EXPLAINED

### Settlement Flow (Loss Case)

**File**: `core/views.py` → `settle_payment()` function

#### **Phase 1: Get Frozen State**

```python
# Get active loss snapshot (FROZEN values)
loss_snapshot = LossSnapshot.objects.get(
    client_exchange=client_exchange,
    is_settled=False
)

# Get FROZEN values (never recalculated)
loss_current = loss_snapshot.loss_amount  # FROZEN
current_balance = loss_snapshot.balance_record.remaining_balance  # FROZEN
old_balance = current_balance + loss_current  # DERIVED

# Get FROZEN share percentages
my_share_pct = loss_snapshot.my_share_pct  # FROZEN
company_share_pct = loss_snapshot.company_share_pct  # FROZEN
total_share_pct = my_share_pct + company_share_pct  # Usually 10%
```

#### **Phase 2: Validate**

```python
# Validate active loss exists
if not loss_snapshot or loss_snapshot.is_settled:
    ERROR: "No active loss to settle"

if loss_current < AUTO_CLOSE_THRESHOLD:
    ERROR: "No loss to settle"

# Validate payment amount
if amount <= 0:
    ERROR: "Amount must be greater than zero"

# Validate payment doesn't exceed pending
pending_before = (loss_current * total_share_pct) / 100
if amount > pending_before:
    ERROR: "Payment exceeds pending amount"
```

#### **Phase 3: Calculate Capital Closed**

```python
# Convert payment to capital space
capital_closed_raw = (amount * Decimal(100)) / total_share_pct

# Validate capital_closed doesn't exceed loss
if capital_closed_raw > loss_current:
    ERROR: "Capital closed exceeds loss"

# Round to 2 decimal places
capital_closed = capital_closed_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

#### **Phase 4: Reduce Loss (LOSS-First Approach)**

```python
# Reduce FROZEN loss by capital closed
loss_new = loss_current - capital_closed

# Guard against negative loss
if loss_new < 0:
    ERROR: "Settlement would create negative loss"

# Clamp to zero
loss_new = max(loss_new, 0)

# Round to 2 decimal places
AUTO_CLOSE_THRESHOLD = Decimal("0.01")
loss_new = loss_new.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

# Auto-close if below threshold
if loss_new < AUTO_CLOSE_THRESHOLD:
    loss_new = Decimal(0)
    loss_snapshot.is_settled = True
```

#### **Phase 5: Update LossSnapshot**

```python
# Update FROZEN loss in snapshot
loss_snapshot.loss_amount = loss_new
if loss_new < AUTO_CLOSE_THRESHOLD:
    loss_snapshot.is_settled = True
loss_snapshot.save()
```

#### **Phase 6: Re-derive Old Balance**

```python
# CAPITAL is ALWAYS derived: CAPITAL = CB + LOSS
if loss_new >= AUTO_CLOSE_THRESHOLD:
    # Partial settlement: Old Balance = CB (frozen) + Loss (updated)
    old_balance_new = current_balance + loss_new
else:
    # Full settlement: Old Balance = Current Balance
    old_balance_new = current_balance
    loss_new = Decimal(0)
```

#### **Phase 7: Validate Invariants**

```python
# Invariant 1: CAPITAL = CB + LOSS (always true by definition)
capital_verify = current_balance + loss_new
if abs(old_balance_new - capital_verify) > AUTO_CLOSE_THRESHOLD:
    ERROR: "CAPITAL invariant violation: CAPITAL != CB + LOSS"

# Invariant 2: Old Balance >= Current Balance (when loss exists)
if loss_new >= AUTO_CLOSE_THRESHOLD and old_balance_new < current_balance:
    ERROR: "Settlement would create profit while loss still exists"

# Invariant 3: Old Balance >= 0
if old_balance_new < 0:
    ERROR: "Old Balance would become negative"
```

#### **Phase 8: Recalculate Pending**

```python
# Pending is ALWAYS from frozen Loss, never recalculated
if loss_new >= AUTO_CLOSE_THRESHOLD:
    pending_new = (loss_new * total_share_pct) / 100
else:
    pending_new = Decimal(0)
```

#### **Phase 9: Update Database**

```python
# Update cached Old Balance (display-only cache, ledger is truth)
client_exchange.cached_old_balance = old_balance_new
client_exchange.balance_last_updated = timezone.now()
client_exchange.save()

# Create SETTLEMENT transaction
Transaction.objects.create(
    client_exchange=client_exchange,
    date=settlement_date,
    transaction_type=Transaction.TYPE_SETTLEMENT,
    amount=amount,  # Payment amount
    your_share_amount=my_share_amount,  # Your cut
    company_share_amount=company_share_amount,  # Company cut
    note=note_text
)

# Final invariant check
assert abs(old_balance_new - (current_balance + loss_new)) < AUTO_CLOSE_THRESHOLD
```

---

## 💻 CODE WALKTHROUGH

### 1. UI Form Opening (JavaScript)

**File**: `core/templates/core/pending/summary.html`

```javascript
window.showSettlementForm = function(
    clientId, 
    clientExchangeId, 
    clientName, 
    exchangeName, 
    amount, 
    paymentType, 
    myShare, 
    companyShare, 
    combinedShare, 
    isCompanyClient
) {
    // 1. Get form element
    const form = document.getElementById('settlement-form-content');
    
    // 2. Set form action URL based on client type
    if (isCompanyClient) {
        form.action = companyClientsUrl;
    } else {
        form.action = myClientsUrl;
    }
    
    // 3. Populate form fields
    document.getElementById('settle-client-id').value = clientId;
    document.getElementById('settle-client-exchange-id').value = clientExchangeId;
    document.getElementById('settle-client-name').value = clientName;
    document.getElementById('settle-exchange-name').value = exchangeName;
    
    // 4. Set amount (pre-filled with pending amount)
    const amountInput = document.getElementById('settle-amount');
    amountInput.value = combinedShare.toFixed(2);  // Pre-fill with pending
    amountInput.max = combinedShare.toFixed(2);  // Set max limit
    amountInput.setAttribute('data-max-amount', combinedShare.toFixed(2));
    
    // 5. Show share breakdown
    document.getElementById('settle-my-share').textContent = '₹' + Math.abs(myShare).toFixed(2);
    document.getElementById('settle-company-share').textContent = '₹' + Math.abs(companyShare).toFixed(2);
    document.getElementById('settle-combined-share').textContent = '₹' + Math.abs(combinedShare).toFixed(2);
    
    // 6. Show modal
    const modal = document.getElementById('settlement-form');
    modal.style.display = 'flex';
};
```

### 2. Form Validation (JavaScript)

```javascript
function validateAmount(input) {
    const maxAmount = parseFloat(input.getAttribute('data-max-amount')) || 0;
    const enteredAmount = parseFloat(input.value) || 0;
    
    if (enteredAmount > maxAmount) {
        // Show error
        document.getElementById('amount-error').style.display = 'block';
        document.getElementById('amount-error').textContent = 
            `Amount cannot exceed ₹${maxAmount.toFixed(2)}`;
        input.value = maxAmount.toFixed(2);  // Clamp to max
        return false;
    } else {
        // Hide error
        document.getElementById('amount-error').style.display = 'none';
        return true;
    }
}

function handleFormSubmit(event) {
    const amountInput = document.getElementById('settle-amount');
    if (!validateAmount(amountInput)) {
        event.preventDefault();
        return false;
    }
    return true;
}
```

### 3. Backend Settlement Handler (Python)

**File**: `core/views.py` → `settle_payment()`

```python
@login_required
def settle_payment(request):
    if request.method == "POST":
        # 1. Extract form data
        client_id = request.POST.get("client_id")
        client_exchange_id = request.POST.get("client_exchange_id")
        amount = Decimal(request.POST.get("amount", 0))
        tx_date = request.POST.get("date")
        payment_type = request.POST.get("payment_type", "client_pays")
        note = request.POST.get("note", "")
        
        # 2. Get client and client_exchange
        client = get_object_or_404(Client, pk=client_id, user=request.user)
        client_exchange = get_object_or_404(ClientExchange, pk=client_exchange_id, client=client)
        
        # 3. Lock for concurrency (prevent race conditions)
        with db_transaction.atomic():
            locked_client_exchange = ClientExchange.objects.select_for_update().get(
                pk=client_exchange.pk
            )
            
            # 4. Get FROZEN state from LossSnapshot
            from core.models import LossSnapshot
            
            try:
                loss_snapshot = LossSnapshot.objects.get(
                    client_exchange=locked_client_exchange,
                    is_settled=False
                )
            except LossSnapshot.DoesNotExist:
                messages.error(request, "No active loss to settle")
                return redirect(...)
            
            # 5. Get FROZEN values
            loss_current = loss_snapshot.loss_amount  # FROZEN
            current_balance = loss_snapshot.balance_record.remaining_balance  # FROZEN
            old_balance = current_balance + loss_current  # DERIVED
            
            # 6. Get FROZEN share percentages
            my_share_pct = loss_snapshot.my_share_pct  # FROZEN
            company_share_pct = loss_snapshot.company_share_pct  # FROZEN
            
            if locked_client_exchange.client.is_company_client:
                total_pct = my_share_pct + company_share_pct  # Usually 10%
            else:
                total_pct = my_share_pct  # Usually 10%
            
            # 7. Validate
            AUTO_CLOSE_THRESHOLD = Decimal("0.01")
            
            if amount <= 0:
                messages.error(request, "Amount must be greater than zero")
                return redirect(...)
            
            if loss_current < AUTO_CLOSE_THRESHOLD:
                messages.error(request, "No loss to settle")
                return redirect(...)
            
            # 8. Convert payment to capital closed
            capital_closed_raw = (amount * Decimal(100)) / total_pct
            
            if capital_closed_raw > loss_current:
                messages.error(request, "Capital closed exceeds loss")
                return redirect(...)
            
            capital_closed = capital_closed_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            
            # 9. Reduce loss
            loss_new = loss_current - capital_closed
            loss_new = max(loss_new, 0)
            loss_new = loss_new.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            
            if loss_new < AUTO_CLOSE_THRESHOLD:
                loss_new = Decimal(0)
                loss_snapshot.is_settled = True
            
            # 10. Update LossSnapshot
            loss_snapshot.loss_amount = loss_new
            loss_snapshot.save()
            
            # 11. Re-derive Old Balance
            if loss_new >= AUTO_CLOSE_THRESHOLD:
                old_balance_new = current_balance + loss_new
            else:
                old_balance_new = current_balance
                loss_new = Decimal(0)
            
            # 12. Validate invariants
            capital_verify = current_balance + loss_new
            if abs(old_balance_new - capital_verify) > AUTO_CLOSE_THRESHOLD:
                messages.error(request, "Capital invariant violation")
                return redirect(...)
            
            # 13. Recalculate pending
            if loss_new >= AUTO_CLOSE_THRESHOLD:
                pending_new = (loss_new * total_pct) / 100
            else:
                pending_new = Decimal(0)
            
            # 14. Update database
            locked_client_exchange.cached_old_balance = old_balance_new
            locked_client_exchange.balance_last_updated = timezone.now()
            locked_client_exchange.save()
            
            # 15. Create transaction
            Transaction.objects.create(
                client_exchange=locked_client_exchange,
                date=settlement_date,
                transaction_type=Transaction.TYPE_SETTLEMENT,
                amount=amount,
                your_share_amount=my_share_amount,
                company_share_amount=company_share_amount,
                note=note_text
            )
            
            # 16. Show success message
            messages.success(request, f"Payment of ₹{amount} recorded. Remaining pending: ₹{pending_new}")
            
            return redirect(...)
```

---

## 📖 COMPLETE EXAMPLES

### Example 1: Simple Partial Payment (My Client)

**Initial State**:
```
Loss (FROZEN) = ₹60
Current Balance (FROZEN) = ₹40
Old Balance (CAPITAL) = ₹40 + ₹60 = ₹100 (DERIVED)
My Share % = 10% (FROZEN)
Pending = ₹60 × 10% = ₹6
```

**User Action**: Click "Record Payment", enter ₹3, submit

**Backend Processing**:
1. Validate: Loss exists (₹60), payment valid (₹3 ≤ ₹6) ✓
2. Calculate: `capital_closed = (₹3 × 100) / 10 = ₹30`
3. Reduce Loss: `loss_new = ₹60 - ₹30 = ₹30`
4. Update LossSnapshot: `loss_amount = ₹30`
5. Re-derive OB: `old_balance_new = ₹40 + ₹30 = ₹70`
6. Recalculate Pending: `pending_new = (₹30 × 10) / 100 = ₹3`
7. Update DB: `cached_old_balance = ₹70`
8. Create Transaction: SETTLEMENT, amount=₹3

**Final State**:
```
Loss (FROZEN) = ₹30 (updated)
Current Balance (FROZEN) = ₹40 (unchanged)
Old Balance (CAPITAL) = ₹40 + ₹30 = ₹70 (DERIVED)
Pending = ₹30 × 10% = ₹3
```

### Example 2: Full Payment (Company Client)

**Initial State**:
```
Loss (FROZEN) = ₹60
Current Balance (FROZEN) = ₹40
Old Balance (CAPITAL) = ₹40 + ₹60 = ₹100 (DERIVED)
Total Share % = 10% (1% you, 9% company) (FROZEN)
Pending = ₹60 × 10% = ₹6
```

**User Action**: Click "Record Payment", enter ₹6 (full), submit

**Backend Processing**:
1. Validate: Loss exists (₹60), payment valid (₹6 ≤ ₹6) ✓
2. Calculate: `capital_closed = (₹6 × 100) / 10 = ₹60`
3. Reduce Loss: `loss_new = ₹60 - ₹60 = ₹0`
4. Update LossSnapshot: `loss_amount = ₹0`, `is_settled = True`
5. Re-derive OB: `old_balance_new = ₹40` (full settlement)
6. Recalculate Pending: `pending_new = ₹0`
7. Update DB: `cached_old_balance = ₹40`
8. Create Transaction: 
   - `your_share_amount = ₹0.6` (1%)
   - `company_share_amount = ₹5.4` (9%)

**Final State**:
```
Loss (FROZEN) = ₹0 (settled)
Current Balance (FROZEN) = ₹40 (unchanged)
Old Balance (CAPITAL) = ₹40 (DERIVED)
Pending = ₹0
```

### Example 3: Multiple Partial Payments

**Initial State**:
```
Loss (FROZEN) = ₹60
Current Balance (FROZEN) = ₹40
Old Balance (CAPITAL) = ₹100 (DERIVED)
Pending = ₹6
```

**Payment 1: ₹2**
- `capital_closed = ₹20`
- `loss_new = ₹40`
- `old_balance_new = ₹80`
- `pending_new = ₹4`

**Payment 2: ₹2**
- `capital_closed = ₹20`
- `loss_new = ₹20`
- `old_balance_new = ₹60`
- `pending_new = ₹2`

**Payment 3: ₹2**
- `capital_closed = ₹20`
- `loss_new = ₹0` (settled)
- `old_balance_new = ₹40`
- `pending_new = ₹0`

---

## ✅ VALIDATION RULES

### Frontend Validation (JavaScript)

1. **Amount Validation**:
   - Must be > 0
   - Must be ≤ pending amount
   - Must be ≤ max amount (from data attribute)

2. **Date Validation**:
   - Must be a valid date
   - Cannot be future date (optional check)

### Backend Validation (Python)

1. **Loss Exists**:
   ```python
   if loss_current < AUTO_CLOSE_THRESHOLD:
       ERROR: "No loss to settle"
   ```

2. **Payment Amount**:
   ```python
   if amount <= 0:
       ERROR: "Amount must be greater than zero"
   ```

3. **Payment Doesn't Exceed Pending**:
   ```python
   pending_before = (loss_current * total_share_pct) / 100
   if amount > pending_before:
       ERROR: "Payment exceeds pending amount"
   ```

4. **Capital Closed Doesn't Exceed Loss**:
   ```python
   capital_closed = (amount * 100) / total_share_pct
   if capital_closed > loss_current:
       ERROR: "Capital closed exceeds loss"
   ```

5. **No Profit While Loss Exists**:
   ```python
   if loss_new >= AUTO_CLOSE_THRESHOLD and old_balance_new < current_balance:
       ERROR: "Settlement would create profit while loss still exists"
   ```

6. **Old Balance >= 0**:
   ```python
   if old_balance_new < 0:
       ERROR: "Old Balance would become negative"
   ```

7. **CAPITAL Invariant (MANDATORY)**:
   ```python
   capital_verify = current_balance + loss_new
   if abs(old_balance_new - capital_verify) > AUTO_CLOSE_THRESHOLD:
       ERROR: "CAPITAL invariant violation: CAPITAL != CB + LOSS"
   ```

---

## 🔧 TROUBLESHOOTING

### Issue 1: "No loss to settle" Error

**Cause**: No active LossSnapshot exists or LossSnapshot is already settled

**Solution**: 
- Check if LossSnapshot exists for this client_exchange
- Verify `is_settled=False` in LossSnapshot
- Check if previous settlement already closed the loss (`is_settled=True`)
- Verify `loss_amount > 0` in LossSnapshot

### Issue 2: "Payment exceeds pending amount" Error

**Cause**: Payment amount > Pending amount

**Solution**:
- Check the pending amount shown in the table
- Enter payment ≤ pending amount
- For partial payment, use a smaller amount

### Issue 3: "Capital closed exceeds loss" Error

**Cause**: Internal calculation error (shouldn't happen if validation works)

**Solution**:
- This is a system error - contact support
- Check if share percentage is configured correctly

### Issue 4: Old Balance Not Updating

**Cause**: LossSnapshot not updated or cache not refreshed

**Solution**:
- Check if LossSnapshot was updated (`loss_amount` and `is_settled`)
- Verify SETTLEMENT transaction was created successfully
- Check `cached_old_balance` in database (display-only cache)
- Verify invariant: `CAPITAL = CB + LOSS` (check LossSnapshot values)
- Check `balance_last_updated` timestamp

### Issue 5: Pending Amount Not Decreasing

**Cause**: LossSnapshot not updated or pending calculated incorrectly

**Solution**:
- Pending is calculated from FROZEN Loss in LossSnapshot
- Verify LossSnapshot was updated (`loss_amount` decreased)
- Check if `is_settled` flag is correct
- Pending = `(LossSnapshot.loss_amount × Share %) / 100`
- Refresh the page to see updated values

---

## 📊 SUMMARY

### Key Formulas

```
# LOSS is FROZEN (from LossSnapshot, never recalculated)
Loss = LossSnapshot.loss_amount  # FROZEN

# CB is FROZEN when loss exists
Current Balance = LossSnapshot.balance_record.remaining_balance  # FROZEN

# CAPITAL is DERIVED (always, never source of truth)
Old Balance (CAPITAL) = Current Balance + Loss  # DERIVED

# Pending from FROZEN Loss
Pending = (Loss × Share %) / 100  # From frozen Loss

# Capital Closed conversion
Capital Closed = (Payment × 100) / Share %

# Loss reduction (only via SETTLEMENT)
Loss New = Loss Current - Capital Closed

# CAPITAL re-derived after settlement
Old Balance New = Current Balance (frozen) + Loss New (updated)
```

### Key Rules (NON-NEGOTIABLE)

1. **LOSS is FROZEN**: Stored in LossSnapshot, NEVER recalculated
2. **CAPITAL is DERIVED**: Always `CB + Loss`, never source of truth
3. **CB is FROZEN when LOSS exists**: New balance records don't affect loss calculations
4. **PROFIT exists ONLY when LOSS = 0**: Cannot have profit while active loss exists
5. **LOSS reduced ONLY by SETTLEMENT**: Balance recovery never reduces loss
6. **Pending from FROZEN Loss**: Always from LossSnapshot, never recalculated
7. **Capital Closed Conversion**: Payment (share space) → Capital Closed (capital space)
8. **Invariant: CAPITAL = CB + LOSS**: Always true by definition
9. **Concurrency Safety**: Database locks prevent race conditions
10. **Auto-Close Threshold**: `AUTO_CLOSE = Decimal("0.01")` - consistent everywhere

### UI Flow

1. Navigate to Pending Payments (`/pending/`)
2. Find client in "Clients Owe You" section
3. Click "Record Payment" button
4. Enter payment amount (≤ pending)
5. Submit form
6. System processes and updates
7. Redirect to pending page with success message

### Backend Flow

1. Get FROZEN state from LossSnapshot
2. Validate payment
3. Convert payment to capital closed
4. Reduce frozen Loss
5. Update LossSnapshot
6. Re-derive Old Balance
7. Validate invariants
8. Recalculate pending
9. Update database
10. Create SETTLEMENT transaction
11. Return success

---

**Document Version**: 3.0 (Frozen Loss Implementation)  
**Last Updated**: 2026-01-05  
**Status**: ✅ Complete Guide - All Aspects Covered
