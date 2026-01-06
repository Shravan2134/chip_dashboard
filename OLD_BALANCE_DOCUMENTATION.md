# Old Balance Calculation and Display Documentation

## Overview

Old Balance is a critical value in the payment system that represents the **capital base** (the amount of money given to the client) at a specific point in time. It is used to calculate profit/loss and determine pending payment amounts.

---

## 🔑 Core Concept

**Old Balance** = The exchange balance (capital) **before** any profit/loss events, adjusted for settlements.

### Key Principles:

1. **Old Balance is NOT the current balance** - It represents the historical capital base
2. **Old Balance changes when settlements occur** - Partial payments move the Old Balance forward
3. **Old Balance is settlement-aware** - It correctly accounts for partial payments made by clients
4. **Old Balance is the same for both My Clients and Company Clients** - The calculation logic is unified

---

## 📐 Calculation Logic

### Function: `get_old_balance_after_settlement(client_exchange, as_of_date=None)`

This function calculates Old Balance using the following logic:

### Case 1: No Settlement Exists

If the client has **never made a payment**:

```
Old Balance = SUM of ALL FUNDING transactions
```

**Example:**
- Funding 1: ₹100
- Funding 2: ₹50
- **Old Balance = ₹150**

### Case 2: Settlement Exists

If the client has made **one or more payments**:

```
Old Balance = Current Balance AT settlement date + Funding AFTER settlement
```

**Detailed Steps:**

1. **Find the last SETTLEMENT transaction** (most recent payment)
2. **Find the settlement adjustment BALANCE_RECORD** (created during settlement)
   - This record contains the new Old Balance after the payment
   - It has a note containing "Settlement adjustment"
   - Priority: Look for this record first
3. **If settlement adjustment record exists:**
   ```
   base_old_balance = settlement_balance.remaining_balance + extra_adjustment
   ```
4. **If settlement adjustment record doesn't exist (fallback):**
   - Find any balance record at or BEFORE the settlement date
   - Use that balance as the base
5. **Add funding after settlement:**
   ```
   funding_after_settlement = SUM(FUNDING transactions where date > settlement_date)
   ```
6. **Final calculation:**
   ```
   Old Balance = base_old_balance + funding_after_settlement
   ```

**Important:** Old Balance cannot be negative. If calculated value < 0, it's set to 0.

---

## 💰 How Partial Payments Affect Old Balance

When a client makes a **partial payment**, the Old Balance is **moved forward** to reflect the reduced capital base.

### Partial Payment Formula:

```
capital_closed = payment × 100 / total_share_pct
```

**For LOSS case:**
```
old_balance_new = old_balance_old - capital_closed
```

**For PROFIT case:**
```
old_balance_new = old_balance_old + capital_closed
```

### Example: Partial Payment for Loss

**Initial State:**
- Old Balance: ₹100
- Current Balance: ₹10
- Total Loss: ₹90 (100 - 10)
- Company Share %: 10%
- Combined Share: ₹9 (10% of ₹90)

**Client pays ₹5 (partial payment):**
- `capital_closed = 5 × 100 / 10 = ₹50`
- `old_balance_new = 100 - 50 = ₹50`

**After Payment:**
- Old Balance: ₹50 (moved from ₹100)
- Current Balance: ₹10 (unchanged)
- Total Loss: ₹40 (50 - 10)
- Combined Share: ₹4 (10% of ₹40)
- Remaining Pending: ₹4 (₹9 - ₹5)

**Key Point:** The Old Balance is **permanently adjusted** by creating a `BALANCE_RECORD` with:
- Date: Settlement date
- Balance: New Old Balance (₹50)
- Note: "Settlement adjustment: Old Balance moved from ₹100 to ₹50.0 (capital_closed: ₹50)"

---

## 🖥️ How Old Balance is Displayed

### In Pending Payments Page

Old Balance is shown in the **"Clients Owe You"** and **"You Owe Clients"** sections:

**Table Column:** "OLD BALANCE"

**Display Format:**
```
₹{old_balance}
```

**Example:**
- Old Balance: ₹50.0
- Current Balance: ₹10.0
- Total Loss: ₹40.0

### Where It's Used

1. **Pending Payments Summary** (`/pending/`)
   - Displayed in the client list table
   - Used to calculate Total Loss/Profit
   - Used to calculate Combined Share and My Share

2. **CSV Reports**
   - Exported with client data
   - Used for accounting and reconciliation

3. **Client Detail Pages**
   - Shown in transaction history
   - Used in balance calculations

---

## 🔍 Technical Implementation Details

### Function Location

**File:** `core/views.py`  
**Function:** `get_old_balance_after_settlement(client_exchange, as_of_date=None)`

### Key Code Sections

#### 1. Finding Last Settlement

```python
last_settlement = Transaction.objects.filter(
    client_exchange=client_exchange,
    transaction_type=Transaction.TYPE_SETTLEMENT
).order_by("-date", "-created_at").first()
```

#### 2. Finding Settlement Adjustment BALANCE_RECORD

```python
settlement_balance = ClientDailyBalance.objects.filter(
    client_exchange=client_exchange,
    date=last_settlement.date,
    note__icontains="Settlement adjustment"
).order_by("-created_at").first()
```

#### 3. Calculating Funding After Settlement

```python
funding_after_settlement = Transaction.objects.filter(
    client_exchange=client_exchange,
    transaction_type=Transaction.TYPE_FUNDING,
    date__gt=last_settlement.date
).aggregate(total=Sum("amount"))["total"] or Decimal(0)
```

#### 4. Final Old Balance

```python
if settlement_balance:
    base_old_balance = settlement_balance.remaining_balance + (settlement_balance.extra_adjustment or Decimal(0))
else:
    # Fallback to balance record at/before settlement date
    balance_at_settlement = ClientDailyBalance.objects.filter(
        client_exchange=client_exchange,
        date__lte=last_settlement.date
    ).order_by("-date", "-created_at").first()
    base_old_balance = balance_at_settlement.remaining_balance + (balance_at_settlement.extra_adjustment or Decimal(0))

final_old_balance = base_old_balance + funding_after_settlement
if final_old_balance < 0:
    final_old_balance = Decimal(0)
```

---

## 📊 Examples

### Example 1: Client with No Payments

**Timeline:**
- Dec 1: Funding ₹100
- Dec 5: Funding ₹50
- Dec 10: Current Balance = ₹80 (loss of ₹70)

**Old Balance Calculation:**
- No settlement exists
- Old Balance = ₹100 + ₹50 = **₹150**
- Total Loss = ₹150 - ₹80 = **₹70**

### Example 2: Client with Full Payment

**Timeline:**
- Dec 1: Funding ₹100
- Dec 5: Current Balance = ₹90 (loss of ₹10)
- Dec 10: Client pays ₹1 (full payment for 10% share)

**After Payment:**
- Settlement adjustment BALANCE_RECORD created with balance = ₹90
- Old Balance = **₹90** (moved from ₹100)
- Current Balance = ₹90
- Total Loss = ₹0 (90 - 90)
- Pending = ₹0

### Example 3: Client with Partial Payment

**Timeline:**
- Dec 1: Funding ₹100
- Dec 5: Current Balance = ₹10 (loss of ₹90)
- Dec 10: Client pays ₹5 (partial payment)

**After Payment:**
- `capital_closed = 5 × 100 / 10 = ₹50`
- Settlement adjustment BALANCE_RECORD created with balance = ₹50
- Old Balance = **₹50** (moved from ₹100)
- Current Balance = ₹10 (unchanged)
- Total Loss = ₹40 (50 - 10)
- Combined Share = ₹4 (10% of ₹40)
- Remaining Pending = ₹4

### Example 4: Multiple Partial Payments

**Timeline:**
- Dec 1: Funding ₹100
- Dec 5: Current Balance = ₹10 (loss of ₹90)
- Dec 10: Client pays ₹5 (first partial payment)
- Dec 15: Client pays ₹2 (second partial payment)

**After First Payment (Dec 10):**
- Old Balance = ₹50
- Remaining Pending = ₹4

**After Second Payment (Dec 15):**
- `capital_closed = 2 × 100 / 10 = ₹20`
- Old Balance = ₹50 - ₹20 = **₹30**
- Current Balance = ₹10
- Total Loss = ₹20 (30 - 10)
- Combined Share = ₹2 (10% of ₹20)
- Remaining Pending = ₹2

---

## ⚠️ Important Rules

### Rule 1: Old Balance Never Goes Below Zero

```python
if final_old_balance < 0:
    final_old_balance = Decimal(0)
```

### Rule 2: Settlement Adjustment Records Take Priority

When calculating Old Balance after a settlement, the system **first looks for** the settlement adjustment BALANCE_RECORD. This ensures the correct Old Balance (after partial payment) is always used.

### Rule 3: Old Balance is Settlement-Aware

Old Balance **automatically adjusts** when payments are made. You don't need to manually update it.

### Rule 4: Funding After Settlement is Added

Any funding transactions **after** the last settlement are added to the Old Balance. This ensures new capital is included in the base.

### Rule 5: Old Balance is the Same for All Client Types

Both **My Clients** and **Company Clients** use the same `get_old_balance_after_settlement()` function. The calculation logic is unified.

---

## 🔄 Relationship with Other Values

### Old Balance vs Current Balance

- **Old Balance:** Historical capital base (adjusted for settlements)
- **Current Balance:** Current exchange balance (from latest BALANCE_RECORD, excluding settlement adjustments)

**Formula:**
```
Total Loss/Profit = Current Balance - Old Balance
```

### Old Balance vs Total Funding

- **Total Funding:** Sum of ALL funding transactions (never changes)
- **Old Balance:** Total funding adjusted for settlements (changes with payments)

**Relationship:**
- If no settlement: `Old Balance = Total Funding`
- If settlement exists: `Old Balance ≤ Total Funding` (usually less, unless profit case)

### Old Balance vs Pending Amount

- **Old Balance:** Used to calculate Total Loss/Profit
- **Total Loss/Profit:** Used to calculate Combined Share
- **Combined Share:** Used to calculate Pending Amount

**Chain:**
```
Old Balance → Total Loss → Combined Share → Pending Amount
```

---

## 🐛 Common Issues and Solutions

### Issue 1: Old Balance Shows Total Funding After Payment

**Symptom:** After a partial payment, Old Balance still shows the original total funding instead of the adjusted amount.

**Cause:** The code is overriding Old Balance with total funding.

**Solution:** Ensure `get_old_balance_after_settlement()` is used and not overridden. Check for code that sets `old_balance = total_funding` after settlements.

### Issue 2: Old Balance Doesn't Change After Payment

**Symptom:** Old Balance remains the same after recording a payment.

**Cause:** Settlement adjustment BALANCE_RECORD not created, or not being found.

**Solution:** Ensure `settle_payment()` function creates a BALANCE_RECORD with "Settlement adjustment" note.

### Issue 3: Old Balance is Negative

**Symptom:** Old Balance shows a negative value.

**Cause:** Calculation error or missing validation.

**Solution:** The code should enforce `if final_old_balance < 0: final_old_balance = Decimal(0)`.

---

## 📝 Summary

**Old Balance** is calculated using:

1. **If no settlement:** Sum of all funding transactions
2. **If settlement exists:** Settlement adjustment BALANCE_RECORD balance + funding after settlement

**Key Features:**
- ✅ Settlement-aware (adjusts with payments)
- ✅ Unified logic for My Clients and Company Clients
- ✅ Automatically updated via BALANCE_RECORDs
- ✅ Never goes below zero
- ✅ Used to calculate profit/loss and pending amounts

**Display:**
- Shown in pending payments table as "OLD BALANCE"
- Format: ₹{amount}
- Used in calculations for Total Loss/Profit and Pending Amount

---

## 🔗 Related Documentation

- `PENDING_PAYMENTS_DOCUMENTATION.md` - Overall pending payments system
- `HOW_PARTIAL_PAYMENTS_WORK.md` - Detailed partial payment logic
- `PAYMENTS_SYSTEM_DOCUMENTATION.md` - Complete payments system overview

---

**Last Updated:** Based on implementation as of latest commit






