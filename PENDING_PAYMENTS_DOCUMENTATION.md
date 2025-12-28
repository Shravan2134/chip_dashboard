# Pending Payments Calculation Documentation

## Overview

This document explains how pending payments are calculated in the system, including all formulas, logic, and differences between **My Clients** and **Company Clients**.

## 🔑 Core Principle

**Old Balance and Current Balance define reality. Total Loss comes ONLY from those two. My Share and Company Share must ALWAYS be derived from Total Loss. Nothing else should influence share calculation.**

## 🔑 Core Principle

**Old Balance and Current Balance define reality. Total Loss comes ONLY from those two. My Share and Company Share must ALWAYS be derived from Total Loss. Nothing else should influence share calculation.**

---

## Table of Contents

1. [Key Concepts](#key-concepts)
2. [Column Definitions](#column-definitions)
3. [Calculation Logic for My Clients](#calculation-logic-for-my-clients)
4. [Calculation Logic for Company Clients](#calculation-logic-for-company-clients)
5. [Example Calculations](#example-calculations)
6. [Important Rules](#important-rules)

---

## Key Concepts

### Transaction Types

The system uses the following transaction types:
- **FUNDING**: Money you give to the client (increases exchange balance)
- **PROFIT**: Client makes profit (increases exchange balance)
- **LOSS**: Client incurs loss (decreases exchange balance)
- **SETTLEMENT**: Payment made (reduces pending amount)
- **BALANCE_RECORD**: Recorded balance snapshot (for historical tracking)

### Client Types

1. **My Clients**: Direct clients where you handle all transactions
2. **Company Clients**: Clients managed through a company, with split shares

---

## Column Definitions

### 1. Old Balance

**Definition**: The exchange balance immediately **BEFORE** any loss/profit occurred.

**Calculation Method**:
```
Old Balance = SUM of all FUNDING transactions
```

**Important Notes**:
- Old Balance is calculated from **FUNDING transactions only**
- It does NOT include BALANCE_RECORD
- It represents the total money that was put into the exchange
- For company clients, if there's a loss and total funding > current balance, we use total funding as old balance

**Formula**:
```python
Old Balance = Σ(FUNDING.amount) for all funding transactions
```

### 2. Current Balance

**Definition**: The current exchange balance as of the latest balance record.

**Calculation Method**:
```
Current Balance = Latest BALANCE_RECORD.remaining_balance
```

**Important Notes**:
- Current Balance comes from the most recent BALANCE_RECORD
- If no balance record exists, it's calculated from transactions
- This is the "real-world" balance in the exchange right now

### 3. Total Loss

**Definition**: The total 100% loss that the client has incurred.

**Calculation Formula**:
```
Total Loss = Old Balance - Current Balance
```

**Important Notes**:
- If Total Loss > 0: Client is in loss (Old Balance > Current Balance)
- If Total Loss < 0: Client is in profit (Old Balance < Current Balance)
- If Total Loss = 0: No profit, no loss (break-even)

**Example**:
- Old Balance = ₹100.0
- Current Balance = ₹10.0
- Total Loss = ₹100.0 - ₹10.0 = ₹90.0

### 4. My Share

**Definition**: Your share of the loss (the amount you earn from the client's loss).

**Calculation for My Clients**:
```
Net Loss = Old Balance - Current Balance
My Share = (Net Loss × My Share %) / 100
My Share (Final) = My Share - Settlements Received
```

**Calculation for Company Clients**:
```
My Share = Net Client Tally (from transaction calculations)
```

**Important Notes**:
- My Share is calculated from the **net loss**, not individual loss transactions
- Settlements received reduce the pending My Share amount
- My Share % is stored in `ClientExchange.my_share_pct`

### 5. Company Share

**Definition**: The company's share of the loss (only for Company Clients).

**Calculation**:
```
Company Share = Net Company Tally (from transaction calculations)
```

**Important Notes**:
- Company Share is **0** for My Clients
- For Company Clients, it's calculated from net tallies
- Company Share % is stored in `ClientExchange.company_share_pct`

### 6. Combined Share (My + Company)

**Definition**: The total share amount that needs to be paid.

**Calculation for My Clients**:
```
Combined Share = My Share (Company Share is always 0)
```

**Calculation for Company Clients**:
```
Combined Share = My Share + Company Share
```

**Example**:
- My Share = ₹0.9
- Company Share = ₹8.1
- Combined Share = ₹0.9 + ₹8.1 = ₹9.0

### 7. My Share & Company Share (%)

**Definition**: The percentage breakdown of shares.

**For My Clients**:
- Shows: **My Share %** (e.g., 10.0%)
- This is the percentage from `ClientExchange.my_share_pct`

**For Company Clients**:
- Shows: **My Share & Company Share (%)** (e.g., 10.0%)
- This represents the combined percentage (My Share % + Company Share %)

---

## Calculation Logic for My Clients

### Step-by-Step Process

1. **Check if Loss Case**:
   ```
   Old Balance > Current Balance → Loss Case
   ```

2. **Calculate Net Loss**:
   ```
   Net Loss = Old Balance - Current Balance
   ```

3. **Get My Share Percentage**:
   ```
   My Share % = ClientExchange.my_share_pct
   ```

4. **Calculate My Share from Net Loss**:
   ```
   My Share (from Net Loss) = (Net Loss × My Share %) / 100
   ```

5. **Get Settlements Received**:
   ```
   Settlements = Σ(SETTLEMENT.your_share_amount) 
                where client_share_amount = 0 
                and your_share_amount > 0
   ```

6. **Calculate Final My Share (Pending)**:
   ```
   My Share (Final) = My Share (from Net Loss) - Settlements Received
   ```

7. **Set Company Share**:
   ```
   Company Share = 0 (My Clients don't have company share)
   ```

8. **Calculate Combined Share**:
   ```
   Combined Share = My Share (Final)
   ```

### Example: My Client Calculation

**Given**:
- Old Balance = ₹100.0
- Current Balance = ₹10.0
- My Share % = 10%
- Settlements Received = ₹0.0

**Calculations**:
1. Net Loss = ₹100.0 - ₹10.0 = ₹90.0
2. My Share (from Net Loss) = (₹90.0 × 10%) / 100 = ₹9.0
3. My Share (Final) = ₹9.0 - ₹0.0 = ₹9.0
4. Company Share = ₹0.0
5. Combined Share = ₹9.0 + ₹0.0 = ₹9.0
6. Total Loss = ₹90.0

**Result**:
- Total Loss: ₹90.0
- Combined Share: ₹9.0
- My Share %: 10.0%

---

## Calculation Logic for Company Clients

### Step-by-Step Process

1. **Calculate Net Tallies from Transactions**:
   ```
   Net Client Tally = Σ(Your Share from LOSS) - Σ(Your Share from PROFIT) - Settlements
   Net Company Tally = Σ(Company Share from LOSS) - Σ(Company Share from PROFIT) - Payments
   ```

2. **Check if Loss Case**:
   ```
   Net Client Tally > 0 → Loss Case
   ```

3. **Set My Share**:
   ```
   My Share = Net Client Tally
   ```

4. **Set Company Share**:
   ```
   Company Share = Net Company Tally (if > 0, else 0)
   ```

5. **Calculate Combined Share**:
   ```
   Combined Share = My Share + Company Share
   ```

6. **Calculate Old Balance**:
   ```
   Old Balance = Total Funding (or balance after settlement + funding after)
   ```

7. **Calculate Current Balance**:
   ```
   Current Balance = Latest Balance Record
   ```

8. **Calculate Total Loss**:
   ```
   Total Loss = Old Balance - Current Balance
   ```

### Example: Company Client Calculation

**Given**:
- Old Balance = ₹100.0
- Current Balance = ₹10.0
- My Share % = 1% (your cut from company)
- Company Share % = 9% (company's cut)
- Total Share % = 10% (combined)

**Calculations**:
1. Total Loss = ₹100.0 - ₹10.0 = ₹90.0
2. Total Share = (₹90.0 × 10%) / 100 = ₹9.0
3. My Share = (₹90.0 × 1%) / 100 = ₹0.9
4. Company Share = (₹90.0 × 9%) / 100 = ₹8.1
5. Combined Share = ₹0.9 + ₹8.1 = ₹9.0

**Result**:
- Total Loss: ₹90.0
- Combined Share: ₹9.0
- My Share: ₹0.9
- Company Share: ₹8.1
- My Share & Company Share (%): 10.0%

---

## Example Calculations

### Example 1: My Client (a1 - diamond)

**Input Data**:
- Client Code: —
- Client Name: a1
- Exchange: diamond
- Old Balance: ₹100.0
- Current Balance: ₹10.0
- My Share %: 10%

**Calculations**:

1. **Total Loss**:
   ```
   Total Loss = ₹100.0 - ₹10.0 = ₹90.0
   ```

2. **My Share**:
   ```
   Net Loss = ₹90.0
   My Share = (₹90.0 × 10%) / 100 = ₹9.0
   ```

3. **Company Share**:
   ```
   Company Share = ₹0.0 (My Clients don't have company share)
   ```

4. **Combined Share**:
   ```
   Combined Share = ₹9.0 + ₹0.0 = ₹9.0
   ```

5. **Percentage**:
   ```
   My Share % = 10.0%
   ```

**Final Result**:
| Column | Value |
|--------|-------|
| Old Balance | ₹100.0 |
| Current Balance | ₹10.0 |
| Total Loss | ₹90.0 |
| Combined Share (My + Company) | ₹9.0 |
| My Share & Company Share (%) | 10.0% |

### Example 2: Company Client

**Input Data**:
- Old Balance: ₹200.0
- Current Balance: ₹20.0
- My Share %: 1%
- Company Share %: 9%
- Total Share %: 10%

**Calculations**:

1. **Total Loss**:
   ```
   Total Loss = ₹200.0 - ₹20.0 = ₹180.0
   ```

2. **Total Share**:
   ```
   Total Share = (₹180.0 × 10%) / 100 = ₹18.0
   ```

3. **My Share**:
   ```
   My Share = (₹180.0 × 1%) / 100 = ₹1.8
   ```

4. **Company Share**:
   ```
   Company Share = (₹180.0 × 9%) / 100 = ₹16.2
   ```

5. **Combined Share**:
   ```
   Combined Share = ₹1.8 + ₹16.2 = ₹18.0
   ```

**Final Result**:
| Column | Value |
|--------|-------|
| Old Balance | ₹200.0 |
| Current Balance | ₹20.0 |
| Total Loss | ₹180.0 |
| Combined Share (My + Company) | ₹18.0 |
| My Share & Company Share (%) | 10.0% |

---

## Important Rules

### Rule 1: Old Balance = Current Balance → No Pending

**If Old Balance equals Current Balance, then:**
- Total Loss = 0
- My Share = 0
- Company Share = 0
- Combined Share = 0
- **Client is NOT shown in pending payments**

This is a **hard rule** with no exceptions.

### Rule 2: Profit Does NOT Reduce Pending

**For My Clients:**
- Profit transactions do NOT reduce pending amount
- Only LOSS transactions and SETTLEMENT transactions affect pending
- Pending = My Share from Net Loss - Settlements Received

### Rule 3: Balance Records Do NOT Affect Pending

- BALANCE_RECORD transactions are for tracking only
- They do NOT affect pending calculations
- Only FUNDING, LOSS, PROFIT, and SETTLEMENT affect pending

### Rule 4: Funding Does NOT Affect Pending

- FUNDING transactions increase exchange balance
- They are used to calculate Old Balance
- But they do NOT directly affect pending amount

### Rule 5: Settlements Reduce Pending

**For My Clients:**
- When client pays you (SETTLEMENT with `client_share_amount = 0` and `your_share_amount > 0`)
- This reduces the pending amount
- Final Pending = My Share - Settlements Received

### Rule 6: Company Clients Use Net Tallies

**For Company Clients:**
- Pending is calculated from net tallies (not net loss)
- Net Tally = Σ(Loss Shares) - Σ(Profit Shares) - Settlements
- This accounts for both losses and profits

### Rule 7: Combined Share Cannot Exceed Total Loss

**Validation:**
- Combined Share ≤ Total Loss × (Total Share % / 100)
- In the form, users cannot enter amount greater than Combined Share
- Amount to Pay ≤ Combined Share

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    PENDING PAYMENTS CALCULATION              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────┐
        │   Get Client Exchange Data        │
        │   - Old Balance (from Funding)   │
        │   - Current Balance (from Record) │
        │   - My Share %                    │
        │   - Company Share %               │
        └─────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────┐
        │   Calculate Total Loss              │
        │   Total Loss = Old - Current        │
        └─────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────┐
        │   Check Client Type                 │
        │   - My Client?                      │
        │   - Company Client?                 │
        └─────────────────────────────────────┘
                              │
                ┌─────────────┴─────────────┐
                ▼                           ▼
    ┌───────────────────┐      ┌──────────────────────┐
    │   MY CLIENT       │      │  COMPANY CLIENT      │
    │                   │      │                      │
    │ My Share =        │      │ My Share =           │
    │ Net Loss ×        │      │ Net Client Tally     │
    │ My Share %        │      │                      │
    │                   │      │ Company Share =      │
    │ Company Share = 0 │      │ Net Company Tally    │
    │                   │      │                      │
    │ Combined =        │      │ Combined =           │
    │ My Share          │      │ My + Company         │
    └───────────────────┘      └──────────────────────┘
                │                           │
                └─────────────┬─────────────┘
                              ▼
        ┌─────────────────────────────────────┐
        │   Calculate Final Values            │
        │   - Total Loss                      │
        │   - Combined Share                  │
        │   - My Share %                      │
        │   - Company Share %                 │
        └─────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────┐
        │   Display in Pending Payments UI   │
        └─────────────────────────────────────┘
```

---

## Summary

### For My Clients:
- **Old Balance**: Sum of all FUNDING transactions
- **Current Balance**: Latest BALANCE_RECORD
- **Total Loss**: Old Balance - Current Balance
- **My Share**: (Total Loss × My Share %) / 100 - Settlements
- **Company Share**: Always 0
- **Combined Share**: My Share (same as My Share)

### For Company Clients:
- **Old Balance**: Sum of all FUNDING transactions (or total funding if > current balance)
- **Current Balance**: Latest BALANCE_RECORD
- **Total Loss**: Old Balance - Current Balance
- **My Share**: Net Client Tally (from transaction calculations)
- **Company Share**: Net Company Tally (from transaction calculations)
- **Combined Share**: My Share + Company Share

### Key Differences:
1. **My Clients**: Calculate from Net Loss directly
2. **Company Clients**: Calculate from Net Tallies (accounts for both losses and profits)
3. **My Clients**: No company share
4. **Company Clients**: Split share (1% you, 9% company)

---

## Technical Implementation

### Database Fields Used:
- `ClientExchange.my_share_pct`: Your share percentage
- `ClientExchange.company_share_pct`: Company share percentage
- `ClientExchange.client.is_company_client`: Client type flag
- `Transaction.amount`: Transaction amount
- `Transaction.transaction_type`: Type of transaction
- `Transaction.your_share_amount`: Your share from transaction
- `Transaction.company_share_amount`: Company share from transaction
- `ClientDailyBalance.remaining_balance`: Current balance record

### Key Functions:
- `get_old_balance_after_settlement()`: Calculates old balance from funding
- `calculate_net_tallies_from_transactions()`: Calculates net tallies for company clients
- `calculate_client_profit_loss()`: Gets current balance and profit/loss data

---

**Document Version**: 1.0  
**Last Updated**: December 2024  
**Author**: System Documentation

