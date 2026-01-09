# PENDING PAYMENTS SYSTEM - COMPLETE DOCUMENTATION

**Version:** 3.0 (With Cycle Separation)  
**Status:** Production Ready  
**Last Updated:** January 2026

---

## TABLE OF CONTENTS

1. [System Overview](#system-overview)
2. [Core Definitions](#core-definitions)
3. [PnL Calculation](#pnl-calculation)
4. [Share Calculation](#share-calculation)
5. [Cycle Separation Logic](#cycle-separation-logic)
6. [Locked Share Mechanism](#locked-share-mechanism)
7. [Settlement Logic](#settlement-logic)
8. [Remaining Amount Calculation](#remaining-amount-calculation)
9. [MaskedCapital Formula](#maskedcapital-formula)
10. [Edge Cases](#edge-cases)
11. [Code Implementation](#code-implementation)
12. [Testing Scenarios](#testing-scenarios)
13. [Failure Cases and Fixes](#failure-cases-and-fixes)

---

## SYSTEM OVERVIEW

The Pending Payments System implements a **Masked Share Settlement System** that:

- **Settles only the admin's share** (not full PnL)
- **Hides actual profit/loss amounts** from UI
- **Hides remaining percentages** from users
- **Avoids decimals completely** (uses floor rounding)
- **Allows partial and manual settlements**
- **Supports dynamic profit percentage** (can change anytime)
- **Separates PnL cycles** (prevents mixing old and new settlements)
- **Keeps math simple, deterministic, and safe**

### Key Principles

1. **Precision is intentionally sacrificed** for simplicity and control
2. **Shares are locked** at first compute per PnL cycle
3. **Cycles reset** when PnL sign changes (LOSS ↔ PROFIT)
4. **Old cycle settlements** never mix with new cycle shares
5. **Manual control** is prioritized over automation

---

## CORE DEFINITIONS

| Term | Meaning | Formula/Notes |
|------|---------|---------------|
| **Funding (F)** | Capital given to client | Stored as BIGINT |
| **Exchange Balance (EB)** | Final balance on exchange | Stored as BIGINT |
| **Loss (L)** | `max(F − EB, 0)` | Always ≥ 0 |
| **Profit (P)** | `max(EB − F, 0)` | Always ≥ 0 |
| **Client PnL** | `EB − F` | Can be negative (loss) or positive (profit) |
| **Loss Share %** | Fixed percentage for losses | Immutable once data exists |
| **Profit Share %** | Percentage for profits | Can change anytime, affects only future profits |
| **Exact Share** | Share before rounding | Full precision, internal only |
| **Final Share** | Share after floor rounding | Integer, shown to users |
| **Settlement** | Actual payment recorded | Tracks individual payments |
| **Remaining** | `LockedInitialFinalShare − TotalSettled` | Amount still to be settled |
| **Cycle Start Date** | Timestamp when PnL cycle started | Used to filter settlements by cycle |

### Important Notes

- **Only one of Loss or Profit can be > 0** at any time
- **Percentages are never rounded** (full precision used internally)
- **Rounding happens ONLY ONCE** (floor method)
- **Fractional values are discarded permanently**

---

## PnL CALCULATION

### Formula

```
Client_PnL = ExchangeBalance − Funding
```

### Implementation

```python
def compute_client_pnl(self):
    """
    MASTER PROFIT/LOSS FORMULA
    Client_PnL = exchange_balance - funding
    
    Returns: BIGINT (can be negative for loss)
    """
    return self.exchange_balance - self.funding
```

### Examples

| Funding | Exchange Balance | Client PnL | Interpretation |
|---------|------------------|------------|---------------|
| 100 | 50 | -50 | Loss (client owes) |
| 100 | 150 | +50 | Profit (you owe client) |
| 100 | 100 | 0 | Flat (no settlement) |

### Rules

- **NO rounding** in PnL calculation
- **Full precision** maintained
- **Can be negative** (loss) or **positive** (profit)

---

## SHARE CALCULATION

### Step 1: Determine Share Percentage

```python
if Client_PnL < 0:
    # LOSS: Use loss_share_percentage
    share_pct = loss_share_percentage if loss_share_percentage > 0 else my_percentage
else:
    # PROFIT: Use profit_share_percentage
    share_pct = profit_share_percentage if profit_share_percentage > 0 else my_percentage
```

### Step 2: Calculate Exact Share (NO Rounding)

```
ExactShare = |Client_PnL| × (Share% / 100)
```

**Rules:**
- Percentages are never rounded
- Full precision is used internally
- ExactShare is a float (not shown to users)

### Step 3: Calculate Final Share (ONLY Rounding Step)

```
FinalShare = floor(ExactShare)
```

**Rounding Policy:**
- **Method:** FLOOR (round down)
- **Happens ONLY ONCE**
- **Applies to both client and admin**
- **No decimals shown or settled**
- **Fractional values discarded permanently**

### Implementation

```python
def compute_my_share(self):
    """
    MASKED SHARE SETTLEMENT SYSTEM - PARTNER SHARE FORMULA
    
    Uses floor() rounding (round down) for final share.
    Separate percentages for loss and profit.
    
    Returns: BIGINT (always positive, floor rounded)
    """
    import math
    client_pnl = self.compute_client_pnl()
    
    if client_pnl == 0:
        return 0
    
    # Determine which percentage to use
    if client_pnl < 0:
        share_pct = self.loss_share_percentage if self.loss_share_percentage > 0 else self.my_percentage
    else:
        share_pct = self.profit_share_percentage if self.profit_share_percentage > 0 else self.my_percentage
    
    # Exact Share (NO rounding)
    exact_share = abs(client_pnl) * (share_pct / 100.0)
    
    # Final Share (ONLY rounding step) - FLOOR (round down)
    final_share = math.floor(exact_share)
    
    return int(final_share)
```

### Examples

| PnL | Share % | Exact Share | Final Share |
|-----|---------|-------------|-------------|
| -90 | 10% | 9.0 | 9 |
| -90 | 5% | 4.5 | 4 |
| +50 | 20% | 10.0 | 10 |
| +50 | 15% | 7.5 | 7 |
| -1 | 10% | 0.1 | 0 |

---

## CYCLE SEPARATION LOGIC

### Critical Rule

**Every time PnL crosses zero (sign changes):**
- **LOSS → PROFIT**: NEW cycle starts
- **PROFIT → LOSS**: NEW cycle starts
- **Old cycle closes** (settlements preserved but not counted)
- **New cycle starts** (only new settlements counted)

### Why Cycle Separation is Critical

**Without cycle separation, the system FAILS:**

**Example Failure:**
```
Step 1: Funding=100, Exchange=10, PnL=-90, Share=9
Step 2: Client pays 5 (remaining=4)
Step 3: Exchange=100, PnL=+50, NEW PROFIT CYCLE starts
Step 4: Exchange=20, PnL=-30, NEW LOSS CYCLE starts

❌ WITHOUT CYCLE SEPARATION:
- Old settlement (5) mixes with new cycle
- Remaining calculation becomes wrong
- Shares from different cycles get confused

✅ WITH CYCLE SEPARATION:
- Old settlement (5) preserved but NOT counted in new cycle
- Each cycle has its own locked share
- Settlements filtered by cycle_start_date
```

### Cycle Start Detection

**Cycle resets when:**

1. **PnL sign flips** (LOSS ↔ PROFIT)
```python
# Check if PnL cycle changed (sign flip)
if (client_pnl < 0) != (self.locked_initial_pnl < 0):
    # PnL cycle changed - lock new share
    # Set cycle_start_date = now()
    # Old cycle settlements are now excluded
```

2. **Funding changes** (NEW EXPOSURE = NEW CYCLE)
```python
# CRITICAL FIX: Funding change should reset cycle (new exposure = new cycle)
if self.locked_initial_final_share is not None:
    if self.locked_initial_funding is not None:
        # New data: Compare with tracked funding
        if self.funding != self.locked_initial_funding:
            # Funding changed → new exposure → new cycle
            # Reset all locks to force new cycle
    else:
        # Old data: Check if PnL changed significantly (likely funding changed)
        # If PnL magnitude changed by >50%, reset cycle
```

**Why funding change resets cycle:**
- New funding = new exposure = new trading cycle
- Old locked share doesn't apply to new exposure
- Example: Funding 100→300, PnL -90→-200, Share should be 9→20, not stuck at 9

### Cycle Tracking Fields

| Field | Purpose |
|-------|---------|
| `cycle_start_date` | Timestamp when current cycle started |
| `locked_initial_final_share` | Share locked at cycle start |
| `locked_initial_pnl` | PnL locked at cycle start (for sign detection) |

### Settlement Filtering

```python
# Only count settlements from CURRENT cycle
if self.cycle_start_date:
    total_settled = self.settlements.filter(
        date__gte=self.cycle_start_date
    ).aggregate(total=models.Sum('amount'))['total'] or 0
else:
    # Backward compatibility: count all settlements
    total_settled = self.settlements.aggregate(total=models.Sum('amount'))['total'] or 0
```

### Cycle Reset Rules

1. **New cycle starts when:**
   - First time locking share
   - PnL sign flips (LOSS ↔ PROFIT)
   - **Funding changes** (new exposure = new cycle) ⭐ NEW FIX

2. **Cycle closes when:**
   - Fully settled (total_settled >= locked_initial_final_share)
   - PnL becomes zero AND fully settled

3. **Cycle persists when:**
   - PnL becomes zero but NOT fully settled
   - Partial settlements exist
   - Funding unchanged (same exposure continues)

---

## LOCKED SHARE MECHANISM

### Purpose

**Prevents share from shrinking after payments.**

Without locking:
- Settlement changes PnL
- PnL change recalculates share
- Share shrinks → **WRONG**

With locking:
- Share locked at first compute
- Settlement doesn't change locked share
- Remaining calculated from locked share → **CORRECT**

### Locking Logic

```python
def lock_initial_share_if_needed(self):
    """
    CRITICAL FIX: Lock InitialFinalShare at first compute per PnL cycle.
    
    This ensures share doesn't shrink after payments.
    Share is decided by trading outcome, not by settlement.
    """
    client_pnl = self.compute_client_pnl()
    
    # Case 1: First time - lock the share
    if self.locked_initial_final_share is None or self.locked_initial_pnl is None:
        final_share = self.compute_my_share()
        if final_share > 0:
            # Lock share, percentage, PnL, and cycle start date
            self.locked_initial_final_share = final_share
            self.locked_share_percentage = share_pct
            self.locked_initial_pnl = client_pnl
            self.cycle_start_date = timezone.now()
    
    # Case 2: PnL cycle changed (sign flip)
    elif client_pnl != 0 and self.locked_initial_pnl != 0:
        if (client_pnl < 0) != (self.locked_initial_pnl < 0):
            # Sign flip detected - NEW CYCLE
            final_share = self.compute_my_share()
            if final_share > 0:
                # Lock new share and reset cycle start date
                self.locked_initial_final_share = final_share
                self.locked_share_percentage = share_pct
                self.locked_initial_pnl = client_pnl
                self.cycle_start_date = timezone.now()
    
    # Case 3: PnL is zero
    elif client_pnl == 0:
        # Only reset if fully settled
        if cycle_settled >= (self.locked_initial_final_share or 0):
            # Reset all locks
            self.locked_initial_final_share = None
            self.locked_share_percentage = None
            self.locked_initial_pnl = None
            self.cycle_start_date = None
```

### Locked Fields

| Field | Purpose | When Set | When Reset |
|-------|---------|----------|------------|
| `locked_initial_final_share` | Share locked at cycle start | First compute or sign flip | Fully settled |
| `locked_share_percentage` | Percentage used for locked share | Same as above | Same as above |
| `locked_initial_pnl` | PnL at cycle start (for sign detection) | Same as above | Same as above |
| `cycle_start_date` | Timestamp when cycle started | Same as above | Same as above |

### Example: Locking Prevents Share Shrinking

**Without Lock:**
```
Initial: Funding=1000, Exchange=700, PnL=-300, Share=30
Client pays 30: Funding=700, Exchange=700, PnL=0, Share=0 ❌ WRONG
```

**With Lock:**
```
Initial: Funding=1000, Exchange=700, PnL=-300, LockedShare=30
Client pays 30: Funding=700, Exchange=700, PnL=0, LockedShare=30 ✅ CORRECT
Remaining = 30 - 30 = 0 ✅ CORRECT
```

---

## SETTLEMENT LOGIC

### Direction Rules

| PnL Sign | Who Owes | Direction |
|----------|----------|-----------|
| **Loss (PnL < 0)** | Client owes admin | Client → Admin |
| **Profit (PnL > 0)** | Admin owes client | Admin → Client |

### Settlement Rules

1. **Partial settlements allowed**
   - Integer values only
   - Can record multiple payments
   - Until remaining = 0

2. **Validation:**
   - `0 < SettlementAmount ≤ Remaining`
   - `FinalShare > 0` (no settlement if share = 0)
   - `Remaining > 0` (no over-settlement)

3. **Settlement creates:**
   - `Settlement` record (tracks payment)
   - Updates `funding` or `exchange_balance` (via MaskedCapital)
   - Updates PnL (as side effect)

### Settlement Flow

```
1. User records payment amount
2. System validates:
   - FinalShare > 0?
   - Remaining > 0?
   - SettlementAmount ≤ Remaining?
3. Calculate MaskedCapital
4. Update funding/exchange_balance
5. Create Settlement record
6. Recalculate remaining
```

### Implementation

```python
def record_payment(request, account_id):
    """
    Record a payment for a client-exchange account.
    
    MASKED SHARE SETTLEMENT SYSTEM - Settlement Logic:
    - Uses database row locking to prevent concurrent payment race conditions
    - Calculates FinalShare using floor() rounding
    - Validates against remaining settlement amount
    - Prevents negative funding/exchange_balance
    - Creates Settlement record to track payments
    - If Client_PnL < 0 (LOSS): funding = funding - MaskedCapital
    - If Client_PnL > 0 (PROFIT): exchange_balance = exchange_balance - MaskedCapital
    - Partial payments allowed
    """
    # Lock account row for concurrency safety
    account = ClientExchangeAccount.objects.select_for_update().get(pk=account_id)
    
    # Lock share if needed
    account.lock_initial_share_if_needed()
    
    # Get settlement info
    settlement_info = account.get_remaining_settlement_amount()
    remaining_amount = settlement_info['remaining']
    initial_final_share = settlement_info['initial_final_share']
    
    # Validate
    if initial_final_share == 0:
        raise ValidationError("No settlement allowed: Final share is zero")
    
    if paid_amount > remaining_amount:
        raise ValidationError(f"Over-settlement: {paid_amount} > {remaining_amount}")
    
    # Calculate MaskedCapital
    locked_initial_pnl = account.locked_initial_pnl
    masked_capital = int((paid_amount * abs(locked_initial_pnl)) / initial_final_share)
    
    # Update funding/exchange_balance
    client_pnl = account.compute_client_pnl()
    if client_pnl < 0:
        # LOSS: Reduce funding
        account.funding -= masked_capital
    else:
        # PROFIT: Reduce exchange_balance
        account.exchange_balance -= masked_capital
    
    # Create Settlement record
    Settlement.objects.create(
        client_exchange=account,
        amount=paid_amount,
        notes=notes
    )
```

---

## REMAINING AMOUNT CALCULATION

### Formula

```
Remaining = LockedInitialFinalShare − TotalSettled (Current Cycle)
Overpaid = max(0, TotalSettled − LockedInitialFinalShare)
```

### Critical Rules

1. **Always use locked share** - NEVER recalculate from current PnL
2. **Only count settlements from current cycle** - Filter by `cycle_start_date`
3. **Share NEVER shrinks** - It's locked at initial compute

### Implementation

```python
def get_remaining_settlement_amount(self):
    """
    CRITICAL FIX: Calculate remaining using LOCKED InitialFinalShare.
    
    Formula: Remaining = LockedInitialFinalShare - Sum(SharePayments)
    Overpaid = max(0, Sum(SharePayments) - LockedInitialFinalShare)
    
    Share is locked at first compute and NEVER shrinks after payments.
    This ensures share is decided by trading outcome, not by settlement.
    
    Returns: dict with 'remaining', 'overpaid', 'initial_final_share', and 'total_settled'
    """
    # Lock share if needed
    self.lock_initial_share_if_needed()
    
    # CRITICAL FIX: Only count settlements from CURRENT cycle
    if self.cycle_start_date:
        # Only count settlements that occurred AFTER this cycle started
        total_settled = self.settlements.filter(
            date__gte=self.cycle_start_date
        ).aggregate(total=models.Sum('amount'))['total'] or 0
    else:
        # Backward compatibility: count all settlements
        total_settled = self.settlements.aggregate(total=models.Sum('amount'))['total'] or 0
    
    # Use locked share
    if self.locked_initial_final_share is not None:
        initial_final_share = self.locked_initial_final_share
    else:
        # No locked share - check if we should lock current share
        current_share = self.compute_my_share()
        if current_share > 0:
            # Lock it now
            # ... (lock logic)
            initial_final_share = current_share
        else:
            return {'remaining': 0, 'overpaid': 0, 'initial_final_share': 0, 'total_settled': total_settled}
    
    # Calculate remaining
    remaining = max(0, initial_final_share - total_settled)
    overpaid = max(0, total_settled - initial_final_share)
    
    return {
        'remaining': remaining,
        'overpaid': overpaid,
        'initial_final_share': initial_final_share,
        'total_settled': total_settled
    }
```

### Examples

| Locked Share | Total Settled | Remaining | Overpaid |
|--------------|---------------|-----------|----------|
| 10 | 0 | 10 | 0 |
| 10 | 5 | 5 | 0 |
| 10 | 10 | 0 | 0 |
| 10 | 15 | 0 | 5 |
| 0 | 0 | 0 | 0 |

---

## MASKEDCAPITAL FORMULA

### Purpose

**Maps settlement payment back to actual capital change.**

When client pays share amount, we need to know how much capital to reduce.

### CORRECT Formula

```
MaskedCapital = (SharePayment × |LockedInitialPnL|) ÷ LockedInitialFinalShare
```

### Why This Formula is Correct

**Proportional mapping:**
- If client pays 50% of share → reduce 50% of PnL
- If client pays 100% of share → reduce 100% of PnL
- Linear relationship, not exponential

### Implementation

```python
# CORRECT FORMULA: MaskedCapital = (SharePayment × abs(LockedInitialPnL)) / LockedInitialFinalShare
masked_capital = int((paid_amount * abs(locked_initial_pnl)) / initial_final_share)
```

### Examples

| Share Payment | Locked PnL | Locked Share | MaskedCapital |
|---------------|-------------|--------------|---------------|
| 5 | -90 | 9 | (5 × 90) ÷ 9 = 50 |
| 3 | -90 | 9 | (3 × 90) ÷ 9 = 30 |
| 10 | +50 | 10 | (10 × 50) ÷ 10 = 50 |

### WRONG Formula (DO NOT USE)

```
❌ MaskedCapital = SharePayment × SharePercentage
```

**Why this is wrong:**
- Double-counts percentage
- Doesn't map proportionally to PnL
- Breaks for partial payments

---

## EDGE CASES

### 1. Zero Share Accounts

**Scenario:** `FinalShare == 0`

**Behavior:**
- No pending amount shown
- No settlement allowed
- Client treated as settled
- Shows "N.A" in UI

**Implementation:**
```python
if final_share == 0:
    show_na = True
    # No settlement button shown
```

**This is by design, not a bug.**

### 2. Very Small Percentages

**Scenario:** Share percentage too small, resulting in `FinalShare = 0`

**Example:**
- PnL = 5
- Share % = 1%
- Exact Share = 0.05
- Final Share = floor(0.05) = 0

**Behavior:** Same as zero share accounts

### 3. Partial Settlements

**Scenario:** Multiple partial payments

**Example:**
- Locked Share = 10
- Payment 1: 3 → Remaining = 7
- Payment 2: 4 → Remaining = 3
- Payment 3: 3 → Remaining = 0

**Behavior:** Allowed, tracked individually

### 4. Over-Settlement Prevention

**Scenario:** User tries to pay more than remaining

**Validation:**
```python
if paid_amount > remaining_amount:
    raise ValidationError("Over-settlement not allowed")
```

**Behavior:** Payment blocked, error shown

### 5. PnL Sign Flip During Settlement

**Scenario:** PnL changes sign while settling

**Example:**
- Start: PnL = -90, Share = 9
- Pay 5: PnL = -40, Remaining = 4
- Exchange changes: PnL = +50, NEW CYCLE

**Behavior:**
- Old cycle closes (remaining = 4 preserved)
- New cycle starts (remaining = 10)
- Old settlement (5) NOT counted in new cycle

### 6. Concurrent Payments

**Scenario:** Multiple users try to record payment simultaneously

**Protection:**
```python
account = ClientExchangeAccount.objects.select_for_update().get(pk=account_id)
```

**Behavior:** Database row locking prevents race conditions

### 7. Negative Balance Prevention

**Scenario:** Payment would make funding/exchange_balance negative

**Validation:**
```python
if account.funding - masked_capital < 0:
    raise ValidationError("Funding would become negative")
```

**Behavior:** Payment blocked, error shown

### 8. Zero PnL After Settlement

**Scenario:** Settlement brings PnL to zero

**Example:**
- Start: PnL = -90, Share = 9
- Pay 9: PnL = 0, Share = 0

**Behavior:**
- Locked share persists (9)
- Remaining = 0 (correct)
- Cycle closes when fully settled

### 9. Profit Percentage Change

**Scenario:** Profit share % changes after profits exist

**Rule:** Changes affect only **future profits**, not historical

**Example:**
- Profit 1: PnL = +100, % = 20%, Share = 20 (LOCKED)
- Change % to 30%
- Profit 2: PnL = +100, % = 30%, Share = 30 (NEW, LOCKED)

**Behavior:** Old profit keeps old %, new profit uses new %

### 10. Loss Share Percentage Immutability

**Scenario:** User tries to change loss share % after data exists

**Validation:**
```python
if has_transactions or has_settlements:
    raise ValidationError("Loss share percentage cannot be changed after data exists")
```

**Behavior:** Change blocked, error shown

---

## CODE IMPLEMENTATION

### Model: `ClientExchangeAccount`

**Location:** `core/models.py`

**Key Methods:**

1. **`compute_client_pnl()`**
   - Calculates: `ExchangeBalance − Funding`
   - Returns: BIGINT (can be negative)

2. **`compute_my_share()`**
   - Calculates: `floor(|PnL| × Share% / 100)`
   - Returns: BIGINT (always positive)

3. **`lock_initial_share_if_needed()`**
   - Locks share at first compute or sign flip
   - Sets `cycle_start_date`
   - Returns: None (modifies self)

4. **`get_remaining_settlement_amount()`**
   - Calculates: `LockedShare − TotalSettled (current cycle)`
   - Filters settlements by `cycle_start_date`
   - Returns: dict with remaining, overpaid, etc.

**Key Fields:**

- `funding` (BIGINT)
- `exchange_balance` (BIGINT)
- `loss_share_percentage` (INT)
- `profit_share_percentage` (INT)
- `locked_initial_final_share` (BIGINT, nullable)
- `locked_share_percentage` (INT, nullable)
- `locked_initial_pnl` (BIGINT, nullable)
- `cycle_start_date` (DateTime, nullable)

### Model: `Settlement`

**Location:** `core/models.py`

**Fields:**
- `client_exchange` (ForeignKey)
- `amount` (BIGINT)
- `date` (DateTime, auto_now_add)
- `notes` (Text, optional)

**Purpose:** Tracks individual settlement payments

### View: `pending_summary`

**Location:** `core/views.py` (line ~926)

**Purpose:** Displays pending payments list

**Logic:**
1. Get all client exchanges
2. For each exchange:
   - Calculate PnL
   - Lock share if needed
   - Get remaining amount
   - Add to appropriate list (clients owe / you owe)
3. Sort by amount
4. Render template

**Key Variables:**
- `clients_owe_list`: Clients in loss (owe you)
- `you_owe_list`: Clients in profit (you owe)
- `remaining_amount`: Amount still to settle

### View: `record_payment`

**Location:** `core/views.py` (line ~3257)

**Purpose:** Records a settlement payment

**Flow:**
1. Lock account row (`select_for_update()`)
2. Lock share if needed
3. Get remaining amount
4. Validate payment amount
5. Calculate MaskedCapital
6. Update funding/exchange_balance
7. Create Settlement record
8. Redirect

**Validations:**
- Final share > 0
- Remaining > 0
- Payment amount ≤ remaining
- Funding/exchange_balance won't go negative

### Template: `pending/summary.html`

**Location:** `core/templates/core/pending/summary.html`

**Displays:**
- Two sections: "Clients Owe You" and "You Owe Clients"
- Columns: Client, Exchange, Funding, Exchange Balance, Final Share, Remaining, Share %, Actions
- "Record Payment" button (only if remaining > 0)
- "Settled" label (if remaining = 0)
- "N.A" label (if share = 0)

### Template: `exchanges/account_detail.html`

**Location:** `core/templates/core/exchanges/account_detail.html`

**Displays:**
- Account summary cards
- Final Share
- Remaining Settlement
- Settlements History
- "Record Payment" button (only if remaining > 0)

---

## TESTING SCENARIOS

### Scenario 1: Basic Loss Settlement

**Setup:**
- Funding: 100
- Exchange Balance: 10
- Loss Share %: 10%

**Expected:**
- PnL: -90
- Final Share: 9
- Remaining: 9

**Test:**
1. Record payment of 5
2. Verify remaining = 4
3. Record payment of 4
4. Verify remaining = 0
5. Verify "Settled" shown

### Scenario 2: Basic Profit Settlement

**Setup:**
- Funding: 50
- Exchange Balance: 100
- Profit Share %: 20%

**Expected:**
- PnL: +50
- Final Share: 10
- Remaining: 10

**Test:**
1. Record payment of 10
2. Verify remaining = 0
3. Verify exchange_balance reduced by MaskedCapital

### Scenario 3: Cycle Separation (Loss → Profit)

**Setup:**
- Step 1: Funding=100, Exchange=10, PnL=-90, Share=9
- Step 2: Pay 5, Remaining=4
- Step 3: Exchange=100, PnL=+50, NEW CYCLE

**Expected:**
- Step 3: Remaining = 10 (old settlement NOT counted)
- Old cycle: Remaining = 4 (preserved but not shown)

**Test:**
1. Record payment of 5 in loss cycle
2. Change exchange balance to 100
3. Verify new cycle starts
4. Verify remaining = 10 (not 5)
5. Verify old settlement (5) NOT counted

### Scenario 4: Cycle Separation (Profit → Loss)

**Setup:**
- Step 1: Funding=50, Exchange=100, PnL=+50, Share=10
- Step 2: Pay 10, Remaining=0
- Step 3: Exchange=20, PnL=-30, NEW CYCLE

**Expected:**
- Step 3: Remaining = 3 (old settlement NOT counted)

**Test:**
1. Record payment of 10 in profit cycle
2. Change exchange balance to 20
3. Verify new cycle starts
4. Verify remaining = 3 (not -7)

### Scenario 5: Zero Share Account

**Setup:**
- Funding: 100
- Exchange Balance: 100
- Share %: 10%

**Expected:**
- PnL: 0
- Final Share: 0
- Remaining: 0
- Shows "N.A"

**Test:**
1. Verify "Record Payment" button NOT shown
2. Verify "N.A" shown in pending list

### Scenario 6: Very Small Share

**Setup:**
- Funding: 100
- Exchange Balance: 95
- Loss Share %: 1%

**Expected:**
- PnL: -5
- Exact Share: 0.05
- Final Share: 0
- Remaining: 0

**Test:**
1. Verify "Record Payment" button NOT shown
2. Verify "N.A" shown

### Scenario 7: Over-Settlement Prevention

**Setup:**
- Funding: 100
- Exchange Balance: 10
- Loss Share %: 10%
- Remaining: 9

**Test:**
1. Try to record payment of 10
2. Verify error: "Over-settlement not allowed"
3. Verify remaining still = 9

### Scenario 8: Concurrent Payments

**Setup:**
- Two users try to record payment simultaneously

**Test:**
1. User 1: Record payment of 5
2. User 2: Try to record payment of 5 (should see remaining = 4)
3. Verify database locking prevents race condition

### Scenario 9: Negative Balance Prevention

**Setup:**
- Funding: 50
- Exchange Balance: 10
- Loss Share %: 10%
- Remaining: 9

**Test:**
1. Try to record payment that would make funding negative
2. Verify error: "Funding would become negative"
3. Verify funding unchanged

### Scenario 10: Partial Payments

**Setup:**
- Funding: 100
- Exchange Balance: 10
- Loss Share %: 10%
- Remaining: 9

**Test:**
1. Record payment of 3 → Remaining = 6
2. Record payment of 4 → Remaining = 2
3. Record payment of 2 → Remaining = 0
4. Verify all payments tracked individually

---

## FAILURE CASES AND FIXES

### Failure Case 1: MaskedCapital Double-Counts Percentage

**❌ Old (Wrong) Formula:**
```
MaskedCapital = SharePayment × SharePercentage
```

**Example:**
- Funding = 100
- Exchange Balance = 30
- PnL = -70
- Loss % = 10%
- Share = 7
- Payment = 3

**Wrong Calculation:**
```
MaskedCapital = 3 × 10 = 30
Funding = 100 - 30 = 70
New PnL = 30 - 70 = -40
```

**Problem:** Only "looks OK" because numbers are small. Breaks for all partials, all percentages, all rounding.

**✅ Correct Formula:**
```
MaskedCapital = (SharePayment × |LockedInitialPnL|) ÷ LockedInitialFinalShare
```

**Correct Calculation:**
```
MaskedCapital = (3 × 70) ÷ 7 = 30
Funding = 100 - 30 = 70
New PnL = 30 - 70 = -40
```

**Result:** Works for ALL partials, ALL percentages, ALL rounding.

**Fix:** Implemented in `record_payment` view (line ~3396)

---

### Failure Case 2: Settlement Shrinks Share (Without Lock)

**❌ Old Dynamic System (before lock):**

**Example:**
- Initial: Funding=1000, Exchange=700, PnL=-300, Share=30
- Client pays 30: Funding=700, Exchange=700, PnL=0, Share=0 ❌

**Problem:** Share disappears because settlement changed PnL.

**✅ Correct Logic (with lock):**
- Initial: Funding=1000, Exchange=700, PnL=-300, LockedShare=30
- Client pays 30: Funding=700, Exchange=700, PnL=0, LockedShare=30 ✅
- Remaining = 30 - 30 = 0 ✅

**Fix:** Implemented `lock_initial_share_if_needed()` method

---

### Failure Case 3: Concurrent Payment Race Conditions

**❌ Problem:**
- User 1 reads remaining = 10
- User 2 reads remaining = 10
- User 1 pays 6 → remaining = 4
- User 2 pays 6 → remaining = 4 ❌ (should be -2, but validation catches it)

**✅ Fix:**
```python
account = ClientExchangeAccount.objects.select_for_update().get(pk=account_id)
```

**Result:** Database row locking prevents concurrent modifications.

**Fix:** Implemented in `record_payment` view (line ~3275)

---

### Failure Case 4: Old Cycle Settlements Mix with New Cycle

**❌ Problem:**
- Old cycle: Share=9, Settled=5, Remaining=4
- New cycle starts: Share=10
- System counts old settlement (5) → Remaining = 5 ❌ (should be 10)

**✅ Fix:**
```python
if self.cycle_start_date:
    total_settled = self.settlements.filter(
        date__gte=self.cycle_start_date
    ).aggregate(total=models.Sum('amount'))['total'] or 0
```

**Result:** Only settlements from current cycle are counted.

**Fix:** Implemented in `get_remaining_settlement_amount()` method (line ~266)

---

### Failure Case 6: Funding Change Doesn't Reset Cycle

**❌ Problem:**
- Old cycle: Funding=100, Exchange=10, PnL=-90, Share=9 (LOCKED)
- New funding added: Funding=300, Exchange=100, PnL=-200
- System reuses old locked share (9) → Remaining = 9 ❌ (should be 20)

**Root Cause:**
- No sign flip (both are LOSS)
- No cycle reset triggered
- Old locked share persists forever
- Undercharging client

**✅ Fix:**
```python
# CRITICAL FIX: Funding change should reset cycle (new exposure = new cycle)
if self.locked_initial_final_share is not None:
    if self.locked_initial_funding is not None:
        if self.funding != self.locked_initial_funding:
            # Funding changed → reset cycle
            self.locked_initial_final_share = None
            # ... reset all locks
    else:
        # Old data: Check if PnL changed significantly
        # If PnL magnitude changed by >50%, likely funding changed
        if pnl_diff_ratio > 1.5 or pnl_diff_ratio < 0.67:
            # Reset cycle
```

**Result:** Funding change triggers new cycle, share recalculated correctly.

**Fix:** Implemented in `lock_initial_share_if_needed()` method (line ~198)

---

### Failure Case 5: Negative Balance After Payment

**❌ Problem:**
- Funding = 50
- Payment would reduce funding to -10

**✅ Fix:**
```python
if account.funding - masked_capital < 0:
    raise ValidationError("Funding would become negative")
```

**Result:** Payment blocked before balance goes negative.

**Fix:** Implemented in `record_payment` view (line ~3402)

---

## SUMMARY

### Key Formulas

1. **PnL:** `Client_PnL = ExchangeBalance − Funding`
2. **Exact Share:** `ExactShare = |PnL| × (Share% / 100)`
3. **Final Share:** `FinalShare = floor(ExactShare)`
4. **Remaining:** `Remaining = LockedInitialFinalShare − TotalSettled (Current Cycle)`
5. **MaskedCapital:** `MaskedCapital = (SharePayment × |LockedInitialPnL|) ÷ LockedInitialFinalShare`

### Key Rules

1. **Shares are locked** at first compute per PnL cycle
2. **Cycles reset** when PnL sign changes (LOSS ↔ PROFIT)
3. **Old cycle settlements** never mix with new cycle shares
4. **Remaining uses locked share**, not current share
5. **MaskedCapital maps proportionally** to PnL

### System Guarantees

- ✅ Deterministic math
- ✅ No rounding drift
- ✅ Ledger stability
- ✅ Safe manual control
- ✅ Support for changing profit %
- ✅ No historical corruption
- ✅ Cycle separation
- ✅ Concurrency safety

---

**END OF DOCUMENTATION**
