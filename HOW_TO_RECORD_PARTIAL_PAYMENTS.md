# How to Record Partial Payments - Complete Guide

## 📋 Table of Contents
1. [⚠️ Critical Rules (Do Not Break)](#critical-rules-do-not-break)
2. [What is a Partial Payment?](#what-is-a-partial-payment)
3. [Step-by-Step Instructions](#step-by-step-instructions)
4. [Understanding the UI](#understanding-the-ui)
5. [What Happens Behind the Scenes](#what-happens-behind-the-scenes)
6. [Common Issues & Troubleshooting](#common-issues--troubleshooting)
7. [Examples](#examples)

---

## ⚠️ Critical Rules (Do Not Break)

**🚨 These rules are MANDATORY and must NEVER be violated:**

### Rule 1: Pending is NEVER reduced by payment
❌ **WRONG:** `pending = pending - payment_amount`  
✅ **CORRECT:** `pending = round_share(remaining_loss * total_pct / 100)`

**Why:** Pending must ALWAYS be recalculated from remaining loss, never from previous pending or payment amount.

---

### Rule 2: Pending is ALWAYS recalculated from remaining loss
✅ **ONLY CORRECT WAY:**
```python
remaining_loss = loss_snapshot.get_remaining_loss()
pending = round_share(remaining_loss * total_pct / Decimal(100))
```

**Why:** This ensures pending is always accurate and never shows ₹0 when loss still exists.

---

### Rule 3: Validation uses RAW pending, not rounded pending
❌ **WRONG:** `amount ≤ pending` (uses rounded value)  
✅ **CORRECT:** `amount ≤ raw_pending` (uses raw value before rounding)

**Why:** In a rounding-down system, raw pending may be higher than displayed pending.

**Example:**
- `remaining_loss = 905`
- `total_pct = 10%`
- `raw_pending = 90.5`
- `display_pending = 90.0` (rounded down)

If user pays ₹90.3:
- ❌ Wrong rule blocks it (90.3 > 90.0)
- ✅ Correct rule allows it (90.3 ≤ 90.5)

---

### Rule 4: LossSnapshot.is_settled is set ONLY when remaining_loss ≤ threshold
❌ **WRONG:** Setting `is_settled = True` after any payment  
✅ **CORRECT:**
```python
if remaining_loss <= AUTO_CLOSE_THRESHOLD:
    loss_snapshot.is_settled = True
else:
    loss_snapshot.is_settled = False  # MUST remain False
```

**Why:** If `is_settled=True` too early:
- Pending instantly becomes ₹0
- Settlement button breaks
- System says "No loss to settle"

---

### Rule 5: All money values MUST be Decimal
❌ **WRONG:**
```python
amount = 10  # int
amount = 10.5  # float
amount.quantize()  # CRASH: 'int' object has no attribute 'quantize'
```

✅ **CORRECT:**
```python
from decimal import Decimal
amount = Decimal(str(amount))  # Always convert to Decimal
amount.quantize()  # Works correctly
```

**Why:** Prevents `'int' object has no attribute 'quantize'` errors.

---

### Rule 6: Never round both sides of a split
❌ **WRONG:**
```python
my_share = round_share(amount * my_pct / total_pct)
company_share = round_share(amount * company_pct / total_pct)
# Problem: my_share + company_share might not equal amount
```

✅ **CORRECT:**
```python
my_share = round_share(amount * my_pct / total_pct)
company_share = amount - my_share  # Give remainder to other side
# Guarantee: my_share + company_share == amount (ALWAYS)
```

**Why:** Prevents money from "disappearing" due to double rounding.

---

## What is a Partial Payment?

A **partial payment** is when a client pays less than the full pending amount. For example:
- **Full Pending:** ₹90.00
- **Partial Payment:** ₹10.00 (client pays only ₹10 instead of ₹90)
- **Remaining Pending:** ₹80.00 (after payment)

✅ **Partial payments are fully supported** - you can record any amount up to the full pending amount.

---

## Step-by-Step Instructions

### Step 1: Navigate to Pending Payments Page

1. Go to **"Client Payable (Share)"** in the navigation menu
2. Or visit: `http://localhost:8000/pending/`
3. You'll see a list of clients who owe money

### Step 2: Find the Client

1. Look for the client in the **"Clients Owe"** section
2. You'll see:
   - **Client Name**
   - **Exchange Name**
   - **Trading Loss (Capital):** e.g., ₹900.00
   - **Client Payable (Share):** e.g., ₹90.00 (this is what client owes)
   - **My Share:** e.g., ₹9.00
   - **Company Share:** e.g., ₹81.00 (for company clients)

### Step 3: Click "Record Share Settlement" Button

1. Find the **"Record Share Settlement"** button next to the client
2. Click it - a modal/popup will appear

### Step 4: Enter Payment Details

In the modal, you'll see:

1. **Client Payable (Share):** Shows the current pending amount (e.g., ₹90.0)
2. **Amount Input Field:** Enter the payment amount here
   - ✅ You can enter **any amount** up to the full pending amount
   - ✅ For partial payment: Enter less than the full amount (e.g., ₹10.00)
   - ✅ For full payment: Enter the full amount (e.g., ₹90.00)

3. **Date:** Select the payment date (defaults to today)

4. **Note (Optional):** Add any notes about the payment

### Step 5: Submit the Payment

1. Click **"Record Payment"** or **"Submit"** button
2. The system will:
   - Validate the amount (must be > 0 and ≤ pending amount)
   - Create a SETTLEMENT transaction
   - Update the remaining loss
   - Recalculate the new pending amount

### Step 6: Verify the Payment

After submission, you should see:
- ✅ Success message: "Payment of ₹X recorded..."
- ✅ The page will refresh
- ✅ The client's pending amount will be reduced
- ✅ You can record another partial payment if needed

---

## Understanding the UI

### What You'll See on the Pending Page

```
┌─────────────────────────────────────────────────────────┐
│ Client Name    Exchange    Loss    Pending    Action    │
├─────────────────────────────────────────────────────────┤
│ John Doe       Binance     ₹900    ₹90.0     [Button]  │
└─────────────────────────────────────────────────────────┘
```

### Payment Modal Fields

When you click "Record Share Settlement", you'll see:

```
┌──────────────────────────────────────┐
│ Record Share Settlement              │
├──────────────────────────────────────┤
│ Client: John Doe - Binance           │
│                                      │
│ Client Payable (Share): ₹90.0       │
│                                      │
│ Amount: [________]  ← Enter here    │
│                                      │
│ Date: [2025-01-15]                  │
│                                      │
│ Note: [________________]             │
│                                      │
│ [Cancel]  [Record Payment]          │
└──────────────────────────────────────┘
```

### Important UI Notes

1. **Amount Input:**
   - Maximum value is set to the **raw pending amount** (not rounded)
   - You can enter any value from ₹0.01 up to the maximum
   - The input accepts decimals (e.g., ₹10.50)

2. **Validation:**
   - Amount must be **greater than 0**
   - Amount must be **less than or equal to** the **RAW pending amount** (before rounding)
   - ⚠️ **Important:** The system validates against the raw pending (e.g., ₹90.5), not the displayed rounded pending (e.g., ₹90.0)
   - If you enter an invalid amount, you'll see an error message

3. **Share Breakdown:**
   - For company clients, you'll see:
     - **My Share:** Your 1% cut
     - **Company Share:** Company's 9% cut
     - **Combined Share:** Total (10%)

---

## What Happens Behind the Scenes

### The Settlement Process

When you record a partial payment, here's what happens:

#### Step 1: Calculate Capital Closed
```
capital_closed = (payment_amount × 100) / total_share_percentage

Example:
  Payment = ₹10
  Total Share % = 10%
  Capital Closed = (10 × 100) / 10 = ₹100
```

#### Step 2: Create SETTLEMENT Transaction
- A new transaction is created in the database
- Type: `SETTLEMENT`
- Amount: Payment amount (e.g., ₹10)
- Capital Closed: Calculated capital closed (e.g., ₹100)

#### Step 3: Recalculate Remaining Loss
```
remaining_loss = original_loss - capital_closed

Example:
  Original Loss = ₹900
  Capital Closed = ₹100
  Remaining Loss = ₹900 - ₹100 = ₹800
```

#### Step 4: Recalculate Pending
```
⚠️ CRITICAL: Pending is ALWAYS recalculated from remaining_loss, NEVER from payment amount.

pending_raw = (remaining_loss × total_share_percentage) / 100
pending = round_share(pending_raw)  # Round DOWN for share-space

Example:
  Remaining Loss = ₹800
  Total Share % = 10%
  Pending Raw = (800 × 10) / 100 = ₹80.0
  Pending = round_share(₹80.0) = ₹80.0
```

**🚨 NEVER do this:**
```python
pending = pending_before - payment_amount  # ❌ WRONG
```

**✅ ALWAYS do this:**
```python
remaining_loss = loss_snapshot.get_remaining_loss()
pending = round_share(remaining_loss * total_pct / Decimal(100))  # ✅ CORRECT
```

#### Step 5: Update Ledgers
- **OutstandingAmount** (for "My Clients"): Updated to new pending
- **TallyLedger** (for "Company Clients"): Updated to new pending

#### Step 6: Mark Loss as Settled (if applicable)
⚠️ **CRITICAL RULE:**
```python
if remaining_loss <= AUTO_CLOSE_THRESHOLD:  # AUTO_CLOSE_THRESHOLD = ₹0.01
    loss_snapshot.is_settled = True
    loss_snapshot.save(update_fields=['is_settled'])
else:
    # MUST remain False - do NOT set to True
    loss_snapshot.is_settled = False
```

**Why this matters:**
- If `is_settled=True` too early:
  - Pending instantly becomes ₹0
  - Settlement button breaks
  - System says "No loss to settle"
- The loss is marked as settled **ONLY** when `remaining_loss ≤ ₹0.01`
- Otherwise, the loss remains active for future payments

---

## Common Issues & Troubleshooting

### Issue 1: "Payment exceeds pending amount" Error

**Problem:** You're trying to enter an amount greater than the **RAW pending amount**.

**Solution:**
- ⚠️ **Important:** The system validates against the **RAW pending** (before rounding), not the displayed rounded pending
- Check the "Client Payable (Share)" value shown in the modal (this is the rounded display value)
- The maximum allowed is the **raw pending amount** (which may be slightly higher than the displayed value)
- Enter an amount **less than or equal to** the raw pending amount

**Example:**
- If `remaining_loss = 905` and `total_pct = 10%`:
  - Raw pending = ₹90.5
  - Display pending = ₹90.0 (rounded down)
- You can enter up to ₹90.5 (raw pending)
- You cannot enter ₹90.6 or more
- ⚠️ Note: The UI may show ₹90.0, but validation allows up to ₹90.5

---

### Issue 2: "Cannot record payment: No loss to settle" Error

**Problem:** There's no active loss for this client-exchange.

**Solution:**
- Check if the client actually has a pending amount
- The loss might have been fully settled already
- Refresh the page to see the current state

---

### Issue 3: Button Not Clickable / Modal Not Opening

**Problem:** The "Record Share Settlement" button doesn't work.

**Solution:**
1. **Check JavaScript Console:**
   - Press `F12` to open developer tools
   - Look for any JavaScript errors
   - Common issues:
     - `showSettlementForm is not defined` → Refresh the page
     - Network errors → Check internet connection

2. **Check Browser Compatibility:**
   - Use a modern browser (Chrome, Firefox, Safari, Edge)
   - Clear browser cache and cookies
   - Try in incognito/private mode

3. **Check Server Logs:**
   - Make sure the Django server is running
   - Check for any server errors in the terminal

---

### Issue 4: Payment Recorded but Pending Doesn't Change

**Problem:** After recording payment, the pending amount stays the same.

**Solution:**
1. **Refresh the page** - The pending amount is recalculated on page load
2. **Check the transaction** - Verify the payment was actually created:
   - Go to the client's transaction history
   - Look for a `SETTLEMENT` transaction with your payment amount
3. **Check for errors** - Look for any error messages in the success/error notifications

**If still not working:**
- Check server logs for errors
- Verify the database connection
- Contact support with:
  - Client name
  - Exchange name
  - Payment amount
  - Date/time of payment

---

### Issue 5: "Amount must be greater than 0" Error

**Problem:** You're trying to enter 0 or a negative amount.

**Solution:**
- Enter a positive amount (e.g., ₹10.00)
- Make sure there are no spaces or special characters
- Use decimal format: ₹10.50 (not ₹10,50)

---

### Issue 6: Pending Shows ₹0 but Loss Still Exists

**Problem:** The UI shows ₹0 pending, but the loss hasn't been fully settled.

**Possible Causes:**
1. **Rounding Issue:** The remaining loss is very small (< ₹0.01) and was auto-closed
2. **Display Issue:** The page might need a refresh
3. **Calculation Bug:** This should not happen - contact support

**Solution:**
1. Refresh the page
2. Check the actual loss amount in the database
3. If the loss is truly zero, it's correctly settled
4. If the loss is not zero but pending shows ₹0, this is a bug - contact support

---

## Examples

### Example 1: Simple Partial Payment

**Scenario:**
- Client: John Doe
- Exchange: Binance
- Trading Loss: ₹900.00
- Client Payable: ₹90.00 (10% of loss)
- Payment: ₹10.00 (partial)

**Steps:**
1. Click "Record Share Settlement" for John Doe - Binance
2. Enter amount: ₹10.00
3. Select date: 2025-01-15
4. Click "Record Payment"

**Result:**
- ✅ Payment recorded: ₹10.00
- ✅ Capital closed: ₹100.00
- ✅ Remaining loss: ₹800.00
- ✅ New pending: ₹80.00

---

### Example 2: Multiple Partial Payments

**Scenario:**
- Initial Loss: ₹900.00
- Initial Pending: ₹90.00

**Payment 1:**
- Amount: ₹20.00
- Result: Remaining pending = ₹70.00

**Payment 2:**
- Amount: ₹30.00
- Result: Remaining pending = ₹40.00

**Payment 3:**
- Amount: ₹40.00 (full remaining)
- Result: Remaining pending = ₹0.00 (fully settled)

---

### Example 3: Company Client Payment

**Scenario:**
- Client: Company Client (is_company_client = True)
- Trading Loss: ₹1000.00
- Total Share %: 10% (1% my share + 9% company share)
- Client Payable: ₹100.00
- Payment: ₹50.00

**Steps:**
1. Click "Record Share Settlement"
2. Enter amount: ₹50.00
3. Submit

**Result:**
- ✅ Payment recorded: ₹50.00
- ✅ Capital closed: ₹500.00
- ✅ Remaining loss: ₹500.00
- ✅ New pending: ₹50.00
- ✅ My share: ₹5.00 (1% of remaining loss)
- ✅ Company share: ₹45.00 (9% of remaining loss)

---

## Quick Reference

### Payment Formula
```
⚠️ CRITICAL: All values MUST be Decimal (never int or float)

capital_closed = (payment_amount × Decimal(100)) / total_share_percentage
capital_closed = round_capital(capital_closed)  # Round HALF_UP for capital-space

remaining_loss = loss_snapshot.get_remaining_loss()  # Query from database
remaining_loss = round_capital(remaining_loss)  # Round HALF_UP for capital-space

pending_raw = (remaining_loss × total_share_percentage) / Decimal(100)
pending = round_share(pending_raw)  # Round DOWN for share-space
```

**🚨 NEVER calculate pending from payment:**
```python
pending = pending_before - payment_amount  # ❌ WRONG
```

**✅ ALWAYS calculate pending from remaining_loss:**
```python
remaining_loss = loss_snapshot.get_remaining_loss()
pending = round_share(remaining_loss * total_pct / Decimal(100))  # ✅ CORRECT
```

### Validation Rules
- ✅ Amount must be > 0
- ✅ Amount must be ≤ **RAW pending amount** (before rounding, not displayed rounded value)
- ✅ Payment date must be valid
- ✅ Active loss must exist
- ✅ All monetary values must be Decimal (never int or float)

### What Gets Updated
- ✅ SETTLEMENT transaction created (with `capital_closed` field)
- ✅ Remaining loss recalculated from database (`loss_snapshot.get_remaining_loss()`)
- ✅ Pending amount recalculated from remaining_loss (NOT from payment)
- ✅ Ledger updated (OutstandingAmount or TallyLedger) with new pending
- ✅ LossSnapshot.is_settled updated (ONLY if `remaining_loss ≤ AUTO_CLOSE_THRESHOLD`)

**🚨 Critical:** Pending is ALWAYS recalculated from remaining_loss, NEVER from payment amount.

---

## Still Having Issues?

If you're still unable to record partial payments:

1. **Check the Error Message:**
   - Read the exact error message shown
   - It will tell you what's wrong

2. **Verify Prerequisites:**
   - Client has an active loss
   - Pending amount > 0
   - You're logged in as admin

3. **Check Server Logs:**
   - Look at the Django server terminal
   - Check for any Python errors or exceptions

4. **Test with Full Payment:**
   - Try recording the full pending amount first
   - If that works, partial payments should also work

5. **Contact Support:**
   - Provide:
     - Client name and exchange
     - Payment amount you're trying to enter
     - Exact error message
     - Screenshot if possible

---

## Summary

✅ **Partial payments are fully supported** - you can pay any amount up to the RAW pending amount

✅ **The process is simple:**
1. Go to "Client Payable (Share)" page
2. Click "Record Share Settlement"
3. Enter payment amount (any amount ≤ RAW pending, not rounded display)
4. Submit

✅ **The system automatically:**
- Calculates capital closed
- Creates SETTLEMENT transaction
- Recalculates remaining_loss from database
- Recalculates pending from remaining_loss (NOT from payment)
- Updates all ledgers
- Marks loss as settled ONLY if `remaining_loss ≤ AUTO_CLOSE_THRESHOLD`

✅ **Critical Rules (Never Break):**
1. Pending is NEVER reduced by payment - always recalculated from remaining_loss
2. Validation uses RAW pending, not rounded pending
3. LossSnapshot.is_settled is set ONLY when `remaining_loss ≤ AUTO_CLOSE_THRESHOLD`
4. All money values MUST be Decimal (never int or float)
5. Never round both sides of a split

✅ **If you encounter issues:**
- Check error messages
- Verify prerequisites
- Refresh the page
- Check the [Critical Rules](#critical-rules-do-not-break) section
- Contact support if needed

---

## 🧪 Sanity Test

Use this test to verify your system is working correctly:

**Initial State:**
- Loss = ₹900
- Share % = 10%
- Pending = ₹90

**Payment 1: ₹10**
- ✅ capital_closed = ₹100
- ✅ remaining_loss = ₹800
- ✅ pending = ₹80

**Payment 2: ₹10**
- ✅ remaining_loss = ₹700
- ✅ pending = ₹70

**If your system shows:**
- ❌ `pending = ₹0` but `loss still exists` → Rule 1 or 2 violated
- ❌ `pending = ₹0` after partial payment → Rule 4 violated (is_settled set too early)
- ❌ Validation blocks valid payment → Rule 3 violated (using rounded pending)

---

**Last Updated:** 2025-01-15
**Version:** 1.0

