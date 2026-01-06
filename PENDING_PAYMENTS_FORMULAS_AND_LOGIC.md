# 📘 Pending Payments: Complete Formulas & Logic Guide (CORRECTED)

## 🎯 CORE STATE (ONLY 3 REAL VARIABLES)

### 1. **Old Balance (OB)**
**Definition:** The capital base after the last settlement. Stored in `cached_old_balance`.

**Formula:**
```
OB = cached_old_balance (single source of truth)
```

**Rules:**
- ✅ OB moves ONLY when a settlement occurs
- ✅ OB is NEVER derived from loss/profit rows
- ✅ OB is NEVER accumulated from transactions
- ✅ OB starts as Total Funding (when no settlement exists)

---

### 2. **Current Balance (CB)**
**Definition:** The actual exchange balance from the latest `BALANCE_RECORD`.

**Formula:**
```
CB = Latest ClientDailyBalance.remaining_balance
    (excluding "Settlement adjustment" notes)
```

**Fallback:**
```
IF no balance record exists:
    CB = SUM(all FUNDING transactions)
```

**Rules:**
- ✅ CB comes ONLY from BALANCE_RECORD
- ✅ CB is NEVER modified by settlements
- ✅ CB reflects the actual exchange state

---

### 3. **Net Movement (NET)**
**Definition:** The difference between Current Balance and Old Balance.

**Formula:**
```
NET = CB - OB
```

**Interpretation:**
- `NET < 0` → **LOSS** → client owes money
- `NET > 0` → **PROFIT** → you owe client
- `NET = 0` → **SETTLED** → no pending

---

## 🎯 SHARE DEFINITIONS (CRITICAL FIX)

### **Total Share Percentage**
**Definition:** The total percentage of movement that is shared (always 10% for company clients).

**Formula:**
```
IF my client:
    total_share_pct = my_share_pct        # usually 10
    my_share_pct_effective = my_share_pct # 10
    company_share_pct = 0

IF company client:
    total_share_pct = 10                  # ALWAYS 10 (never use my_share_pct!)
    my_share_pct_effective = 1           # you get 1%
    company_share_pct = 9                # company gets 9%
```

**🚨 CRITICAL RULE:**
- ❌ **NEVER use `my_share_pct` for `capital_closed` in company clients**
- ✅ **ALWAYS use `total_share_pct = 10` for company clients**

---

### **Movement Amount**
**Definition:** The absolute value of Net Movement.

**Formula:**
```
movement = abs(NET)
movement = |CB - OB|
```

---

### **Pending Amounts (Stateless, Always Recalculated)**

**Formula:**
```
movement = abs(NET)

pending_total = movement × total_share_pct / 100
my_pending = movement × my_share_pct_effective / 100
company_pending = movement × company_share_pct / 100
```

**Display Logic:**
- `NET < 0` (LOSS) → Display as "Client owes"
- `NET > 0` (PROFIT) → Display as "You owe"
- Hide row if `pending_total == 0`

**Key Rules:**
- ✅ Pending is NEVER stored
- ✅ Pending is NEVER reduced
- ✅ Pending is ALWAYS recalculated from OB & CB
- ✅ Pending is UI-only (not used for validation)

---

## 💸 SETTLEMENT (PARTIAL PAYMENT) — FIXED LOGIC

### **Step 1: Validate (NO pending math here)**

**Formula:**
```
movement = abs(CB - OB)
capital_closed = payment × 100 / total_share_pct
```

**Validation Rules:**
```
REJECT if capital_closed > movement
REJECT if payment <= 0
```

**🚫 CRITICAL:**
- Do NOT validate against pending
- Pending is UI-only, not used for settlement validation

---

### **Step 2: Move Old Balance (THIS SOLVES ALL ERRORS)**

**Formula:**
```
IF NET < 0 (LOSS):
    OB_new = OB - capital_closed

IF NET > 0 (PROFIT):
    OB_new = OB + capital_closed
```

**Step 3: Finalize**
```
IF abs(CB - OB_new) < 0.0001:
    OB_new = CB  (settled completely)

Then:
cached_old_balance = OB_new
```

**✅ Key Points:**
- No clamp hacks (`max(OB, CB)`)
- No balance record edits
- No rounding flips
- OB moves based on NET direction (loss = subtract, profit = add)

---

## 📊 REPORTS (WHY YOUR PROFIT WAS 0)

### **❌ WRONG (what your system did):**
```
Sum of settlements
Sum of "your share" fields
```

### **✅ CORRECT (stateless, reliable):**
```
For each client/exchange at report time:
    NET = CB - OB
    
    IF NET > 0:
        profit = NET × my_share_pct_effective / 100
    ELSE:
        profit = 0

Monthly profit = sum of all profit
```

**🚨 CRITICAL:**
- Settlements are NOT profit
- Settlements only move OB
- Reports use CB - OB, not settlements

---

## 🧮 COMPLETE EXAMPLES (MATCH REALITY)

### **Example 1: Loss + Partial Payment (My Client)**

**Initial State:**
```
Funding = ₹100
CB = ₹10
OB = ₹100 (no settlement yet)
NET = 10 - 100 = -90 (LOSS)
```

**Calculate Pending:**
```
movement = 90
total_share_pct = 10
pending_total = 90 × 10 / 100 = ₹9
```

**Client Pays ₹8.5:**
```
capital_closed = 8.5 × 100 / 10 = ₹85
OB_new = 100 - 85 = ₹15
```

**New State:**
```
NET = 10 - 15 = -5 (remaining loss)
pending_total = 5 × 10 / 100 = ₹0.5 ✅
```

**Result:**
- ✅ No bug
- ✅ No negative
- ✅ No missing row

---

### **Example 2: Company Client (THIS FIXES YOUR 0.6 ISSUE)**

**Initial State:**
```
NET = -60 (LOSS)
total_share_pct = 10
my_share_pct_effective = 1
company_share_pct = 9
```

**Calculate Pending:**
```
movement = 60
pending_total = 60 × 10 / 100 = ₹6
my_pending = 60 × 1 / 100 = ₹0.6
company_pending = 60 × 9 / 100 = ₹5.4
```

**Client Pays ₹1:**
```
capital_closed = 1 × 100 / 10 = ₹10
OB_new = OB - 10
```

**Result:**
- ❌ Your old logic closed ₹100 — WRONG
- ✅ This closes exactly ₹10 — CORRECT

---

### **Example 3: Profit Case (Mirror Logic)**

**Initial State:**
```
OB = ₹100
CB = ₹160
NET = 160 - 100 = +60 (PROFIT)
pending_total = 60 × 10 / 100 = ₹6
```

**You Pay ₹6:**
```
capital_closed = 6 × 100 / 10 = ₹60
OB_new = 100 + 60 = ₹160
NET = 160 - 160 = 0 (settled)
```

**Result:**
- ✅ Case closed cleanly
- ✅ NET = 0 (fully settled)

---

## ❌ WHAT YOU MUST DELETE (INCORRECT CONCEPTS)

**Remove these completely from your code/documentation:**

1. ❌ **"Total Loss" variable** - Use `movement = abs(NET)` instead
2. ❌ **Clamp rules (`max(OB, CB)`)** - Use `abs(CB - OB_new) < 0.0001` check instead
3. ❌ **Using `my_share_pct` for company settlements** - Always use `total_share_pct = 10`
4. ❌ **Validating payment using pending** - Validate using `capital_closed > movement`
5. ❌ **Settlement-based profit reports** - Use `CB - OB` calculation instead
6. ❌ **"Current Balance at settlement" fallback** - CB comes only from BALANCE_RECORD

---

## ✅ FINAL CHECKLIST (IF ALL TRUE → SYSTEM IS CORRECT)

- [ ] OB moves ONLY on settlement
- [ ] CB comes ONLY from BALANCE_RECORD
- [ ] `capital_closed` uses `total_share_pct` (not `my_share_pct` for company clients)
- [ ] Pending is recalculated, never stored
- [ ] Reports use `CB - OB`, not settlements
- [ ] Profit & loss logic is symmetric (loss subtracts, profit adds)
- [ ] No clamp hacks or balance record edits
- [ ] Validation uses `capital_closed > movement`, not pending

---

## 📝 QUICK REFERENCE FORMULAS

### **Core State:**
```
OB = cached_old_balance
CB = Latest BALANCE_RECORD
NET = CB - OB
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
movement = abs(NET)
pending_total = movement × total_share_pct / 100
my_pending = movement × my_share_pct_effective / 100
company_pending = movement × company_share_pct / 100
```

### **Settlement:**
```
capital_closed = payment × 100 / total_share_pct

IF NET < 0 (LOSS):
    OB_new = OB - capital_closed
ELSE IF NET > 0 (PROFIT):
    OB_new = OB + capital_closed

IF abs(CB - OB_new) < 0.0001:
    OB_new = CB

cached_old_balance = OB_new
```

### **Reports:**
```
For each client/exchange:
    NET = CB - OB
    IF NET > 0:
        profit = NET × my_share_pct_effective / 100
    ELSE:
        profit = 0
```

---

## 🔒 CRITICAL RULES SUMMARY

1. **OB Rules:**
   - OB moves ONLY on settlement
   - OB stored in `cached_old_balance` (single source of truth)
   - OB direction: loss subtracts, profit adds

2. **CB Rules:**
   - CB comes ONLY from BALANCE_RECORD
   - CB is NEVER modified by settlements

3. **NET Rules:**
   - NET = CB - OB (never reversed)
   - NET < 0 = loss, NET > 0 = profit, NET = 0 = settled

4. **Share Rules:**
   - Company clients: ALWAYS use `total_share_pct = 10`
   - Never use `my_share_pct` for `capital_closed` in company clients

5. **Pending Rules:**
   - Pending is ALWAYS recalculated from OB & CB
   - Pending is NEVER stored
   - Pending is UI-only (not used for validation)

6. **Settlement Rules:**
   - Validate: `capital_closed > movement` (not pending)
   - OB moves: loss subtracts, profit adds
   - Finalize: if `abs(CB - OB_new) < 0.0001`, set `OB_new = CB`

7. **Report Rules:**
   - Use `CB - OB` calculation
   - Settlements are NOT profit (they only move OB)

---

**Last Updated:** January 3, 2025
**Version:** 2.0 (CORRECTED)
**Status:** ✅ All bugs fixed, logic verified
