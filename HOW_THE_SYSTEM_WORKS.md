# How The System Works - Complete Operational Guide

## Table of Contents
1. [System Overview](#system-overview)
2. [Core Concepts Explained](#core-concepts-explained)
3. [Complete Workflow Examples](#complete-workflow-examples)
4. [Data Flow and Calculations](#data-flow-and-calculations)
5. [Step-by-Step Operations](#step-by-step-operations)
6. [Real-World Scenarios](#real-world-scenarios)
7. [How Calculations Work](#how-calculations-work)
8. [How Ledgers Interact](#how-ledgers-interact)
9. [Payment Processing Flow](#payment-processing-flow)
10. [Reporting System](#reporting-system)

---

## System Overview

### What This System Does
This is a **Broker Portal** that manages financial transactions between you (the broker), your clients, and exchanges. It tracks:
- How much money you give to clients (funding)
- How much clients have in their exchange accounts (balance)
- How much clients owe you (pending losses)
- How much you owe clients (unpaid profits)
- All transactions with complete audit trail

### The Three Ledger System
The system uses **three separate ledgers** that work independently:

1. **Exchange Balance Ledger**: Client's actual balance in exchange account
2. **Pending Amount Ledger**: Unpaid losses (money client owes you)
3. **Transaction Ledger**: Complete history of all activities

**Why Separate?**
- Exchange balance can be high while pending is also high (client playing with profit but hasn't paid losses)
- You can owe client profit while they also owe you losses
- Complete transparency and audit trail

---

## Core Concepts Explained

### 1. Client Types

**My Clients** (Personal Clients):
- You manage these directly
- Company is NOT involved
- Your share percentage applies
- Admin profit share is **10%** (hardcoded, not from settings)

**Company Clients**:
- Managed by company
- Company gets a share
- Your share percentage applies
- Company share is calculated from **client's share**, not total

**Example**:
- Total profit: ₹1000
- Your share: 30%
- Company share: 9% (of client's 70%, not of ₹1000)

**Calculation**:
- You get: ₹1000 × 30% = ₹300
- Client gets: ₹1000 - ₹300 = ₹700
- Company gets: ₹700 × 9% = ₹63 (not ₹1000 × 9% = ₹90)

### 2. Share Percentages

**My Share %**: Your percentage of profit/loss
- Set per client-exchange combination
- Can be different for each client
- Example: 30% means you get 30% of profit or loss

**Company Share %**: Company's percentage
- Only applies to company clients
- Calculated from **client's remaining share**
- Example: If you take 30%, client gets 70%, company gets 9% of that 70%

### 3. Transaction Types

**FUNDING**: You give money to client
- Increases exchange balance
- Does NOT affect pending
- Example: You give client ₹5000 chips

**PROFIT**: Client made profit
- Increases exchange balance
- Does NOT affect pending
- Creates "You Owe Client" amount
- Example: Client won ₹2000

**LOSS**: Client lost money
- Decreases exchange balance
- **Increases pending** (client owes you)
- Example: Client lost ₹1500

**SETTLEMENT**: Payment made
- Two types:
  - **Client pays you**: Reduces pending
  - **You pay client**: Reduces "You Owe Client"
- Does NOT affect exchange balance
- Example: Client pays ₹500 of pending amount

**BALANCE_RECORD**: Manual balance entry
- Records actual balance in exchange
- Creates transaction automatically
- Example: You record that client has ₹3000 in account

---

## Complete Workflow Examples

### Example 1: New Client Setup

**Step 1: Create Client**
1. Go to `/my-clients/` or `/company-clients/`
2. Click "Add Client"
3. Enter:
   - Name: "John Doe"
   - Code: "JD001" (optional)
   - Referred by: "Mike" (optional)
4. Save

**What Happens**:
- Client record created in database
- No transactions yet
- No balances yet
- Client is ready to link to exchanges

**Step 2: Create Exchange (if not exists)**
1. Go to `/exchanges/`
2. Click "Add Exchange"
3. Enter:
   - Name: "Diamond"
   - Code: "DIA" (optional)
4. Save

**Step 3: Link Client to Exchange**
1. Go to client detail page
2. Click "Link Exchange"
3. Select "Diamond"
4. Set:
   - My Share %: 30
   - Company Share %: 9 (if company client)
5. Save

**What Happens**:
- ClientExchange record created
- Client can now have transactions for this exchange
- Share percentages are set

**Result**: Client is ready to receive funding and start playing.

---

### Example 2: Complete Transaction Cycle

**Scenario**: Client "John" linked to "Diamond" exchange with 30% your share, 9% company share.

#### Day 1: Give Client Funding

**Action**: Record funding of ₹10,000

**What Happens**:
1. Transaction created:
   - Type: FUNDING
   - Amount: ₹10,000
   - Date: Day 1
2. Exchange Balance: ₹10,000 (increased)
3. Pending: ₹0 (unchanged)
4. Total Funding: ₹10,000

**System State**:
- Exchange Balance Ledger: ₹10,000
- Pending Ledger: ₹0
- Transaction Ledger: 1 FUNDING transaction

#### Day 2: Client Wins (Profit)

**Action**: Record profit of ₹5,000

**What Happens**:
1. Transaction created:
   - Type: PROFIT
   - Amount: ₹5,000
   - Date: Day 2
2. Shares calculated:
   - Your share: ₹5,000 × 30% = ₹1,500
   - Client share: ₹5,000 - ₹1,500 = ₹3,500
   - Company share: ₹3,500 × 9% = ₹315
3. Exchange Balance: ₹15,000 (₹10,000 + ₹5,000)
4. Pending: ₹0 (unchanged)
5. "You Owe Client": ₹3,500 (client's share minus company share = ₹3,185)

**System State**:
- Exchange Balance Ledger: ₹15,000
- Pending Ledger: ₹0
- Transaction Ledger: 2 transactions (1 FUNDING, 1 PROFIT)
- You Owe Client: ₹3,185

#### Day 3: Client Loses (Loss)

**Action**: Record loss of ₹3,000

**What Happens**:
1. Transaction created:
   - Type: LOSS
   - Amount: ₹3,000
   - Date: Day 3
2. Shares calculated:
   - Your share (earn): ₹3,000 × 30% = ₹900
   - Client share (loss): ₹3,000 - ₹900 = ₹2,100
   - Company share (earn): ₹2,100 × 9% = ₹189
3. Exchange Balance: ₹12,000 (₹15,000 - ₹3,000)
4. **Pending: ₹2,100** (increased - client owes you this)
5. "You Owe Client": Still ₹3,185 (unchanged)

**System State**:
- Exchange Balance Ledger: ₹12,000
- Pending Ledger: ₹2,100 (client owes you)
- Transaction Ledger: 3 transactions
- You Owe Client: ₹3,185
- **Net**: Client owes you ₹2,100, but you also owe client ₹3,185

#### Day 4: Record Balance

**Action**: Manually record that client has ₹11,500 in exchange

**What Happens**:
1. ClientDailyBalance record created:
   - Date: Day 4
   - Remaining Balance: ₹11,500
2. **Transaction automatically created**:
   - Type: BALANCE_RECORD
   - Amount: ₹11,500
   - Date: Day 4
3. Exchange Balance: ₹11,500 (updated to recorded value)
4. Pending: ₹2,100 (unchanged)
5. Difference: ₹12,000 - ₹11,500 = ₹500 (this is the adjustment)

**System State**:
- Exchange Balance Ledger: ₹11,500 (from balance record)
- Pending Ledger: ₹2,100
- Transaction Ledger: 4 transactions (includes balance record)

#### Day 5: Client Pays Partial Pending

**Action**: Client pays ₹1,000 of ₹2,100 pending

**What Happens**:
1. Transaction created:
   - Type: SETTLEMENT
   - Amount: ₹1,000
   - client_share_amount: ₹0 (client pays)
   - your_share_amount: ₹1,000 (you receive)
2. **Pending reduced**: ₹2,100 - ₹1,000 = ₹1,100
3. Exchange Balance: ₹11,500 (unchanged - settlement doesn't affect balance)
4. "You Owe Client": ₹3,185 (unchanged)

**System State**:
- Exchange Balance Ledger: ₹11,500
- Pending Ledger: ₹1,100 (reduced)
- Transaction Ledger: 5 transactions
- You Owe Client: ₹3,185

#### Day 6: You Pay Client Profit

**Action**: You pay client ₹2,000 of their profit

**What Happens**:
1. Transaction created:
   - Type: SETTLEMENT
   - Amount: ₹2,000
   - client_share_amount: ₹2,000 (client receives)
   - your_share_amount: ₹0 (you pay)
2. **"You Owe Client" reduced**: ₹3,185 - ₹2,000 = ₹1,185
3. Exchange Balance: ₹11,500 (unchanged)
4. Pending: ₹1,100 (unchanged)

**System State**:
- Exchange Balance Ledger: ₹11,500
- Pending Ledger: ₹1,100
- Transaction Ledger: 6 transactions
- You Owe Client: ₹1,185 (reduced)

**Final Summary**:
- Exchange Balance: ₹11,500
- Client owes you: ₹1,100 (pending)
- You owe client: ₹1,185 (unpaid profit)
- Net: You owe client ₹85 more than they owe you

---

## Data Flow and Calculations

### How Exchange Balance is Calculated

**Formula**:
```
Exchange Balance = Latest Recorded Balance + Extra Adjustment
```

**If no balance recorded**:
```
Exchange Balance = Total Funding
```

**Step-by-Step Process**:

1. **Check for Balance Record**:
   - Look for `ClientDailyBalance` records for this client-exchange
   - Filter by date (if `as_of_date` provided)
   - Get the most recent one

2. **Calculate Balance**:
   - If balance record exists:
     - Balance = `remaining_balance + extra_adjustment`
   - If no balance record:
     - Balance = Sum of all FUNDING transactions up to date

3. **Example**:
   - Funding: ₹10,000
   - Latest balance record: ₹11,500
   - Extra adjustment: ₹0
   - **Exchange Balance = ₹11,500** (not ₹10,000)

**Key Point**: Balance record overrides calculated balance from funding.

### How Pending Amount is Calculated

**Formula**:
```
Pending = Sum of LOSS transactions - Sum of Client Payments
```

**Step-by-Step Process**:

1. **Get All Losses**:
   - Find all transactions with type = LOSS
   - Filter by date (if `as_of_date` provided)
   - Sum their amounts

2. **Get Client Payments**:
   - Find all SETTLEMENT transactions where:
     - `client_share_amount = 0` (client pays)
     - `your_share_amount > 0` (you receive)
   - Filter by date
   - Sum the `your_share_amount` values

3. **Calculate Pending**:
   - Pending = Total Losses - Total Client Payments
   - If negative, set to 0 (can't have negative pending)

4. **Example**:
   - Losses: ₹5,000
   - Client payments: ₹2,000
   - **Pending = ₹5,000 - ₹2,000 = ₹3,000**

**Key Point**: Pending is separate from exchange balance. Client can have high balance but also high pending.

### How Profit/Loss is Calculated

**Formula**:
```
Client Profit/Loss = Exchange Balance - Total Funding
```

**Step-by-Step Process**:

1. **Get Total Funding**:
   - Sum all FUNDING transactions
   - Filter by date if needed

2. **Get Exchange Balance**:
   - Use `get_exchange_balance()` function
   - Returns latest recorded balance or total funding

3. **Calculate Difference**:
   - Profit/Loss = Exchange Balance - Total Funding
   - If positive: Client is in profit
   - If negative: Client is in loss

4. **Example**:
   - Total Funding: ₹10,000
   - Exchange Balance: ₹12,000
   - **Profit/Loss = ₹12,000 - ₹10,000 = ₹2,000** (profit)

**Key Point**: This shows how much client gained/lost from their initial funding.

### How Share Amounts are Calculated

#### On Profit

**Your Share**:
```
Your Share = Total Profit × (My Share % / 100)
```

**Client Share**:
```
Client Share = Total Profit - Your Share
```

**Company Share** (for company clients):
```
Company Share = Client Share × (Company Share % / 100)
```

**Example**:
- Total Profit: ₹10,000
- My Share %: 30%
- Company Share %: 9%

**Calculation**:
- Your Share: ₹10,000 × 30% = ₹3,000
- Client Share: ₹10,000 - ₹3,000 = ₹7,000
- Company Share: ₹7,000 × 9% = ₹630

**Final Distribution**:
- You get: ₹3,000
- Client gets: ₹7,000 - ₹630 = ₹6,370
- Company gets: ₹630

#### On Loss

**Your Share (Earn)**:
```
Your Share = Total Loss × (My Share % / 100)
```

**Client Share (Loss)**:
```
Client Share = Total Loss - Your Share
```

**Company Share (Earn)** (for company clients):
```
Company Share = Client Share × (Company Share % / 100)
```

**Example**:
- Total Loss: ₹5,000
- My Share %: 30%
- Company Share %: 9%

**Calculation**:
- Your Share (earn): ₹5,000 × 30% = ₹1,500
- Client Share (loss): ₹5,000 - ₹1,500 = ₹3,500
- Company Share (earn): ₹3,500 × 9% = ₹315

**Final Distribution**:
- You earn: ₹1,500
- Client loses: ₹3,500
- Company earns: ₹315
- **Pending increases by ₹3,500** (client owes you this)

---

## Step-by-Step Operations

### Operation 1: Recording a Funding Transaction

**User Action**: 
1. Go to `/transactions/add/`
2. Fill form:
   - Client-Exchange: John - Diamond
   - Date: 2025-01-15
   - Type: Funding
   - Amount: 5000.0
3. Click "Save"

**System Process**:

1. **Validate Input**:
   - Check amount > 0
   - Check date is valid
   - Check client-exchange exists and belongs to user

2. **Round Amount**:
   - Amount = 5000.0 (already 1 decimal)

3. **Create Transaction**:
   ```python
   Transaction.objects.create(
       client_exchange=client_exchange,
       date=2025-01-15,
       transaction_type="FUNDING",
       amount=5000.0,
       client_share_amount=5000.0,  # Client receives
       your_share_amount=0.0,        # You give
       company_share_amount=0.0
   )
   ```

4. **Update Exchange Balance** (if no balance record exists):
   - Exchange Balance = Previous Balance + 5000.0

5. **Result**:
   - Transaction saved
   - Exchange balance increased
   - Pending unchanged
   - User redirected to transaction list

**Database Changes**:
- 1 new Transaction record
- Exchange balance calculation updated (not stored, calculated on-the-fly)

### Operation 2: Recording a Profit Transaction

**User Action**:
1. Go to `/transactions/add/`
2. Fill form:
   - Client-Exchange: John - Diamond
   - Date: 2025-01-16
   - Type: Profit
   - Amount: 3000.0
3. Click "Save"

**System Process**:

1. **Validate Input**: (same as funding)

2. **Get Share Percentages**:
   - My Share %: 30% (from ClientExchange)
   - Company Share %: 9% (from ClientExchange, if company client)

3. **Calculate Shares**:
   - Your Share: 3000.0 × 30% = 900.0
   - Client Share: 3000.0 - 900.0 = 2100.0
   - Company Share: 2100.0 × 9% = 189.0

4. **Round All Amounts**:
   - Amount: 3000.0
   - Your Share: 900.0
   - Client Share: 2100.0
   - Company Share: 189.0

5. **Create Transaction**:
   ```python
   Transaction.objects.create(
       client_exchange=client_exchange,
       date=2025-01-16,
       transaction_type="PROFIT",
       amount=3000.0,
       client_share_amount=2100.0,  # Client's share
       your_share_amount=900.0,      # Your share
       company_share_amount=189.0    # Company's share
   )
   ```

6. **Update Calculations**:
   - Exchange Balance: Increased by 3000.0
   - "You Owe Client": Increased by (2100.0 - 189.0) = 1911.0
   - Pending: Unchanged

7. **Result**:
   - Transaction saved with calculated shares
   - Exchange balance increased
   - "You Owe Client" amount increased
   - User redirected

**Database Changes**:
- 1 new Transaction record with all share amounts

### Operation 3: Recording a Loss Transaction

**User Action**:
1. Go to `/transactions/add/`
2. Fill form:
   - Client-Exchange: John - Diamond
   - Date: 2025-01-17
   - Type: Loss
   - Amount: 2000.0
3. Click "Save"

**System Process**:

1. **Validate Input**: (same as before)

2. **Get Share Percentages**: (same as profit)

3. **Calculate Shares**:
   - Your Share (earn): 2000.0 × 30% = 600.0
   - Client Share (loss): 2000.0 - 600.0 = 1400.0
   - Company Share (earn): 1400.0 × 9% = 126.0

4. **Round All Amounts**: (same as profit)

5. **Create Transaction**:
   ```python
   Transaction.objects.create(
       client_exchange=client_exchange,
       date=2025-01-17,
       transaction_type="LOSS",
       amount=2000.0,
       client_share_amount=1400.0,  # Client's loss
       your_share_amount=600.0,     # Your earnings
       company_share_amount=126.0   # Company's earnings
   )
   ```

6. **Update Pending Amount**:
   - Get current pending: ₹1,000 (example)
   - Add client's loss share: ₹1,000 + ₹1,400 = ₹2,400
   - Update PendingAmount record

7. **Update Calculations**:
   - Exchange Balance: Decreased by 2000.0
   - Pending: Increased by 1400.0
   - "You Owe Client": Unchanged

8. **Result**:
   - Transaction saved
   - Exchange balance decreased
   - Pending increased (client owes you more)
   - User redirected

**Database Changes**:
- 1 new Transaction record
- PendingAmount record updated (pending_amount increased)

### Operation 4: Recording a Balance

**User Action**:
1. Go to `/my-clients/21/balance/?exchange=27`
2. Fill form:
   - Exchange: Diamond
   - Date: 2025-01-18
   - Remaining Balance: 5500.0
   - Extra Adjustment: 100.0 (optional)
   - Note: "Verified balance"
3. Click "Record Balance"

**System Process**:

1. **Validate Input**:
   - Check balance >= 0
   - Check date is valid
   - Check client-exchange exists

2. **Get Previous Balance**:
   - Previous Balance = get_exchange_balance(client_exchange)
   - Example: ₹6,000

3. **Calculate New Balance**:
   - New Balance = 5500.0 + 100.0 = 5600.0

4. **Create/Update Balance Record**:
   ```python
   ClientDailyBalance.objects.update_or_create(
       client_exchange=client_exchange,
       date=2025-01-18,
       defaults={
           "remaining_balance": 5500.0,
           "extra_adjustment": 100.0,
           "note": "Verified balance"
       }
   )
   ```

5. **Create Transaction Automatically**:
   ```python
   Transaction.objects.create(
       client_exchange=client_exchange,
       date=2025-01-18,
       transaction_type="BALANCE_RECORD",
       amount=5600.0,  # remaining_balance + extra_adjustment
       client_share_amount=5600.0,
       your_share_amount=0.0,
       company_share_amount=0.0,
       note="Balance Record: ₹5500.0 + Adjustment: ₹100.0 (Recorded at 14:30:25)"
   )
   ```

6. **Update Pending (if balance decreased)**:
   - If new_balance < previous_balance:
     - Difference = 6000.0 - 5600.0 = 400.0
     - Add to pending: Pending += 400.0

7. **Result**:
   - Balance record saved
   - Transaction created automatically
   - Exchange balance updated to recorded value
   - Pending updated if balance decreased
   - User sees updated balance

**Database Changes**:
- 1 ClientDailyBalance record (created or updated)
- 1 new Transaction record (BALANCE_RECORD type)
- PendingAmount updated (if balance decreased)

**Key Point**: Every balance record creates a separate transaction, even if same date.

### Operation 5: Client Pays Pending Amount

**User Action**:
1. Go to `/pending/?section=clients-owe`
2. Click "Record Payment" for client
3. Fill form:
   - Amount: 1000.0
   - Date: 2025-01-19
   - Note: "Partial payment"
4. Click "Record Payment"

**System Process**:

1. **Validate Input**:
   - Check amount > 0
   - Check date is valid
   - Check client-exchange exists

2. **Round Amount**:
   - Amount = 1000.0 (rounded to 1 decimal)

3. **Get Current Pending**:
   - Current Pending = ₹2,400 (example)

4. **Calculate Payment**:
   - Payment Amount = min(1000.0, 2400.0) = 1000.0
   - New Pending = max(0, 2400.0 - 1000.0) = 1400.0

5. **Update PendingAmount**:
   ```python
   pending.pending_amount = 1400.0
   pending.save()
   ```

6. **Create Settlement Transaction**:
   ```python
   Transaction.objects.create(
       client_exchange=client_exchange,
       date=2025-01-19,
       transaction_type="SETTLEMENT",
       amount=1000.0,
       client_share_amount=0.0,      # Client pays
       your_share_amount=1000.0,     # You receive
       company_share_amount=0.0,
       note="Client payment against pending amount (₹1000.0 of ₹2400.0)"
   )
   ```

7. **Result**:
   - Pending reduced by ₹1,000
   - Transaction created
   - Client removed from "Clients Owe You" list if pending = 0
   - User redirected to pending page

**Database Changes**:
- 1 new Transaction record (SETTLEMENT type)
- PendingAmount record updated (pending_amount decreased)

**Key Point**: Partial payments are supported. Client can pay any amount up to pending.

### Operation 6: You Pay Client Profit

**User Action**:
1. Go to `/pending/?section=you-owe`
2. Click "Pay Client" for client
3. Fill form:
   - Amount: 1500.0
   - Date: 2025-01-20
   - Note: "Profit payment"
4. Click "Pay Client"

**System Process**:

1. **Validate Input**: (same as client payment)

2. **Round Amount**:
   - Amount = 1500.0

3. **Get Current "You Owe" Amount**:
   - Calculate: Client profit shares - Settlements already paid
   - Example: ₹2,000

4. **Create Settlement Transaction**:
   ```python
   Transaction.objects.create(
       client_exchange=client_exchange,
       date=2025-01-20,
       transaction_type="SETTLEMENT",
       amount=1500.0,
       client_share_amount=1500.0,  # Client receives
       your_share_amount=0.0,       # You pay
       company_share_amount=0.0,
       note="Admin payment for client profit"
   )
   ```

5. **Update "You Owe" Calculation**:
   - New "You Owe" = ₹2,000 - ₹1,500 = ₹500
   - This is calculated on-the-fly, not stored

6. **Result**:
   - Transaction created
   - "You Owe Client" reduced
   - Client removed from "You Owe Clients" list if amount = 0
   - Exchange balance unchanged
   - Pending unchanged
   - User redirected

**Database Changes**:
- 1 new Transaction record (SETTLEMENT type)
- No other records changed (pending and balance unaffected)

**Key Point**: Admin profit payments don't affect pending or exchange balance.

---

## Real-World Scenarios

### Scenario 1: Client Wins Big, Then Loses

**Day 1**: Give client ₹10,000 funding
- Exchange Balance: ₹10,000
- Pending: ₹0

**Day 2**: Client wins ₹20,000
- Exchange Balance: ₹30,000
- Pending: ₹0
- You Owe Client: ₹14,000 (70% of ₹20,000, minus company share)

**Day 3**: Client loses ₹25,000
- Exchange Balance: ₹5,000
- Pending: ₹17,500 (70% of ₹25,000 loss)
- You Owe Client: Still ₹14,000

**Result**:
- Client has ₹5,000 in account
- Client owes you ₹17,500 (pending)
- You owe client ₹14,000 (unpaid profit)
- **Net**: Client owes you ₹3,500 more

**Key Insight**: Even though client is in profit overall (₹5,000 balance from ₹10,000 funding = -₹5,000), they still owe you pending from losses, and you still owe them profit from wins.

### Scenario 2: Multiple Balance Records Same Day

**Morning**: Record balance ₹5,000
- Transaction 1 created: BALANCE_RECORD, ₹5,000, 09:00:00

**Afternoon**: Update balance to ₹5,500
- Transaction 2 created: BALANCE_RECORD, ₹5,500, 14:30:25

**Evening**: Update balance to ₹6,000
- Transaction 3 created: BALANCE_RECORD, ₹6,000, 18:45:10

**Result**:
- 3 separate transactions for same date
- Each has unique timestamp in note
- Latest balance (₹6,000) is used for calculations
- All 3 transactions visible in transaction list

**Key Insight**: Every balance update creates a new transaction, providing complete audit trail.

### Scenario 3: Partial Payments Over Time

**Initial**: Client owes ₹10,000 (pending)

**Payment 1**: Client pays ₹3,000
- Pending: ₹7,000
- Transaction 1: SETTLEMENT, ₹3,000

**Payment 2**: Client pays ₹2,000
- Pending: ₹5,000
- Transaction 2: SETTLEMENT, ₹2,000

**Payment 3**: Client pays ₹5,000
- Pending: ₹0
- Transaction 3: SETTLEMENT, ₹5,000
- Client removed from "Clients Owe You" list

**Result**:
- 3 separate payment transactions
- Complete payment history
- Client cleared after final payment

**Key Insight**: System tracks every payment separately, allowing partial payments over time.

---

## How Calculations Work

### Calculation Flow Diagram

```
User Action
    ↓
Input Validation
    ↓
Get Related Data (ClientExchange, Settings, etc.)
    ↓
Calculate Shares (if profit/loss)
    ↓
Round All Amounts to 1 Decimal
    ↓
Create Transaction Record
    ↓
Update Related Records (PendingAmount, etc.)
    ↓
Recalculate Derived Values (Exchange Balance, etc.)
    ↓
Save All Changes
    ↓
Redirect User with Success Message
```

### Rounding Process

**Step 1: User Input**
- User enters: 1234.567

**Step 2: Backend Rounding**
```python
amount = Decimal("1234.567")
amount = amount.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
# Result: 1234.6
```

**Step 3: Storage**
- Stored in database: 1234.60 (2 decimals in DB, but treated as 1 decimal)

**Step 4: Display**
- Template: `{{ amount|floatformat:1 }}`
- Displayed: ₹1234.6

**Key Point**: All amounts are consistently rounded to 1 decimal throughout the system.

### Share Calculation Details

#### For "My Clients" (No Company)

**On Profit**:
```
Total Profit: ₹10,000
My Share %: 30%
Admin Profit Share: 10% (hardcoded)

Your Share: ₹10,000 × 30% = ₹3,000
Client Share: ₹10,000 - ₹3,000 = ₹7,000

You Pay Client: ₹7,000 × 10% = ₹700 (from your 30%)
Client Receives: ₹7,000 - ₹700 = ₹6,300
```

**On Loss**:
```
Total Loss: ₹5,000
My Share %: 30%

Your Share (earn): ₹5,000 × 30% = ₹1,500
Client Share (loss): ₹5,000 - ₹1,500 = ₹3,500

Pending Increases: ₹3,500
```

#### For "Company Clients"

**On Profit**:
```
Total Profit: ₹10,000
My Share %: 30%
Company Share %: 9% (of client's share)

Your Share: ₹10,000 × 30% = ₹3,000
Client Share: ₹10,000 - ₹3,000 = ₹7,000
Company Share: ₹7,000 × 9% = ₹630

You Pay Client: ₹7,000 - ₹630 = ₹6,370
Company Gets: ₹630
```

**On Loss**:
```
Total Loss: ₹5,000
My Share %: 30%
Company Share %: 9%

Your Share (earn): ₹5,000 × 30% = ₹1,500
Client Share (loss): ₹5,000 - ₹1,500 = ₹3,500
Company Share (earn): ₹3,500 × 9% = ₹315

Pending Increases: ₹3,500
```

---

## How Ledgers Interact

### Ledger Independence

**Exchange Balance Ledger**:
- Affected by: Funding, Profit, Loss, Balance Records
- NOT affected by: Settlements

**Pending Amount Ledger**:
- Affected by: Losses (increases), Client Payments (decreases)
- NOT affected by: Funding, Profit, Profit Payouts, Balance Records

**Transaction Ledger**:
- Contains: All transactions (immutable history)
- Used for: Calculations, Reports, Audit Trail

### Example: Ledger Interaction

**Initial State**:
- Exchange Balance: ₹10,000
- Pending: ₹0
- Transactions: 1 (FUNDING ₹10,000)

**After Profit ₹5,000**:
- Exchange Balance: ₹15,000 (increased)
- Pending: ₹0 (unchanged)
- Transactions: 2 (added PROFIT ₹5,000)

**After Loss ₹8,000**:
- Exchange Balance: ₹7,000 (decreased)
- Pending: ₹5,600 (increased - 70% of loss)
- Transactions: 3 (added LOSS ₹8,000)

**After Client Pays ₹2,000**:
- Exchange Balance: ₹7,000 (unchanged)
- Pending: ₹3,600 (decreased)
- Transactions: 4 (added SETTLEMENT ₹2,000)

**Key Insight**: Each ledger updates independently based on transaction type.

---

## Payment Processing Flow

### Client Payment Flow

```
User clicks "Record Payment"
    ↓
Form validation (amount > 0, date valid)
    ↓
Get current pending amount
    ↓
Calculate: payment_amount = min(entered_amount, pending)
    ↓
Calculate: new_pending = max(0, current_pending - payment_amount)
    ↓
Update PendingAmount record
    ↓
Create SETTLEMENT transaction:
    - client_share_amount = 0
    - your_share_amount = payment_amount
    ↓
Recalculate "Clients Owe You" list
    ↓
If pending = 0, remove client from list
    ↓
Redirect with success message
```

### Admin Profit Payment Flow

```
User clicks "Pay Client"
    ↓
Form validation (amount > 0, date valid)
    ↓
Round amount to 1 decimal
    ↓
Create SETTLEMENT transaction:
    - client_share_amount = amount
    - your_share_amount = 0
    ↓
Recalculate "You Owe Clients" list:
    - Get client profit shares
    - Get settlements already paid
    - Calculate: unpaid_profit = profit_shares - settlements_paid
    ↓
If unpaid_profit = 0, remove client from list
    ↓
Redirect with success message
```

**Key Difference**: 
- Client payment affects PendingAmount record
- Admin payment doesn't affect any stored record (calculated on-the-fly)

---

## Reporting System

### How Reports Work

**Daily Report**:
1. Get all transactions for today
2. Filter by selected client/exchange (if any)
3. Calculate aggregates:
   - Total turnover (funding)
   - Total profit
   - Total loss
   - Your profit
   - Company profit
4. Display in table and charts

**Weekly Report**:
1. Calculate date range: Last 7 days from today
2. Get all transactions in range
3. Calculate daily averages
4. Show trends over week
5. Display aggregates

**Monthly Report**:
1. Calculate date range: Same day last month to today
2. Handle month-end edge cases
3. Get all transactions in range
4. Calculate monthly aggregates
5. Show trends

**Time Travel Report**:
1. User selects "as of" date
2. Get all transactions up to that date
3. Calculate balances as of that date
4. Show snapshot of system state at that time
5. Useful for historical analysis

### Report Calculation Process

```
User selects report type and filters
    ↓
Calculate date range
    ↓
Query transactions with filters:
    - Date range
    - Client (if selected)
    - Exchange (if selected)
    - Client type (if filtered)
    ↓
Group and aggregate:
    - By date
    - By client
    - By exchange
    - By transaction type
    ↓
Calculate derived values:
    - Profit/Loss
    - Shares
    - Net amounts
    ↓
Round all amounts to 1 decimal
    ↓
Format for display
    ↓
Render template with data
```

---

## Key System Behaviors

### 1. Balance Record Creates Transaction

**Every time** you record a balance:
- ClientDailyBalance record created/updated
- **Transaction automatically created** (BALANCE_RECORD type)
- Even if same date, creates new transaction
- Transaction includes timestamp in note

### 2. Pending Only from Losses

**Pending increases** when:
- Loss transaction recorded
- Balance decreases (if balance < previous balance)

**Pending decreases** when:
- Client pays (SETTLEMENT with client_share_amount = 0)

**Pending NOT affected** by:
- Funding
- Profit
- Admin profit payments
- Balance records (unless balance decreased)

### 3. "You Owe Client" Calculation

**Calculated as**:
```
Client Profit Shares - Settlements Already Paid
```

**Where**:
- Client Profit Shares = Sum of client_share_amount from PROFIT transactions
- Settlements Paid = Sum of client_share_amount from SETTLEMENT transactions where you paid

**Updated when**:
- New PROFIT transaction
- New SETTLEMENT transaction (you pay client)

### 4. Rounding Consistency

**All amounts**:
- Input: Step 0.1 (1 decimal)
- Storage: Rounded to 1 decimal
- Display: 1 decimal
- Calculations: Rounded to 1 decimal

**Ensures**:
- No precision errors
- Consistent display
- Accurate calculations

### 5. Client Type Filtering

**Global filter** in sidebar:
- "All": Shows all clients
- "My Clients": Shows only personal clients
- "Company Clients": Shows only company clients

**Effect**:
- Filters data on all pages
- Hides navigation links accordingly
- Persists in session

---

## Common Operations Summary

### Quick Reference

**Add Funding**:
- Transaction Type: FUNDING
- Increases: Exchange Balance
- Unchanged: Pending

**Add Profit**:
- Transaction Type: PROFIT
- Increases: Exchange Balance, "You Owe Client"
- Unchanged: Pending

**Add Loss**:
- Transaction Type: LOSS
- Decreases: Exchange Balance
- Increases: Pending
- Unchanged: "You Owe Client"

**Record Balance**:
- Creates: ClientDailyBalance, Transaction (BALANCE_RECORD)
- Updates: Exchange Balance
- May Update: Pending (if balance decreased)

**Client Pays**:
- Transaction Type: SETTLEMENT (client_share_amount = 0)
- Decreases: Pending
- Unchanged: Exchange Balance, "You Owe Client"

**You Pay Client**:
- Transaction Type: SETTLEMENT (your_share_amount = 0)
- Decreases: "You Owe Client"
- Unchanged: Exchange Balance, Pending

---

## System State Tracking

### How System Tracks State

**Exchange Balance**:
- Stored in: ClientDailyBalance (latest record)
- Calculated from: Latest balance record + extra adjustment
- Fallback: Sum of funding if no balance record

**Pending Amount**:
- Stored in: PendingAmount (one record per client-exchange)
- Calculated from: Losses - Client Payments
- Updated: When loss recorded or client pays

**"You Owe Client"**:
- NOT stored (calculated on-the-fly)
- Calculated from: Profit shares - Settlements paid
- Updated: When profit recorded or you pay client

**Transaction History**:
- Stored in: Transaction (all transactions)
- Immutable: Once created, not modified
- Ordered: By date (newest first), then created_at

---

## Error Handling

### Validation Errors

**Amount Validation**:
- Must be > 0
- Must be valid decimal
- Rounded to 1 decimal

**Date Validation**:
- Must be valid date
- Cannot be future date (for some operations)

**Client-Exchange Validation**:
- Must exist
- Must belong to current user
- Must be active

### Calculation Errors

**Division by Zero**:
- Handled: Returns 0 if denominator is 0
- Example: Profit margin = 0 if turnover is 0

**Negative Amounts**:
- Prevented: Input validation ensures >= 0
- Pending: Cannot go below 0 (max(0, value))

**Rounding Errors**:
- Prevented: All calculations rounded consistently
- Ensures: Amounts match exactly for comparisons

---

## Performance Considerations

### Query Optimization

**Used Techniques**:
- `select_related()`: For foreign key relationships
- `prefetch_related()`: For reverse foreign keys
- `aggregate()`: For sums and counts
- Date filtering: To limit query scope

**Example**:
```python
transactions = Transaction.objects.filter(
    client_exchange__client__user=request.user
).select_related(
    "client_exchange",
    "client_exchange__client",
    "client_exchange__exchange"
).order_by("-date", "-created_at")[:200]
```

### Caching Opportunities

**Potential Caches**:
- System settings (rarely changes)
- Client-exchange relationships
- Recent transactions
- Calculated balances (with invalidation)

**Current Implementation**:
- No caching (calculations on-the-fly)
- Fast enough for current scale
- Can be optimized if needed

---

## Data Integrity

### Constraints

**Database Level**:
- Unique constraints on (client, exchange)
- Unique constraints on (client_exchange, date) for balances
- Foreign key constraints

**Application Level**:
- User ownership validation
- Amount validation
- Date validation
- Share percentage validation

### Transaction Safety

**Atomic Operations**:
- Transaction creation
- Pending amount updates
- Balance record creation

**Rollback on Error**:
- Django transactions ensure data consistency
- If error occurs, all changes rolled back

---

## End of Document

This document explains how the Broker Portal system works from an operational perspective. For technical implementation details, see `PROJECT_DOCUMENTATION.md`.

**Key Takeaways**:
1. System uses three separate ledgers that work independently
2. Every action creates immutable transaction records
3. All amounts rounded to 1 decimal for consistency
4. Calculations performed on-the-fly for accuracy
5. Complete audit trail maintained for all activities

---

**Last Updated**: 2025-01-15



