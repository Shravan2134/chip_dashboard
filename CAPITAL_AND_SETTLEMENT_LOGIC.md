# 💰 Capital & Settlement Logic: Complete Guide

## 🎯 CORRECT TERMINOLOGY

### **Critical Renaming**

| ❌ Wrong Name | ✅ Correct Name | Meaning |
|--------------|----------------|---------|
| Old Balance (OB) | **CAPITAL (C)** | Total money you have put into the exchange that is not yet settled |
| Current Balance (CB) | **CURRENT BALANCE (CB)** | Actual exchange balance |
| Net Movement (NET) | **LOSS / PROFIT** | Difference between CB and CAPITAL |

**Alternative Names for CAPITAL:**
- Capital Given
- Total Funding Outstanding
- Capital Base
- Unsettled Funding Amount

---

## 📊 CORE FORMULAS

### **Capital (C)**
```
CAPITAL = cached_old_balance  (in database)
CAPITAL = Total funded money currently at risk
```

**Key Insight:** It's not "old balance" - it's funding amount before settling.

### **Current Balance (CB)**
```
CB = Latest ClientDailyBalance.remaining_balance
CB = Actual exchange balance
```

### **Loss / Profit**
```
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

### **NET (for calculations)**
```
NET = CB - CAPITAL

NET < 0 → LOSS (client owes you)
NET > 0 → PROFIT (you owe client)
NET = 0 → SETTLED
```

---

## 🔑 FINAL RULES (DEFINITIVE - FOR YOUR SYSTEM)

### **🟢 FUNDING RULE**
```
On funding:
    CAPITAL += funding_amount
    CB += funding_amount

Loss remains unchanged.
```

**Why:** Funding means you added money to the exchange. That money is both:
- Your capital at risk (CAPITAL)
- Part of the exchange balance (CB)

**Key Insight:** Loss does NOT change when funding happens. You just increase exposure.

---

### **🟢 SETTLEMENT RULE**
```
On settlement:
    CAPITAL = CB

Loss resets to zero.
```

**Why:** Settlement means "close the old loss/profit and reset capital to current balance"

---

### **🟢 LOSS RULE**
```
LOSS = max(CAPITAL - CB, 0)
```

**Key Insight:**
- CAPITAL = Total funded money currently at risk
- CB = Where the exchange actually is
- LOSS = Difference between them (if positive)

---

### **🧠 MENTAL MODEL (WHY YOUR INTUITION WAS RIGHT)**
```
You kept saying: "it is not old balance, it is funding"

That is the key insight.

CAPITAL = Total funded money currently at risk
CB = Actual exchange balance
Settlement syncs them: CAPITAL = CB
```

**Correct Mental Naming:**
- CAPITAL = Total funded money currently at risk
- It's NOT "old balance" - it's funding amount before settling

---

## 📝 COMPLETE EXAMPLES

### **✅ EXAMPLE 1: Funding → Loss → Funding in Middle → Settlement**

**Step 1: Initial Funding ₹100**
```
Action: Funding +₹100

CAPITAL = 100
CB = 100
LOSS = 0
PROFIT = 0
```

**Step 2: Trading Loss → Balance Becomes ₹40**
```
Action: BALANCE_RECORD = ₹40

CAPITAL = 100  (unchanged)
CB = 40
LOSS = 100 - 40 = 60
PROFIT = 0
```

**Step 3: Funding +₹20 (NO Settlement Yet)**
```
Action: Funding +₹20

CAPITAL = 100 + 20 = 120
CB = 40 + 20 = 60
LOSS = 120 - 60 = 60  ✅ (same loss)
PROFIT = 0
```

**Key Point:** Loss does NOT change. You just increased exposure.

**Step 4: Client Settles Full Loss ₹60**
```
Action: Settlement of ₹60

CAPITAL = CB = 60  (reset to current balance)
CB = 60
LOSS = 0
PROFIT = 0
```

**Step 5: Funding After Settlement +₹20**
```
Action: Funding +₹20

CAPITAL = 60 + 20 = 80
CB = 60 + 20 = 80
LOSS = 0
PROFIT = 0
```

**Full Timeline:**
| Step | Action | CAPITAL | CB | LOSS |
|------|--------|---------|----|----|
| 1 | Funding +100 | 100 | 100 | 0 |
| 2 | Loss → 40 | 100 | 40 | 60 |
| 3 | Funding +20 | 120 | 60 | 60 |
| 4 | Settlement | 60 | 60 | 0 |
| 5 | Funding +20 | 80 | 80 | 0 |

---

### **✅ EXAMPLE 2: Funding → Loss → Funding → MORE Loss → Partial Settlement**

**Step 1: Initial Funding ₹200**
```
CAPITAL = 200
CB = 200
LOSS = 0
```

**Step 2: Balance Drops to ₹120**
```
CAPITAL = 200
CB = 120
LOSS = 80
```

**Step 3: Funding +₹50 (Before Settlement)**
```
CAPITAL = 200 + 50 = 250
CB = 120 + 50 = 170
LOSS = 250 - 170 = 80  ✅ (same loss)
```

**Step 4: More Loss → CB = ₹140**
```
CAPITAL = 250
CB = 140
LOSS = 250 - 140 = 110
```

**Step 5: Partial Settlement of Loss ₹60**
```
Settlement calculation:
    capital_closed = 60 × 100 / 10 = 600 (if 10% share)
    CAPITAL_new = 250 - 600 = -350 ❌ (invalid)

Correct calculation:
    payment = ₹60
    capital_closed = 60 × 100 / 10 = 600 (capital closed)
    CAPITAL_new = 250 - 600 = -350 ❌

Wait, this doesn't match. Let me recalculate:

If client pays ₹60 for 10% share:
    capital_closed = 60 × 100 / 10 = 600
    But CAPITAL is only 250, so this is wrong.

Correct approach:
    If client pays ₹60 (which is 10% of loss):
    Total loss = 110
    10% of 110 = 11 (not 60)
    
    If client pays ₹60, that means:
    capital_closed = 60 × 100 / 10 = 600
    But this exceeds the loss of 110.

Let me fix this example with realistic numbers:

Step 5: Partial Settlement of ₹11 (10% of loss)
    payment = ₹11
    capital_closed = 11 × 100 / 10 = 110
    CAPITAL_new = 250 - 110 = 140
    CB = 140
    LOSS = 0  ✅ (settled completely)
```

**Corrected Step 5: Partial Settlement**
```
If client pays ₹55 (partial):
    capital_closed = 55 × 100 / 10 = 550
    But CAPITAL is 250, loss is 110.
    
    Realistic: If client pays ₹11 (10% of 110 loss):
    capital_closed = 11 × 100 / 10 = 110
    CAPITAL_new = 250 - 110 = 140
    CB = 140
    LOSS = 0  ✅
```

**Better Example:**
```
Step 5: Client pays ₹5.5 (5% of loss)
    capital_closed = 5.5 × 100 / 10 = 55
    CAPITAL_new = 250 - 55 = 195
    CB = 140
    LOSS = 195 - 140 = 55  ✅ (remaining loss)
```

---

### **✅ EXAMPLE 3: Funding → Loss → Funding → PROFIT (No Settlement)**

**Step 1: Funding ₹100**
```
CAPITAL = 100
CB = 100
LOSS = 0
```

**Step 2: Loss → CB = ₹40**
```
CAPITAL = 100
CB = 40
LOSS = 60
```

**Step 3: Funding +₹20**
```
CAPITAL = 100 + 20 = 120
CB = 40 + 20 = 60
LOSS = 120 - 60 = 60  ✅ (same loss)
```

**Step 4: Profit Happens → CB = ₹140**
```
CAPITAL = 120
CB = 140
LOSS = 0
PROFIT = 140 - 120 = 20  ✅
```

**Key Point:** Loss auto-recovered. Now it's profit.

---

### **✅ EXAMPLE 4: Multiple Fundings Before Any Settlement**

**Step 1: Funding ₹100**
```
CAPITAL = 100
CB = 100
LOSS = 0
```

**Step 2: Loss → CB = ₹70**
```
CAPITAL = 100
CB = 70
LOSS = 30
```

**Step 3: Funding +₹50**
```
CAPITAL = 100 + 50 = 150
CB = 70 + 50 = 120
LOSS = 150 - 120 = 30  ✅ (same loss)
```

**Step 4: Funding +₹30**
```
CAPITAL = 150 + 30 = 180
CB = 120 + 30 = 150
LOSS = 180 - 150 = 30  ✅ (same loss)
```

**Key Point:** Loss remains SAME. Funding only increases exposure.

---

### **✅ EXAMPLE 5: Settlement FIRST, Then Funding**

**Step 1: Funding ₹100**
```
CAPITAL = 100
CB = 100
LOSS = 0
```

**Step 2: Loss → CB = ₹40**
```
CAPITAL = 100
CB = 40
LOSS = 60
```

**Step 3: Settlement of ₹60**
```
CAPITAL = CB = 40  (reset)
CB = 40
LOSS = 0
```

**Step 4: Funding +₹20**
```
CAPITAL = 40 + 20 = 60
CB = 40 + 20 = 60
LOSS = 0
```

**Key Point:** Clean new cycle. Old loss is gone forever.

---

### **🚫 EXAMPLE 6: WRONG LOGIC (What You Must NOT Do)**

**❌ Wrong Assumption:**
```
Funding only increases CAPITAL, not CB

That would give:
    CAPITAL = 120
    CB = 40
    LOSS = 80  ❌ WRONG
```

**✅ Correct Reality:**
```
Funding always goes into exchange:
    CAPITAL = 120
    CB = 60
    LOSS = 60  ✅ CORRECT
```

---

## 🧮 SETTLEMENT CALCULATION

### **Settlement Formula**
```
capital_closed = payment × 100 / total_share_pct

IF LOSS (CAPITAL > CB):
    CAPITAL_new = CAPITAL - capital_closed

IF PROFIT (CB > CAPITAL):
    CAPITAL_new = CAPITAL + capital_closed

IF abs(CB - CAPITAL_new) < epsilon:
    CAPITAL_new = CB  (fully settled)
```

### **Example: Loss Settlement**
```
Initial:
    CAPITAL = 100
    CB = 40
    LOSS = 60

Client pays ₹6 (10% of loss):
    capital_closed = 6 × 100 / 10 = 60
    CAPITAL_new = 100 - 60 = 40
    CB = 40
    LOSS = 0  ✅ (fully settled)
```

### **Example: Partial Loss Settlement**
```
Initial:
    CAPITAL = 100
    CB = 40
    LOSS = 60

Client pays ₹3 (5% of loss):
    capital_closed = 3 × 100 / 10 = 30
    CAPITAL_new = 100 - 30 = 70
    CB = 40
    LOSS = 70 - 40 = 30  ✅ (remaining loss)
```

---

## 🔄 FUNDING LOGIC

### **When Funding Happens**

**Scenario A: Funding with Balance Record Update**
```
Action: Funding +₹50
    AND BALANCE_RECORD created with new balance

Result:
    CAPITAL += 50
    CB = new_balance (from BALANCE_RECORD)
```

**Scenario B: Funding Without Balance Record**
```
Action: Funding +₹50
    BUT no BALANCE_RECORD yet

Result:
    CAPITAL += 50
    CB += 50  (assumed to increase)
```

**Key Rule:** Funding increases BOTH CAPITAL and CB together.

---

## 📊 SHARE CALCULATIONS

### **Loss Share Calculation**
```
LOSS = CAPITAL - CB

Combined Share = LOSS × total_share_pct / 100
My Share = LOSS × my_share_pct_effective / 100
Company Share = LOSS × company_share_pct / 100
```

### **Profit Share Calculation**
```
PROFIT = CB - CAPITAL

Combined Share = PROFIT × total_share_pct / 100
My Share = PROFIT × my_share_pct_effective / 100
Company Share = PROFIT × company_share_pct / 100
```

### **Example: Loss with Shares**
```
CAPITAL = 100
CB = 40
LOSS = 60

For My Client (10%):
    Combined Share = 60 × 10 / 100 = ₹6
    My Share = ₹6
    Company Share = ₹0

For Company Client (1% + 9%):
    Combined Share = 60 × 10 / 100 = ₹6
    My Share = 60 × 1 / 100 = ₹0.6
    Company Share = 60 × 9 / 100 = ₹5.4
```

---

## 🗄️ DATABASE FIELD MAPPING

### **Current Database Fields**
```
ClientExchange.cached_old_balance → CAPITAL
ClientDailyBalance.remaining_balance → CB (latest)
```

### **Recommended Renaming (Future)**
```
cached_old_balance → cached_capital
cached_current_balance → cached_cb
```

**Note:** For now, keep field names as-is to avoid migration complexity. Use correct terminology in code comments and documentation.

---

## 🎯 ONE-LINE RULES (PIN THESE)

1. **Funding Rule:**
   ```
   Funding increases CAPITAL and CURRENT BALANCE together.
   ```

2. **Settlement Rule:**
   ```
   Settlement synchronizes CAPITAL = CURRENT BALANCE.
   ```

3. **Mental Model:**
   ```
   CAPITAL is how much money is currently at risk.
   CB is where the exchange actually is.
   Settlement syncs them.
   ```

---

## ✅ VERIFICATION CHECKLIST

- [ ] CAPITAL = Total funding given that is NOT yet settled
- [ ] CB = Latest exchange balance from BALANCE_RECORD
- [ ] Funding increases BOTH CAPITAL and CB
- [ ] Settlement resets CAPITAL = CB
- [ ] LOSS = CAPITAL - CB (if CAPITAL > CB)
- [ ] PROFIT = CB - CAPITAL (if CB > CAPITAL)
- [ ] Share calculations use LOSS or PROFIT, not CAPITAL directly

---

**Last Updated:** January 3, 2025  
**Version:** 2.0 - CORRECTED TERMINOLOGY  
**Status:** ✅ Complete - All Examples Documented

