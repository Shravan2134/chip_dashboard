# 📘 Pending Payments: All Formulas & Logic

## 🎯 CORE VARIABLES

### **Capital (C) - Total Funding Outstanding**
```
CAPITAL = cached_old_balance  (database field)
CAPITAL = Total funded money currently at risk
```

**Initialization:**
```
IF first FUNDING:
    CAPITAL = SUM(all FUNDING)
```

**After Settlement:**
```
PARTIAL Settlement (LOSS):
    CAPITAL_new = CAPITAL - capital_closed

FULL Settlement (only when capital_closed == LOSS):
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
LOSS = max(CAPITAL - CB, 0)
PROFIT = max(CB - CAPITAL, 0)

⚠️ PROFIT and LOSS are mutually exclusive. Only one can exist at a time.
```

**Key Principle:**
- **Client profit = your liability** (you owe client)
- **Client loss = your receivable** (client owes you)

**Examples:**
```
Example 1 - Simple Profit:
    CAPITAL = 100
    CB = 160
    PROFIT = 160 - 100 = 60
    LOSS = 0
    
    ✔ Client profit = ₹60
    ✔ You must pay client ₹60
    ✔ Client can withdraw ONLY ₹60, not more

Example 2 - Loss:
    CAPITAL = 100
    CB = 40
    LOSS = 100 - 40 = 60
    PROFIT = 0
    
    ✔ Client loss = ₹60
    ✔ Client owes you ₹60
```

**🚨 CRITICAL:** Negative LOSS has no meaning. Always use `max(CAPITAL - CB, 0)`.

---

## 📊 TOTAL LOSS

### **Formula:**
```
LOSS = max(CAPITAL - CB, 0)

IF CAPITAL > CB + epsilon:
    Total Loss = CAPITAL - CB
ELSE:
    Total Loss = 0
```

**Example:**
```
CAPITAL = 100
CB = 40
LOSS = max(100 - 40, 0) = ₹60
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
LOSS = max(CAPITAL - CB, 0)

Combined Share = LOSS × total_share_pct / 100
(Only when LOSS > 0)
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
    My Share = LOSS × 1 / 100
    My Share Percentage = 1%
ELSE:
    My Share = LOSS × my_share_pct / 100
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
Company Share = LOSS × company_share_pct / 100

For Company Clients:
    Company Share = LOSS × 9 / 100

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
LOSS = max(CAPITAL - CB, 0)

# Pending exists ONLY when LOSS exists
IF LOSS > 0:
    pending_total = LOSS × total_share_pct / 100
    my_pending = LOSS × my_share_pct_effective / 100
    company_pending = LOSS × company_share_pct / 100
ELSE:
    pending_total = 0
    my_pending = 0
    company_pending = 0
```

**Display Logic:**
- `LOSS > 0` → Display as "Client owes" (pending shown)
- `PROFIT > 0` → No pending shown (you owe client, not pending)
- `LOSS == 0` → Hide (settled)

**Key Rules:**
- Pending is **ALWAYS recalculated**, never stored
- Pending exists **ONLY when LOSS exists**, never for profit
- **Profit never creates pending payments** (because pending = money client owes you, profit = money you owe client)

**Situation Table:**
| Situation | Pending shown? |
|-----------|----------------|
| LOSS > 0 | ✅ Yes |
| PROFIT > 0 | ❌ No |
| LOSS = 0 & PROFIT = 0 | ❌ No |

---

## 💸 SETTLEMENT LOGIC

### **Step 1: Lock & Recompute**
```
WITH db_transaction.atomic():
    locked = ClientExchange.objects.select_for_update().get(...)
    CAPITAL = get_old_balance_after_settlement(locked)
    CB = get_exchange_balance(locked, use_cache=False)
    NET = CB - CAPITAL
    LOSS = max(CAPITAL - CB, 0)
```

### **Step 2: Calculate Capital Closed**
```
capital_closed = payment × 100 / total_share_pct
```

### **Step 3: Validate**
```
Validation Rules for LOSS Settlement (ALL MUST PASS):
- capital_closed <= LOSS  (validate against LOSS, not movement)
- capital_closed <= CAPITAL  (prevent negative)
- payment > 0
- LOSS > 0  (LOSS must exist for LOSS settlement)
- CAPITAL_new >= CB  (prevent LOSS → PROFIT flip, OR exact full settlement)
- NET < 0  (LOSS must exist for LOSS settlement)

Validation Rules for PROFIT Withdrawal (ALL MUST PASS):
- withdrawal_amount <= PROFIT  (never exceed profit)
- withdrawal_amount > 0
- PROFIT > 0  (PROFIT must exist for withdrawal)
- NET > 0  (PROFIT must exist for withdrawal)
```

### **Step 4: Move CAPITAL (LOSS Settlement) or CB (PROFIT Withdrawal)**
```
IF NET < 0 (LOSS Settlement):
    CAPITAL_new = CAPITAL - capital_closed
    
    # Full settlement only when capital_closed exactly equals LOSS
    IF capital_closed == LOSS:
        CAPITAL_new = CB  (fully settled)
    
    CB remains unchanged

ELSE IF NET > 0 (PROFIT Withdrawal):
    CB_new = CB - withdrawal_amount
    CAPITAL_new = CAPITAL  (unchanged - profit never touches CAPITAL)
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

**Calculate Shares:**
```
total_share_pct = 10
LOSS = 90

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
LOSS = 90

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
LOSS_new = max(15 - 10, 0) = ₹5
pending_new = 5 × 10 / 100 = ₹0.5
```

---

## 🔑 FINAL RULES

### **🟢 FUNDING RULE (AUTHORITATIVE - NO EXCEPTIONS)**
```
When funding is given and it is auto-credited by the exchange:
    CAPITAL += funding_amount
    CB += funding_amount

➡️ Both MUST move together
➡️ LOSS must NOT change
```

**🚨 CRITICAL INVARIANT:**
```
ASSERT after FUNDING:
    (CAPITAL - CB) is unchanged

If this assertion fails → BUG
```

**Examples:**

**Example 1 - Clean Funding (Most Common):**
```
Before: CAPITAL = 100, CB = 40, LOSS = 60
Funding +₹20 (auto credited)
After: CAPITAL = 120, CB = 60, LOSS = 60  ✅
(Loss unchanged)
```

**Example 2 - Fully Settled, Then Funding:**
```
Before: CAPITAL = 100, CB = 100, LOSS = 0
Funding +₹50
After: CAPITAL = 150, CB = 150, LOSS = 0  ✅
(No artificial loss)
```

**Example 3 - Partial Loss, Then Funding:**
```
Before: CAPITAL = 200, CB = 140, LOSS = 60
Funding +₹30
After: CAPITAL = 230, CB = 170, LOSS = 60  ✅
(Trading loss preserved)
```

**🚫 WHAT MUST NEVER HAPPEN:**
```
CAPITAL += funding
CB unchanged

Because that would:
- Create fake loss
- Inflate pending
- Break settlement math
- Corrupt reports
```

**🧠 Mental Model:**
```
Funding increases exposure, not risk.
Trading creates risk, not funding.
```

---

### **🟢 SETTLEMENT RULE**
```
PARTIAL Settlement (LOSS):
    CAPITAL_new = CAPITAL - capital_closed
    (Validate: capital_closed <= LOSS)
    (Validate: CAPITAL_new >= CB to prevent flip)

FULL Settlement (only when capital_closed exactly equals LOSS):
    IF capital_closed == LOSS:
        CAPITAL_new = CB
    (NOT by epsilon proximity - must be exact match)
```

---

### **🟢 LOSS RULE**
```
LOSS = max(CAPITAL - CB, 0)
```

---

### **🟢 PROFIT RULE (AUTHORITATIVE - NON-NEGOTIABLE)**
```
PROFIT = max(CB - CAPITAL, 0)

Profit withdrawal affects ONLY CB, never CAPITAL.

On PROFIT_WITHDRAWAL:
    Validate: withdrawal_amount <= PROFIT
    CB_new = CB - withdrawal_amount
    CAPITAL remains unchanged
```

**🚨 CRITICAL RULES:**
- **Profit withdrawal affects ONLY CB, never CAPITAL**
- **Validation: withdrawal_amount <= PROFIT** (reject if exceeds)
- **Profit never creates pending payments**
- **Profit does NOT touch CAPITAL (ever)**

**Examples:**

**Example 1 - Partial Profit Withdrawal:**
```
Before:
    CAPITAL = 100
    CB = 160
    PROFIT = 60

Client withdraws ₹40:
    CB = 160 - 40 = 120
    CAPITAL = 100 (unchanged)
    PROFIT = 20
    
    ✔ Still profit
    ✔ No loss created
    ✔ Capital untouched
```

**Example 2 - Full Profit Withdrawal:**
```
Withdraw remaining ₹20:
    CB = 100
    CAPITAL = 100
    PROFIT = 0
    LOSS = 0
    
    ✔ Fully settled
    ✔ Clean state
```

**Example 3 - Profit + New Funding:**
```
Before:
    CAPITAL = 100
    CB = 160
    PROFIT = 60

Funding +40 (auto credited):
    CAPITAL = 140
    CB = 200
    PROFIT = 60  ✅ unchanged
    
    ✔ Funding does NOT affect profit
    ✔ Profit comes only from trading
```

**🚫 WHAT MUST NEVER BE ALLOWED:**
```
Client withdrawing capital:
    Withdraw > PROFIT ❌

Example (INVALID):
    CAPITAL = 100
    CB = 160
    PROFIT = 60
    Withdraw = 80 ❌
    
    Why? 80 > PROFIT (60)
    This would eat into CAPITAL, which is forbidden.
```

**🧠 Mental Model:**
```
CAPITAL = company exposure
CB = exchange reality

LOSS   → client owes you
PROFIT → you owe client

They are two different directions, never mix them.
```

**✅ FINAL PROFIT LOGIC:**
```
LOSS = max(CAPITAL - CB, 0)
PROFIT = max(CB - CAPITAL, 0)

# Profit withdrawal
if PROFIT > 0:
    assert withdrawal <= PROFIT
    CB -= withdrawal

No epsilon hacks
No NET branching
No CAPITAL movement
```

---

## 📊 QUICK REFERENCE TABLE

| Concept | Formula |
|---------|---------|
| **CAPITAL** | `cached_old_balance` |
| **CB** | `Latest BALANCE_RECORD` |
| **NET** | `CB - CAPITAL` |
| **Total Loss** | `max(CAPITAL - CB, 0)` |
| **PROFIT** | `max(CB - CAPITAL, 0)` |
| **Combined Share** | `LOSS × total_share_pct / 100` (only when LOSS > 0) |
| **My Share** | `LOSS × my_share_pct_effective / 100` (only when LOSS > 0) |
| **My Share %** | `1%` (company) or `my_share_pct%` (my client) |
| **Company Share** | `LOSS × company_share_pct / 100` (only when LOSS > 0) |
| **pending_total** | `LOSS × total_share_pct / 100` (only when LOSS > 0) |
| **my_pending** | `LOSS × my_share_pct_effective / 100` (only when LOSS > 0) |
| **company_pending** | `LOSS × company_share_pct / 100` (only when LOSS > 0) |
| **capital_closed** | `payment × 100 / total_share_pct` |

### **Action Effects Table:**

| Action | CAPITAL | CB |
|--------|---------|-----|
| Trading profit | ❌ No change | ✅ Changes |
| Profit withdrawal | ❌ No change | ✅ Decreases |
| Funding | ✅ Increases | ✅ Increases |
| Loss settlement | ✅ Decreases | ❌ No change |

---

## ✅ VERIFICATION CHECKLIST

- [ ] CAPITAL = Total funded money currently at risk
- [ ] CB = Latest exchange balance from BALANCE_RECORD
- [ ] NET = CB - CAPITAL
- [ ] **Total Loss = max(CAPITAL - CB, 0)**
- [ ] **PROFIT = max(CB - CAPITAL, 0)**
- [ ] **Combined Share = LOSS × total_share_pct / 100** (only when LOSS > 0)
- [ ] **My Share = LOSS × my_share_pct_effective / 100** (only when LOSS > 0)
- [ ] **My Share Percentage = 1% (company) or my_share_pct% (my client)**
- [ ] Company Share = LOSS × company_share_pct / 100 (only when LOSS > 0)
- [ ] pending_total = LOSS × total_share_pct / 100 (only when LOSS > 0)
- [ ] For company clients: My Share (1%) + Company Share (9%) = Combined Share (10%)
- [ ] **FUNDING RULE:** CAPITAL += amount, CB += amount (both move together, LOSS unchanged)
- [ ] **SETTLEMENT RULE:** Validate capital_closed <= LOSS, CAPITAL_new >= CB (or exact full)
- [ ] **FULL SETTLEMENT:** Only when capital_closed == LOSS (exact match, not epsilon)
- [ ] **PROFIT RULE:** Profit withdrawal changes CB only, CAPITAL unchanged
- [ ] **PENDING RULE:** Pending exists ONLY when LOSS exists, never for unrealized profit

---

**Last Updated:** January 4, 2025  
**Version:** 1.0  
**Status:** ✅ Complete - All Formulas & Logic Documented

