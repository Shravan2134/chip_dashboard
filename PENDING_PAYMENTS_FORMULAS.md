# 📘 Pending Payments: All Formulas & Logic

## 🎯 CORE VARIABLES

### **Capital (C) - Also called: Capital Given / Total Funding Outstanding**
```
CAPITAL = cached_old_balance  (database field name)
CAPITAL = Total money you have put into the exchange that is NOT yet settled
```

**Initialization (ONE TIME ONLY):**
```
IF cached_old_balance IS NULL:
    AND first FUNDING created:
        CAPITAL = SUM(all FUNDING)
        cached_old_balance = CAPITAL
```

**After Settlement:**
```
IF NET < 0 (LOSS):
    CAPITAL_new = CAPITAL - capital_closed
ELSE IF NET > 0 (PROFIT):
    CAPITAL_new = CAPITAL + capital_closed

IF abs(CB - CAPITAL_new) < 0.0001:
    CAPITAL_new = CB  (fully settled)
```

**🚨 CRITICAL RULES:**
- **Funding increases BOTH CAPITAL and CB together**
- **Settlement resets CAPITAL = CB**

---

### **Current Balance (CB)**
```
CB = Latest ClientDailyBalance.remaining_balance
    (ORDER BY date DESC, id DESC)
```

**Fallback:**
```
IF no balance record AND no settlements:
    CB = SUM(all FUNDING)
```

---

### **Net Movement (NET) / Loss / Profit**
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

**Interpretation:**
- `NET < -0.0001` → **LOSS** (client owes)
- `NET > 0.0001` → **PROFIT** (you owe)
- `abs(NET) < 0.0001` → **SETTLED**

---

## 📊 TOTAL LOSS

### **Formula:**
```
IF CAPITAL > CB + 0.0001:
    Total Loss = CAPITAL - CB
ELSE:
    Total Loss = 0
```

---

## 🎯 SHARE PERCENTAGES

### **My Client:**
```
total_share_pct = my_share_pct          # usually 10
my_share_pct_effective = my_share_pct    # 10
company_share_pct = 0
```

### **Company Client:**
```
total_share_pct = 10                     # ALWAYS 10
my_share_pct_effective = 1               # you get 1%
company_share_pct = 9                    # company gets 9%
```

**🚨 INVARIANT:**
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
    My Share = 90 × 10 / 100 = ₹9

Company Client (1%):
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
    Company Share = 90 × 9 / 100 = ₹8.1
    Verification: My Share (₹0.9) + Company Share (₹8.1) = ₹9 ✓
```

---

## 💸 SETTLEMENT LOGIC

### **Step 1: Lock & Recompute**
```
WITH db_transaction.atomic():
    locked = ClientExchange.objects.select_for_update().get(...)
    CAPITAL = get_old_balance_after_settlement(locked)  # function name unchanged
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
- OB_new >= 0
- SIGN(CB - OB_new) == SIGN(CB - OB_old) OR abs(CB - OB_new) < 0.0001
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
locked.cached_old_balance = CAPITAL_new  # field name unchanged
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
Total Loss = max(100 - 10, 0) = ₹90
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

## 🔒 CRITICAL RULES

1. **Funding increases BOTH CAPITAL and CB together**
2. **Settlement resets CAPITAL = CB**
3. **CB comes ONLY from BALANCE_RECORD**
4. **Company clients: ALWAYS use total_share_pct = 10**
5. **Pending is ALWAYS recalculated, never stored**
6. **NET = CB - CAPITAL (computed inside DB lock)**
7. **Total Loss = max(CAPITAL - CB, 0) with epsilon**
8. **Combined Share = My Share + Company Share**
9. **ASSERT CAPITAL >= 0, CB >= 0**
10. **ASSERT my_share_pct_effective + company_share_pct == total_share_pct**
11. **Settlement MUST use SELECT FOR UPDATE**

---

## ✅ QUICK REFERENCE

| Concept | Formula |
|---------|---------|
| **CAPITAL** | `cached_old_balance` (database field) |
| **CB** | `Latest BALANCE_RECORD` |
| **NET** | `CB - CAPITAL` |
| **Total Loss** | `max(CAPITAL - CB, 0)` if `CAPITAL > CB + 0.0001` else `0` |
| **movement** | `abs(CB - CAPITAL)` |
| **Combined Share** | `movement × total_share_pct / 100` |
| **My Share** | `movement × my_share_pct_effective / 100` |
| **Company Share** | `movement × company_share_pct / 100` |
| **pending_total** | `movement × total_share_pct / 100` |
| **capital_closed** | `payment × 100 / total_share_pct` |

---

**Last Updated:** January 3, 2025  
**Version:** 1.0  
**Status:** ✅ Complete

