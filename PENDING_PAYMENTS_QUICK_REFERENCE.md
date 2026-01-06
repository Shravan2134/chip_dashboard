# 📘 Pending Payments: Quick Reference - All Formulas

## 🎯 CORE VARIABLES

### **Capital (C) - Also called: Total Funding Outstanding**
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

**After Settlement:**
```
IF LOSS:
    CAPITAL_new = CAPITAL - capital_closed
IF PROFIT:
    CAPITAL_new = CAPITAL + capital_closed
IF fully settled:
    CAPITAL_new = CB
```

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
IF CAPITAL > CB + 0.0001:
    Total Loss = CAPITAL - CB
ELSE:
    Total Loss = 0
```

**Example:**
```
CAPITAL = 100
CB = 40
Total Loss = 100 - 40 = ₹60
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

## 💰 PENDING PAYMENTS

### **Formulas:**
```
movement = abs(CB - CAPITAL)  (same as LOSS or PROFIT)

pending_total = movement × total_share_pct / 100
my_pending = movement × my_share_pct_effective / 100
company_pending = movement × company_share_pct / 100
```

**Display:**
- `NET < 0` → "Client owes"
- `NET > 0` → "You owe"
- `abs(NET) < 0.0001` → Hide (settled)

---

## 🧮 COMBINED SHARE

### **Formula:**
```
Combined Share = movement × total_share_pct / 100
Combined Share = abs(CB - CAPITAL) × total_share_pct / 100
```

**Example:**
```
Loss = ₹90, total_share_pct = 10%
Combined Share = 90 × 10 / 100 = ₹9
```

---

## 👤 MY SHARE

### **Formula:**
```
IF company client:
    My Share = movement × 1 / 100
ELSE:
    My Share = movement × my_share_pct / 100
```

**Examples:**
```
My Client (10%):
    Loss = ₹90
    My Share = 90 × 10 / 100 = ₹9

Company Client (1%):
    Loss = ₹90
    My Share = 90 × 1 / 100 = ₹0.9
```

---

## 🏢 COMPANY SHARE

### **Formula:**
```
Company Share = movement × 9 / 100  (company clients only)
Company Share = 0                   (my clients)
```

**Example:**
```
Company Client:
    Loss = ₹90
    Company Share = 90 × 9 / 100 = ₹8.1
    My Share = ₹0.9
    Verification: 0.9 + 8.1 = ₹9 ✓
```

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

### **Step 2: Validate**
```
capital_closed = payment × 100 / total_share_pct

Validation:
- capital_closed < movement + 0.0001
- payment > 0
- movement >= 0.0001
- CAPITAL_new >= 0
- SIGN(CB - CAPITAL_new) == SIGN(CB - CAPITAL_old)
```

### **Step 3: Move CAPITAL**
```
IF NET < 0 (LOSS):
    CAPITAL_new = CAPITAL - capital_closed
ELSE IF NET > 0 (PROFIT):
    CAPITAL_new = CAPITAL + capital_closed

IF abs(CB - CAPITAL_new) < 0.0001:
    CAPITAL_new = CB  (fully settled)
```

### **Step 4: Save**
```
locked.cached_old_balance = CAPITAL_new
locked.save()
```

---

## 📝 COMPLETE EXAMPLE

### **Scenario: Loss with Partial Payment**

**Initial:**
```
Funding = ₹100
Balance = ₹10
CAPITAL = ₹100
CB = ₹10
NET = -90 (LOSS)
```

**Calculate:**
```
Total Loss = 100 - 10 = ₹90
movement = 90
Combined Share = 90 × 10 / 100 = ₹9
My Share = 90 × 10 / 100 = ₹9  (my client)
OR
My Share = 90 × 1 / 100 = ₹0.9  (company client)
Company Share = 90 × 9 / 100 = ₹8.1  (company client)
pending_total = ₹9
```

**Client Pays ₹8.5:**
```
capital_closed = 8.5 × 100 / 10 = ₹85
CAPITAL_new = 100 - 85 = ₹15
```

**After Settlement:**
```
NET_new = 10 - 15 = -5
Total Loss_new = ₹5
pending_new = 5 × 10 / 100 = ₹0.5
```

---

## 🔑 FINAL RULES (DEFINITIVE)

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

**Why:** Funding means you added money to the exchange. That money is both your capital at risk (CAPITAL) and part of the exchange balance (CB).

---

### **🟢 SETTLEMENT RULE**
```
On settlement:
    CAPITAL = CB

Loss resets to zero.
```

**Example:**
```
Before: CAPITAL = 100, CB = 40, LOSS = 60
Settlement of ₹60
After: CAPITAL = 40, CB = 40, LOSS = 0  ✅
```

**Why:** Settlement means "close the old loss/profit and reset capital to current balance".

---

### **🟢 LOSS RULE**
```
LOSS = max(CAPITAL - CB, 0)
```

**Example:**
```
CAPITAL = 100
CB = 40
LOSS = max(100 - 40, 0) = ₹60
```

**Key Insight:**
- CAPITAL = Total funded money currently at risk
- CB = Where the exchange actually is
- LOSS = Difference between them (if positive)

---

### **🧠 MENTAL MODEL**
```
CAPITAL = Total funded money currently at risk
CB = Actual exchange balance
Settlement syncs them: CAPITAL = CB
```

---

## 📊 QUICK REFERENCE TABLE

| Concept | Formula |
|---------|---------|
| **CAPITAL** | `cached_old_balance` |
| **CB** | `Latest BALANCE_RECORD` |
| **NET** | `CB - CAPITAL` |
| **Total Loss** | `max(CAPITAL - CB, 0)` (FINAL RULE) |
| **movement** | `abs(CB - CAPITAL)` |
| **Combined Share** | `movement × total_share_pct / 100` |
| **My Share** | `movement × my_share_pct_effective / 100` |
| **Company Share** | `movement × company_share_pct / 100` |
| **pending_total** | `movement × total_share_pct / 100` |
| **my_pending** | `movement × my_share_pct_effective / 100` |
| **company_pending** | `movement × company_share_pct / 100` |
| **capital_closed** | `payment × 100 / total_share_pct` |

---

## ✅ VERIFICATION CHECKLIST

- [ ] CAPITAL = Total funded money currently at risk
- [ ] CB = Latest exchange balance from BALANCE_RECORD
- [ ] NET = CB - CAPITAL
- [ ] LOSS = max(CAPITAL - CB, 0) (FINAL RULE)
- [ ] movement = abs(CB - CAPITAL)
- [ ] Combined Share = movement × total_share_pct / 100
- [ ] My Share = movement × my_share_pct_effective / 100
- [ ] Company Share = movement × company_share_pct / 100
- [ ] pending_total = movement × total_share_pct / 100
- [ ] For company clients: My Share (1%) + Company Share (9%) = Combined Share (10%)
- [ ] **FUNDING RULE:** CAPITAL += funding_amount, CB += funding_amount (Loss unchanged)
- [ ] **SETTLEMENT RULE:** CAPITAL = CB (Loss resets to zero)

---

**Last Updated:** January 4, 2025  
**Version:** 1.0  
**Status:** ✅ Complete Quick Reference

