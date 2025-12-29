# Payments System Documentation

## Overview

This document provides comprehensive documentation for the entire payments system, including pending payments, old balances, total loss/profit calculations, combined shares, and CSV reporting.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Key Concepts](#key-concepts)
3. [Old Balance Calculation](#old-balance-calculation)
4. [Current Balance Calculation](#current-balance-calculation)
5. [Total Loss / Total Profit Calculation](#total-loss--total-profit-calculation)
6. [My Share & Company Share Calculation](#my-share--company-share-calculation)
7. [Pending Payments Logic](#pending-payments-logic)
8. [CSV Report Structure](#csv-report-structure)
9. [Example Calculations](#example-calculations)
10. [Business Rules](#business-rules)

---

## System Overview

The payments system tracks financial transactions between you (admin) and your clients across different exchanges. It calculates:

- **Old Balance**: The exchange balance before any loss/profit occurred
- **Current Balance**: The current exchange balance
- **Total Loss/Profit**: The difference between old and current balance
- **My Share**: Your percentage share of the loss/profit
- **Company Share**: Company's percentage share (for company clients only)
- **Combined Share**: Total share amount (My Share + Company Share)
- **Pending Amount**: Amount still owed after settlements

---

## Key Concepts

### Transaction Types

1. **FUNDING**: Money you give to the client (increases exchange balance)
2. **PROFIT**: Client makes profit (increases exchange balance)
3. **LOSS**: Client incurs loss (decreases exchange balance)
4. **SETTLEMENT**: Payment made (reduces pending amount)
5. **BALANCE_RECORD**: Recorded balance snapshot (for historical tracking)

### Client Types

1. **My Clients**: Direct clients where you handle all transactions
   - Only "My Share" applies
   - Company Share = 0

2. **Company Clients**: Clients managed through a company
   - Both "My Share" and "Company Share" apply
   - Shares are split (e.g., 1% you, 9% company)

---

## Old Balance Calculation

### Definition

**Old Balance** = The exchange balance immediately **BEFORE** any loss/profit occurred.

### Calculation Method

```
Old Balance = SUM of all FUNDING transactions
```

### Important Notes

- Old Balance is calculated from **FUNDING transactions only**
- It does NOT include BALANCE_RECORD
- It represents the total money that was put into the exchange
- For company clients, if total funding > current balance, we use total funding as old balance

### Formula

```python
Old Balance = Σ(FUNDING.amount) for all funding transactions
```

### Example

- Funding Transaction 1: ₹50.0
- Funding Transaction 2: ₹50.0
- **Old Balance = ₹100.0**

---

## Current Balance Calculation

### Definition

**Current Balance** = The current exchange balance as of the latest balance record.

### Calculation Method

```
Current Balance = Latest BALANCE_RECORD.remaining_balance
```

### Important Notes

- Current Balance comes from the most recent BALANCE_RECORD
- If no balance record exists, it's calculated from transactions
- This is the "real-world" balance in the exchange right now

### Example

- Latest Balance Record: ₹10.0
- **Current Balance = ₹10.0**

---

## Total Loss / Total Profit Calculation

### Definition

**Total Loss/Profit** = The total 100% loss or profit that the client has incurred.

### Calculation Formula

```
Total Loss/Profit = Old Balance - Current Balance
```

### Interpretation

- **Total Loss > 0**: Client is in LOSS (Old Balance > Current Balance)
- **Total Profit < 0**: Client is in PROFIT (Old Balance < Current Balance)
- **Total Loss/Profit = 0**: No profit, no loss (break-even)

### Example 1: Loss Case

- Old Balance = ₹100.0
- Current Balance = ₹10.0
- **Total Loss = ₹100.0 - ₹10.0 = ₹90.0**

### Example 2: Profit Case

- Old Balance = ₹100.0
- Current Balance = ₹200.0
- **Total Profit = ₹100.0 - ₹200.0 = -₹100.0** (negative indicates profit)

---

## My Share & Company Share Calculation

### Core Principle

**My Share and Company Share must ALWAYS be derived from Total Loss/Profit. Nothing else should influence share calculation.**

### For My Clients

#### Formula

```
If Total Loss > 0:
    My Share = Total Loss × My Share %
    Company Share = 0
Else:
    My Share = 0
    Company Share = 0
```

#### Example

- Old Balance = ₹100.0
- Current Balance = ₹10.0
- Total Loss = ₹90.0
- My Share % = 10%

**Calculation:**
- My Share = ₹90.0 × 10% = ₹9.0
- Company Share = ₹0.0
- Combined Share = ₹9.0

### For Company Clients

#### Formula

```
If Total Loss > 0:
    My Share = Total Loss × My Share %
    Company Share = Total Loss × Company Share %
Else:
    My Share = 0
    Company Share = 0
```

#### Example

- Old Balance = ₹100.0
- Current Balance = ₹10.0
- Total Loss = ₹90.0
- My Share % = 1%
- Company Share % = 9%

**Calculation:**
- My Share = ₹90.0 × 1% = ₹0.9
- Company Share = ₹90.0 × 9% = ₹8.1
- Combined Share = ₹0.9 + ₹8.1 = ₹9.0

---

## Pending Payments Logic

### Definition

**Pending Amount** = The amount still owed after settlements have been deducted.

### Calculation Formula

```
Pending Amount = Calculated Share - Settlements Received
```

### Settlement Types

1. **Client Pays You** (for losses):
   - SETTLEMENT with `client_share_amount = 0` and `your_share_amount > 0`
   - Reduces your pending amount

2. **You Pay Client** (for profits):
   - SETTLEMENT with `client_share_amount > 0` and `your_share_amount = 0`
   - Reduces amount you owe client

### For My Clients

```
My Share Pending = My Share - Settlements Received
Company Share Pending = 0
Combined Share Pending = My Share Pending
```

### For Company Clients

```
My Share Pending = My Share - My Share Settlements
Company Share Pending = Company Share - Company Share Settlements
Combined Share Pending = My Share Pending + Company Share Pending
```

### Example

**Initial Calculation:**
- My Share = ₹9.0
- Settlements Received = ₹2.0

**Final Pending:**
- My Share Pending = ₹9.0 - ₹2.0 = ₹7.0

---

## CSV Report Structure

### Report Header

The CSV report includes the following columns (in order):

1. **REPORT DATE**: Current date when the report is generated
2. **CLIENT CODE**: Unique client identifier
3. **CLIENT NAME**: Name of the client
4. **EXCHANGE**: Exchange name
5. **OLD BALANCE**: Balance before loss/profit
6. **CURRENT BALANCE**: Current exchange balance
7. **TOTAL LOSS**: Total loss (Old Balance - Current Balance)
8. **MY SHARE (AMOUNT)**: Your share amount
9. **MY SHARE (%)**: Your share percentage
10. **COMPANY SHARE (AMOUNT)**: Company share amount (only for company clients)
11. **COMPANY SHARE (%)**: Company share percentage (only for company clients)
12. **COMBINED SHARE (MY + COMPANY)**: Total share amount
13. **MY SHARE & COMPANY SHARE (%)**: Combined percentage

### CSV Format Details

- **Headers**: All uppercase for better visibility
- **Date Format**: YYYY-MM-DD
- **Currency**: Indian Rupees (₹)
- **Decimal Places**: 1 decimal place for amounts, 2 decimal places for percentages

### CSV Report Sections

#### For My Clients

When "Combine My Share & Company Share" is **NOT** ticked:
- Shows: My Share Amount, My Share %, Combined Share
- Column header for percentage: "My Share %"

When "Combine My Share & Company Share" is **ticked**:
- Shows: Combined Share (My + Company), My Share %
- Column header for percentage: "My Share %"

#### For Company Clients

When "Combine My Share & Company Share" is **NOT** ticked:
- Shows: My Share Amount, My Share %, Company Share Amount, Company Share %, Combined Share
- Column header for percentage: "My Share & Company Share (%)"

When "Combine My Share & Company Share" is **ticked**:
- Shows: Combined Share (My + Company), My Share & Company Share (%)
- Hides individual My Share and Company Share columns

### CSV Example Output

```csv
REPORT DATE,CLIENT CODE,CLIENT NAME,EXCHANGE,OLD BALANCE,CURRENT BALANCE,TOTAL LOSS,COMBINED SHARE (MY + COMPANY),MY SHARE & COMPANY SHARE (%)
2024-12-28,—,a1,diamond,100.0,10.0,90.0,9.0,10.0
```

---

## Example Calculations

### Example 1: My Client - Loss Case

**Given:**
- Client: a1
- Exchange: diamond
- Old Balance: ₹100.0
- Current Balance: ₹10.0
- My Share %: 10%
- Settlements Received: ₹0.0

**Step 1: Calculate Total Loss**
```
Total Loss = ₹100.0 - ₹10.0 = ₹90.0
```

**Step 2: Calculate My Share**
```
My Share = ₹90.0 × 10% = ₹9.0
```

**Step 3: Calculate Pending**
```
Pending = ₹9.0 - ₹0.0 = ₹9.0
```

**Result:**
- Total Loss: ₹90.0
- My Share: ₹9.0
- Company Share: ₹0.0
- Combined Share: ₹9.0
- Pending Amount: ₹9.0

### Example 2: Company Client - Loss Case

**Given:**
- Old Balance: ₹100.0
- Current Balance: ₹10.0
- My Share %: 1%
- Company Share %: 9%
- Settlements Received: ₹0.0

**Step 1: Calculate Total Loss**
```
Total Loss = ₹100.0 - ₹10.0 = ₹90.0
```

**Step 2: Calculate Shares**
```
My Share = ₹90.0 × 1% = ₹0.9
Company Share = ₹90.0 × 9% = ₹8.1
Combined Share = ₹0.9 + ₹8.1 = ₹9.0
```

**Step 3: Calculate Pending**
```
My Share Pending = ₹0.9 - ₹0.0 = ₹0.9
Company Share Pending = ₹8.1 - ₹0.0 = ₹8.1
Combined Share Pending = ₹0.9 + ₹8.1 = ₹9.0
```

**Result:**
- Total Loss: ₹90.0
- My Share: ₹0.9
- Company Share: ₹8.1
- Combined Share: ₹9.0
- Pending Amount: ₹9.0

### Example 3: My Client - Profit Case

**Given:**
- Old Balance: ₹100.0
- Current Balance: ₹200.0
- My Share %: 10%
- Settlements Paid: ₹0.0

**Step 1: Calculate Total Profit**
```
Total Profit = ₹100.0 - ₹200.0 = -₹100.0 (negative = profit)
```

**Step 2: Calculate My Share**
```
My Share = ₹100.0 × 10% = ₹10.0 (you owe this to client)
```

**Step 3: Calculate Pending**
```
Pending = ₹10.0 - ₹0.0 = ₹10.0 (amount you owe client)
```

**Result:**
- Total Profit: ₹100.0
- My Share: ₹10.0 (you owe)
- Company Share: ₹0.0
- Combined Share: ₹10.0
- Pending Amount: ₹10.0 (you owe client)

---

## Business Rules

### Rule 1: Old Balance = Current Balance → No Pending

**If Old Balance equals Current Balance:**
- Total Loss = 0
- My Share = 0
- Company Share = 0
- Combined Share = 0
- **Client is NOT shown in pending payments**

This is a **hard rule** with no exceptions.

### Rule 2: Shares are Stateless

**Shares are recalculated fresh from Total Loss every time.**
- ❌ WRONG: `My Share = previous_pending + new_loss_share`
- ❌ WRONG: `Company Share = net transaction tally`
- ✅ CORRECT: `My Share = Total Loss × My Share %`
- ✅ CORRECT: `Company Share = Total Loss × Company Share %`

### Rule 3: Total Loss is the ONLY Source

**Total Loss comes ONLY from Old Balance and Current Balance.**
- ❌ Do NOT mix past losses
- ❌ Do NOT mix past profits
- ❌ Do NOT mix unsettled pending
- ❌ Do NOT mix transaction tallies
- ✅ ONLY use: `Total Loss = Old Balance - Current Balance`

### Rule 4: Settlements Reduce Pending

**For My Clients:**
- When client pays you (SETTLEMENT with `client_share_amount = 0` and `your_share_amount > 0`)
- This reduces the pending amount
- Final Pending = My Share - Settlements Received

**For Company Clients:**
- My Share Pending = My Share - My Share Settlements
- Company Share Pending = Company Share - Company Share Settlements

### Rule 5: Combined Share Cannot Exceed Total Loss

**Validation:**
- Combined Share ≤ Total Loss × (Total Share % / 100)
- In the form, users cannot enter amount greater than Combined Share
- Amount to Pay ≤ Combined Share

### Rule 6: Same Logic for Both Client Types

**The only difference:**
- My Clients: One percentage (My Share %)
- Company Clients: Two percentages (My Share % + Company Share %)

**Everything else is the same:**
- Calculate Total Loss from Old Balance and Current Balance
- Calculate Shares from Total Loss
- Calculate Pending = Share - Settlements

### Rule 7: CSV Report Always Includes Report Date

**Every CSV row includes:**
- Report Date as the first column
- Current date in YYYY-MM-DD format
- All headers in uppercase for better visibility

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    PAYMENTS SYSTEM FLOW                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────┐
        │   Get Client Exchange Data          │
        │   - Old Balance (from Funding)     │
        │   - Current Balance (from Record)  │
        │   - My Share %                      │
        │   - Company Share %                │
        └─────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────┐
        │   Calculate Total Loss/Profit       │
        │   Total Loss = Old - Current        │
        └─────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────┐
        │   Check Client Type                  │
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
    │ Total Loss ×      │      │ Total Loss ×         │
    │ My Share %        │      │ My Share %           │
    │                   │      │                      │
    │ Company Share = 0 │      │ Company Share =      │
    │                   │      │ Total Loss ×         │
    │ Combined =        │      │ Company Share %      │
    │ My Share          │      │                      │
    │                   │      │ Combined =           │
    │                   │      │ My + Company         │
    └───────────────────┘      └──────────────────────┘
                │                           │
                └─────────────┬─────────────┘
                              ▼
        ┌─────────────────────────────────────┐
        │   Calculate Pending                 │
        │   Pending = Share - Settlements     │
        └─────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────┐
        │   Generate CSV Report              │
        │   - Include Report Date            │
        │   - Format Headers (Uppercase)     │
        │   - Include All Columns            │
        └─────────────────────────────────────┘
```

---

## Summary

### Core Principle

**Old Balance and Current Balance define reality. Total Loss comes ONLY from those two. My Share and Company Share must ALWAYS be derived from Total Loss. Nothing else should influence share calculation.**

### Key Formulas

1. **Old Balance**: `SUM of all FUNDING transactions`
2. **Current Balance**: `Latest BALANCE_RECORD.remaining_balance`
3. **Total Loss**: `Old Balance - Current Balance`
4. **My Share**: `Total Loss × My Share %`
5. **Company Share**: `Total Loss × Company Share %` (for company clients)
6. **Combined Share**: `My Share + Company Share`
7. **Pending**: `Share - Settlements`

### For My Clients

- Old Balance: Sum of all FUNDING transactions
- Current Balance: Latest BALANCE_RECORD
- Total Loss: Old Balance - Current Balance
- My Share: Total Loss × My Share % - Settlements
- Company Share: Always 0
- Combined Share: My Share (same as My Share)

### For Company Clients

- Old Balance: Sum of all FUNDING transactions (or total funding if > current balance)
- Current Balance: Latest BALANCE_RECORD
- Total Loss: Old Balance - Current Balance
- My Share: Total Loss × My Share % - Settlements
- Company Share: Total Loss × Company Share % - Company Settlements
- Combined Share: My Share + Company Share

### CSV Report

- Always includes Report Date as first column
- Headers in uppercase for better visibility
- Dynamic columns based on client type and "Combine Shares" option
- Includes all relevant financial data

---

**Document Version**: 1.0  
**Last Updated**: December 2024  
**Status**: Complete Documentation

