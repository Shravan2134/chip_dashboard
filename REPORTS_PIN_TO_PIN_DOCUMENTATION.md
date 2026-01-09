# REPORTS SYSTEM - PIN-TO-PIN DOCUMENTATION

**Version:** 2.1  
**Status:** Current Implementation  
**Last Updated:** January 2026  
**Document Type:** Complete End-to-End Pin-to-Pin Guide

---

## 🔑 CORRECTNESS LOGIC (SOURCE OF TRUTH)

**⚠️ CRITICAL: This section defines the LAW of the system. All implementations MUST follow these rules.**

### Core Truth (Non-Negotiable)

**Profit exists ONLY when money actually moves.**
- If no money moved → profit = 0
- PnL alone ≠ profit
- Exchange balance ≠ profit
- Funding ≠ profit
- **✅ Only payments matter**

### 1. Single Source of Truth

**✅ Allowed for Profit Calculation:**
- `Transaction(type = 'RECORD_PAYMENT')`

**❌ Forbidden for Profit:**
- `FUNDING` transactions
- `TRADE` transactions
- `FEE` transactions
- `ADJUSTMENT` transactions
- Exchange balance
- PnL snapshots
- Settlement model (for profit calculation)

**👉 If profit is calculated from anything else → INCORRECT**

### 2. Money Direction Rule (Absolute)

**The sign of `RECORD_PAYMENT.amount` IS the truth:**

| RECORD_PAYMENT.amount | Meaning |
|----------------------|---------|
| +X | Client paid YOU |
| -X | YOU paid client |

**Properties:**
- ✅ No guessing
- ✅ No PnL check needed
- ✅ No locked_initial_pnl check needed
- ✅ No fallback logic needed
- **The sign itself is the truth**

### 3. Your Total Profit (Top-Level)

**✅ Correct Formula:**
```
Your Total Profit = Σ(RECORD_PAYMENT.amount)
WHERE filtered by:
  - your user
  - selected client (if any)
  - selected date range (if any)
```

**Properties:**
- Positive → you earned
- Negative → you lost
- Zero → break-even

**❌ Wrong if:**
- Split logic applied here
- Settlement model used
- PnL used
- Any other source

### 4. My Profit & Friend Profit (Split Logic)

**Required Configuration:**
```
my_percentage = total_share_percentage
my_own_percentage + friend_percentage = my_percentage
```

**✅ Correct Split Formula (PER PAYMENT):**
```
For each RECORD_PAYMENT:
  payment = RECORD_PAYMENT.amount
  
  my_profit = payment × (my_own_percentage / my_percentage)
  friend_profit = payment × (friend_percentage / my_percentage)
```

**✅ Mandatory Identity (MUST ALWAYS HOLD):**
```
payment == my_profit + friend_profit
```

**Properties:**
- ✅ Works for +ve and -ve amounts
- ✅ Works for profit and loss cases
- ✅ Always reconciles
- ✅ If identity fails → BUG

### 5. Aggregated Totals (System-Wide)

**✅ Mandatory Reconciliation:**
```
Your Total Profit == Σ(My Profit) + Σ(Friend Profit)
```

**If this fails → system is broken**

### 6. Time Filtering Correctness

**Filtering affects which payments are included, NOT how profit is calculated.**

**✅ Allowed filters:**
- Client
- Month
- Date range
- As-of date (time travel)

**❌ NOT allowed:**
- Re-calculating direction
- Re-calculating split
- Changing signs
- Using different data sources

### 7. Turnover Correctness

**You MUST choose one meaning:**

**Option A: Cash Movement Only**
```
Turnover = Σ(RECORD_PAYMENT.amount) + Σ(FUNDING.amount)
```

**Option B: Activity Volume**
```
Turnover = Σ(|ALL transaction amounts|)
```

**🚫 Mixing definitions is incorrect**
**🚫 Label must match meaning**

### 8. Chart Correctness Rules

**❌ Current Behavior (WRONG):**
- Daily profit = 0
- Weekly profit = 0
- Monthly profit = 0

**✅ Correct Behavior:**
Charts must reflect grouped `Σ(RECORD_PAYMENT.amount)` by:
- Day
- Week
- Month

Even if split is not shown in charts, **net profit MUST show**.

### 9. No Dual Source Rule

**❌ Forbidden:**
- Settlement used for totals
- RECORD_PAYMENT used for split
- PnL used for direction

**✅ Only one truth:**
- `RECORD_PAYMENT` transactions
- Everything derives from it

### 10. Correctness Self-Check

For any report or code, ask:

1. ❓ Is profit derived ONLY from RECORD_PAYMENT?
2. ❓ Is sign of amount deciding direction?
3. ❓ Is split proportional and reversible?
4. ❓ Does My + Friend = Payment?
5. ❓ Does Total Profit = Σ(payments)?
6. ❓ Do charts match summary?
7. ❓ Does filtering only include/exclude rows?

**If YES to all → ✅ Correct**  
**If NO to any → ❌ Wrong**

### 🔒 Final Lock Statement

**Profit is not calculated. Profit is recorded. Reports only aggregate it.**

---

## TABLE OF CONTENTS

1. [System Overview](#1-system-overview)
2. [Data Flow - End to End](#2-data-flow---end-to-end)
3. [Data Sources](#3-data-sources)
4. [Report Page Structure](#4-report-page-structure)
5. [Formulas and Calculations](#5-formulas-and-calculations)
6. [Filtering Logic](#6-filtering-logic)
7. [Chart Data Preparation](#7-chart-data-preparation)
8. [Template Rendering](#8-template-rendering)
9. [Code Implementation Details](#9-code-implementation-details)
10. [Examples and Scenarios](#10-examples-and-scenarios)
11. [Correctness Logic Reference](#correctness-logic-reference)

---

## 1. SYSTEM OVERVIEW

### 1.1 Purpose

The Reports System provides **real-time analytics and insights** into transaction activity and business performance. It shows:
- Total transaction volume (turnover)
- Your actual profit/loss (cash-flow based)
- My Profit and Friend Profit (split from settlements)
- Daily, weekly, and monthly trends
- Transaction type breakdowns
- Recent transaction history

### 1.2 Key Principles

1. **Transaction-Based**: Reports built from `Transaction` model (audit trail)
2. **User-Scoped**: All data filtered by `request.user` (only your clients)
3. **Time-Filtered**: Supports month selection, date ranges, and time-travel mode
4. **Client-Filterable**: Can filter by specific client
5. **Real-Time**: Calculations performed on-demand from database
6. **Cash-Flow Based**: Profit calculated from actual money received/paid

### 1.3 Report Types

- **Overview Report** (`report_overview`): Main dashboard with all charts
- **Daily Report**: Day-by-day breakdown (last 30 days)
- **Weekly Report**: Week-by-week trends (last 4 weeks)
- **Monthly Report**: Month-by-month trends (last 6 months)
- **Custom Report**: User-defined date range
- **Client Report**: Per-client analysis
- **Exchange Report**: Per-exchange analysis
- **Time Travel Report**: Historical point-in-time analysis

---

## 2. DATA FLOW - END TO END

### 2.1 User Request Flow

```
User clicks "Reports" in navigation
    ↓
URL: /reports/
    ↓
Django routes to: report_overview(request)
    ↓
View function processes request
    ↓
Data is calculated from database
    ↓
Context dictionary is prepared
    ↓
Template renders HTML with charts
    ↓
JavaScript (Chart.js) renders visualizations
    ↓
User sees reports page
```

### 2.2 Data Processing Flow

```
1. GET REQUEST PARAMETERS
   ├─ report_type (daily/weekly/monthly)
   ├─ month (YYYY-MM format)
   ├─ client (client ID)
   ├─ start_date, end_date (for custom range)
   └─ date (for time-travel mode)

2. BUILD BASE QUERYSET
   ├─ Filter by user: client_exchange__client__user = request.user
   ├─ Filter by client (if specified)
   └─ Filter by date range (if specified)

3. APPLY TRANSACTION TYPE FILTER
   └─ Only include: RECORD_PAYMENT, FUNDING

4. CALCULATE SUMMARY STATISTICS
   ├─ Total Turnover (from RECORD_PAYMENT + FUNDING transactions)
   ├─ Your Total Profit (from RECORD_PAYMENT transactions ONLY)
   ├─ My Profit (split from RECORD_PAYMENT transactions)
   └─ Friend Profit (split from RECORD_PAYMENT transactions)

5. PREPARE CHART DATA
   ├─ Daily trends (last 30 days)
   ├─ Weekly trends (last 4 weeks)
   ├─ Monthly trends (last 6 months)
   ├─ Transaction type breakdown
   └─ Top clients (currently empty)

6. PREPARE CONTEXT
   └─ All calculated data + filters + client list

7. RENDER TEMPLATE
   └─ HTML + JavaScript charts
```

---

## 3. DATA SOURCES

### 3.1 Primary Source: Transaction Model

**Model:** `Transaction`  
**Location:** `core/models.py`  
**Purpose:** Audit trail of all transactions

**Fields Used:**
- `id`: Transaction ID
- `client_exchange`: ForeignKey to `ClientExchangeAccount`
- `date`: Transaction date (DateTimeField)
- `type`: Transaction type (CharField with choices)
- `amount`: Transaction amount (BigIntegerField)
- `exchange_balance_after`: Exchange balance after transaction
- `notes`: Optional notes
- `created_at`: Timestamp when record was created

**Transaction Types (TRANSACTION_TYPES):**
```python
TRANSACTION_TYPES = [
    ('FUNDING', 'Funding'),
    ('TRADE', 'Trade'),
    ('FEE', 'Fee'),
    ('ADJUSTMENT', 'Adjustment'),
    ('RECORD_PAYMENT', 'Record Payment'),
]
```

**What Each Type Means:**
- `FUNDING`: Money given to client (funding increased)
- `RECORD_PAYMENT`: Settlement payment recorded (used for profit calculation)
- `TRADE`: Trading activity (legacy/placeholder, rarely used)
- `FEE`: Fee transaction
- `ADJUSTMENT`: Balance adjustment

### 3.2 Secondary Source: Settlement Model

**Model:** `Settlement`  
**Location:** `core/models.py`  
**Purpose:** Records actual settlement payments

**Fields Used:**
- `client_exchange`: ForeignKey to `ClientExchangeAccount`
- `amount`: Settlement amount (BigIntegerField)
- `date`: Settlement date (DateTimeField)
- `notes`: Optional notes

**Used For:**
- Calculating "Your Total Profit" (cash-flow based)
- Determining payment direction (client paid me vs I paid client)

### 3.3 Supporting Source: ClientExchangeAccount Model

**Model:** `ClientExchangeAccount`  
**Location:** `core/models.py`  
**Purpose:** Account configuration and current state

**Fields Used:**
- `locked_initial_pnl`: PnL when settlement cycle started
- `my_percentage`: Total share percentage
- `report_config`: Related `ClientExchangeReportConfig` (for My/Friend split)

**Used For:**
- Determining payment direction (loss vs profit)
- Calculating My Profit and Friend Profit split

### 3.4 Supporting Source: ClientExchangeReportConfig Model

**Model:** `ClientExchangeReportConfig`  
**Location:** `core/models.py`  
**Purpose:** Configuration for profit split between You and Friend

**Fields Used:**
- `my_own_percentage`: Your share percentage
- `friend_percentage`: Friend's share percentage

**Used For:**
- Splitting RECORD_PAYMENT amounts between My Profit and Friend Profit

---

## 4. REPORT PAGE STRUCTURE

### 4.1 Page Layout

```
┌─────────────────────────────────────────────────┐
│  Reports & Analytics                            │
│  Comprehensive insights into your business      │
├─────────────────────────────────────────────────┤
│  [Filters Section]                              │
│  ├─ Client Dropdown                            │
│  ├─ Month Selector                              │
│  └─ Report Type Tabs (Daily/Weekly/Monthly)    │
├─────────────────────────────────────────────────┤
│  [Summary Statistics Cards]                     │
│  ├─ Total Turnover                              │
│  ├─ Your Total Profit                           │
│  ├─ My Profit                                   │
│  └─ Friend Profit                               │
├─────────────────────────────────────────────────┤
│  [Charts Section]                               │
│  ├─ Daily/Weekly/Monthly Trends Chart           │
│  ├─ Transaction Type Breakdown Chart            │
│  └─ Top Clients Chart (if data available)       │
├─────────────────────────────────────────────────┤
│  [Recent Transactions Table]                   │
│  └─ Last 50 transactions                       │
└─────────────────────────────────────────────────┘
```

### 4.2 Summary Statistics Cards

**Card 1: Total Turnover**
- **Label:** "Total Turnover"
- **Value:** Sum of all transaction amounts
- **Color:** Blue border
- **Note:** "All-time transaction volume"

**Card 2: Your Total Profit**
- **Label:** "Your Total Profit"
- **Value:** Cash-flow based profit (money received - money paid)
- **Color:** Green border (if positive) / Red border (if negative)
- **Note:** Shows breakdown: "Money received (₹X) - Money paid (₹Y)"

**Card 3: My Profit**
- **Label:** "My Profit"
- **Value:** Your share from settlements (split from ClientExchangeReportConfig)
- **Color:** Green border (if positive) / Red border (if negative)
- **Note:** "Your share from settlements (split from ClientExchangeReportConfig)"

**Card 4: Friend Profit**
- **Label:** "Friend Profit"
- **Value:** Friend's share from settlements (split from ClientExchangeReportConfig)
- **Color:** Green border (if positive) / Red border (if negative)
- **Note:** "Friend share from settlements (split from ClientExchangeReportConfig)"

---

## 5. FORMULAS AND CALCULATIONS

### 5.1 Formula 1: Total Turnover

**Definition:**
```
TotalTurnover = Σ(Transaction.amount)
WHERE Transaction.client_exchange.client.user = current_user
  AND Transaction.type IN ('RECORD_PAYMENT', 'FUNDING')
  AND Transaction.date >= start_date (if filtered)
  AND Transaction.date <= end_date (if filtered)
  AND Transaction.client_exchange.client_id = client_id (if filtered)
```

**Django ORM Implementation:**
```python
# Step 1: Build base queryset
user_filter = {"client_exchange__client__user": request.user}
base_qs = Transaction.objects.filter(**user_filter)

# Step 2: Apply client filter (if specified)
if client_id:
    user_filter["client_exchange__client_id"] = client_id
    base_qs = base_qs.filter(**user_filter)

# Step 3: Apply date filter (if specified)
if date_filter:
    base_qs = base_qs.filter(**date_filter)

# Step 4: Filter transaction types
settled_filter = Q(type__in=['RECORD_PAYMENT', 'FUNDING'])
base_qs = base_qs.filter(settled_filter)

# Step 5: Calculate total
total_turnover = base_qs.aggregate(total=Sum("amount"))["total"] or 0
```

**What It Shows:**
- Sum of all transaction amounts in selected time period
- Includes FUNDING and RECORD_PAYMENT transactions only
- Filtered by user and optional date/client filters

**Example:**
```
Transactions:
  FUNDING: +10,000
  RECORD_PAYMENT: +5,000
  RECORD_PAYMENT: +3,000
  FUNDING: +2,000

Total Turnover = 10,000 + 5,000 + 3,000 + 2,000 = 20,000
```

---

### 5.2 Formula 2: Your Total Profit (Cash-Flow Based)

**⚠️ CORRECTNESS RULE: This formula MUST use ONLY RECORD_PAYMENT transactions.**

**Definition:**
```
YourTotalProfit = Σ(RECORD_PAYMENT.amount)
WHERE Transaction.type = 'RECORD_PAYMENT'
  AND Transaction.client_exchange.client.user = current_user
  AND date filters applied (if any)
  AND client filter applied (if any)
```

**Sign Convention (ABSOLUTE RULE):**
- **+X** = Client paid YOU → Income (positive)
- **-X** = YOU paid client → Expense (negative)
- **The sign itself is the truth** - no PnL check, no locked_initial_pnl check, no fallback logic needed

**Django ORM Implementation (CORRECT):**
```python
# Step 1: Get all RECORD_PAYMENT transactions for user
payment_transactions = Transaction.objects.filter(
    client_exchange__client__user=request.user,
    type='RECORD_PAYMENT'
)

# Step 2: Apply client filter (if specified)
if client_id:
    payment_transactions = payment_transactions.filter(
        client_exchange__client_id=client_id
    )

# Step 3: Apply date filter (if specified)
if date_filter:
    payment_transactions = payment_transactions.filter(**date_filter)

# Step 4: Calculate total profit (simple sum)
your_total_profit = payment_transactions.aggregate(
    total=Sum("amount")
)["total"] or Decimal(0)

# Step 5: Calculate breakdown for display
your_total_income_from_clients = payment_transactions.filter(
    amount__gt=0
).aggregate(total=Sum("amount"))["total"] or Decimal(0)

your_total_paid_to_clients = abs(
    payment_transactions.filter(amount__lt=0).aggregate(
        total=Sum("amount")
    )["total"] or Decimal(0)
)
```

**❌ WRONG Implementation (DO NOT USE):**
```python
# DO NOT use Settlement model
# DO NOT check locked_initial_pnl
# DO NOT use fallback logic
# DO NOT check current PnL
```

**Example:**
```
RECORD_PAYMENT Transactions:
  Transaction 1: +4,000  (client paid me)
  Transaction 2: +6,000  (client paid me)
  Transaction 3: -3,000  (I paid client)
  Transaction 4: -5,000  (I paid client)

Your Total Profit = 4,000 + 6,000 + (-3,000) + (-5,000) = 2,000

Breakdown:
  Money received = 4,000 + 6,000 = 10,000
  Money paid = 3,000 + 5,000 = 8,000
  Net Profit = 10,000 - 8,000 = 2,000 ✓
```

**Display:**
- Shows actual cash-flow based profit
- Positive = you earned money
- Negative = you paid more than received
- Shows breakdown: "Money received (₹X) - Money paid (₹Y)"

---

### 5.3 Formula 3: My Profit & Friend Profit (Split from RECORD_PAYMENT)

**⚠️ CORRECTNESS RULE: Payment direction is determined by sign, NOT by PnL checks.**

**Definition:**
```
FOR EACH RECORD_PAYMENT transaction:
  payment = RECORD_PAYMENT.amount  (sign is absolute: +X = client paid you, -X = you paid client)
  
  my_profit = payment × (my_own_percentage / my_percentage)
  friend_profit = payment × (friend_percentage / my_percentage)

WHERE:
  my_percentage = ClientExchangeAccount.my_percentage
  my_own_percentage = ClientExchangeReportConfig.my_own_percentage
  friend_percentage = ClientExchangeReportConfig.friend_percentage

MANDATORY IDENTITY (MUST ALWAYS HOLD):
  payment == my_profit + friend_profit

AGGREGATED TOTALS (MUST RECONCILE):
  Your Total Profit == Σ(My Profit) + Σ(Friend Profit)
```

**Django ORM Implementation (CORRECT):**
```python
# Step 1: Get all RECORD_PAYMENT transactions
payment_qs = Transaction.objects.filter(
    client_exchange__client__user=request.user,
    type='RECORD_PAYMENT'
)

# Step 2: Apply client filter (if specified)
if client_id:
    payment_qs = payment_qs.filter(client_exchange__client_id=client_id)

# Step 3: Apply date filter (if specified)
if date_filter:
    # Convert date to datetime for comparison
    filter_dict = {}
    if 'date__gte' in date_filter:
        filter_dict['date__gte'] = timezone.make_aware(
            datetime.combine(date_filter['date__gte'], datetime.min.time())
        )
    if 'date__lte' in date_filter:
        filter_dict['date__lte'] = timezone.make_aware(
            datetime.combine(date_filter['date__lte'], datetime.max.time())
        )
    payment_qs = payment_qs.filter(**filter_dict)

# Step 4: Process each transaction
my_profit_total = Decimal(0)
friend_profit_total = Decimal(0)

for tx in payment_qs.select_related('client_exchange', 'client_exchange__report_config'):
    # Step 5: Payment amount IS the signed amount (no direction determination needed)
    payment_amount = Decimal(str(tx.amount))  # Can be positive or negative
    
    account = tx.client_exchange
    
    # Step 6: Get split percentages
    my_total_pct = Decimal(str(account.my_percentage))
    if my_total_pct == 0:
        continue
    
    report_config = getattr(account, 'report_config', None)
    if report_config:
        my_own_pct = Decimal(str(report_config.my_own_percentage))
        friend_pct = Decimal(str(report_config.friend_percentage))
        
        # Step 7: Split payment amount (works for both +ve and -ve)
        my_profit_part = payment_amount * my_own_pct / my_total_pct
        friend_profit_part = payment_amount * friend_pct / my_total_pct
        
        # Step 8: Verify identity (for debugging - can be removed in production)
        assert abs((my_profit_part + friend_profit_part) - payment_amount) < Decimal('0.01'), \
            f"Split identity failed: {my_profit_part} + {friend_profit_part} != {payment_amount}"
    else:
        # No report config: all goes to me
        my_profit_part = payment_amount
        friend_profit_part = Decimal(0)
    
    my_profit_total += my_profit_part
    friend_profit_total += friend_profit_part

# Step 9: Verify aggregated totals reconcile (for debugging)
your_total_profit_from_payments = payment_qs.aggregate(total=Sum("amount"))["total"] or Decimal(0)
assert abs((my_profit_total + friend_profit_total) - your_total_profit_from_payments) < Decimal('0.01'), \
    f"Aggregated totals failed: {my_profit_total} + {friend_profit_total} != {your_total_profit_from_payments}"
```

**❌ WRONG Implementation (DO NOT USE):**
```python
# DO NOT determine direction from locked_initial_pnl
# DO NOT check current PnL
# DO NOT use fallback logic
# DO NOT convert amount to absolute value
```

**Example:**
```
Transaction 1:
  RECORD_PAYMENT.amount: +9  (client paid me)
  My percentage: 10%
  My own percentage: 6%
  Friend percentage: 4%
  
  My Profit = 9 × 6 / 10 = 5.4
  Friend Profit = 9 × 4 / 10 = 3.6
  Verification: 5.4 + 3.6 = 9 ✓

Transaction 2:
  RECORD_PAYMENT.amount: -5  (I paid client)
  My percentage: 10%
  My own percentage: 6%
  Friend percentage: 4%
  
  My Profit = -5 × 6 / 10 = -3.0
  Friend Profit = -5 × 4 / 10 = -2.0
  Verification: -3.0 + (-2.0) = -5 ✓

Total My Profit = 5.4 + (-3.0) = 2.4
Total Friend Profit = 3.6 + (-2.0) = 1.6
Total Profit = 2.4 + 1.6 = 4.0
Verification: 9 + (-5) = 4 ✓
```

---

### 5.4 Formula 4: Daily Trends

**⚠️ CORRECTNESS RULE: Charts MUST show actual profit, not zeros.**

**Definition:**
```
FOR EACH date FROM start_date TO end_date (max 30 days):
    DailyTurnover[date] = Σ(Transaction.amount)
                          WHERE Transaction.date = date
                            AND Transaction.type IN ('RECORD_PAYMENT', 'FUNDING')
                            AND filtered_by_user_and_client
    
    DailyProfit[date] = Σ(RECORD_PAYMENT.amount)
                        WHERE Transaction.type = 'RECORD_PAYMENT'
                          AND Transaction.date = date
                          AND Transaction.amount > 0
                          AND filtered_by_user_and_client
    
    DailyLoss[date] = ABS(Σ(RECORD_PAYMENT.amount))
                      WHERE Transaction.type = 'RECORD_PAYMENT'
                        AND Transaction.date = date
                        AND Transaction.amount < 0
                        AND filtered_by_user_and_client
```

**Date Range Calculation:**
```python
if time_travel_mode and start_date_str and end_date_str:
    start_date = date.fromisoformat(start_date_str)
    end_date = date.fromisoformat(end_date_str)
    days_diff = (end_date - start_date).days
    if days_diff > 30:
        end_date = start_date + timedelta(days=30)  # Limit to 30 days
else:
    start_date = today - timedelta(days=30)
    end_date = today
```

**Django ORM Implementation:**
```python
daily_data = defaultdict(lambda: {"profit": 0, "loss": 0, "turnover": 0})

# Daily turnover (all transaction types)
daily_transactions = base_qs.filter(
    date__gte=start_date,
    date__lte=end_date
).values("date").annotate(
    turnover_sum=Sum("amount")
)

for item in daily_transactions:
    tx_date = item['date']
    daily_data[tx_date]["turnover"] += float(item["turnover_sum"] or 0)

# Daily profit/loss from RECORD_PAYMENT transactions
daily_payments = base_qs.filter(
    type='RECORD_PAYMENT',
    date__gte=start_date,
    date__lte=end_date
).values("date").annotate(
    profit_sum=Sum("amount")
)

for item in daily_payments:
    tx_date = item['date']
    profit_amount = float(item["profit_sum"] or 0)
    if profit_amount > 0:
        daily_data[tx_date]["profit"] += profit_amount
    elif profit_amount < 0:
        daily_data[tx_date]["loss"] += abs(profit_amount)

# Create date labels and data arrays
date_labels = []
profit_data = []
loss_data = []
turnover_data = []

current_date = start_date
days_count = 0
while current_date <= end_date and days_count < 30:
    day_data = daily_data[current_date]
    date_labels.append(current_date.strftime("%Y-%m-%d"))
    profit_data.append(float(day_data.get("profit", 0)))  # Actual profit
    loss_data.append(float(day_data.get("loss", 0)))      # Actual loss
    turnover_data.append(float(day_data.get("turnover", 0)))
    current_date += timedelta(days=1)
    days_count += 1
```

**Chart Display:**
- X-axis: Dates (YYYY-MM-DD format)
- Y-axis: Amount
- Lines:
  - Profit line (always 0)
  - Loss line (always 0)
  - Turnover line (actual data)

---

### 5.5 Formula 5: Weekly Trends

**⚠️ CORRECTNESS RULE: Charts MUST show actual profit, not zeros.**

**Definition:**
```
FOR EACH week FROM last 4 weeks:
    WeekStart = WeekEnd - 6 days
    WeekEnd = PreviousWeekStart - 1 day (for next iteration)
    
    WeeklyTurnover[week] = Σ(Transaction.amount)
                           WHERE Transaction.date >= WeekStart
                             AND Transaction.date <= WeekEnd
                             AND Transaction.type IN ('RECORD_PAYMENT', 'FUNDING')
                             AND filtered_by_user_and_client
    
    WeeklyProfit[week] = Σ(RECORD_PAYMENT.amount)
                         WHERE Transaction.type = 'RECORD_PAYMENT'
                           AND Transaction.date >= WeekStart
                           AND Transaction.date <= WeekEnd
                           AND Transaction.amount > 0
                           AND filtered_by_user_and_client
    
    WeeklyLoss[week] = ABS(Σ(RECORD_PAYMENT.amount))
                       WHERE Transaction.type = 'RECORD_PAYMENT'
                         AND Transaction.date >= WeekStart
                         AND Transaction.date <= WeekEnd
                         AND Transaction.amount < 0
                         AND filtered_by_user_and_client
```

**Django ORM Implementation:**
```python
weekly_labels = []
weekly_profit = []
weekly_loss = []
weekly_turnover = []

# Initialize week_end to end_date
week_end = end_date

for i in range(4):
    week_start = week_end - timedelta(days=6)
    weekly_labels.insert(0, f"Week {4-i} ({week_start.strftime('%b %d')} - {week_end.strftime('%b %d')})")
    
    week_transactions = base_qs.filter(
        date__gte=week_start,
        date__lte=week_end
    )
    
    # Calculate profit/loss from RECORD_PAYMENT transactions
    week_payments = week_transactions.filter(type='RECORD_PAYMENT')
    week_profit_val = week_payments.filter(amount__gt=0).aggregate(
        total=Sum("amount")
    )["total"] or 0
    week_loss_val = abs(week_payments.filter(amount__lt=0).aggregate(
        total=Sum("amount")
    )["total"] or 0)
    week_turnover_val = week_transactions.aggregate(total=Sum("amount"))["total"] or 0
    
    weekly_profit.insert(0, float(week_profit_val))
    weekly_loss.insert(0, float(week_loss_val))
    weekly_turnover.insert(0, float(week_turnover_val))
    
    # Move week_end backwards for next iteration
    week_end = week_start - timedelta(days=1)
```

**Chart Display:**
- X-axis: Week labels ("Week 1 (Jan 01 - Jan 07)")
- Y-axis: Amount
- Bars:
  - Profit bars (always 0)
  - Loss bars (always 0)
  - Turnover bars (actual data)

---

### 5.6 Formula 6: Monthly Trends

**⚠️ CORRECTNESS RULE: Charts MUST show actual profit, not zeros.**

**Definition:**
```
FOR EACH month FROM last 6 months:
    MonthDate = Today.replace(day=1) - i months
    MonthEnd = Last day of MonthDate
    
    MonthlyTurnover[month] = Σ(Transaction.amount)
                             WHERE Transaction.date >= MonthDate
                               AND Transaction.date <= MonthEnd
                               AND Transaction.type IN ('RECORD_PAYMENT', 'FUNDING')
                               AND filtered_by_user_and_client
    
    MonthlyProfit[month] = Σ(RECORD_PAYMENT.amount)
                           WHERE Transaction.type = 'RECORD_PAYMENT'
                             AND Transaction.date >= MonthDate
                             AND Transaction.date <= MonthEnd
                             AND Transaction.amount > 0
                             AND filtered_by_user_and_client
    
    MonthlyLoss[month] = ABS(Σ(RECORD_PAYMENT.amount))
                         WHERE Transaction.type = 'RECORD_PAYMENT'
                           AND Transaction.date >= MonthDate
                           AND Transaction.date <= MonthEnd
                           AND Transaction.amount < 0
                           AND filtered_by_user_and_client
```

**Django ORM Implementation:**
```python
monthly_labels = []
monthly_profit = []
monthly_loss = []
monthly_turnover = []

for i in range(6):
    month_date = today.replace(day=1)
    # Go back i months
    for _ in range(i):
        if month_date.month == 1:
            month_date = month_date.replace(year=month_date.year - 1, month=12)
        else:
            month_date = month_date.replace(month=month_date.month - 1)
    
    # Calculate month end date
    if month_date.month == 12:
        month_end = date(month_date.year, 12, 31)
    else:
        month_end = month_date.replace(month=month_date.month + 1) - timedelta(days=1)
    
    monthly_labels.insert(0, month_date.strftime("%b %Y"))
    
    month_transactions = base_qs.filter(
        date__gte=month_date,
        date__lte=month_end
    )
    
    # Calculate profit/loss from RECORD_PAYMENT transactions
    month_payments = month_transactions.filter(type='RECORD_PAYMENT')
    month_profit_val = month_payments.filter(amount__gt=0).aggregate(
        total=Sum("amount")
    )["total"] or 0
    month_loss_val = abs(month_payments.filter(amount__lt=0).aggregate(
        total=Sum("amount")
    )["total"] or 0)
    month_turnover_val = month_transactions.aggregate(total=Sum("amount"))["total"] or 0
    
    monthly_profit.insert(0, float(month_profit_val))
    monthly_loss.insert(0, float(month_loss_val))
    monthly_turnover.insert(0, float(month_turnover_val))
```

**Chart Display:**
- X-axis: Month labels ("Jan 2026")
- Y-axis: Amount
- Bars:
  - Profit bars (always 0)
  - Loss bars (always 0)
  - Turnover bars (actual data)

---

### 5.7 Formula 7: Transaction Type Breakdown

**Definition:**
```
FOR EACH transaction_type IN ('FUNDING', 'TRADE', 'FEE', 'ADJUSTMENT', 'RECORD_PAYMENT'):
    TypeCount[type] = COUNT(Transaction.id)
                      WHERE Transaction.type = type
                        AND filtered_by_user_and_dates
    
    TypeAmount[type] = Σ(Transaction.amount)
                       WHERE Transaction.type = type
                         AND filtered_by_user_and_dates
```

**Django ORM Implementation:**
```python
type_breakdown = base_qs.values("type").annotate(
    count=Count("id"),
    total_amount=Sum("amount")
)

type_labels = []
type_counts = []
type_amounts = []
type_colors = []

type_map = {
    'FUNDING': ("Funding", "#4b5563"),
    'TRADE': ("Trade", "#6b7280"),
    'FEE': ("Fee", "#9ca3af"),
    'ADJUSTMENT': ("Adjustment", "#6b7280"),
    'RECORD_PAYMENT': ("Record Payment", "#10b981"),
}

for item in type_breakdown:
    tx_type = item["type"]
    if tx_type in type_map:
        label, color = type_map[tx_type]
        type_labels.append(label)
        type_counts.append(item["count"])
        type_amounts.append(float(item["total_amount"] or 0))
        type_colors.append(color)
```

**Chart Display:**
- Pie/Donut chart
- Each slice represents a transaction type
- Size = total amount for that type
- Color = predefined color from type_map

---

## 6. FILTERING LOGIC

### 6.1 User Filtering

**Always Applied:**
```python
user_filter = {"client_exchange__client__user": request.user}
```

**Purpose:**
- Ensures users only see their own data
- Applied to all queries
- Cannot be disabled

### 6.2 Client Filtering

**Applied When:**
- User selects a client from dropdown
- `client_id` parameter in GET request

**Implementation:**
```python
client_id = request.GET.get("client")
if client_id:
    user_filter["client_exchange__client_id"] = client_id
```

**Effect:**
- Only shows transactions for selected client
- All calculations limited to that client

### 6.3 Date Filtering

**Three Modes:**

**Mode 1: Month Selection (Default)**
```python
month_str = request.GET.get("month", today.strftime("%Y-%m"))
year, month = map(int, month_str.split("-"))
selected_month_start = date(year, month, 1)
if month == 12:
    selected_month_end = date(year, 12, 31)
else:
    selected_month_end = date(year, month + 1, 1) - timedelta(days=1)

date_filter = {
    "date__gte": selected_month_start,
    "date__lte": selected_month_end
}
```

**Mode 2: Date Range (Custom)**
```python
start_date_str = request.GET.get("start_date")
end_date_str = request.GET.get("end_date")

if start_date_str and end_date_str:
    start_date_filter = date.fromisoformat(start_date_str)
    end_date_filter = date.fromisoformat(end_date_str)
    date_filter = {
        "date__gte": start_date_filter,
        "date__lte": end_date_filter
    }
```

**Mode 3: Time Travel (As-Of Date)**
```python
as_of_str = request.GET.get("date")

if as_of_str:
    time_travel_mode = True
    as_of_filter = date.fromisoformat(as_of_str)
    date_filter = {"date__lte": as_of_filter}
```

### 6.4 Transaction Type Filtering

**Always Applied:**
```python
settled_filter = Q(type__in=['RECORD_PAYMENT', 'FUNDING'])
base_qs = base_qs.filter(settled_filter)
```

**Purpose:**
- Only includes relevant transaction types
- Excludes TRADE, FEE, ADJUSTMENT from main calculations
- These types may still appear in type breakdown chart

---

## 7. CHART DATA PREPARATION

### 7.1 Daily Trends Chart

**Data Structure:**
```python
{
    "date_labels": ["2026-01-01", "2026-01-02", ...],
    "profit_data": [0, 0, 0, ...],  # Always zeros
    "loss_data": [0, 0, 0, ...],    # Always zeros
    "turnover_data": [1000, 2000, 1500, ...]
}
```

**Chart.js Configuration:**
```javascript
new Chart(ctx, {
    type: 'line',
    data: {
        labels: date_labels,
        datasets: [
            {label: 'Profit', data: profit_data, borderColor: 'green'},
            {label: 'Loss', data: loss_data, borderColor: 'red'},
            {label: 'Turnover', data: turnover_data, borderColor: 'blue'}
        ]
    }
})
```

### 7.2 Weekly Trends Chart

**Data Structure:**
```python
{
    "weekly_labels": ["Week 1 (Jan 01 - Jan 07)", "Week 2 (Jan 08 - Jan 14)", ...],
    "weekly_profit": [0, 0, 0, 0],
    "weekly_loss": [0, 0, 0, 0],
    "weekly_turnover": [5000, 6000, 7000, 8000]
}
```

**Chart.js Configuration:**
```javascript
new Chart(ctx, {
    type: 'bar',
    data: {
        labels: weekly_labels,
        datasets: [
            {label: 'Profit', data: weekly_profit, backgroundColor: 'green'},
            {label: 'Loss', data: weekly_loss, backgroundColor: 'red'},
            {label: 'Turnover', data: weekly_turnover, backgroundColor: 'blue'}
        ]
    }
})
```

### 7.3 Monthly Trends Chart

**Data Structure:**
```python
{
    "monthly_labels": ["Jul 2025", "Aug 2025", "Sep 2025", ...],
    "monthly_profit": [0, 0, 0, 0, 0, 0],
    "monthly_loss": [0, 0, 0, 0, 0, 0],
    "monthly_turnover": [20000, 25000, 30000, 35000, 40000, 45000]
}
```

**Chart.js Configuration:**
```javascript
new Chart(ctx, {
    type: 'bar',
    data: {
        labels: monthly_labels,
        datasets: [
            {label: 'Profit', data: monthly_profit, backgroundColor: 'green'},
            {label: 'Loss', data: monthly_loss, backgroundColor: 'red'},
            {label: 'Turnover', data: monthly_turnover, backgroundColor: 'blue'}
        ]
    }
})
```

### 7.4 Transaction Type Breakdown Chart

**Data Structure:**
```python
{
    "type_labels": ["Funding", "Record Payment", "Trade", "Fee", "Adjustment"],
    "type_counts": [10, 5, 2, 1, 0],
    "type_amounts": [100000, 50000, 20000, 1000, 0],
    "type_colors": ["#4b5563", "#10b981", "#6b7280", "#9ca3af", "#6b7280"]
}
```

**Chart.js Configuration:**
```javascript
new Chart(ctx, {
    type: 'doughnut',
    data: {
        labels: type_labels,
        datasets: [{
            data: type_amounts,
            backgroundColor: type_colors
        }]
    }
})
```

---

## 8. TEMPLATE RENDERING

### 8.1 Template File

**Location:** `core/templates/core/reports/overview.html`

### 8.2 Context Variables Passed

```python
context = {
    # Filters
    "report_type": report_type,  # "daily", "weekly", "monthly"
    "client_type_filter": client_type_filter,  # "all" (always)
    "all_clients": all_clients,  # List of Client objects
    "selected_client": selected_client,  # Selected Client or None
    "selected_month": month_str,  # "YYYY-MM"
    
    # Summary Statistics
    "total_turnover": total_turnover,
    "your_total_profit": your_total_profit,
    "your_total_income_from_clients": total_received_from_clients,
    "your_total_paid_to_clients": total_paid_to_clients,
    "my_profit": my_profit_total,
    "friend_profit": friend_profit_total,
    "company_profit": Decimal(0),  # Always 0
    
    # Daily Chart Data
    "date_labels": json.dumps(date_labels),
    "profit_data": json.dumps(profit_data),
    "loss_data": json.dumps(loss_data),
    "turnover_data": json.dumps(turnover_data),
    
    # Weekly Chart Data
    "weekly_labels": json.dumps(weekly_labels),
    "weekly_profit": json.dumps(weekly_profit),
    "weekly_loss": json.dumps(weekly_loss),
    "weekly_turnover": json.dumps(weekly_turnover),
    
    # Monthly Chart Data
    "monthly_labels": json.dumps(monthly_labels),
    "monthly_profit": json.dumps(monthly_profit),
    "monthly_loss": json.dumps(monthly_loss),
    "monthly_turnover": json.dumps(monthly_turnover),
    
    # Transaction Type Breakdown
    "type_labels": json.dumps(type_labels),
    "type_counts": json.dumps(type_counts),
    "type_amounts": json.dumps(type_amounts),
    "type_colors": json.dumps(type_colors),
    
    # Top Clients (currently empty)
    "client_labels": json.dumps(client_labels),
    "client_profits": json.dumps(client_profits),
    
    # Recent Transactions
    "time_travel_transactions": time_travel_transactions,
    
    # Time Travel Mode
    "time_travel_mode": time_travel_mode,
    "start_date": start_date_str if start_date_str else None,
    "end_date": end_date_str if end_date_str else None,
    "as_of_date": as_of_str if as_of_str else None,
}
```

### 8.3 Template Sections

**Section 1: Filters**
```html
<div class="filters-section">
    <select id="clientFilter">...</select>
    <input type="month" id="monthSelector">...</input>
    <div class="tabs-simple">
        <a href="?report_type=daily">Daily</a>
        <a href="?report_type=weekly">Weekly</a>
        <a href="?report_type=monthly">Monthly</a>
    </div>
</div>
```

**Section 2: Summary Cards**
```html
<div class="stats-grid">
    <div class="stat-box turnover">
        <div class="stat-label">Total Turnover</div>
        <div class="stat-value">₹ {{ total_turnover|floatformat:1 }}</div>
    </div>
    <div class="stat-box profit">
        <div class="stat-label">Your Total Profit</div>
        <div class="stat-value">₹ {{ your_total_profit|floatformat:1 }}</div>
        <div class="stat-note">
            Money received (₹{{ your_total_income_from_clients|floatformat:1 }}) 
            - Money paid (₹{{ your_total_paid_to_clients|floatformat:1 }})
        </div>
    </div>
    <!-- My Profit and Friend Profit cards -->
</div>
```

**Section 3: Charts**
```html
{% if report_type == 'daily' %}
    <canvas id="dailyTrendsChart"></canvas>
{% elif report_type == 'weekly' %}
    <canvas id="weeklyTrendsChart"></canvas>
{% elif report_type == 'monthly' %}
    <canvas id="monthlyTrendsChart"></canvas>
{% endif %}

<canvas id="typeBreakdownChart"></canvas>
```

**Section 4: Recent Transactions Table**
```html
<table>
    {% for tx in time_travel_transactions %}
        <tr>
            <td>{{ tx.date|date:"Y-m-d" }}</td>
            <td>{{ tx.client_exchange.client.name }}</td>
            <td>{{ tx.client_exchange.exchange.name }}</td>
            <td>{{ tx.type }}</td>
            <td>₹ {{ tx.amount|floatformat:0 }}</td>
            <td>{{ tx.notes|default:"" }}</td>
        </tr>
    {% endfor %}
</table>
```

### 8.4 JavaScript Chart Initialization

**Location:** Bottom of `overview.html` template

**Chart.js Library:**
```html
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
```

**Daily Trends Chart:**
```javascript
const dailyCtx = document.getElementById('dailyTrendsChart');
new Chart(dailyCtx, {
    type: 'line',
    data: {
        labels: {{ date_labels|safe }},
        datasets: [
            {
                label: 'Profit',
                data: {{ profit_data|safe }},
                borderColor: 'rgb(34, 197, 94)',
                backgroundColor: 'rgba(34, 197, 94, 0.1)'
            },
            {
                label: 'Loss',
                data: {{ loss_data|safe }},
                borderColor: 'rgb(239, 68, 68)',
                backgroundColor: 'rgba(239, 68, 68, 0.1)'
            },
            {
                label: 'Turnover',
                data: {{ turnover_data|safe }},
                borderColor: 'rgb(59, 130, 246)',
                backgroundColor: 'rgba(59, 130, 246, 0.1)'
            }
        ]
    },
    options: {
        responsive: true,
        scales: {
            y: { beginAtZero: true }
        }
    }
});
```

**Similar initialization for weekly, monthly, and type breakdown charts**

---

## 9. CODE IMPLEMENTATION DETAILS

### 9.1 View Function: report_overview

**Location:** `core/views.py`, line ~1484

**Function Signature:**
```python
@login_required
def report_overview(request):
    """High-level reporting screen with simple totals and graphs."""
```

**Step-by-Step Flow:**

**Step 1: Parse Request Parameters**
```python
today = date.today()
report_type = request.GET.get("report_type", "monthly")
client_type_filter = request.GET.get("client_type") or request.session.get('client_type_filter', 'all')
client_id = request.GET.get("client")
month_str = request.GET.get("month", today.strftime("%Y-%m"))
start_date_str = request.GET.get("start_date")
end_date_str = request.GET.get("end_date")
as_of_str = request.GET.get("date")
```

**Step 2: Calculate Month Boundaries**
```python
try:
    year, month = map(int, month_str.split("-"))
    selected_month_start = date(year, month, 1)
    if month == 12:
        selected_month_end = date(year, 12, 31)
    else:
        selected_month_end = date(year, month + 1, 1) - timedelta(days=1)
except (ValueError, IndexError):
    selected_month_start = date(today.year, today.month, 1)
    if today.month == 12:
        selected_month_end = date(today.year, 12, 31)
    else:
        selected_month_end = date(today.year, today.month + 1, 1) - timedelta(days=1)
```

**Step 3: Build Date Filter**
```python
time_travel_mode = False
date_filter = {}

if start_date_str and end_date_str:
    start_date_filter = date.fromisoformat(start_date_str)
    end_date_filter = date.fromisoformat(end_date_str)
    date_filter = {"date__gte": start_date_filter, "date__lte": end_date_filter}
elif as_of_str:
    time_travel_mode = True
    as_of_filter = date.fromisoformat(as_of_str)
    date_filter = {"date__lte": as_of_filter}
elif not time_travel_mode:
    date_filter = {"date__gte": selected_month_start, "date__lte": selected_month_end}
```

**Step 4: Build Base Queryset**
```python
user_filter = {"client_exchange__client__user": request.user}

if client_id:
    user_filter["client_exchange__client_id"] = client_id

base_qs = Transaction.objects.filter(**user_filter)

if date_filter:
    base_qs = base_qs.filter(**date_filter)

# Filter transaction types
settled_filter = Q(type__in=['RECORD_PAYMENT', 'FUNDING'])
base_qs = base_qs.filter(settled_filter)
```

**Step 5: Calculate Summary Statistics**
```python
# Total Turnover
total_turnover = base_qs.aggregate(total=Sum("amount"))["total"] or 0

# Your Total Profit (from Settlement model)
# ... (see Formula 2 implementation)

# My Profit and Friend Profit (from RECORD_PAYMENT transactions)
# ... (see Formula 3 implementation)
```

**Step 6: Prepare Chart Data**
```python
# Daily trends
# ... (see Formula 4 implementation)

# Weekly trends
# ... (see Formula 5 implementation)

# Monthly trends
# ... (see Formula 6 implementation)

# Transaction type breakdown
# ... (see Formula 7 implementation)
```

**Step 7: Prepare Context and Render**
```python
context = {
    # ... all calculated data
}

return render(request, "core/reports/overview.html", context)
```

---

## 10. EXAMPLES AND SCENARIOS

### Example 1: Basic Monthly Report

**User Action:**
- Navigates to `/reports/`
- Selects month: "2026-01"
- Report type: "monthly"

**Data Flow:**
1. `report_type = "monthly"`
2. `month_str = "2026-01"`
3. `selected_month_start = date(2026, 1, 1)`
4. `selected_month_end = date(2026, 1, 31)`
5. `date_filter = {"date__gte": date(2026, 1, 1), "date__lte": date(2026, 1, 31)}`
6. Base queryset filtered to January 2026 transactions
7. All calculations limited to January 2026
8. Monthly chart shows last 6 months (including January 2026)

**Display:**
- Summary cards show January 2026 totals
- Monthly trends chart shows last 6 months
- Transaction type breakdown shows January 2026 types
- Recent transactions table shows January 2026 transactions

---

### Example 2: Client-Specific Report

**User Action:**
- Navigates to `/reports/?client=5`
- Selects month: "2026-01"

**Data Flow:**
1. `client_id = 5`
2. `user_filter["client_exchange__client_id"] = 5`
3. Base queryset filtered to client ID 5 only
4. All calculations limited to client 5

**Display:**
- Summary cards show totals for client 5 only
- Charts show trends for client 5 only
- Recent transactions table shows client 5 transactions only

---

### Example 3: Time Travel Report

**User Action:**
- Navigates to `/reports/?date=2025-12-31`

**Data Flow:**
1. `as_of_str = "2025-12-31"`
2. `time_travel_mode = True`
3. `date_filter = {"date__lte": date(2025, 12, 31)}`
4. Base queryset filtered to transactions up to Dec 31, 2025
5. All calculations show data as of Dec 31, 2025

**Display:**
- Summary cards show totals as of Dec 31, 2025
- Charts show trends up to Dec 31, 2025
- Recent transactions table shows transactions up to Dec 31, 2025

---

### Example 4: Profit Calculation with Multiple Settlements

**Scenario:**
- Account A: Loss case, Settlement 1 = 4,000, Settlement 2 = 2,000
- Account B: Loss case, Settlement 1 = 6,000
- Account C: Profit case, Settlement 1 = 3,000
- Account D: Profit case, Settlement 1 = 5,000

**Calculation:**
```
Total Received (Loss cases):
  Account A: 4,000 + 2,000 = 6,000
  Account B: 6,000
  Total = 12,000

Total Paid (Profit cases):
  Account C: 3,000
  Account D: 5,000
  Total = 8,000

Your Total Profit = 12,000 - 8,000 = 4,000
```

**Display:**
- "Your Total Profit" card shows: ₹ 4,000
- Note shows: "Money received (₹12,000) - Money paid (₹8,000)"

---

### Example 5: My Profit and Friend Profit Split

**Scenario:**
- RECORD_PAYMENT transaction: amount = 9
- Account locked_initial_pnl = -100 (loss case)
- Payment amount = +9 (client paid me)
- Account my_percentage = 10%
- Report config: my_own_percentage = 6%, friend_percentage = 4%

**Calculation:**
```
Payment amount = 9 (positive, client paid me)

My Profit = 9 × 6 / 10 = 5.4
Friend Profit = 9 × 4 / 10 = 3.6

Total = 5.4 + 3.6 = 9 ✓
```

**Display:**
- "My Profit" card shows: ₹ 5.4
- "Friend Profit" card shows: ₹ 3.6

---

## APPENDIX A: DATABASE SCHEMA

### Transaction Model Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | BigAutoField | Primary key |
| `client_exchange` | ForeignKey | Links to ClientExchangeAccount |
| `date` | DateTimeField | Transaction date/time |
| `type` | CharField(20) | Transaction type (choices) |
| `amount` | BigIntegerField | Transaction amount |
| `exchange_balance_after` | BigIntegerField | Balance after transaction |
| `notes` | TextField | Optional notes |
| `created_at` | DateTimeField | Record creation timestamp |
| `updated_at` | DateTimeField | Record update timestamp |

### Settlement Model Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | BigAutoField | Primary key |
| `client_exchange` | ForeignKey | Links to ClientExchangeAccount |
| `amount` | BigIntegerField | Settlement amount |
| `date` | DateTimeField | Settlement date/time |
| `notes` | TextField | Optional notes |
| `created_at` | DateTimeField | Record creation timestamp |
| `updated_at` | DateTimeField | Record update timestamp |

---

## APPENDIX B: URL ROUTING

**URL Pattern:**
```python
path('reports/', views.report_overview, name='report_overview')
```

**URL Examples:**
- `/reports/` - Default monthly report
- `/reports/?report_type=daily` - Daily report
- `/reports/?report_type=weekly` - Weekly report
- `/reports/?month=2026-01` - January 2026 report
- `/reports/?client=5` - Client 5 report
- `/reports/?date=2025-12-31` - Time travel to Dec 31, 2025
- `/reports/?start_date=2025-12-01&end_date=2025-12-31` - Custom date range

---

## APPENDIX C: CURRENT LIMITATIONS

### 1. Daily/Weekly/Monthly Profit/Loss Charts (CORRECTNESS VIOLATION)

**⚠️ Current Issue (WRONG per Correctness Logic):**
- Daily, weekly, and monthly profit/loss charts always show 0
- This violates the correctness rule: "Charts must reflect grouped Σ(RECORD_PAYMENT.amount)"

**✅ Correct Implementation Required:**
- Calculate profit from RECORD_PAYMENT transactions for each period
- Group by day/week/month
- Show actual profit/loss values in charts
- Positive amounts = profit (client paid you)
- Negative amounts = loss (you paid client)

**Implementation Needed:**
- Query RECORD_PAYMENT transactions grouped by date/week/month
- Sum amounts for each period
- Separate positive (profit) and negative (loss) amounts
- Populate chart data with actual values

### 2. Top Clients Chart Always Empty

**Issue:**
- Top clients chart never shows data
- Always shows empty list

**Reason:**
- Transaction model doesn't have `your_share_amount` field
- Cannot calculate client-level profit from transactions

**Workaround:**
- Would need to calculate from Settlement model grouped by client

### 3. Monthly/Weekly Trends Not Filtered by Time Travel

**Issue:**
- Monthly trends always show last 6 months from today
- Weekly trends always show last 4 weeks from today
- Not relative to time-travel date

**Reason:**
- Code uses `today` instead of time-travel date for month/week calculation

**Expected Behavior:**
- If time-travel mode, should show months/weeks relative to selected date

---

## APPENDIX D: FUTURE ENHANCEMENTS

### 1. Calculate Daily/Weekly/Monthly Profit/Loss

**Implementation:**
- Query Settlement model for each period
- Group by date/week/month
- Calculate profit/loss for each period
- Populate chart data

### 2. Top Clients Chart

**Implementation:**
- Query Settlement model grouped by client
- Calculate total profit per client
- Sort by profit descending
- Limit to top 10
- Populate chart data

### 3. Export to CSV/Excel

**Implementation:**
- Add export button
- Generate CSV/Excel file with all report data
- Include all charts data as separate sheets

### 4. Email Reports

**Implementation:**
- Schedule daily/weekly/monthly email reports
- Send summary statistics and charts
- Include PDF attachment

---

## 11. CORRECTNESS LOGIC REFERENCE

### 11.1 Core Truth Statement

**Profit exists ONLY when money actually moves.**
- If no money moved → profit = 0
- PnL alone ≠ profit
- Exchange balance ≠ profit
- Funding ≠ profit
- **✅ Only payments matter**

### 11.2 Single Source of Truth

**✅ Allowed for Profit Calculation:**
- `Transaction(type = 'RECORD_PAYMENT')`

**❌ Forbidden for Profit:**
- `FUNDING` transactions
- `TRADE` transactions
- `FEE` transactions
- `ADJUSTMENT` transactions
- Exchange balance
- PnL snapshots
- Settlement model (for profit calculation)

**👉 If profit is calculated from anything else → INCORRECT**

### 11.3 Money Direction Rule

**The sign of `RECORD_PAYMENT.amount` IS the truth:**

| RECORD_PAYMENT.amount | Meaning |
|----------------------|---------|
| +X | Client paid YOU |
| -X | YOU paid client |

**Properties:**
- ✅ No guessing
- ✅ No PnL check needed
- ✅ No locked_initial_pnl check needed
- ✅ No fallback logic needed
- **The sign itself is the truth**

### 11.4 Mandatory Identities

**Per-Payment Identity (MUST ALWAYS HOLD):**
```
payment == my_profit + friend_profit
```

**Aggregated Totals Identity (MUST RECONCILE):**
```
Your Total Profit == Σ(My Profit) + Σ(Friend Profit)
```

**If either identity fails → BUG**

### 11.5 Correctness Self-Check

For any report or code, ask:

1. ❓ Is profit derived ONLY from RECORD_PAYMENT?
2. ❓ Is sign of amount deciding direction?
3. ❓ Is split proportional and reversible?
4. ❓ Does My + Friend = Payment?
5. ❓ Does Total Profit = Σ(payments)?
6. ❓ Do charts match summary?
7. ❓ Does filtering only include/exclude rows?

**If YES to all → ✅ Correct**  
**If NO to any → ❌ Wrong**

### 11.6 Final Lock Statement

**🔒 Profit is not calculated. Profit is recorded. Reports only aggregate it.**

---

**END OF DOCUMENT**

