# 📘 Pending Payments: Complete Formulas & Logic

## 🎯 CORE VARIABLES

### **Capital (C) - Total Funding Outstanding**
```
CAPITAL = cached_old_balance  (database field)
CAPITAL = Total funded money currently at risk
```

**Key Insight:** It's not "old balance" - it's funding amount before settling.

**Initialization:**
```
IF first FUNDING:
    CAPITAL = SUM(all FUNDING)
```

**🚨 CRITICAL RULE:** 
- **Backdated FUNDING after BALANCE_RECORD is FORBIDDEN**
- OR system must replay all balances after backdated funding
- Right now: Reject backdated FUNDING after first BALANCE_RECORD

**After Settlement:**
```
PARTIAL Settlement:
    CAPITAL_new = CAPITAL - capital_closed  (for LOSS)
    OR
    CAPITAL_new = CAPITAL + capital_closed  (for PROFIT)

FULL Settlement (when abs(CAPITAL_new - CB) < epsilon):
    CAPITAL_new = CB  (reset to current balance)
```

**🚨 CRITICAL:** Partial settlement reduces CAPITAL, full settlement resets CAPITAL = CB

---

### **Current Balance (CB)**
```
CB = Latest ClientDailyBalance.remaining_balance
    (ORDER BY date DESC, id DESC)
```

---

### **Loss / Profit**
```
NET = CB - CAPITAL

IF CAPITAL > CB:
    LOSS = CAPITAL - CB
    PROFIT = 0

IF CB > CAPITAL:
    PROFIT = CB - CAPITAL
    LOSS = 0

IF CAPITAL == CB:
    LOSS = 0
    PROFIT = 0
```

---

## 📊 TOTAL LOSS

### **Formula:**
```
LOSS = max(CAPITAL - CB, 0)
```

**Example:**
```
CAPITAL = 100
CB = 40
LOSS = max(100 - 40, 0) = ₹60
```

**When Loss Exists:**
```
IF CAPITAL > CB:
    Total Loss = CAPITAL - CB
ELSE:
    Total Loss = 0
```

---

## 🎯 SHARE PERCENTAGES

### **My Client:**
```
total_share_pct = my_share_pct          # usually 10
my_share_pct_effective = my_share_pct  # 10
company_share_pct = 0
```

### **Company Client:**
```
total_share_pct = 10                     # ALWAYS 10
my_share_pct_effective = 1               # you get 1%
company_share_pct = 9                    # company gets 9%
```

**Validation:**
```
ASSERT my_share_pct_effective + company_share_pct == total_share_pct
```

---

## 🧮 COMBINED SHARE (My Share + Company Share)

### **Formula:**
```
movement = abs(CB - CAPITAL)  (same as LOSS or PROFIT)

Combined Share = movement × total_share_pct / 100
```

**Example:**
```
Loss = ₹90, total_share_pct = 10%
Combined Share = 90 × 10 / 100 = ₹9
```

**For Company Clients:**
```
Combined Share = My Share + Company Share
₹9 = ₹0.9 (1%) + ₹8.1 (9%)  ✓
```

---

## 👤 MY SHARE PERCENTAGE

### **Formula:**
```
IF company client:
    My Share = movement × 1 / 100
    My Share Percentage = 1%
ELSE:
    My Share = movement × my_share_pct / 100
    My Share Percentage = my_share_pct (usually 10%)
```

**Examples:**
```
My Client (10%):
    Loss = ₹90
    My Share = 90 × 10 / 100 = ₹9
    My Share Percentage = 10%

Company Client (1%):
    Loss = ₹90
    My Share = 90 × 1 / 100 = ₹0.9
    My Share Percentage = 1%
```

---

## 🏢 COMPANY SHARE

### **Formula:**
```
Company Share = movement × company_share_pct / 100

For Company Clients:
    Company Share = movement × 9 / 100

For My Clients:
    Company Share = 0
```

**Example:**
```
Company Client:
    Loss = ₹90
    Company Share = 90 × 9 / 100 = ₹8.1
    My Share = ₹0.9
    Combined Share = ₹0.9 + ₹8.1 = ₹9  ✓
```

---

## 💰 PENDING PAYMENTS

### **Formulas:**
```
movement = abs(CB - CAPITAL)

pending_total = movement × total_share_pct / 100
my_pending = movement × my_share_pct_effective / 100
company_pending = movement × company_share_pct / 100
```

**Display Logic:**
- `NET < 0` (LOSS) → Display as "Client owes"
- `NET > 0` (PROFIT) → Display as "You owe"
- `abs(NET) < 0.0001` → Hide (settled)

**Key Rules:**
- Pending is **ALWAYS recalculated**, never stored
- Pending represents **unrealized settlement obligation**

---

## 💸 SETTLEMENT LOGIC

### **Step 1: Lock & Recompute**
```
WITH db_transaction.atomic():
    locked = ClientExchange.objects.select_for_update().get(...)
    CAPITAL = get_old_balance_after_settlement(locked)
    CB = get_exchange_balance(locked, use_cache=False)
    NET = CB - CAPITAL
    movement = abs(NET)
```

### **Step 2: Calculate Capital Closed**
```
capital_closed = payment × 100 / total_share_pct
```

### **Step 3: Validate**
```
Validation Rules:
- capital_closed <= movement  (never exceed movement)
- payment > 0
- movement >= 0.0001
- CAPITAL_new >= 0  (never negative)

Then normalize:
IF abs(CAPITAL_new - CB) < epsilon:
    CAPITAL_new = CB  (fully settled, prevent direction flip)
```

**🚨 CRITICAL:** Do NOT rely on sign comparison. Use epsilon normalization to prevent LOSS → tiny PROFIT flip.

### **Step 4: Move CAPITAL**
```
IF NET < 0 (LOSS):
    CAPITAL_new = CAPITAL - capital_closed
ELSE IF NET > 0 (PROFIT):
    CAPITAL_new = CAPITAL + capital_closed  (only if explicitly settled)

IF abs(CB - CAPITAL_new) < 0.0001:
    CAPITAL_new = CB  (fully settled)
```

**🚨 CRITICAL RULE:** 
- **LOSS settlement:** Always moves CAPITAL
- **PROFIT settlement:** Only moves CAPITAL if client explicitly withdraws/settles
- **Unrealized PROFIT:** Does NOT move CAPITAL automatically

### **Step 5: Save**
```
locked.cached_old_balance = CAPITAL_new
locked.save()
```

---

## 📝 COMPLETE EXAMPLE

### **Scenario: Loss with Partial Payment**

**Initial State:**
```
Funding = ₹100
Balance = ₹10
CAPITAL = ₹100
CB = ₹10
NET = -90 (LOSS)
```

**Calculate Total Loss:**
```
Total Loss = max(100 - 10, 0) = ₹90
```

**Calculate Movement:**
```
movement = abs(10 - 100) = 90
```

**Calculate Shares:**
```
total_share_pct = 10

Combined Share = 90 × 10 / 100 = ₹9

For My Client:
    My Share = 90 × 10 / 100 = ₹9
    My Share Percentage = 10%
    Company Share = ₹0

For Company Client:
    My Share = 90 × 1 / 100 = ₹0.9
    My Share Percentage = 1%
    Company Share = 90 × 9 / 100 = ₹8.1
    Verification: ₹0.9 + ₹8.1 = ₹9 ✓
```

**Calculate Pending:**
```
pending_total = 90 × 10 / 100 = ₹9
my_pending = 90 × 10 / 100 = ₹9  (my client)
OR
my_pending = 90 × 1 / 100 = ₹0.9  (company client)
company_pending = 90 × 9 / 100 = ₹8.1  (company client)
```

**Client Pays ₹8.5:**
```
capital_closed = 8.5 × 100 / 10 = ₹85
CAPITAL_new = 100 - 85 = ₹15
```

**After Settlement:**
```
NET_new = 10 - 15 = -5
Total Loss_new = max(15 - 10, 0) = ₹5
movement_new = 5
pending_new = 5 × 10 / 100 = ₹0.5
```

---

## 🔴 CRITICAL ERROR EXAMPLES

### **ERROR 1: Partial Settlement Logic**

**❌ Wrong:**
```
After settlement: CAPITAL = CB  (only true for FULL settlement)
```

**🧪 Example - Partial Settlement:**
```
Initial:
    CAPITAL = 100
    CB = 40
    LOSS = 60

Client pays ₹3 (partial):
    capital_closed = 30

❌ Wrong:
    CAPITAL = CB = 40
    LOSS = 0  ❌ (erased unpaid loss)

✅ Correct:
    CAPITAL = 100 - 30 = 70
    CB = 40
    LOSS = 30  ✅
```

---

### **ERROR 2: Profit Auto-Settling CAPITAL**

**❌ Wrong:**
```
PROFIT automatically moves CAPITAL (treats profit symmetric to loss)
```

**🧪 Example:**
```
Initial:
    CAPITAL = 100
    CB = 150
    PROFIT = 50

❌ Wrong:
    CAPITAL = 150  ❌ (auto-settled profit)
    LOSS = 0

✅ Correct:
    CAPITAL = 100  ✅ (stays same)
    CB = 150
    PROFIT = 50  ✅ (unrealized, doesn't move CAPITAL)
```

**Key Rule:** PROFIT does NOT move CAPITAL unless explicitly settled.

---

### **ERROR 3: Funding During Loss**

**🧪 Example (Common Bug):**
```
Before:
    CAPITAL = 100
    CB = 40
    LOSS = 60

Funding +₹20:
    Exchange balance increases by 20

❌ Wrong:
    CAPITAL = 120
    CB = 40  ❌ (assumes exchange didn't receive funds)
    LOSS = 80  ❌

✅ Correct:
    CAPITAL = 120
    CB = 60  ✅ (exchange received funds)
    LOSS = 60  ✅ (loss remains same)
```

**Key Rule:** Funding increases BOTH CAPITAL and CB. Loss remains unchanged.

---

### **ERROR 4: Settlement Direction Flip**

**🧪 Example:**
```
Initial:
    CAPITAL = 100
    CB = 40
    LOSS = 60

Client pays ₹6.01:
    capital_closed = 60.1
    CAPITAL_new = 39.9

❌ Without epsilon check:
    CB - CAPITAL_new = +0.1 → PROFIT ❌ (flipped direction)

✅ Correct handling:
    IF abs(CAPITAL_new - CB) < epsilon:
        CAPITAL_new = CB
    
    Final:
        CAPITAL = 40
        CB = 40
        LOSS = 0  ✅
```

**Key Rule:** Use epsilon normalization to prevent LOSS → tiny PROFIT flip.

---

### **ERROR 5: Backdated Funding**

**🧪 Example:**
```
Day 1: FUNDING 100
Day 2: BALANCE 40 → LOSS 60
Day 3: FUNDING (backdated) 20

❌ Wrong recomputation:
    CAPITAL = 120
    CB = 40
    LOSS = 80  ❌ (corrupted)

✅ Correct (Option A - Recommended):
    ❌ Reject backdated FUNDING after BALANCE_RECORD

✅ Correct (Option B - Hard):
    Replay balances:
    CB = 60
    CAPITAL = 120
    LOSS = 60  ✅
```

**Key Rule:** Backdated FUNDING after BALANCE_RECORD must be forbidden or trigger full replay.

---

### **ERROR 6: Cached CAPITAL as Source of Truth**

**🧪 Example:**
```
Cached CAPITAL = 70
Actual transaction-based CAPITAL = 90

❌ Result:
    LOSS, pending, shares → all wrong

✅ Correct:
    Transactions = source of truth
    cached_old_balance = performance cache only
    
    Add:
    - Recompute command
    - Admin repair button
    - Integrity check on startup
```

**Key Rule:** `cached_old_balance` is a performance cache. Transaction log is source of truth.

---

## ✅ GOLDEN EXAMPLE (Everything Working Correctly)

```
Step 1: Funding 100
    CAPITAL = 100
    CB = 100
    LOSS = 0

Step 2: Loss → CB = 40
    CAPITAL = 100
    CB = 40
    LOSS = 60

Step 3: Funding +20
    CAPITAL = 120
    CB = 60
    LOSS = 60  ✅ (loss unchanged)

Step 4: Partial settle ₹3
    capital_closed = 30
    CAPITAL = 90
    CB = 60
    LOSS = 30  ✅

Step 5: Full settle ₹3
    capital_closed = 30
    CAPITAL = 60
    CB = 60
    LOSS = 0  ✅

Step 6: Profit → CB = 90
    CAPITAL = 60  ✅ (stays same)
    CB = 90
    PROFIT = 30  ✅ (unrealized, doesn't move CAPITAL)
```

**Result:**
- ✅ No drift
- ✅ No fake profit
- ✅ No loss corruption
- ✅ Matches real trading behavior

---

## 🔑 FINAL RULES (DEFINITIVE - CORRECTED)

### **🟢 FUNDING RULE**
```
On funding:
    CAPITAL += funding_amount
    CB += funding_amount

Loss remains unchanged.
```

**Example:**
```
Before: CAPITAL = 100, CB = 40, LOSS = 60
Funding +₹20
After: CAPITAL = 120, CB = 60, LOSS = 60  ✅ (same loss)
```

**Key Insight:** Funding increases BOTH CAPITAL and CB together. Loss does NOT change.

---

### **🟢 SETTLEMENT RULE**
```
PARTIAL Settlement:
    CAPITAL_new = CAPITAL - capital_closed  (for LOSS)
    OR
    CAPITAL_new = CAPITAL + capital_closed  (for PROFIT)

FULL Settlement (when abs(CAPITAL_new - CB) < epsilon):
    CAPITAL_new = CB
    Loss/Profit resets to zero.
```

**Examples:**

**Full Settlement:**
```
Before: CAPITAL = 100, CB = 40, LOSS = 60
Settlement of ₹6 (capital_closed = 60)
After: CAPITAL = 40, CB = 40, LOSS = 0  ✅
```

**Partial Settlement:**
```
Before: CAPITAL = 100, CB = 40, LOSS = 60
Settlement of ₹3 (capital_closed = 30)
After: CAPITAL = 70, CB = 40, LOSS = 30  ✅
```

---

### **🟢 LOSS RULE**
```
LOSS = max(CAPITAL - CB, 0)
```

### **🟢 PROFIT RULE**
```
PROFIT = max(CB - CAPITAL, 0)

PROFIT does NOT move CAPITAL unless explicitly settled.
Unrealized profit stays unrealized.
```

**Mental Model:**
```
CAPITAL = Total funded money currently at risk
CB = Where the exchange actually is
LOSS = Difference when CAPITAL > CB (affects CAPITAL on settlement)
PROFIT = Difference when CB > CAPITAL (does NOT affect CAPITAL unless settled)
```

---

## 📊 QUICK REFERENCE TABLE

| Concept | Formula |
|---------|---------|
| **CAPITAL** | `cached_old_balance` |
| **CB** | `Latest BALANCE_RECORD` |
| **NET** | `CB - CAPITAL` |
| **Total Loss** | `max(CAPITAL - CB, 0)` |
| **movement** | `abs(CB - CAPITAL)` |
| **Combined Share** | `movement × total_share_pct / 100` |
| **My Share** | `movement × my_share_pct_effective / 100` |
| **My Share %** | `1%` (company) or `my_share_pct%` (my client) |
| **Company Share** | `movement × company_share_pct / 100` |
| **pending_total** | `movement × total_share_pct / 100` |
| **my_pending** | `movement × my_share_pct_effective / 100` |
| **company_pending** | `movement × company_share_pct / 100` |
| **capital_closed** | `payment × 100 / total_share_pct` |

---

## ✅ FINAL CORRECTED CORE RULESET

```
CAPITAL = Total funded money currently at risk
CB = Actual exchange balance

LOSS = max(CAPITAL - CB, 0)

On FUNDING:
    CAPITAL += amount
    CB += amount

On PARTIAL SETTLEMENT:
    CAPITAL -= capital_closed  (for LOSS)
    OR
    CAPITAL += capital_closed  (for PROFIT, only if explicitly settled)

On FULL SETTLEMENT:
    IF abs(CAPITAL_new - CB) < epsilon:
        CAPITAL = CB

PROFIT does NOT move CAPITAL unless explicitly settled
```

---

## ✅ VERIFICATION CHECKLIST

- [ ] CAPITAL = Total funded money currently at risk
- [ ] CB = Latest exchange balance from BALANCE_RECORD
- [ ] NET = CB - CAPITAL
- [ ] **Total Loss = max(CAPITAL - CB, 0)**
- [ ] movement = abs(CB - CAPITAL)
- [ ] **Combined Share = My Share + Company Share**
- [ ] **My Share = movement × my_share_pct_effective / 100**
- [ ] **My Share Percentage = 1% (company) or my_share_pct% (my client)**
- [ ] Company Share = movement × company_share_pct / 100
- [ ] pending_total = movement × total_share_pct / 100
- [ ] For company clients: My Share (1%) + Company Share (9%) = Combined Share (10%)
- [ ] **FUNDING RULE:** CAPITAL += funding_amount, CB += funding_amount (Loss unchanged)
- [ ] **PARTIAL SETTLEMENT:** CAPITAL -= capital_closed (not CAPITAL = CB)
- [ ] **FULL SETTLEMENT:** CAPITAL = CB (only when abs(CAPITAL_new - CB) < epsilon)
- [ ] **PROFIT RULE:** PROFIT does NOT move CAPITAL unless explicitly settled
- [ ] **Backdated FUNDING:** Forbidden after BALANCE_RECORD
- [ ] **Cached CAPITAL:** Performance cache only, transactions are source of truth

---

**Last Updated:** January 4, 2025  
**Version:** 1.0  
**Status:** ✅ Complete - All Formulas & Logic Documented
