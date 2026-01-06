# Debug Guide: Why Partial Payments Are Not Getting Recorded

## 🔍 Step-by-Step Debugging Process

### Step 1: Check Browser Console (JavaScript Errors)

1. **Open Developer Tools:**
   - Press `F12` or right-click → "Inspect"
   - Go to the **Console** tab

2. **Look for these messages when clicking "Record Share Settlement":**
   - ✅ `=== showSettlementForm CALLED ===` (should appear)
   - ✅ `Modal displayed successfully` (should appear)
   - ❌ Any **red error messages** (these block the form)

3. **Common JavaScript Errors:**
   - `showSettlementForm is not defined` → Page didn't load JavaScript properly
   - `Cannot read property 'value' of null` → Form element missing
   - `form.action is not set` → Form action URL not configured

**Fix:** Refresh the page (Ctrl+F5 or Cmd+Shift+R to clear cache)

---

### Step 2: Check Form Submission

1. **Enter a partial payment amount** (e.g., ₹10 when pending is ₹90)

2. **Click "Record Payment"**

3. **Check Console for:**
   - ✅ `handleFormSubmit called - form submission started`
   - ✅ `Form data: { amount: 10, paymentType: 'client_pays', ... }`
   - ✅ `Form validation passed, submitting to: /company-clients/settle-payment/` (or similar)
   - ✅ `Allowing form submission to: ...`

4. **If you see validation errors:**
   - `Amount cannot exceed ₹X` → Check if amount is valid
   - `Please enter a valid amount greater than 0` → Amount is 0 or invalid
   - `Please select a date` → Date field is empty

**Fix:** Check the error message and correct the input

---

### Step 3: Check Backend (Django Server Logs)

1. **Look at your terminal/console where Django is running**

2. **When you submit the form, you should see:**
   - `POST /company-clients/settle-payment/` (or similar)
   - `200 OK` (success) or `302 Redirect` (redirect after success)

3. **If you see errors:**
   - `404 Not Found` → URL pattern not configured
   - `500 Internal Server Error` → Backend code error
   - `ValidationError` → Backend validation failed

4. **Common Backend Errors:**
   ```
   Cannot record payment: No active loss to settle
   → LossSnapshot doesn't exist or is_settled=True
   
   Cannot record payment: Payment exceeds pending amount
   → Amount > raw pending (check validation logic)
   
   Cannot record payment: No loss to settle (LOSS: ₹0)
   → Loss is already fully settled
   ```

**Fix:** Check the error message and verify:
- LossSnapshot exists with `is_settled=False`
- Payment amount ≤ raw pending amount
- Active loss exists

---

### Step 4: Check Database State

Run these checks in Django shell:

```python
python manage.py shell

from core.models import LossSnapshot, ClientExchange, Transaction

# 1. Check if LossSnapshot exists
client_exchange = ClientExchange.objects.get(pk=YOUR_CLIENT_EXCHANGE_ID)
loss_snapshot = LossSnapshot.objects.filter(
    client_exchange=client_exchange,
    is_settled=False
).first()

if loss_snapshot:
    print(f"✅ Active loss exists: ₹{loss_snapshot.loss_amount}")
    print(f"   Remaining loss: ₹{loss_snapshot.get_remaining_loss()}")
else:
    print("❌ No active loss found - this is why payments can't be recorded")

# 2. Check recent transactions
recent = Transaction.objects.filter(
    client_exchange=client_exchange,
    transaction_type='SETTLEMENT'
).order_by('-created_at')[:5]

for tx in recent:
    print(f"SETTLEMENT: ₹{tx.amount} on {tx.date} (capital_closed: ₹{tx.capital_closed})")
```

---

### Step 5: Verify Form Data

**Check what's being sent to the server:**

1. **In Browser Console, before clicking "Record Payment", run:**
   ```javascript
   const form = document.getElementById('settlement-form-content');
   const formData = new FormData(form);
   for (let [key, value] of formData.entries()) {
       console.log(key + ': ' + value);
   }
   ```

2. **Verify these fields exist:**
   - ✅ `client_id` (should be a number)
   - ✅ `client_exchange_id` (should be a number)
   - ✅ `amount` (should be your payment amount, e.g., "10")
   - ✅ `payment_type` (should be "client_pays")
   - ✅ `date` (should be a date string, e.g., "2025-01-15")
   - ✅ `csrfmiddlewaretoken` (should be a long string)

3. **If any field is missing:**
   - Check the form HTML
   - Verify `showSettlementForm` is setting all fields correctly

---

## 🐛 Common Issues & Fixes

### Issue 1: Form Action Not Set

**Symptoms:**
- Console shows: `Form action not set`
- Form doesn't submit

**Fix:**
- Check `showSettlementForm` function
- Verify `form.action` is set based on client type
- Check URL patterns in `urls.py`

---

### Issue 2: Validation Too Strict

**Symptoms:**
- Alert: "Amount cannot exceed ₹X"
- Even though amount is less than pending

**Fix:**
- Check `data-raw-max` attribute on amount input
- Verify it's set to raw pending (not rounded)
- Check `showSettlementForm` sets this correctly

---

### Issue 3: No Active Loss

**Symptoms:**
- Backend error: "No active loss to settle"
- LossSnapshot doesn't exist or `is_settled=True`

**Fix:**
- Check if LossSnapshot exists:
  ```python
  LossSnapshot.objects.filter(
      client_exchange=client_exchange,
      is_settled=False
  ).exists()
  ```
- If not, create one or check why it was marked as settled

---

### Issue 4: JavaScript Not Loading

**Symptoms:**
- `showSettlementForm is not defined`
- Button click does nothing

**Fix:**
- Check browser console for JavaScript errors
- Verify `showSettlementForm` is defined at top of page
- Clear browser cache and refresh (Ctrl+F5)

---

### Issue 5: CSRF Token Missing

**Symptoms:**
- `403 Forbidden` error
- "CSRF verification failed"

**Fix:**
- Verify `{% csrf_token %}` is in the form
- Check if form is inside a modal (CSRF token should still work)

---

## 🧪 Quick Test

**Test if the form works at all:**

1. Open browser console (F12)
2. Click "Record Share Settlement" button
3. Enter amount: `10`
4. Select a date
5. Click "Record Payment"
6. Watch console for:
   - `handleFormSubmit called`
   - `Form validation passed`
   - `Allowing form submission`
7. Check network tab for:
   - POST request to `/company-clients/settle-payment/` (or similar)
   - Response status: `200` or `302`

**If you see all of these, the form is submitting correctly.**

**If you don't see the POST request, the form is being blocked by JavaScript.**

---

## 📋 Checklist

Before reporting an issue, verify:

- [ ] Browser console shows no JavaScript errors
- [ ] `showSettlementForm` is called when clicking button
- [ ] Modal opens and shows form
- [ ] Amount input accepts your value
- [ ] Date is selected
- [ ] `handleFormSubmit` is called when clicking "Record Payment"
- [ ] Form validation passes (no alerts)
- [ ] POST request appears in Network tab
- [ ] Django server shows the request in logs
- [ ] LossSnapshot exists with `is_settled=False`
- [ ] Payment amount ≤ raw pending amount

---

## 🔧 If Still Not Working

**Provide this information:**

1. **Browser Console Output:**
   - Copy all console messages when clicking the button
   - Include any red error messages

2. **Network Tab:**
   - Check if POST request is made
   - What's the response status?
   - What's the response body?

3. **Django Server Logs:**
   - Copy the error traceback
   - Include the request details

4. **Database State:**
   - Run the Django shell checks above
   - Share the output

5. **What You're Trying:**
   - Client name
   - Exchange name
   - Pending amount shown
   - Payment amount you're entering
   - Date selected

---

## ✅ Expected Behavior

**When everything works correctly:**

1. Click "Record Share Settlement" → Modal opens
2. Enter amount (e.g., ₹10) → Amount accepted
3. Select date → Date selected
4. Click "Record Payment" → Confirmation dialog
5. Click "OK" → Form submits
6. Page redirects → Success message appears
7. Pending amount updates → Shows new pending (e.g., ₹80)

**If any step fails, that's where the issue is.**

