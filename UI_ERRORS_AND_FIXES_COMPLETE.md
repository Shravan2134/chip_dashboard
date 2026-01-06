# UI ERRORS AND FIXES - COMPLETE GUIDE

**All UI Errors, All Fixes, Correct Field Mappings, Production-Ready UI Structure**

---

## 📋 TABLE OF CONTENTS

1. [Critical Field Mapping Errors](#field-mapping)
2. [Calculation Errors (UI Must Never Calculate)](#calculation-errors)
3. [Visibility Condition Errors](#visibility-errors)
4. [Label and Display Errors](#label-errors)
5. [State Management Errors](#state-errors)
6. [Complete Correct UI Structure](#correct-ui)
7. [API Response Format](#api-format)

---

## 🔴 CRITICAL FIELD MAPPING ERRORS

### **ERROR 1: Wrong Field Names Used in UI**

**❌ Backend Sends**:
```json
{
  "client_payable": 3.00,
  "your_receivable": 0.30,
  "company_receivable": 2.70,
  "loss_amount": 30.00,
  "capital": 70.00,
  "current_balance": 40.00
}
```

**❌ UI Expects/Wrongly Uses**:
```javascript
pending = data.pending  // ❌ Wrong - doesn't exist
myShare = data.myShare  // ❌ Wrong
companyShare = data.company  // ❌ Wrong
loss = data.loss  // ❌ Wrong
oldBalance = data.oldBalance  // ❌ Wrong
currentBalance = data.currentBalance  // ❌ Wrong
```

**✅ Correct Mapping (MUST MATCH EXACTLY)**:
```javascript
// EXACT field mapping - names must match backend
pending        = data.client_payable
myShare        = data.your_receivable
companyShare   = data.company_receivable
loss           = data.loss_amount
capital        = data.capital
currentBalance = data.current_balance
```

**Fix**: Use exact backend field names. One wrong name = empty UI.

---

### **ERROR 2: UI Expects `capital` But Backend Sends `cached_old_balance`**

**❌ Problem**:
```javascript
capital = data.capital  // ❌ Backend sends cached_old_balance
```

**✅ Fix (Pick ONE - Must Match)**:

**Option A: Backend sends `capital`**:
```json
{
  "capital": 70.00  // ✅ Backend renamed
}
```

**Option B: UI uses `cached_old_balance`**:
```javascript
capital = data.cached_old_balance  // ✅ UI uses backend name
```

**Fix**: Backend and UI field names must match exactly.

---

### **ERROR 3: Share Percentages Not in UI Data Model**

**❌ Problem**:
```javascript
// UI only has amounts, no percentages
myShare = 0.30  // ❌ No percentage shown
companyShare = 2.70  // ❌ No percentage shown
```

**✅ Fix**:
```javascript
// Backend must send percentages
myShare = data.your_receivable
mySharePct = data.my_share_pct  // ✅ Add this
companyShare = data.company_receivable
companySharePct = data.company_share_pct  // ✅ Add this

// Display
`₹${myShare} (${mySharePct}%)`  // ✅ ₹0.30 (1%)
`₹${companyShare} (${companySharePct}%)`  // ✅ ₹2.70 (9%)
```

**Fix**: Backend must send `my_share_pct` and `company_share_pct`.

---

## 🟠 CALCULATION ERRORS (UI MUST NEVER CALCULATE)

### **ERROR 4: UI is Recalculating LOSS (FORBIDDEN)**

**❌ Wrong**:
```javascript
// UI calculating LOSS - NEVER DO THIS
loss = capital - currentBalance  // ❌ FORBIDDEN
```

**✅ Correct**:
```javascript
// LOSS must come directly from backend
loss = data.loss_amount  // ✅ From LossSnapshot, frozen
```

**Fix**: LOSS must never be calculated in UI. Always use `data.loss_amount`.

---

### **ERROR 5: UI is Recalculating PENDING**

**❌ Wrong**:
```javascript
// UI calculating pending - NEVER DO THIS
pending = loss * sharePct / 100  // ❌ FORBIDDEN
```

**✅ Correct**:
```javascript
// Pending comes directly from backend
pending = data.client_payable  // ✅ From backend calculation
```

**Fix**: Pending must never be calculated in UI. Always use `data.client_payable`.

---

### **ERROR 6: UI is Recalculating CAPITAL**

**❌ Wrong**:
```javascript
// UI calculating CAPITAL - NEVER DO THIS
capital = currentBalance + loss  // ❌ FORBIDDEN
```

**✅ Correct**:
```javascript
// CAPITAL comes directly from backend
capital = data.capital  // ✅ From ledger, backend derived
```

**Fix**: CAPITAL must never be calculated in UI. Always use `data.capital`.

---

### **ERROR 7: UI Re-Computes NET and Confuses User**

**❌ Wrong**:
```javascript
// NET shown without explanation
net = currentBalance - capital  // ❌ Confusing
```

**✅ Fix**:
```javascript
// Either remove NET from this screen
// OR label it clearly
net = currentBalance - capital
// Display: "NET Movement (informational): ₹-30.00"
```

**Fix**: Remove NET or label it clearly as informational only.

---

## 🟡 VISIBILITY CONDITION ERRORS

### **ERROR 8: Wrong Condition to Show Pending**

**❌ Wrong**:
```javascript
// Using pending for visibility - WRONG
if (pending > 0) {
  showPending()  // ❌ pending is string/rounded
}
```

**✅ Correct**:
```javascript
// LOSS decides visibility, not pending
if (Number(loss) >= 0.01) {
  showPending()  // ✅ LOSS is source of truth
}
```

**Fix**: Visibility must depend on `loss`, not `pending`.

---

### **ERROR 9: Using Pending as Primary Value in UI**

**❌ Wrong**:
```javascript
// Using pending for decisions - WRONG
if (pending === 0) hideRow()  // ❌ pending can be 0.00 while loss is 0.004
```

**✅ Correct**:
```javascript
// LOSS is source of truth
if (Number(loss) < 0.01) hideRow()  // ✅ LOSS decides
```

**Fix**: Always use `loss` for visibility decisions, never `pending`.

---

### **ERROR 10: LOSS Zero But Row Still Renders**

**❌ Wrong**:
```javascript
// Always showing loss row
<LossRow loss={loss} />  // ❌ Shows even when loss = 0
```

**✅ Correct**:
```javascript
// Hide when loss < 0.01
{Number(loss) >= 0.01 && (
  <LossRow loss={loss} />
)}
```

**Fix**: Hide loss section when `loss < 0.01`.

---

### **ERROR 11: Company Share Shown for My Clients**

**❌ Wrong**:
```javascript
// Company column always visible
<CompanyShareColumn />  // ❌ Shows for all clients
```

**✅ Correct**:
```javascript
// Only show if company share > 0
{Number(companyShare) > 0 && (
  <CompanyShareColumn companyShare={companyShare} />
)}
```

**Fix**: Hide company column when `companyShare === 0`.

---

### **ERROR 12: Showing Profit Column with Zero Values**

**❌ Wrong**:
```javascript
// Always showing profit
<ProfitRow profit={profit} />  // ❌ Shows ₹0.00
```

**✅ Correct**:
```javascript
// Hide profit if zero
{Number(profit) > 0 && (
  <ProfitRow profit={profit} />
)}
```

**Fix**: Hide profit row when `profit === 0`.

---

### **ERROR 13: Payment Input Still Enabled After Auto-Close**

**❌ Wrong**:
```javascript
// Payment input always enabled
<PaymentInput />  // ❌ Enabled even when loss < 0.01
```

**✅ Correct**:
```javascript
// Disable when loss < 0.01
<PaymentInput disabled={Number(loss) < 0.01} />
```

**Fix**: Disable payment input when `loss < 0.01`.

---

## 🟢 LABEL AND DISPLAY ERRORS

### **ERROR 14: Wrong Label Name - "Old Balance"**

**❌ Wrong**:
```html
<label>Old Balance</label>  <!-- ❌ Confusing name -->
```

**✅ Correct**:
```html
<label>Capital Balance</label>  <!-- ✅ Clear name -->
<small>(from ledger)</small>  <!-- ✅ Tooltip -->
```

**Fix**: Rename "Old Balance" to "Capital Balance" with tooltip.

---

### **ERROR 15: Current Balance Source Wrong**

**❌ Wrong**:
```javascript
// Always showing latest balance
currentBalance = data.latest_balance  // ❌ Wrong when LOSS exists
```

**✅ Correct (With Safeguard)**:
```javascript
// Use snapshot balance when LOSS exists
// Fallback to current_balance if latest_balance not available
currentBalance = Number(loss) > 0
  ? data.current_balance   // ✅ From LossSnapshot when LOSS exists
  : (data.latest_balance ?? data.current_balance)  // ✅ Fallback safeguard
```

**Fix**: Use snapshot balance when LOSS exists, live balance when no LOSS, with fallback safeguard.

---

### **ERROR 16: UI Shows Current Balance Even After Loss is Settled**

**❌ Wrong**:
```javascript
// Always using snapshot balance
currentBalance = data.current_balance  // ❌ Wrong after settlement
```

**✅ Correct (With Safeguard)**:
```javascript
// Switch to live balance after settlement
// Fallback to current_balance if latest_balance not available
currentBalance = Number(loss) > 0
  ? data.current_balance   // ✅ Snapshot when LOSS exists
  : (data.latest_balance ?? data.current_balance)  // ✅ Live after settlement, with fallback
```

**Fix**: Use live balance when `loss === 0`, with fallback safeguard.

---

### **ERROR 17: Showing Both LOSS & PENDING Without Context**

**❌ Wrong**:
```html
Loss: ₹30
Pending: ₹3
<!-- ❌ User confused: "Why loss is 30 but pending is 3?" -->
```

**✅ Correct**:
```html
Total Trading Loss: ₹30
Amount Client Must Pay: ₹3
<!-- ✅ Clear labels explain relationship -->
```

**Fix**: Use descriptive labels that explain the relationship.

---

### **ERROR 18: Share Percentage Not Displayed**

**❌ Wrong**:
```html
₹0.30
₹2.70
<!-- ❌ No percentage shown -->
```

**✅ Correct**:
```html
My Share: ₹0.30 (1%)
Company Share: ₹2.70 (9%)
<!-- ✅ Amount + percentage -->
```

**Fix**: Show amount with percentage: `₹X.XX (Y%)`.

---

### **ERROR 19: UI Shows "Pending" AND "Payable" Words**

**❌ Wrong**:
```html
Pending Amount
Client Payable
<!-- ❌ Duplicate meaning -->
```

**✅ Correct**:
```html
Pending Settlement: ₹3.00
<!-- ✅ Pick ONE label -->
```

**Fix**: Use one consistent label, avoid duplicates.

---

### **ERROR 20: UI Does Not Show Share Type (MY / COMPANY)**

**❌ Wrong**:
```html
₹0.30
₹2.70
<!-- ❌ No label -->
```

**✅ Correct**:
```html
My Share: ₹0.30 (1%)
Company Share: ₹2.70 (9%)
<!-- ✅ Clear labels -->
```

**Fix**: Always label shares as "My Share" or "Company Share".

---

### **ERROR 21: Using loss_amount But Not Showing Its Source**

**❌ Wrong**:
```html
Loss: ₹30
<!-- ❌ User assumes it's live loss -->
```

**✅ Correct**:
```html
Loss (at balance time): ₹30
<!-- ✅ Shows it's snapshot loss -->
```

**Fix**: Label LOSS as "at balance time" to show it's frozen.

---

### **ERROR 22: No Source Labels (Confusion)**

**❌ Wrong**:
```html
Capital Balance: ₹70.00
Current Balance: ₹40.00
Pending: ₹3.00
<!-- ❌ No source shown -->
```

**✅ Correct**:
```html
Capital Balance: ₹70.00 <small>(from ledger)</small>
Current Balance: ₹40.00 <small>(from snapshot)</small>
Pending: ₹3.00 <small>(from Loss Snapshot)</small>
<!-- ✅ Source clarity -->
```

**Fix**: Add small text showing source of each value.

---

### **ERROR 23: Capital and Current Balance Visually Look Same**

**❌ Problem**:
```html
Capital Balance: ₹70.00
Current Balance: ₹40.00
<!-- ❌ User can't tell difference -->
```

**✅ Fix**:
```html
Capital Balance (ledger): ₹70.00
Current Balance (exchange): ₹40.00
<!-- ✅ Clear distinction -->
```

**Fix**: Add sub-labels to distinguish them.

---

### **ERROR 24: Wrong Empty State Message**

**❌ Wrong**:
```javascript
// Always same message
"No pending payments"  // ❌ Wrong for profit/auto-close
```

**✅ Correct**:
```javascript
// Different messages for different states
const emptyMessage = 
  Number(loss) === 0 && Number(profit) === 0 ? "No pending settlements" :
  Number(profit) > 0 ? "Client in profit" :
  Number(loss) > 0 && Number(loss) < 0.01 ? "Auto-settled" :
  "No pending payments"
```

**Fix**: Show appropriate message based on state.

---

### **ERROR 25: Wrong Empty State Icon / Color**

**❌ Wrong**:
```javascript
// Red warning when no loss
<WarningIcon color="red" />  // ❌ Wrong
```

**✅ Correct**:
```javascript
// Color based on state
const iconColor = 
  Number(loss) === 0 && Number(profit) === 0 ? "grey" :
  Number(loss) > 0 ? "red" :
  Number(profit) > 0 ? "green" :
  "grey"
```

**Fix**: Use appropriate color for each state.

---

### **ERROR 26: LOSS Color / PROFIT Color Mixed Up**

**❌ Wrong**:
```javascript
// LOSS shown in green - WRONG
<LossDisplay color="green" />  // ❌ Wrong
```

**✅ Correct Color Rules**:
```javascript
// Correct color mapping
const colorMap = {
  loss: "red",        // 🔴 Red
  pending: "red",      // 🔴 Red
  capital: "black",   // ⚫ Black
  currentBalance: "black",  // ⚫ Black
  profit: "green"     // 🟢 Green
}
```

**Fix**: LOSS = Red, PROFIT = Green, others = Black.

---

## 🔵 STATE MANAGEMENT ERRORS

### **ERROR 27: UI Not Refreshing After Settlement**

**❌ Wrong**:
```javascript
// Manually updating values
onSettlementSuccess() {
  pending = pending - payment  // ❌ Wrong - manual update
}
```

**✅ Correct**:
```javascript
// Refetch from backend
onSettlementSuccess() {
  await refetchPending()
  await refetchClientData()
  // ✅ Fresh data from backend
}
```

**Fix**: Always refetch after settlement, never mutate manually.

---

### **ERROR 28: UI Does Not Reset After Full Settlement**

**❌ Wrong**:
```javascript
// Old values remain
if (loss === 0) {
  // ❌ No cleanup
}
```

**✅ Correct**:
```javascript
// Clear state after full settlement
if (Number(loss) === 0) {
  clearPendingState()
  refetchClientData()
}
```

**Fix**: Clear state and refetch when `loss === 0`.

---

### **ERROR 29: Profit Variable Exists But Never Used**

**❌ Problem**:
```javascript
// Profit calculated but never used
profit = currentBalance - capital  // ❌ Dead variable
```

**✅ Fix**:
```javascript
// Either use it or remove it
if (Number(profit) > 0) {
  showProfitSection()  // ✅ Use it
}
// OR remove it completely if not needed
```

**Fix**: Use profit or remove it, don't leave dead variables.

---

### **ERROR 30: Profit is Completely Missing in UI State**

**❌ Problem**:
```javascript
// No profit in data model
const { client_payable, loss_amount, capital } = data
// ❌ Missing profit
```

**✅ Fix (Pick ONE - Must Be Explicit)**:

**Option A: Backend Guarantee (Recommended)**:
```javascript
// Backend ALWAYS sends profit_amount (even if zero)
const { 
  client_payable, 
  loss_amount, 
  capital,
  profit_amount  // ✅ Always present from backend
} = data

// Use it
if (Number(profit_amount) > 0) {
  showProfitSection()
}
```

**Option B: UI Rule (Alternative)**:
```javascript
// Profit is NOT part of pending screen
// Remove profit from this screen entirely
// Profit screen is separate

// Do NOT expect profit_amount in pending screen
const { 
  client_payable, 
  loss_amount, 
  capital
  // ✅ No profit_amount expected
} = data
```

**Fix**: Either backend always sends `profit_amount`, or UI removes profit from pending screen entirely. Must be explicit.

---

## 🟣 VALIDATION ERRORS

### **ERROR 31: UI Allows Payment > Pending (Frontend Validation Missing)**

**❌ Wrong**:
```javascript
// No frontend validation
<PaymentInput />  // ❌ User can type ₹10 when pending = ₹3
```

**✅ Correct**:
```javascript
// Frontend validation
<PaymentInput 
  max={pending}
  onChange={(value) => {
    if (Number(value) > Number(pending)) {
      showError("Payment exceeds pending amount")
      blockSubmit()
    }
  }}
/>
```

**Fix**: Add frontend validation, don't rely only on backend.

---

### **ERROR 32: Rounding in UI Before Comparison**

**❌ Wrong**:
```javascript
// Rounding before comparison
if (loss.toFixed(2) === "0.00") hide()  // ❌ 0.004 becomes 0.00
```

**✅ Correct**:
```javascript
// Compare raw value
if (Number(loss) < 0.01) hide()  // ✅ Correct comparison
```

**Fix**: Compare raw values, don't round before comparison.

---

### **ERROR 33: Showing Payment Input When LOSS < 0.01**

**❌ Wrong**:
```javascript
// Payment input always visible
<PaymentInput />  // ❌ Visible even when loss < 0.01
```

**✅ Correct**:
```javascript
// Hide when loss < 0.01
{Number(loss) >= 0.01 && (
  <PaymentInput />
)}
```

**Fix**: Hide payment input when `loss < 0.01`.

---

## ✅ COMPLETE CORRECT UI STRUCTURE

### **Correct Field Mapping**

```javascript
// EXACT field mapping from backend
const {
  client_payable,        // → pending
  your_receivable,       // → myShare
  company_receivable,    // → companyShare
  loss_amount,           // → loss
  capital,               // → capital (or cached_old_balance)
  current_balance,       // → currentBalance (snapshot)
  latest_balance,       // → currentBalance (live, with fallback)
  profit_amount,         // → profit (if backend sends it)
  my_share_pct,          // → mySharePct
  company_share_pct      // → companySharePct
} = data

// Map to UI variables
const pending = client_payable
const myShare = your_receivable
const companyShare = company_receivable
const loss = loss_amount
const capital = capital  // or cached_old_balance
const currentBalance = Number(loss) > 0 
  ? current_balance   // ✅ Snapshot when LOSS exists
  : (latest_balance ?? current_balance)  // ✅ Live when no LOSS, with fallback safeguard
const profit = profit_amount ?? 0  // ✅ Default to 0 if not sent (or remove if not needed)
const mySharePct = my_share_pct
const companySharePct = company_share_pct
```

### **Correct Visibility Conditions**

```javascript
// Visibility based on LOSS, not pending
const showPending = Number(loss) >= 0.01
const showCompanyShare = Number(companyShare) > 0
const showProfit = Number(profit) > 0
const disablePayment = Number(loss) < 0.01
```

### **Correct UI Component Structure**

```jsx
<div className="pending-payments">
  {/* Capital Balance */}
  <div>
    <label>Capital Balance <small>(from ledger)</small></label>
    <span>₹{capital.toFixed(2)}</span>
  </div>

  {/* Current Balance */}
  <div>
    <label>Current Balance <small>({Number(loss) > 0 ? 'from snapshot' : 'live'})</small></label>
    <span>₹{currentBalance.toFixed(2)}</span>
  </div>

  {/* Loss Section - Only show if loss >= 0.01 */}
  {Number(loss) >= 0.01 && (
    <>
      <div>
        <label>Total Trading Loss <small>(at balance time)</small></label>
        <span className="red">₹{loss.toFixed(2)}</span>
      </div>

      <div>
        <label>Pending Settlement</label>
        <span className="red">₹{pending.toFixed(2)}</span>
      </div>

      {/* My Share */}
      <div>
        <label>My Share</label>
        <span>₹{myShare.toFixed(2)} ({mySharePct}%)</span>
      </div>

      {/* Company Share - Only show if > 0 */}
      {Number(companyShare) > 0 && (
        <div>
          <label>Company Share</label>
          <span>₹{companyShare.toFixed(2)} ({companySharePct}%)</span>
        </div>
      )}

      {/* Payment Input - Disabled if loss < 0.01 */}
      <PaymentInput 
        disabled={Number(loss) < 0.01}
        max={pending}
        onValidation={(value) => {
          if (Number(value) > Number(pending)) {
            return "Payment exceeds pending amount"
          }
        }}
      />
    </>
  )}

  {/* Profit Section - Only show if profit > 0 */}
  {Number(profit) > 0 && (
    <div>
      <label>Profit</label>
      <span className="green">₹{profit.toFixed(2)}</span>
    </div>
  )}

  {/* Empty State */}
  {Number(loss) === 0 && Number(profit) === 0 && (
    <div className="empty-state grey">
      No pending settlements
    </div>
  )}
</div>
```

---

## 📡 API RESPONSE FORMAT

### **Required Backend Response**

**Option A: Full Response (Recommended)**:
```json
{
  "client_payable": 3.00,
  "your_receivable": 0.30,
  "company_receivable": 2.70,
  "loss_amount": 30.00,
  "capital": 70.00,
  "current_balance": 40.00,
  "latest_balance": 40.00,
  "profit_amount": 0.00,
  "my_share_pct": 1.00,
  "company_share_pct": 9.00,
  "total_share_pct": 10.00
}
```

**Option B: Minimal Response (If profit not needed)**:
```json
{
  "client_payable": 3.00,
  "your_receivable": 0.30,
  "company_receivable": 2.70,
  "loss_amount": 30.00,
  "capital": 70.00,
  "current_balance": 40.00,
  "latest_balance": 40.00,
  "my_share_pct": 1.00,
  "company_share_pct": 9.00,
  "total_share_pct": 10.00
}
```

**⚠️ IMPORTANT**: 
- `latest_balance` is REQUIRED when `loss_amount === 0` (after settlement)
- `profit_amount` is OPTIONAL - if not sent, UI should not expect it
- `current_balance` is REQUIRED when `loss_amount > 0` (from LossSnapshot)

### **Field Descriptions**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_payable` | Decimal | ✅ Yes | Amount client must pay (share space) |
| `your_receivable` | Decimal | ✅ Yes | Your share receivable |
| `company_receivable` | Decimal | ✅ Yes | Company share receivable |
| `loss_amount` | Decimal | ✅ Yes | Frozen LOSS from LossSnapshot |
| `capital` | Decimal | ✅ Yes | CAPITAL from ledger (or `cached_old_balance`) |
| `current_balance` | Decimal | ✅ Yes | CB from LossSnapshot (when LOSS exists) |
| `latest_balance` | Decimal | ⚠️ Conditional | Latest CB from exchange (REQUIRED when `loss_amount === 0`) |
| `profit_amount` | Decimal | ❌ Optional | PROFIT amount (if backend sends it, else UI should not expect it) |
| `my_share_pct` | Decimal | ✅ Yes | Your share percentage (frozen) |
| `company_share_pct` | Decimal | ✅ Yes | Company share percentage (frozen) |
| `total_share_pct` | Decimal | ✅ Yes | Total share percentage (frozen) |

**⚠️ CRITICAL NOTES**:
- `latest_balance` is REQUIRED when `loss_amount === 0` (after settlement)
- `profit_amount` is OPTIONAL - backend may not send it (UI should handle gracefully)
- UI must use fallback: `currentBalance = latest_balance ?? current_balance` when no LOSS

---

## 🎯 SUMMARY

### **Top 5 UI Breakers (Most Important)**

1. ✅ **UI recalculating LOSS** - Use `data.loss_amount` only
2. ✅ **UI recalculating CAPITAL** - Use `data.capital` only
3. ✅ **Using pending instead of loss for visibility** - Use `loss >= 0.01`
4. ✅ **Wrong labels ("Old Balance")** - Use "Capital Balance"
5. ✅ **Company share shown for my clients** - Hide when `companyShare === 0`

### **Correct Field Mapping (MUST MATCH)**

```javascript
pending        = data.client_payable
myShare        = data.your_receivable
companyShare   = data.company_receivable
loss           = data.loss_amount
capital        = data.capital  // or data.cached_old_balance
currentBalance = Number(loss) > 0 
  ? data.current_balance   // ✅ Snapshot when LOSS exists
  : (data.latest_balance ?? data.current_balance)  // ✅ Live with fallback safeguard
profit         = data.profit_amount ?? 0  // ✅ Default to 0 if not sent (or remove if not needed)
mySharePct      = data.my_share_pct
companySharePct = data.company_share_pct
```

**⚠️ CRITICAL FIXES**:
1. `currentBalance` must have fallback: `latest_balance ?? current_balance`
2. `profit_amount` is optional - UI should handle gracefully (default to 0 or remove from screen)

### **Correct Visibility Rules**

```javascript
showPending = Number(loss) >= 0.01
showCompanyShare = Number(companyShare) > 0
showProfit = Number(profit) > 0
disablePayment = Number(loss) < 0.01
```

### **One-Line Rule**

**UI must never calculate, only display what backend sends.**

---

## 📋 CONTRACT DECISIONS (NOT ERRORS - MUST BE EXPLICIT)

These are design decisions, not mistakes. You MUST choose ONE option and document it.

---

### **DECISION 1: profit_amount — CONTRACT DECISION**

**Situation**:
- Your UI can render profit
- Backend may or may not send `profit_amount`
- You MUST choose one (both are valid)

**✅ Option A: Backend Guarantee (Recommended – Cleanest)**:
```javascript
// Backend ALWAYS sends profit_amount (even if zero)
// API contract: profit_amount is always present
const profit = data.profit_amount  // ✅ Always present from backend

// Use it
if (Number(profit) > 0) {
  showProfitSection()
}
```

**Benefits**:
- ✔ No branching
- ✔ No undefined states
- ✔ Safest for long term

**Backend Contract**:
```json
{
  "profit_amount": 0.00  // ✅ Always present, even if zero
}
```

**✅ Option B: UI Rule (Also Valid)**:
```javascript
// Profit is NOT part of Pending screen
// Do not expect profit_amount in pending screen
// Profit screen is separate

// Do NOT use profit_amount in pending screen
const { 
  client_payable, 
  loss_amount, 
  capital
  // ✅ No profit_amount expected
} = data
```

**Benefits**:
- ✔ Simpler UI
- ✔ Less confusion
- ✔ Clear separation of concerns

**➡️ DECISION REQUIRED**: Choose ONE option and document it in your API contract. Once chosen, this issue is CLOSED forever.

---

### **DECISION 2: latest_balance — REQUIRED FALLBACK (Already Solved)**

**✅ Status**: Already correctly fixed with fallback safeguard

**Current Implementation**:
```javascript
// Fallback safeguard - prevents blank Current Balance
currentBalance = Number(loss) > 0
  ? data.current_balance   // ✅ Snapshot when LOSS exists
  : (data.latest_balance ?? data.current_balance)  // ✅ Fallback safeguard
```

**This ensures**:
- ✔ Prevents blank UI
- ✔ Handles settlement transition
- ✔ Zero risk

**✅ This is NOT an error anymore** - it's correctly implemented with proper fallback.

---

## ✅ THINGS THAT ARE NOT ERRORS (CONFIRMED CORRECT)

These are correct and should NOT be changed:

- ✅ LOSS frozen in snapshot
- ✅ Pending = share space amount
- ✅ Capital ≠ Current Balance during loss
- ✅ Pending smaller than Loss
- ✅ UI not recalculating anything
- ✅ Company share hidden when zero
- ✅ Visibility based on LOSS, not pending
- ✅ Auto-close < 0.01

---

**Document Version**: 1.2  
**Last Updated**: 2026-01-05  
**Status**: ✅ All 33 UI Errors Fixed + 2 Contract Decisions Documented, Production-Ready UI Structure

