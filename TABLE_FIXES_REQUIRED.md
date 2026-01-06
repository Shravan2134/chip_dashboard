# TABLE FIXES REQUIRED - Pending Summary Table

**Complete Fixes for the Pending Summary Table to Use New Backend-Driven Model**

---

## 🔴 PROBLEMS IDENTIFIED

### **Problem 1: "Old Balance" Label Still Shown**
- **Current**: Table shows "Old Balance"
- **Should Be**: "Capital Balance"
- **Location**: `core/templates/core/pending/summary.html` line 854

### **Problem 2: Exchange Balance Using Live Value**
- **Current**: `exchange_balance = current_balance` (always live)
- **Should Be**: Use snapshot when LOSS exists, live when no LOSS
- **Location**: `core/views.py` line 2664

### **Problem 3: Total Profit Can Be Negative**
- **Current**: `total_profit = old_balance - exchange_balance` (can be negative)
- **Should Be**: `profit_amount = max(exchange_balance - old_balance, 0)` (never negative)
- **Location**: `core/views.py` line 2889

### **Problem 4: Combined Share Can Be Negative**
- **Current**: `combined_share = (total_profit * share_pct) / 100` (can be negative)
- **Should Be**: `client_payable = LOSS × total_share_pct / 100` (never negative)
- **Location**: `core/views.py` line 2903

### **Problem 5: Wrong Field Names**
- **Current**: `old_balance`, `exchange_balance`, `total_profit`, `combined_share`
- **Should Be**: `capital`, `current_balance`, `profit_amount`, `client_payable`
- **Location**: `core/views.py` lines 2655-2678

---

## ✅ REQUIRED FIXES

### **Fix 1: Update View to Send Correct Fields**

**In `core/views.py` - `pending_summary` function**:

**For "Clients Owe You" section** (LOSS case):
```python
# Get CAPITAL from ledger (not old_balance)
capital = get_capital(client_exchange)  # Σ(FUNDING) − Σ(CAPITAL_CLOSED)

# Get LOSS from LossSnapshot (frozen, never recalculated)
loss_snapshot = LossSnapshot.objects.filter(
    client_exchange=client_exchange,
    is_settled=False
).first()

if loss_snapshot:
    loss_amount = loss_snapshot.loss_amount  # Frozen LOSS
    current_balance = loss_snapshot.balance_record.remaining_balance  # Frozen CB
    my_share_pct = loss_snapshot.my_share_pct  # Frozen shares
    company_share_pct = loss_snapshot.company_share_pct
    total_share_pct = my_share_pct + company_share_pct
    
    # Calculate receivables from frozen LOSS
    client_payable = (loss_amount * total_share_pct) / 100
    your_receivable = (loss_amount * my_share_pct) / 100
    company_receivable = (loss_amount * company_share_pct) / 100
    
    profit_amount = Decimal(0)  # No profit when LOSS exists
else:
    # No active LOSS
    loss_amount = Decimal(0)
    current_balance = get_exchange_balance(client_exchange)  # Live CB
    profit_amount = max(current_balance - capital, 0)  # Calculate PROFIT
    client_payable = Decimal(0)
    your_receivable = Decimal(0)
    company_receivable = Decimal(0)
    my_share_pct = client_exchange.my_share_pct
    company_share_pct = client_exchange.company_share_pct
    total_share_pct = my_share_pct + company_share_pct

clients_owe_list.append({
    "client_id": client_exchange.client.pk,
    "client_name": client_exchange.client.name,
    "client_code": client_exchange.client.code,
    "exchange_name": client_exchange.exchange.name,
    "exchange_id": client_exchange.exchange.pk,
    "client_exchange_id": client_exchange.pk,
    # ✅ FIXED: Use correct field names
    "capital": capital,  # ✅ Not "old_balance"
    "current_balance": current_balance,  # ✅ Snapshot when LOSS exists, live when no LOSS
    "latest_balance": get_exchange_balance(client_exchange),  # ✅ For fallback
    "loss_amount": loss_amount,  # ✅ Frozen from LossSnapshot
    "profit_amount": profit_amount,  # ✅ Never negative
    "client_payable": client_payable,  # ✅ Never negative
    "your_receivable": your_receivable,  # ✅ Never negative
    "company_receivable": company_receivable,  # ✅ Never negative
    "my_share_pct": my_share_pct,  # ✅ Frozen when LOSS exists
    "company_share_pct": company_share_pct,  # ✅ Frozen when LOSS exists
    "total_share_pct": total_share_pct,  # ✅ Frozen when LOSS exists
    "is_company_client": client_exchange.client.is_company_client,
})
```

**For "You Owe Clients" section** (PROFIT case):
```python
# Get CAPITAL from ledger
capital = get_capital(client_exchange)

# Get current balance (live, no LOSS exists)
current_balance = get_exchange_balance(client_exchange)

# Calculate PROFIT (never negative)
profit_amount = max(current_balance - capital, 0)

if profit_amount > 0:
    # Calculate shares from profit
    my_share_pct = client_exchange.my_share_pct
    company_share_pct = client_exchange.company_share_pct
    total_share_pct = my_share_pct + company_share_pct
    
    # Calculate what you owe (share space)
    client_payable = (profit_amount * total_share_pct) / 100
    your_receivable = (profit_amount * my_share_pct) / 100
    company_receivable = (profit_amount * company_share_pct) / 100
    
    you_owe_list.append({
        "client_id": client_exchange.client.pk,
        "client_name": client_exchange.client.name,
        "client_code": client_exchange.client.code,
        "exchange_name": client_exchange.exchange.name,
        "exchange_id": client_exchange.exchange.pk,
        "client_exchange_id": client_exchange.pk,
        # ✅ FIXED: Use correct field names
        "capital": capital,  # ✅ Not "old_balance"
        "current_balance": current_balance,  # ✅ Live when no LOSS
        "latest_balance": current_balance,  # ✅ Same as current_balance
        "loss_amount": Decimal(0),  # ✅ No LOSS when PROFIT exists
        "profit_amount": profit_amount,  # ✅ Never negative
        "client_payable": client_payable,  # ✅ What you owe client
        "your_receivable": your_receivable,  # ✅ Your share of profit
        "company_receivable": company_receivable,  # ✅ Company share of profit
        "my_share_pct": my_share_pct,
        "company_share_pct": company_share_pct,
        "total_share_pct": total_share_pct,
        "is_company_client": client_exchange.client.is_company_client,
    })
```

---

### **Fix 2: Update Template to Use Correct Fields**

**In `core/templates/core/pending/summary.html`**:

**Change Table Headers**:
```html
<!-- Line 854: Change label -->
<th style="text-align: right;">Capital Balance <small>(from ledger)</small></th>
<!-- Line 855: Keep but add tooltip -->
<th style="text-align: right;">Exchange Balance <small>(from snapshot if LOSS exists)</small></th>
<!-- Line 856: Change label and ensure never negative -->
<th style="text-align: right;">Profit <small>(never negative)</small></th>
```

**Change Table Data**:
```html
<!-- For "Clients Owe You" section -->
{% for item in clients_owe %}
    <tr>
        <td><strong>{% if item.client_code %}{{ item.client_code }}{% else %}<span style="color: #9ca3af;">—</span>{% endif %}</strong></td>
        <td>
            <a href="{% url 'clients:balance' item.client_id %}?exchange={{ item.client_exchange_id }}" class="client-link">
                {{ item.client_name }}
            </a>
        </td>
        <td>{{ item.exchange_name }}</td>
        <!-- ✅ FIXED: Use capital, not old_balance -->
        <td style="text-align: right;">₹{{ item.capital|floatformat:1 }} <small style="color: #6b7280;">(ledger)</small></td>
        <!-- ✅ FIXED: Use current_balance (snapshot when LOSS exists) -->
        <td style="text-align: right;">₹{{ item.current_balance|floatformat:1 }} <small style="color: #6b7280;">{% if item.loss_amount > 0 %}(snapshot){% else %}(live){% endif %}</small></td>
        <!-- ✅ FIXED: Use profit_amount (never negative) -->
        <td style="text-align: right;">{% if item.profit_amount > 0 %}<span class="green">₹{{ item.profit_amount|floatformat:1 }}</span>{% else %}<span style="color: #9ca3af;">—</span>{% endif %}</td>
        <!-- ✅ FIXED: Use client_payable, not combined_share -->
        <td style="text-align: right;">{% if item.client_payable > 0 %}<span class="red">₹{{ item.client_payable|floatformat:1 }}</span>{% else %}<span style="color: #9ca3af;">—</span>{% endif %}</td>
        <!-- ✅ FIXED: Use your_receivable, not my_share -->
        <td style="text-align: right;">₹{{ item.your_receivable|floatformat:1 }} <small>({{ item.my_share_pct|floatformat:1 }}%)</small></td>
        <!-- ✅ FIXED: Use company_receivable, show only if > 0 -->
        {% if item.company_receivable > 0 %}
        <td style="text-align: right;">₹{{ item.company_receivable|floatformat:1 }} <small>({{ item.company_share_pct|floatformat:1 }}%)</small></td>
        {% else %}
        <td style="text-align: right;"><span style="color: #9ca3af;">—</span></td>
        {% endif %}
        <!-- ✅ FIXED: Action based on loss_amount, not total_profit -->
        <td>
            {% if item.loss_amount >= 0.01 %}
                <button onclick="..." class="action-button">Collect from Client</button>
            {% elif item.profit_amount > 0 %}
                <button onclick="..." class="action-button">Pay Client</button>
            {% else %}
                <span style="color: #9ca3af;">No action</span>
            {% endif %}
        </td>
    </tr>
{% endfor %}
```

---

### **Fix 3: Remove All Calculations from Template**

**❌ REMOVE**:
```html
<!-- ❌ WRONG: Calculating in template -->
{{ item.exchange_balance|sub:item.old_balance|floatformat:1 }}
```

**✅ REPLACE WITH**:
```html
<!-- ✅ CORRECT: Display backend value -->
{{ item.profit_amount|floatformat:1 }}
```

---

### **Fix 4: Update Visibility Conditions**

**❌ WRONG**:
```html
{% if item.combined_share > 0 %}
```

**✅ CORRECT**:
```html
{% if item.loss_amount >= 0.01 %}
    <!-- Show LOSS section -->
{% elif item.profit_amount > 0 %}
    <!-- Show PROFIT section -->
{% endif %}
```

---

## 📋 COMPLETE FIELD MAPPING

### **Old Fields → New Fields**

| Old Field | New Field | Notes |
|-----------|-----------|-------|
| `old_balance` | `capital` | Always from ledger |
| `exchange_balance` | `current_balance` | Snapshot when LOSS exists, live when no LOSS |
| `total_profit` | `profit_amount` | Never negative, `max(CB - CAPITAL, 0)` |
| `combined_share` | `client_payable` | Never negative, from frozen LOSS |
| `my_share` | `your_receivable` | Never negative, from frozen LOSS |
| `company_share` | `company_receivable` | Never negative, from frozen LOSS |
| `total_loss` | `loss_amount` | Frozen from LossSnapshot |

---

## 🎯 SUMMARY

### **What Must Change**

1. **View (`core/views.py`)**:
   - Use `get_capital()` instead of `get_old_balance_after_settlement()`
   - Get LOSS from `LossSnapshot` (frozen)
   - Use snapshot CB when LOSS exists
   - Calculate `profit_amount = max(CB - CAPITAL, 0)` (never negative)
   - Calculate `client_payable` from frozen LOSS (never negative)
   - Send correct field names

2. **Template (`core/templates/core/pending/summary.html`)**:
   - Change "Old Balance" → "Capital Balance"
   - Use `item.capital` instead of `item.old_balance`
   - Use `item.current_balance` instead of `item.exchange_balance`
   - Use `item.profit_amount` instead of `item.total_profit`
   - Use `item.client_payable` instead of `item.combined_share`
   - Remove all calculations
   - Use `loss_amount` for visibility conditions

3. **Action Buttons**:
   - Show "Collect from Client" when `loss_amount >= 0.01`
   - Show "Pay Client" when `profit_amount > 0`
   - Show "No action" when both are 0

---

**Document Version**: 1.0  
**Last Updated**: 2026-01-05  
**Status**: ✅ Complete Fixes Documented for Pending Summary Table

