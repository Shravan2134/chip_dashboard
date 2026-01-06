# 📘 Pending Payments: Complete Reference Guide

## 🎯 CORE STATE (ONLY 3 REAL VARIABLES)

### **1. Old Balance (OB)**
**Definition:** Capital base after last settlement. Stored in `cached_old_balance`.

```
OB = cached_old_balance
```

**Bootstrap Rule (ERROR 1 FIX):**
```
IF cached_old_balance IS NULL:
    OB = SUM(all FUNDING transactions)
    cached_old_balance = OB  (update cache)
```

**After Settlement:**
```
IF NET < 0 (LOSS):
    OB_new = OB - capital_closed
ELSE IF NET > 0 (PROFIT):
    OB_new = OB + capital_closed

IF abs(CB - OB_new) < epsilon:
    OB_new = CB  (settled completely)
```

---

### **2. Current Balance (CB)**
**Definition:** Actual exchange balance from latest `BALANCE_RECORD`.

```
CB = Latest ClientDailyBalance.remaining_balance
    (excluding "Settlement adjustment" notes)
```

**Fallback:**
```
IF no balance record exists:
    CB = SUM(all FUNDING transactions)
```

---

### **3. Net Movement (NET)**
**Definition:** Difference between Current Balance and Old Balance.

```
NET = CB - OB
```

**Interpretation:**
- `NET < 0` → **LOSS** (client owes you)
- `NET > 0` → **PROFIT** (you owe client)
- `NET = 0` → **SETTLED** (no pending)

**Negative Zero Fix (ERROR 14 FIX):**
```
IF abs(NET) < epsilon:
    NET = 0
```

---

## 🎯 SHARE DEFINITIONS (CRITICAL)

### **Total Share Percentage**

```
IF my client:
    total_share_pct = my_share_pct        # usually 10
    my_share_pct_effective = my_share_pct  # 10
    company_share_pct = 0

IF company client:
    total_share_pct = 10                  # ALWAYS 10 (CRITICAL!)
    my_share_pct_effective = 1              # you get 1%
    company_share_pct = 9                  # company gets 9%
```

**🚨 CRITICAL RULE:**
- **NEVER use `my_share_pct` for `capital_closed` in company clients**
- **ALWAYS use `total_share_pct = 10` for company clients**

---

### **Movement Amount**

```
movement = abs(NET)
movement = |CB - OB|
```

---

## 💰 PENDING AMOUNTS (STATELESS, ALWAYS RECALCULATED)

### **Formulas:**

```
movement = abs(NET)

pending_total = movement × total_share_pct / 100
my_pending = movement × my_share_pct_effective / 100
company_pending = movement × company_share_pct / 100
```

### **Display Logic:**
- `NET < 0` (LOSS) → Display as "Client owes"
- `NET > 0` (PROFIT) → Display as "You owe"
- Hide row if `pending_total == 0`

### **Key Rules:**
- ✅ Pending is **NEVER stored**
- ✅ Pending is **NEVER reduced**
- ✅ Pending is **ALWAYS recalculated** from OB & CB
- ✅ Pending is **UI-only** (not used for validation)

---

## 📊 TOTAL LOSS CALCULATION

### **Formula:**

```
Total Loss = |NET|  (when NET < 0)
Total Loss = 0      (when NET >= 0)
```

**For Loss Case:**
```
Total Loss = OB - CB  (when OB > CB)
```

**Alternative:**
```
Total Loss = |CB - OB|  (when CB < OB)
Total Loss = 0          (when CB >= OB)
```

---

## 🧮 SHARE CALCULATIONS

### **Combined Share (Total Share)**

```
Combined Share = movement × total_share_pct / 100
Combined Share = |NET| × total_share_pct / 100
```

**Example:**
```
Loss = ₹90, total_share_pct = 10%
Combined Share = 90 × 10 / 100 = ₹9
```

---

### **My Share (Your Cut)**

**For My Clients:**
```
My Share = Combined Share
My Share = movement × my_share_pct / 100
```

**For Company Clients:**
```
My Share = movement × 1 / 100
My Share = |NET| × 1 / 100
```

**General Formula:**
```
IF company client:
    My Share = |NET| × 1 / 100
ELSE:
    My Share = |NET| × my_share_pct / 100
```

---

### **Company Share**

**Formula:**
```
Company Share = |NET| × 9 / 100  (only for company clients)
Company Share = 0                (for my clients)
```

**Verification:**
```
For Company Clients:
    My Share + Company Share = Combined Share
    1% + 9% = 10% ✓
```

---

## 💸 SETTLEMENT (PARTIAL PAYMENT) LOGIC

### **Step 1: Recompute State (ERROR 2 FIX)**

```
✅ ALWAYS recalculate fresh inside settlement transaction:
OB = get_old_balance_after_settlement(locked_client_exchange)
CB = get_exchange_balance(locked_client_exchange, use_cache=False)
NET = CB - OB  (recomputed fresh)
movement = abs(NET)
```

**🚫 Never trust cached NET for settlement**

---

### **Step 2: Validate (NO pending math here)**

```
capital_closed = payment × 100 / total_share_pct
```

**Validation Rules (ERROR 3 FIX):**
```
REJECT if capital_closed >= movement + epsilon
REJECT if payment <= 0
REJECT if NET direction would flip after settlement
```

**Epsilon Definition (ERROR 7 FIX):**
```
epsilon = Decimal("0.0001")
```

---

### **Step 3: Move Old Balance**

```
IF NET < 0 (LOSS):
    OB_new = OB - capital_closed

IF NET > 0 (PROFIT):
    OB_new = OB + capital_closed
```

---

### **Step 4: Finalize**

```
IF abs(CB - OB_new) < epsilon:
    OB_new = CB  (settled completely)

Then:
cached_old_balance = OB_new
```

---

## 🔒 SETTLEMENT ORDERING (ERROR 4 FIX)

### **Deterministic Ordering Rule:**

```
Settlements MUST be applied in:
ORDER BY created_at ASC, id ASC
```

**Why:**
- Date alone is insufficient
- Same-second settlements need deterministic order
- Prevents non-deterministic OB calculations

---

## 📝 COMPLETE CALCULATION FLOW

### **Scenario: Loss with Partial Payment**

**Initial State:**
```
Funding = ₹100
CB = ₹10
OB = ₹100 (no settlement yet)
NET = 10 - 100 = -90 (LOSS)
```

**Step 1: Calculate Movement**
```
movement = |NET| = 90
```

**Step 2: Calculate Pending**
```
total_share_pct = 10
pending_total = 90 × 10 / 100 = ₹9
```

**Step 3: Client Pays ₹8.5**
```
capital_closed = 8.5 × 100 / 10 = ₹85
OB_new = 100 - 85 = ₹15
```

**Step 4: Recalculate NET**
```
NET_new = 10 - 15 = -5 (remaining loss)
movement_new = 5
```

**Step 5: Recalculate Pending**
```
pending_new = 5 × 10 / 100 = ₹0.5
```

**Result:**
- Old Balance: ₹100 → ₹15
- Pending: ₹9 → ₹0.5
- Remaining Loss: ₹5

---

## 🧮 SHARE CALCULATION EXAMPLES

### **Example 1: My Client - Loss**
```
Total Loss = ₹90
my_share_pct = 10%

movement = 90
total_share_pct = 10

Combined Share = 90 × 10 / 100 = ₹9
My Share = ₹9 (you get full 10%)
Company Share = ₹0 (not applicable)
```

---

### **Example 2: Company Client - Loss**
```
Total Loss = ₹90
total_share_pct = 10
my_share_pct_effective = 1
company_share_pct = 9

movement = 90

Combined Share = 90 × 10 / 100 = ₹9
My Share = 90 × 1 / 100 = ₹0.9 (you get 1%)
Company Share = 90 × 9 / 100 = ₹8.1 (company gets 9%)
Verification: 0.9 + 8.1 = ₹9 ✓
```

---

### **Example 3: Company Client - Profit**
```
Total Profit = ₹100
total_share_pct = 10
my_share_pct_effective = 1
company_share_pct = 9

movement = 100

Combined Share = 100 × 10 / 100 = ₹10
My Share = 100 × 1 / 100 = ₹1 (you pay 1%)
Company Share = 100 × 9 / 100 = ₹9 (company pays 9%)
Verification: 1 + 9 = ₹10 ✓
```

---

## 🔒 CRITICAL RULES & FIXES

### **ERROR 1 FIX: Bootstrap cached_old_balance**
```
IF cached_old_balance IS NULL:
    OB = SUM(all FUNDING)
    cached_old_balance = OB
```

### **ERROR 2 FIX: Recompute NET Fresh**
```
✅ ALWAYS recalculate CB, OB, NET inside settlement transaction
🚫 Never trust cached NET for settlement
```

### **ERROR 3 FIX: Stricter Validation**
```
REJECT if capital_closed >= movement + epsilon
REJECT if NET direction would flip
```

### **ERROR 4 FIX: Deterministic Ordering**
```
ORDER BY created_at, id  (not just date)
```

### **ERROR 7 FIX: Precision Policy**
```
epsilon = Decimal("0.0001")
All comparisons use epsilon
All UI values round to 2 decimals
```

### **ERROR 14 FIX: Negative Zero**
```
IF abs(NET) < epsilon:
    NET = 0
```

---

## 📝 QUICK REFERENCE FORMULAS

### **Core State:**
```
OB = cached_old_balance (bootstrap if NULL)
CB = Latest BALANCE_RECORD
NET = CB - OB
movement = |NET|
```

### **Share Definitions:**
```
IF my client:
    total_share_pct = my_share_pct
    my_share_pct_effective = my_share_pct
    company_share_pct = 0

IF company client:
    total_share_pct = 10
    my_share_pct_effective = 1
    company_share_pct = 9
```

### **Pending (Stateless):**
```
pending_total = movement × total_share_pct / 100
my_pending = movement × my_share_pct_effective / 100
company_pending = movement × company_share_pct / 100
```

### **Total Loss:**
```
Total Loss = |NET|  (when NET < 0)
Total Loss = OB - CB  (when OB > CB)
```

### **Settlement:**
```
capital_closed = payment × 100 / total_share_pct

IF NET < 0 (LOSS):
    OB_new = OB - capital_closed
ELSE IF NET > 0 (PROFIT):
    OB_new = OB + capital_closed

IF abs(CB - OB_new) < epsilon:
    OB_new = CB

cached_old_balance = OB_new
```

---

## ✅ VERIFICATION CHECKLIST

- [ ] OB moves ONLY on settlement
- [ ] CB comes ONLY from BALANCE_RECORD
- [ ] `capital_closed` uses `total_share_pct` (not `my_share_pct` for company clients)
- [ ] Pending is recalculated, never stored
- [ ] NET = CB - OB (never reversed)
- [ ] Profit & loss logic is symmetric (loss subtracts, profit adds)
- [ ] No clamp hacks or balance record edits
- [ ] Validation uses `capital_closed >= movement + epsilon`, not pending
- [ ] NET is recomputed fresh inside settlement transaction
- [ ] Settlements ordered by `created_at, id`
- [ ] Bootstrap OB when `cached_old_balance` is NULL
- [ ] Handle negative zero: `if abs(NET) < epsilon: NET = 0`
- [ ] For company clients: My Share (1%) + Company Share (9%) = Combined Share (10%)

---

## 🎯 SUMMARY

**Core Variables:**
- OB (Old Balance) - capital base after settlement
- CB (Current Balance) - actual exchange balance
- NET (CB - OB) - determines profit/loss

**Key Formulas:**
- `movement = |NET|`
- `pending = movement × total_share_pct / 100`
- `capital_closed = payment × 100 / total_share_pct`
- `OB_new = OB ± capital_closed` (based on NET direction)

**Critical Rules:**
- Company clients: ALWAYS use `total_share_pct = 10`
- Pending is always recalculated, never stored
- OB moves only on settlement
- NET recomputed fresh inside settlement transaction
- Settlements ordered by `created_at, id`
- Bootstrap OB when cache is NULL
- Use epsilon for all precision checks

---

**Last Updated:** January 3, 2025
**Version:** 2.0 (All Critical Errors Fixed)
**Status:** ✅ Complete - Production Ready



