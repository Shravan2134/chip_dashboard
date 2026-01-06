# 📘 Pending Payments: Final Corrected Documentation (All Errors Fixed)

## 🎯 CORE STATE (3 Financial Variables + Configuration State)

### **Financial Variables:**
1. **OB (Old Balance)** - Capital base after last settlement
2. **CB (Current Balance)** - Actual exchange balance from latest BALANCE_RECORD
3. **NET (CB - OB)** - Determines profit/loss

### **Configuration State (Required):**
- Client type (my vs company)
- Share policy (1/9 vs custom)
- Currency precision
- Settlement ordering cursor
- Funding after settlement policy

**✅ FIX ERROR 16:** Acknowledge that results depend on both financial variables AND configuration state.

---

## 🔒 CRITICAL INVARIANTS (MANDATORY)

### **INVARIANT 1: OB Bootstrap Timing (ERROR 24 FIX)**
```
cached_old_balance MUST be initialized
IMMEDIATELY when first FUNDING is created
NOT lazily
NOT during settlement
```

**Implementation:**
- Signal handler on FUNDING creation
- Initialize `cached_old_balance = funding_amount` immediately
- Never bootstrap during settlement

---

### **INVARIANT 2: Funding After Settlement (ERROR 17 FIX)**
```
Any FUNDING transaction AFTER last settlement
MUST increase cached_old_balance immediately

Rule: OB_new = OB_old + funding_amount
```

**Explicit Rule:**
```
Funding ALWAYS increases OB
Funding NEVER auto-settles NET
Funding NEVER affects pending directly
```

---

### **INVARIANT 3: Funding During Open Loss (ERROR 25 FIX)**
```
Scenario: OB = 100, CB = 40 (loss), movement = 60
New funding = +50

Rule:
OB_new = 100 + 50 = 150
CB = 40 (unchanged)
NET_new = 40 - 150 = -110 (loss increases)
pending_new = 110 × share_pct / 100

Funding increases OB, does NOT reduce loss
```

---

### **INVARIANT 4: NET Direction Flip (ERROR 27 FIX)**
```
NET direction MAY flip due to CB changes
OB must NOT move automatically
Pending must reflect new NET

Example:
OB = 100, CB = 40 (loss)
Next day: CB = 160
NET = 160 - 100 = +60 (profit)

Rule:
OB stays 100 (no auto-move)
Pending = 60 × share_pct / 100 (you owe)
```

---

### **INVARIANT 5: Profit After Partial Loss (ERROR 28 FIX)**
```
Loss and profit offset naturally via NET
There is NO priority system

Example:
Loss 90, Client paid 80, Remaining loss = 10
Then profit = +20
NET = +10

Rule:
NET is the ONLY truth
No priority system
Loss and profit naturally offset
```

---

### **INVARIANT 6: Settlement Atomicity (ERROR 29 FIX)**
```
Settlement MUST execute inside
SELECT ... FOR UPDATE on ClientExchange

Required:
with db_transaction.atomic():
    locked_client_exchange = ClientExchange.objects.select_for_update().get(pk=...)
    # All settlement logic here
```

---

### **INVARIANT 7: Direction Flip Validation (ERROR 20 FIX)**
```
Compute OB_new
Compute NET_new = CB - OB_new
REJECT if sign(NET_new) != sign(NET) AND abs(NET_new) > epsilon

Stronger invariant:
SIGN(CB - OB_new) MUST equal SIGN(CB - OB_old)
unless abs(CB - OB_new) < epsilon
```

---

### **INVARIANT 8: Negative OB Prevention (ERROR 33 FIX)**
```
ASSERT OB_new >= 0

If violated → system halt
```

---

### **INVARIANT 9: Company Share Validation (CE-9 FIX)**
```
ASSERT my_share_pct_effective + company_share_pct == total_share_pct

For company clients:
ASSERT 1 + 9 == 10
```

---

### **INVARIANT 10: Historical Reconciliation (ERROR 35 FIX)**
```
cached_old_balance
= SUM(funding)
± SUM(capital_closed)

At any time, this must reconcile.
```

---

### **INVARIANT 11: Precision Storage (ERROR 21 FIX, ERROR 30 FIX)**
```
Store all money as Decimal(18,8)
All arithmetic in Decimal
NO rounding in engine
ONLY round for display (HALF_UP to 2 decimals)

OB, CB stored at ≥ 6 decimal precision
capital_closed must NOT be rounded
```

---

### **INVARIANT 12: Balance Record Immutability (ERROR 22 FIX, CE-7 FIX)**
```
BALANCE_RECORD.date MUST be strictly increasing
OR recomputation must reprocess entire timeline

Balance records older than last settlement timestamp are immutable
```

---

### **INVARIANT 13: Settlement Currency Precision (ERROR 30 FIX, CE-10 FIX)**
```
capital_closed = payment × 100 / total_share_pct
(No rounding in calculation)

OB stored at high precision (≥ 6 decimals)
UI rounds — engine NEVER does
```

---

### **INVARIANT 14: Pending Display Threshold (ERROR 26 FIX)**
```
IF pending_total < display_epsilon:
    settlement must be blocked

display_epsilon = Decimal("0.01")
```

---

### **INVARIANT 15: Corruption Recovery (ERROR 23 FIX)**
```
cached_old_balance must always be derivable from funding + settlements
A repair job must exist to recompute it

Repair function:
def repair_cached_old_balance(client_exchange):
    OB = SUM(funding) ± SUM(capital_closed)
    client_exchange.cached_old_balance = OB
    client_exchange.save()
```

---

## 📊 REPORTING DEFINITIONS (ERROR 18 FIX)

### **Concept Definitions:**

| Concept | Formula | Meaning |
|---------|---------|---------|
| **Realized Profit** | `SUM(settlement amounts)` | Cash received/paid |
| **Unrealized P/L** | `movement × share_pct` | Current exposure |
| **Total P/L** | `Realized + Unrealized` | Complete picture |
| **Exposure** | `pending_total` | Current obligation |

### **Example:**
```
Client loses 90
Client pays 9

Realized Profit = 9 (cash received)
Unrealized P/L = remaining_loss × share_pct
Total P/L = 9 + unrealized
```

---

## 💰 PENDING SEMANTICS (ERROR 19 FIX, ERROR 31 FIX, CE-5 FIX)

### **Correct Definition:**
```
Pending = derived financial obligation (unrealized settlement)
Pending represents unrealized settlement obligation
Pending is NOT booked as profit/loss until settlement
```

**❌ WRONG:** "Pending is UI-only"

**✅ CORRECT:** "Pending = derived obligation (unrealized settlement)"

**Why:**
- Pending drives human action
- Pending drives settlement eligibility
- Pending represents legal obligation
- Pending appears in reports

---

## 📝 TOTAL LOSS FORMULA (ERROR 32 FIX)

### **Canonical Formula (ONE definition):**
```
Total Loss = max(OB - CB, 0)
```

**❌ REMOVED:** Redundant definitions that cause confusion

**Why:**
- One canonical formula prevents bugs
- `max()` ensures non-negative
- Works for all cases

---

## 🔒 SETTLEMENT STORAGE SEMANTICS (ERROR 34 FIX)

### **Settlement Row Structure:**
```
Settlement stores:
- direction (client_pays | admin_pays)
- amount (positive, always)
- capital_closed (for reconciliation)
```

**NOT stored:**
- Signed amount (confusing)
- Direction flag separate from type

---

## 📊 REPORT TRUTH HIERARCHY (CE-12 FIX)

### **Required Rule:**
```
Reports MUST use same OB & CB functions as engine
NO independent calculations

Reports use:
- get_old_balance_after_settlement()
- get_exchange_balance()
- Same NET calculation

NO:
- Direct database queries
- Cached values
- Independent formulas
```

---

## 🎯 PRECISION POLICY (ERROR 21 FIX, CE-10 FIX)

### **Complete Precision Contract:**

```
Storage: Decimal(18,8)
Arithmetic: Decimal (no float)
Epsilon: Decimal("0.0001")
Display: round(value, 2, HALF_UP)
Display Threshold: Decimal("0.01")

Engine Rules:
- NO rounding in calculations
- NO rounding in storage
- Round ONLY for display

Validation Rules:
- Use epsilon for comparisons
- Use display_epsilon for UI thresholds
```

---

## 🔒 SETTLEMENT VALIDATION (CE-3 FIX)

### **Complete Validation Rules:**

```
1. Recompute CB, OB, NET fresh (inside transaction)
2. Validate: capital_closed >= movement + epsilon → REJECT
3. Validate: payment <= 0 → REJECT
4. Validate: SIGN(CB - OB_new) == SIGN(CB - OB_old) OR abs(CB - OB_new) < epsilon
5. Validate: OB_new >= 0 → REJECT if false
6. Validate: pending_total < display_epsilon → REJECT (if UI threshold)
```

---

## 📝 COMPLETE FORMULAS (FINAL)

### **Core State:**
```
OB = cached_old_balance (bootstrap on first FUNDING)
CB = Latest BALANCE_RECORD
NET = CB - OB
movement = |NET|

IF abs(NET) < epsilon:
    NET = 0
```

### **Total Loss (Canonical):**
```
Total Loss = max(OB - CB, 0)
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
    
ASSERT my_share_pct_effective + company_share_pct == total_share_pct
```

### **Pending (Derived Obligation):**
```
pending_total = movement × total_share_pct / 100
my_pending = movement × my_share_pct_effective / 100
company_pending = movement × company_share_pct / 100

IF pending_total < display_epsilon:
    Block settlement
```

### **Settlement:**
```
# Inside SELECT FOR UPDATE transaction
OB = get_old_balance_after_settlement(locked_client_exchange)  # Fresh
CB = get_exchange_balance(locked_client_exchange, use_cache=False)  # Fresh
NET = CB - OB  # Fresh
movement = abs(NET)

capital_closed = payment × 100 / total_share_pct  # No rounding

# Validation
REJECT if capital_closed >= movement + epsilon
REJECT if payment <= 0
REJECT if OB_new < 0
REJECT if pending_total < display_epsilon

# Move OB
IF NET < 0 (LOSS):
    OB_new = OB - capital_closed
ELSE IF NET > 0 (PROFIT):
    OB_new = OB + capital_closed

# Validate direction
NET_new = CB - OB_new
REJECT if SIGN(NET_new) != SIGN(NET) AND abs(NET_new) > epsilon

# Finalize
IF abs(CB - OB_new) < epsilon:
    OB_new = CB

cached_old_balance = OB_new  # Update atomically
```

### **Funding After Settlement:**
```
OB_new = OB_old + funding_amount
cached_old_balance = OB_new  # Update immediately
```

---

## ✅ COMPLETE VERIFICATION CHECKLIST

### **Core Invariants:**
- [ ] OB bootstrap happens on first FUNDING creation (not lazily)
- [ ] Funding after settlement increases OB immediately
- [ ] Funding during open loss increases OB (doesn't reduce loss)
- [ ] NET direction can flip without OB moving
- [ ] Profit after partial loss offsets naturally (no priority)
- [ ] Settlement uses SELECT FOR UPDATE (atomic)
- [ ] Direction flip validation uses SIGN check
- [ ] OB_new >= 0 (assertion)
- [ ] Company share validation: 1 + 9 == 10
- [ ] Historical reconciliation: OB = SUM(funding) ± SUM(capital_closed)
- [ ] Precision: Decimal(18,8) storage, no rounding in engine
- [ ] Balance records are immutable after settlement
- [ ] Pending < display_epsilon blocks settlement
- [ ] Corruption recovery function exists

### **Reporting:**
- [ ] Reports use same OB & CB functions as engine
- [ ] Realized/Unrealized P/L clearly defined
- [ ] Reports never contradict ledger

### **Semantics:**
- [ ] Pending defined as "derived obligation" (not "UI-only")
- [ ] Total Loss uses canonical formula: max(OB - CB, 0)
- [ ] Settlement storage semantics defined

---

## 🎯 SUMMARY

**Core State:**
- 3 financial variables (OB, CB, NET) + configuration state
- OB bootstrap on first FUNDING (not lazily)
- Funding always increases OB
- NET can flip without OB moving

**Critical Invariants:**
- 15 mandatory invariants defined
- Atomic settlement with SELECT FOR UPDATE
- Precision policy: Decimal(18,8), no rounding in engine
- Historical reconciliation guaranteed

**Reporting:**
- Realized/Unrealized P/L clearly defined
- Reports use same functions as engine
- No contradictions possible

**Semantics:**
- Pending = derived obligation (not UI-only)
- Total Loss = max(OB - CB, 0) (canonical)
- All edge cases explicitly defined

---

**Last Updated:** January 3, 2025
**Version:** 3.0 (All Errors Fixed - Production Ready)
**Status:** ✅ Complete - All 35 Errors + 12 Critical Errors Addressed



