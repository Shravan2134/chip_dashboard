# 🗄️ Database Design Documentation

## 📋 Table of Contents
1. [Overview](#overview)
2. [Entity Relationship Diagram](#entity-relationship-diagram)
3. [Core Tables](#core-tables)
4. [Financial Tables](#financial-tables)
5. [Reporting Tables](#reporting-tables)
6. [System Tables](#system-tables)
7. [Indexes & Performance](#indexes--performance)
8. [Constraints & Validations](#constraints--validations)
9. [Relationships](#relationships)
10. [Data Types & Precision](#data-types--precision)

---

## 🎯 Overview

This database design supports a **Pending Payments & Profit System** that tracks:
- Client funding and exchange balances
- Profit/loss calculations with share percentages
- Settlement tracking and partial payments
- Company vs. personal client differentiation
- Time-travel reporting capabilities

**Key Design Principles:**
- **Single Source of Truth**: Transactions are the authoritative financial record
- **Denormalization**: Cached fields for performance (updated via signals)
- **Audit Trail**: All financial activities timestamped
- **Flexibility**: Support for different share percentages per client-exchange

---

## 🔗 Entity Relationship Diagram

```
┌─────────────┐
│    User     │ (Django Auth)
└──────┬──────┘
       │
       │ 1:N
       ▼
┌─────────────┐
│   Client    │
│─────────────│
│ id (PK)     │
│ user_id (FK)│
│ name        │
│ code        │
│ is_company  │
│ security_dep│
└──────┬──────┘
       │
       │ 1:N
       ▼
┌─────────────────┐      N:1    ┌─────────────┐
│ ClientExchange  │◄───────────│  Exchange   │
│─────────────────│            │─────────────│
│ id (PK)         │            │ id (PK)     │
│ client_id (FK)  │            │ name        │
│ exchange_id (FK)│            │ code        │
│ my_share_pct    │            │ is_active   │
│ company_share_pct│           └─────────────┘
│ cached_* fields │
└──────┬──────────┘
       │
       │ 1:N
       ▼
┌─────────────────┐
│  Transaction    │
│─────────────────│
│ id (PK)         │
│ client_exchange │
│ date            │
│ transaction_type│
│ amount          │
│ your_share_amt  │
│ company_share_amt│
└─────────────────┘
       │
       │ 1:N
       ▼
┌─────────────────┐
│ClientDailyBalance│
│─────────────────│
│ id (PK)         │
│ client_exchange │
│ date            │
│ remaining_balance│
│ extra_adjustment│
└─────────────────┘

┌─────────────────┐
│DailyBalanceSnap │
│─────────────────│
│ id (PK)         │
│ client_exchange │
│ date            │
│ total_funding   │
│ total_profit    │
│ total_loss      │
└─────────────────┘

┌─────────────────┐
│ OutstandingAmount│ (My Clients Only)
│─────────────────│
│ id (PK)         │
│ client_exchange │ (OneToOne)
│ outstanding_amt │
└─────────────────┘

┌─────────────────┐
│  TallyLedger    │ (Company Clients Only)
│─────────────────│
│ id (PK)         │
│ client_exchange │ (OneToOne)
│ client_owes_you │
│ company_owes_you│
│ you_owe_client  │
│ you_owe_company │
└─────────────────┘

┌─────────────────┐
│ SystemSettings  │ (Singleton)
│─────────────────│
│ id (PK) = 1     │
│ weekly_report_day│
│ admin_loss_share│
│ company_loss_share│
└─────────────────┘
```

---

## 📊 Core Tables

### **1. Client**
**Purpose:** Represents end clients (personal or company clients)

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | BigAutoField | PK | Primary key |
| `user_id` | ForeignKey(User) | FK, NULL | Owner of this client |
| `name` | CharField(255) | NOT NULL | Client name |
| `code` | CharField(50) | NULL, UNIQUE per user | Client code |
| `referred_by` | CharField(255) | NULL | Referrer name |
| `is_active` | Boolean | DEFAULT True | Active status |
| `is_company_client` | Boolean | DEFAULT False | Company vs. personal |
| `security_deposit` | Decimal(14,2) | DEFAULT 0 | One-time deposit (company only) |
| `security_deposit_paid_date` | Date | NULL | Deposit payment date |
| `created_at` | DateTime | AUTO | Creation timestamp |
| `updated_at` | DateTime | AUTO | Last update timestamp |

**Unique Constraints:**
- `(user, code)` - Code must be unique per user

**Indexes:**
- `(user, is_active)`
- `(user, is_company_client)`
- `(is_company_client, is_active)`
- `(code)`

---

### **2. Exchange**
**Purpose:** Standalone exchanges (A, B, C, D, etc.)

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | BigAutoField | PK | Primary key |
| `name` | CharField(255) | UNIQUE, NOT NULL | Exchange name |
| `code` | CharField(50) | UNIQUE, NULL | Exchange code |
| `is_active` | Boolean | DEFAULT True | Active status |
| `created_at` | DateTime | AUTO | Creation timestamp |
| `updated_at` | DateTime | AUTO | Last update timestamp |

**Unique Constraints:**
- `name` - Exchange name must be unique
- `code` - Exchange code must be unique (if provided)

---

### **3. ClientExchange**
**Purpose:** Links Client to Exchange with specific share percentages

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | BigAutoField | PK | Primary key |
| `client_id` | ForeignKey(Client) | FK, NOT NULL | Client reference |
| `exchange_id` | ForeignKey(Exchange) | FK, NOT NULL | Exchange reference |
| `my_share_pct` | Decimal(5,2) | NOT NULL | Your share percentage |
| `company_share_pct` | Decimal(5,2) | NOT NULL | Company share percentage |
| `is_active` | Boolean | DEFAULT True | Active status |
| `cached_current_balance` | Decimal(14,2) | DEFAULT 0 | Cached CB (updated via signals) |
| `cached_old_balance` | Decimal(14,2) | DEFAULT 0 | Cached OB (updated via signals) |
| `cached_total_funding` | Decimal(14,2) | DEFAULT 0 | Cached total funding |
| `balance_last_updated` | DateTime | NULL | Cache update timestamp |
| `created_at` | DateTime | AUTO | Creation timestamp |
| `updated_at` | DateTime | AUTO | Last update timestamp |

**Unique Constraints:**
- `(client, exchange)` - One relationship per client-exchange pair

**Indexes:**
- `(client, is_active)`
- `(exchange, is_active)`
- `(is_active)`

**Business Rules:**
- `company_share_pct < 100` (validation)
- Cached fields updated automatically via Django signals
- `cached_old_balance` bootstrapped on first FUNDING transaction

---

## 💰 Financial Tables

### **4. Transaction**
**Purpose:** Core source-of-truth for all financial activities

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | BigAutoField | PK | Primary key |
| `client_exchange_id` | ForeignKey(ClientExchange) | FK, NOT NULL | Client-exchange reference |
| `date` | Date | NOT NULL | Transaction date |
| `transaction_type` | CharField(20) | NOT NULL | Type: FUNDING, PROFIT, LOSS, SETTLEMENT, BALANCE_RECORD |
| `amount` | Decimal(14,2) | NOT NULL | Positive amount |
| `client_share_amount` | Decimal(14,2) | DEFAULT 0 | Client's share (denormalized) |
| `your_share_amount` | Decimal(14,2) | DEFAULT 0 | Your share (denormalized) |
| `company_share_amount` | Decimal(14,2) | DEFAULT 0 | Company share (denormalized) |
| `note` | TextField | NULL | Optional note |
| `created_at` | DateTime | AUTO | Creation timestamp |
| `updated_at` | DateTime | AUTO | Last update timestamp |

**Transaction Types:**
- `FUNDING` - You give money to client
- `PROFIT` - Client profit (AUDIT ONLY, not used in calculations)
- `LOSS` - Client loss (AUDIT ONLY, not used in calculations)
- `SETTLEMENT` - Payment/payout settlement
- `BALANCE_RECORD` - Exchange balance record

**Indexes:**
- `(client_exchange, transaction_type)`
- `(client_exchange, date)`
- `(transaction_type, date)`
- `(date)`
- `(client_exchange, transaction_type, date)` - Composite

**Ordering:**
- `-date, -created_at` (newest first)

**Business Rules:**
- `amount > 0` (always positive)
- Share amounts denormalized for snapshot consistency
- `LOSS`/`PROFIT` rows are AUDIT ONLY, never used in calculations

---

### **5. ClientDailyBalance**
**Purpose:** Manual daily balance records (source of truth for CB)

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | BigAutoField | PK | Primary key |
| `client_exchange_id` | ForeignKey(ClientExchange) | FK, NULL | Client-exchange reference |
| `client_id` | ForeignKey(Client) | FK, NULL | Legacy client reference |
| `date` | Date | NOT NULL | Balance date |
| `remaining_balance` | Decimal(14,2) | NOT NULL | Exchange balance |
| `extra_adjustment` | Decimal(14,2) | DEFAULT 0 | Extra adjustment amount |
| `note` | TextField | NULL | Optional note |
| `created_at` | DateTime | AUTO | Creation timestamp |
| `updated_at` | DateTime | AUTO | Last update timestamp |

**Unique Constraints:**
- `(client_exchange, date)` - One balance per client-exchange per date
- `(client, date)` - Legacy support

**Indexes:**
- `(client_exchange, date)`
- `(client, date)` - Legacy
- `(date)`

**Ordering:**
- `-date, client_exchange__exchange__name`

**Business Rules:**
- Latest record (by date DESC, id DESC) = Current Balance (CB)
- Records must be strictly increasing by (date, id)
- Backdated inserts trigger full recompute OR are forbidden

---

## 📈 Reporting Tables

### **6. DailyBalanceSnapshot**
**Purpose:** Pre-computed daily snapshots for time-travel reporting

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | BigAutoField | PK | Primary key |
| `client_exchange_id` | ForeignKey(ClientExchange) | FK, NOT NULL | Client-exchange reference |
| `date` | Date | NOT NULL | Snapshot date |
| `total_funding` | Decimal(14,2) | DEFAULT 0 | Cumulative funding up to date |
| `total_profit` | Decimal(14,2) | DEFAULT 0 | Cumulative profit up to date |
| `total_loss` | Decimal(14,2) | DEFAULT 0 | Cumulative loss up to date |
| `client_net_balance` | Decimal(14,2) | DEFAULT 0 | Client net balance |
| `you_net_balance` | Decimal(14,2) | DEFAULT 0 | Your net balance |
| `company_net_profit` | Decimal(14,2) | DEFAULT 0 | Company net profit |
| `pending_client_owes_you` | Decimal(14,2) | DEFAULT 0 | Pending client owes |
| `pending_you_owe_client` | Decimal(14,2) | DEFAULT 0 | Pending you owe |
| `created_at` | DateTime | AUTO | Creation timestamp |
| `updated_at` | DateTime | AUTO | Last update timestamp |

**Unique Constraints:**
- `(client_exchange, date)` - One snapshot per client-exchange per date

**Indexes:**
- `(client_exchange, date)`
- `(date)`

**Ordering:**
- `-date` (newest first)

**Business Rules:**
- All fields are cumulative up to and including `date`
- Used for fast time-travel reporting without recomputing aggregates

---

### **7. CompanyShareRecord**
**Purpose:** Denormalized company share records for transparency

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | BigAutoField | PK | Primary key |
| `client_exchange_id` | ForeignKey(ClientExchange) | FK, NOT NULL | Client-exchange reference |
| `transaction_id` | ForeignKey(Transaction) | FK, NOT NULL | Transaction reference |
| `date` | Date | NOT NULL | Record date |
| `company_amount` | Decimal(14,2) | NOT NULL | Company share amount |
| `created_at` | DateTime | AUTO | Creation timestamp |
| `updated_at` | DateTime | AUTO | Last update timestamp |

**Business Rules:**
- Tracks company share amounts for reporting and transparency

---

## 🏦 Ledger Tables

### **8. OutstandingAmount**
**Purpose:** Netted ledger for MY CLIENTS only

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | BigAutoField | PK | Primary key |
| `client_exchange_id` | OneToOne(ClientExchange) | UNIQUE, NOT NULL | Client-exchange reference |
| `outstanding_amount` | Decimal(14,2) | DEFAULT 0 | Net outstanding (Your Share) |
| `note` | TextField | NULL | Optional note |
| `created_at` | DateTime | AUTO | Creation timestamp |
| `updated_at` | DateTime | AUTO | Last update timestamp |

**Business Rules:**
- **ONLY for My Clients** (not company clients)
- Positive = Client owes you (unpaid loss share)
- Negative = You owe client (auto-settles and resets to 0)
- Zero = All settled
- One ledger per client-exchange (OneToOne)

---

### **9. TallyLedger**
**Purpose:** Separate ledger for COMPANY CLIENTS only

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | BigAutoField | PK | Primary key |
| `client_exchange_id` | OneToOne(ClientExchange) | UNIQUE, NOT NULL | Client-exchange reference |
| `client_owes_you` | Decimal(14,2) | DEFAULT 0 | Your direct share from losses |
| `company_owes_you` | Decimal(14,2) | DEFAULT 0 | Company's portion from losses |
| `you_owe_client` | Decimal(14,2) | DEFAULT 0 | Your direct share from profits |
| `you_owe_company` | Decimal(14,2) | DEFAULT 0 | Company's portion from profits |
| `note` | TextField | NULL | Optional note |
| `created_at` | DateTime | AUTO | Creation timestamp |
| `updated_at` | DateTime | AUTO | Last update timestamp |

**Computed Properties:**
- `net_client_payable = you_owe_client - client_owes_you`
- `net_company_payable = you_owe_company - company_owes_you`

**Business Rules:**
- **ONLY for Company Clients** (not my clients)
- Separate tracking of who owes whom
- Nothing paid immediately - only tallied
- One ledger per client-exchange (OneToOne)

---

### **10. PendingAmount**
**Purpose:** Separate ledger for unpaid losses (legacy/alternative approach)

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | BigAutoField | PK | Primary key |
| `client_exchange_id` | ForeignKey(ClientExchange) | FK, UNIQUE, NOT NULL | Client-exchange reference |
| `pending_amount` | Decimal(14,2) | DEFAULT 0 | Total pending (unpaid losses) |
| `note` | TextField | NULL | Optional note |
| `created_at` | DateTime | AUTO | Creation timestamp |
| `updated_at` | DateTime | AUTO | Last update timestamp |

**Unique Constraints:**
- `(client_exchange)` - One pending record per client-exchange

**Business Rules:**
- Created only from losses
- Reduced only when client pays
- NOT affected by funding, profit, or profit payout

---

## ⚙️ System Tables

### **11. SystemSettings**
**Purpose:** System-wide configuration (Singleton pattern)

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | IntegerField | PK = 1 | Primary key (always 1) |
| `weekly_report_day` | IntegerField | DEFAULT 0 | Day of week (0=Monday, 6=Sunday) |
| `auto_generate_weekly_reports` | Boolean | DEFAULT False | Auto-generate reports |
| `admin_loss_share_pct` | Decimal(5,2) | DEFAULT 5.00 | Admin share of loss |
| `company_loss_share_pct` | Decimal(5,2) | DEFAULT 10.00 | Company share of loss |
| `admin_profit_share_pct` | Decimal(5,2) | DEFAULT 5.00 | Admin share of profit |
| `company_profit_share_pct` | Decimal(5,2) | DEFAULT 10.00 | Company share of profit |

**Business Rules:**
- Singleton pattern - only one record exists (pk=1)
- Auto-enforced in `save()` method
- Load via `SystemSettings.load()`

---

## 🔍 Indexes & Performance

### **Composite Indexes (Most Common Queries)**

1. **Transaction Queries:**
   - `(client_exchange, transaction_type, date)` - Fast filtering by type and date
   - `(client_exchange, date)` - Date range queries
   - `(transaction_type, date)` - Type-based reporting

2. **Balance Queries:**
   - `(client_exchange, date)` - Latest balance lookup
   - `(date)` - Date-based reporting

3. **Client Queries:**
   - `(user, is_active)` - Active clients per user
   - `(user, is_company_client)` - Client type filtering
   - `(is_company_client, is_active)` - Company client filtering

4. **ClientExchange Queries:**
   - `(client, is_active)` - Active exchanges per client
   - `(exchange, is_active)` - Active clients per exchange

### **Performance Optimizations**

1. **Cached Fields (Denormalization):**
   - `ClientExchange.cached_current_balance` - Avoids recalculating CB
   - `ClientExchange.cached_old_balance` - Avoids recalculating OB
   - `ClientExchange.cached_total_funding` - Fast funding totals
   - Updated via Django signals automatically

2. **Daily Snapshots:**
   - Pre-computed aggregates for time-travel reporting
   - Avoids expensive date-range aggregations

3. **Index Strategy:**
   - All foreign keys indexed automatically
   - Composite indexes for common query patterns
   - Date indexes for time-based queries

---

## 🔒 Constraints & Validations

### **Unique Constraints**

1. **Client:**
   - `(user, code)` - Code unique per user

2. **Exchange:**
   - `name` - Unique exchange name
   - `code` - Unique exchange code (if provided)

3. **ClientExchange:**
   - `(client, exchange)` - One relationship per pair

4. **Transaction:**
   - None (multiple transactions per day allowed)

5. **ClientDailyBalance:**
   - `(client_exchange, date)` - One balance per date
   - `(client, date)` - Legacy support

6. **DailyBalanceSnapshot:**
   - `(client_exchange, date)` - One snapshot per date

7. **OutstandingAmount:**
   - `client_exchange` - OneToOne (one ledger per client-exchange)

8. **TallyLedger:**
   - `client_exchange` - OneToOne (one ledger per client-exchange)

9. **PendingAmount:**
   - `client_exchange` - One per client-exchange

### **Check Constraints (Application-Level)**

1. **ClientExchange:**
   - `company_share_pct < 100` (enforced in `clean()`)

2. **Transaction:**
   - `amount > 0` (always positive)

3. **SystemSettings:**
   - `weekly_report_day IN [0, 6]` (day of week)

### **Referential Integrity**

- All foreign keys use `CASCADE` delete
- Deleting a Client deletes all related ClientExchanges
- Deleting a ClientExchange deletes all related Transactions
- Deleting a Transaction deletes related CompanyShareRecords

---

## 🔗 Relationships

### **One-to-Many (1:N)**

1. **User → Client**
   - One user can have many clients
   - `Client.user` → `User`

2. **Client → ClientExchange**
   - One client can have many exchanges
   - `Client.client_exchanges` → `ClientExchange[]`

3. **Exchange → ClientExchange**
   - One exchange can serve many clients
   - `Exchange.client_exchanges` → `ClientExchange[]`

4. **ClientExchange → Transaction**
   - One client-exchange can have many transactions
   - `ClientExchange.transactions` → `Transaction[]`

5. **ClientExchange → ClientDailyBalance**
   - One client-exchange can have many balance records
   - `ClientExchange.daily_balances` → `ClientDailyBalance[]`

6. **ClientExchange → DailyBalanceSnapshot**
   - One client-exchange can have many snapshots
   - `ClientExchange.daily_snapshots` → `DailyBalanceSnapshot[]`

7. **Transaction → CompanyShareRecord**
   - One transaction can have many company share records
   - `Transaction.company_shares` → `CompanyShareRecord[]`

### **One-to-One (1:1)**

1. **ClientExchange → OutstandingAmount**
   - One client-exchange has one outstanding ledger (My Clients only)
   - `ClientExchange.outstanding_amount_ledger` → `OutstandingAmount`

2. **ClientExchange → TallyLedger**
   - One client-exchange has one tally ledger (Company Clients only)
   - `ClientExchange.tally_ledger` → `TallyLedger`

---

## 📐 Data Types & Precision

### **Decimal Fields**

All monetary amounts use `DecimalField` with precision:
- **Standard Amounts:** `DecimalField(max_digits=14, decimal_places=2)`
  - Range: -99,999,999,999,999.99 to 99,999,999,999,999.99
  - Examples: `cached_current_balance`, `amount`, `remaining_balance`

- **Percentages:** `DecimalField(max_digits=5, decimal_places=2)`
  - Range: -999.99 to 999.99
  - Examples: `my_share_pct`, `company_share_pct`

- **System Settings:** `DecimalField(max_digits=5, decimal_places=2)`
  - Range: -999.99 to 999.99
  - Examples: `admin_loss_share_pct`, `company_profit_share_pct`

### **Storage Precision Policy**

- **Engine Calculations:** Use full precision (no rounding)
- **Storage:** `Decimal(14,2)` for amounts, `Decimal(5,2)` for percentages
- **UI Display:** Round to 2 decimals (HALF_UP)
- **Epsilon:** `Decimal("0.0001")` for comparisons

### **Date/Time Fields**

- **Date Fields:** `DateField` - Store date only (no time)
- **DateTime Fields:** `DateTimeField` - Store with timezone
  - `created_at`, `updated_at` - Auto-managed timestamps
  - `balance_last_updated` - Manual timestamp

### **Text Fields**

- **CharField:** Max lengths vary (50-255)
- **TextField:** Unlimited length for notes

---

## 🎯 Key Design Decisions

### **1. Denormalization Strategy**
- **Why:** Performance optimization for frequently accessed data
- **What:** Cached fields in `ClientExchange` (OB, CB, total funding)
- **How:** Updated automatically via Django signals
- **Trade-off:** Slight data redundancy for query speed

### **2. Separate Ledgers for Client Types**
- **My Clients:** Use `OutstandingAmount` (netted ledger)
- **Company Clients:** Use `TallyLedger` (separate tracking)
- **Why:** Different business rules require different data structures

### **3. Transaction Types as Audit Trail**
- **LOSS/PROFIT:** Audit only, not used in calculations
- **FUNDING/SETTLEMENT/BALANCE_RECORD:** Active transaction types
- **Why:** Historical record while maintaining calculation integrity

### **4. Daily Snapshots for Reporting**
- **Why:** Avoid expensive date-range aggregations
- **What:** Pre-computed cumulative fields
- **Trade-off:** Storage space for query performance

### **5. Singleton SystemSettings**
- **Why:** Single source of truth for system configuration
- **How:** Enforced via `save()` method (pk=1)
- **Benefit:** No need to query for "current" settings

---

## ✅ Database Integrity Rules

1. **OB Bootstrap:** `cached_old_balance` initialized on first FUNDING
2. **CB Source:** Always from latest `ClientDailyBalance` (by date DESC, id DESC)
3. **Settlement Locking:** Must use `SELECT FOR UPDATE` on `ClientExchange`
4. **Balance Ordering:** `ClientDailyBalance` must be strictly increasing
5. **Share Validation:** `my_share_pct_effective + company_share_pct == total_share_pct`
6. **Non-Negative:** `OB >= 0`, `CB >= 0` (application-level enforcement)
7. **Transaction Amounts:** Always positive (`amount > 0`)

---

**Last Updated:** January 3, 2025  
**Version:** 1.0  
**Status:** ✅ Complete Database Design Documentation


