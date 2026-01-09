# ADDING EXCHANGES IN ACCOUNT - COMPLETE DOCUMENTATION
## End-to-End UI Flow, Data Storage, Logic, and Implementation Details

---

## TABLE OF CONTENTS

1. [System Overview](#1-system-overview)
2. [UI Flow - Pin to Pin](#2-ui-flow---pin-to-pin)
3. [Data Storage Structure](#3-data-storage-structure)
4. [Database Models](#4-database-models)
5. [Views and Business Logic](#5-views-and-business-logic)
6. [Forms and Validation](#6-forms-and-validation)
7. [URL Routing](#7-url-routing)
8. [Templates and UI Components](#8-templates-and-ui-components)
9. [Edge Cases and Validation Rules](#9-edge-cases-and-validation-rules)
10. [Code Mapping Reference](#10-code-mapping-reference)

---

## 1. SYSTEM OVERVIEW

### 1.1 Purpose
The Exchange Management system allows users to:
- **Create Exchange Platforms**: Add new trading exchanges (e.g., Binance, Coinbase, etc.)
- **Link Clients to Exchanges**: Associate client accounts with specific exchanges
- **Configure Share Percentages**: Set profit/loss share percentages for each client-exchange relationship
- **Manage Exchange Accounts**: View and manage all client-exchange account configurations

### 1.2 Two-Step Process
1. **Step 1: Create Exchange** - Create a standalone exchange platform entity
2. **Step 2: Link Client to Exchange** - Associate a client with an exchange and configure percentages

### 1.3 Key Principles
- **Exchange Independence**: Exchanges exist independently and can be reused across multiple clients
- **Unique Client-Exchange Pairs**: Each client can only have one account per exchange (enforced by unique constraint)
- **MASKED SHARE SETTLEMENT SYSTEM**: Uses separate loss and profit share percentages
- **Report Configuration**: Optional friend/own percentage split for reporting purposes only
- **Initial State**: New client-exchange accounts start with `funding=0` and `exchange_balance=0`

---

## 2. UI FLOW - PIN TO PIN

### 2.1 Flow Diagram

```
[Exchange List Page]
    ↓ (Click "Add Exchange" button)
[Create Exchange Form]
    ↓ (Fill: Exchange Name, Optional Code)
    ↓ (Submit POST request)
[Exchange Created - Redirect to Exchange List]
    ↓ (Click "Link Client to Exchange" button)
[Link Client to Exchange Form]
    ↓ (Select: Client, Exchange, My Total %, Optional Report Config)
    ↓ (Submit POST request)
[Client-Exchange Account Created - Redirect to Client Detail]
```

### 2.2 Step-by-Step UI Flow

#### **STEP 1: Access Exchange List**

**Entry Point:** Navigation menu → "Exchanges" or direct URL: `/exchanges/`

**UI Component:** `core/templates/core/exchanges/list.html`

**What User Sees:**
- Table showing all existing exchanges
- Columns: Exchange Name, Code, Status, Actions (client count)
- Two action buttons at top:
  - **"Add Exchange"** button → Routes to `/exchanges/create/`
  - **"Link Client to Exchange"** button → Routes to `/exchanges/link/`

**Code Location:** 
- View: `core/views.py` lines 786-791
- Template: `core/templates/core/exchanges/list.html` lines 1-46
- URL: `core/urls.py` line 21

#### **STEP 2: Create Exchange Form**

**URL:** `/exchanges/create/`

**UI Component:** `core/templates/core/exchanges/create.html`

**Form Fields:**
1. **Exchange Name** (required)
   - Input type: `text`
   - Field name: `name`
   - HTML attribute: `required`
   - Validation: Non-empty string after stripping whitespace

2. **Exchange Code** (optional)
   - Input type: `text`
   - Field name: `code`
   - HTML attribute: None (optional)
   - Validation: If provided, must be unique across all exchanges
   - Placeholder: "Leave blank if not needed"

**Form Submission:**
- Method: `POST`
- CSRF Token: Required (Django CSRF protection)
- Action: Same URL (`/exchanges/create/`)

**User Actions:**
- Fill in Exchange Name (required)
- Optionally fill in Exchange Code
- Click "Save Exchange" button → Submits POST request
- Click "Cancel" button → Redirects to `/exchanges/`

**Code Location:**
- View: `core/views.py` lines 1908-1926
- Template: `core/templates/core/exchanges/create.html` lines 1-33
- URL: `core/urls.py` line 22

#### **STEP 3: Exchange Creation Processing**

**Backend Processing (POST request):**

1. **Extract Form Data:**
   ```python
   name = request.POST.get("name", "").strip()
   code = request.POST.get("code", "").strip()
   ```

2. **Validation:**
   - Check if `name` is non-empty
   - If validation fails: Show error message, re-render form

3. **Database Insert:**
   ```python
   Exchange.objects.create(
       name=name,
       code=code if code else None,  # Store None if empty string
   )
   ```

4. **Success Response:**
   - Create success message: `"Exchange '{name}' has been created successfully."`
   - Redirect to `/exchanges/` (Exchange List)

**Database Storage:**
- **Table:** `core_exchange`
- **Fields Stored:**
  - `id`: Auto-increment primary key
  - `name`: VARCHAR(200) - Exchange name
  - `code`: VARCHAR(50) NULL - Exchange code (if provided)
  - `created_at`: DATETIME - Auto-set on creation
  - `updated_at`: DATETIME - Auto-updated on modification

**Code Location:** `core/views.py` lines 1910-1921

#### **STEP 4: Link Client to Exchange Form**

**URL:** `/exchanges/link/`

**UI Component:** `core/templates/core/exchanges/link_to_client.html`

**Form Fields:**

1. **Client** (required)
   - Input type: `<select>` dropdown
   - Field name: `client`
   - Options: All clients belonging to current user
   - Format: `{client.name}{if client.code} ({client.code}){endif}`
   - HTML attribute: `required`

2. **Exchange** (required)
   - Input type: `<select>` dropdown
   - Field name: `exchange`
   - Options: All exchanges (ordered by name)
   - Format: `{exchange.name}{if exchange.code} ({exchange.code}){endif}`
   - HTML attribute: `required`

3. **My Total %** (required)
   - Input type: `number`
   - Field name: `my_percentage`
   - Min: 0, Max: 100
   - HTML attribute: `required`
   - Help text: "Your total percentage share (0-100). Used for system logic."

4. **Friend % (Report Only)** (optional)
   - Input type: `number`
   - Field name: `friend_percentage`
   - Min: 0, Max: 100
   - Help text: "Friend/Student percentage. Must equal: My Total % - My Own %"

5. **My Own % (Report Only)** (optional)
   - Input type: `number`
   - Field name: `my_own_percentage`
   - Min: 0, Max: 100
   - Help text: "Your own percentage. Friend % + My Own % must equal My Total %"

**Form Submission:**
- Method: `POST`
- CSRF Token: Required
- Action: Same URL (`/exchanges/link/`)

**User Actions:**
- Select Client from dropdown
- Select Exchange from dropdown
- Enter My Total % (0-100)
- Optionally enter Friend % and My Own % (must sum to My Total %)
- Click "Link Client to Exchange" button → Submits POST request
- Click "Cancel" button → Redirects to `/exchanges/`

**Code Location:**
- View: `core/views.py` lines 2991-3083
- Template: `core/templates/core/exchanges/link_to_client.html` lines 1-75
- URL: `core/urls.py` line 23

#### **STEP 5: Client-Exchange Link Processing**

**Backend Processing (POST request):**

1. **Extract Form Data:**
   ```python
   client_id = request.POST.get("client")
   exchange_id = request.POST.get("exchange")
   my_percentage = request.POST.get("my_percentage", "").strip()
   friend_percentage = request.POST.get("friend_percentage", "").strip()
   my_own_percentage = request.POST.get("my_own_percentage", "").strip()
   ```

2. **Primary Validation:**
   - Check if `client_id`, `exchange_id`, and `my_percentage` are provided
   - If missing: Show error "Client, Exchange, and My Total % are required."

3. **Database Lookup:**
   ```python
   client = Client.objects.get(pk=client_id, user=request.user)
   exchange = Exchange.objects.get(pk=exchange_id)
   my_percentage_int = int(my_percentage)
   ```

4. **Percentage Validation:**
   - Check if `my_percentage_int` is between 0 and 100
   - If invalid: Show error "My Total % must be between 0 and 100."

5. **Duplicate Check:**
   ```python
   if ClientExchangeAccount.objects.filter(client=client, exchange=exchange).exists():
       # Show error: "Client '{client.name}' is already linked to '{exchange.name}'."
   ```

6. **Create ClientExchangeAccount:**
   ```python
   account = ClientExchangeAccount.objects.create(
       client=client,
       exchange=exchange,
       funding=0,  # Initial state: no funding
       exchange_balance=0,  # Initial state: no balance
       my_percentage=my_percentage_int,
       loss_share_percentage=my_percentage_int,  # Default to my_percentage
       profit_share_percentage=my_percentage_int,  # Default to my_percentage
   )
   ```

7. **Create Report Config (if provided):**
   ```python
   if friend_percentage or my_own_percentage:
       friend_pct = int(friend_percentage) if friend_percentage else 0
       own_pct = int(my_own_percentage) if my_own_percentage else 0
       
       # Validate: friend % + my own % = my total %
       if friend_pct + own_pct != my_percentage_int:
           # Show warning, but don't fail
       else:
           ClientExchangeReportConfig.objects.create(
               client_exchange=account,
               friend_percentage=friend_pct,
               my_own_percentage=own_pct,
           )
   ```

8. **Success Response:**
   - Create success message: `"Successfully linked '{client.name}' to '{exchange.name}'."`
   - Redirect to `/clients/{client.pk}/` (Client Detail page)

**Code Location:** `core/views.py` lines 2993-3067

---

## 3. DATA STORAGE STRUCTURE

### 3.1 Exchange Table (`core_exchange`)

**Database Schema:**

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `name` | VARCHAR(200) | NOT NULL | Exchange platform name |
| `code` | VARCHAR(50) | NULL, UNIQUE | Optional exchange code |
| `created_at` | DATETIME | NOT NULL, AUTO | Creation timestamp |
| `updated_at` | DATETIME | NOT NULL, AUTO | Last update timestamp |

**Unique Constraints:**
- `code` must be unique if provided (NULL values are allowed)

**Indexes:**
- Primary key on `id`
- Unique index on `code` (if not NULL)

**Code Location:** `core/models.py` lines 36-47

### 3.2 ClientExchangeAccount Table (`core_clientexchangeaccount`)

**Database Schema:**

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `client_id` | BIGINT | FOREIGN KEY → `core_client.id`, CASCADE DELETE | Client reference |
| `exchange_id` | BIGINT | FOREIGN KEY → `core_exchange.id`, CASCADE DELETE | Exchange reference |
| `funding` | BIGINT | NOT NULL, DEFAULT=0, MIN=0 | Total funding given to client |
| `exchange_balance` | BIGINT | NOT NULL, DEFAULT=0, MIN=0 | Current balance on exchange |
| `my_percentage` | INT | NOT NULL, DEFAULT=0, MIN=0, MAX=100 | Admin total share % (deprecated) |
| `loss_share_percentage` | INT | NOT NULL, DEFAULT=0, MIN=0, MAX=100 | Admin share % for losses |
| `profit_share_percentage` | INT | NOT NULL, DEFAULT=0, MIN=0, MAX=100 | Admin share % for profits |
| `created_at` | DATETIME | NOT NULL, AUTO | Creation timestamp |
| `updated_at` | DATETIME | NOT NULL, AUTO | Last update timestamp |

**Unique Constraints:**
- Composite unique: `(client_id, exchange_id)` - One account per client-exchange pair

**Foreign Keys:**
- `client_id` → `core_client.id` (CASCADE DELETE)
- `exchange_id` → `core_exchange.id` (CASCADE DELETE)

**Initial Values on Creation:**
- `funding = 0`
- `exchange_balance = 0`
- `my_percentage = my_percentage_int` (from form)
- `loss_share_percentage = my_percentage_int` (defaulted to my_percentage)
- `profit_share_percentage = my_percentage_int` (defaulted to my_percentage)

**Code Location:** `core/models.py` lines 50-91

### 3.3 ClientExchangeReportConfig Table (`core_clientexchangereportconfig`)

**Database Schema:**

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `client_exchange_id` | BIGINT | FOREIGN KEY → `core_clientexchangeaccount.id`, CASCADE DELETE | Account reference |
| `friend_percentage` | INT | NOT NULL, DEFAULT=0, MIN=0, MAX=100 | Friend/student share % (report only) |
| `my_own_percentage` | INT | NOT NULL, DEFAULT=0, MIN=0, MAX=100 | Admin own share % (report only) |
| `created_at` | DATETIME | NOT NULL, AUTO | Creation timestamp |
| `updated_at` | DATETIME | NOT NULL, AUTO | Last update timestamp |

**Unique Constraints:**
- One-to-one relationship: One config per `client_exchange_id`

**Foreign Keys:**
- `client_exchange_id` → `core_clientexchangeaccount.id` (CASCADE DELETE)

**Validation Rule:**
- `friend_percentage + my_own_percentage = my_percentage` (from ClientExchangeAccount)

**Code Location:** `core/models.py` (referenced in views, model definition needed)

---

## 4. DATABASE MODELS

### 4.1 Exchange Model

**File:** `core/models.py` lines 36-47

```python
class Exchange(TimeStampedModel):
    """
    Exchange entity - trading platform.
    """
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, blank=True, null=True, unique=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name
```

**Key Points:**
- Inherits from `TimeStampedModel` (adds `created_at`, `updated_at`)
- `name`: Required, max 200 characters
- `code`: Optional, unique if provided, can be NULL
- Default ordering: Alphabetical by name
- String representation: Returns exchange name

### 4.2 ClientExchangeAccount Model

**File:** `core/models.py` lines 50-91

```python
class ClientExchangeAccount(TimeStampedModel):
    """
    CORE SYSTEM TABLE - LOGIC SAFE
    
    Stores ONLY real money values:
    - funding: Total real money given to client
    - exchange_balance: Current balance on exchange
    
    All other values (profit, loss, shares) are DERIVED, never stored.
    """
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='exchange_accounts')
    exchange = models.ForeignKey(Exchange, on_delete=models.CASCADE, related_name='client_accounts')
    
    # ONLY TWO MONEY VALUES STORED (BIGINT as per spec)
    funding = models.BigIntegerField(default=0, validators=[MinValueValidator(0)])
    exchange_balance = models.BigIntegerField(default=0, validators=[MinValueValidator(0)])
    
    # Partner percentage (INT as per spec) - kept for backward compatibility
    my_percentage = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Your total percentage share (0-100) - DEPRECATED: Use loss_share_percentage and profit_share_percentage"
    )
    
    # MASKED SHARE SETTLEMENT SYSTEM: Separate loss and profit percentages
    loss_share_percentage = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Admin share percentage for losses (0-100). IMMUTABLE once data exists."
    )
    profit_share_percentage = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Admin share percentage for profits (0-100). Can change anytime, affects only future profits."
    )
    
    class Meta:
        unique_together = [['client', 'exchange']]
        ordering = ['client__name', 'exchange__name']
    
    def __str__(self):
        return f"{self.client.name} - {self.exchange.name}"
```

**Key Points:**
- **Foreign Keys:**
  - `client`: CASCADE DELETE (if client deleted, account deleted)
  - `exchange`: CASCADE DELETE (if exchange deleted, account deleted)
- **Money Fields:** BIGINT (stored in smallest currency unit)
  - `funding`: Default 0, minimum 0
  - `exchange_balance`: Default 0, minimum 0
- **Percentage Fields:** INT (0-100)
  - `my_percentage`: Deprecated, kept for backward compatibility
  - `loss_share_percentage`: Used for loss calculations
  - `profit_share_percentage`: Used for profit calculations
- **Unique Constraint:** One account per `(client, exchange)` pair
- **Default Ordering:** By client name, then exchange name

**Model Methods:**
- `compute_client_pnl()`: Returns `exchange_balance - funding` (BIGINT)
- `compute_my_share()`: Calculates floor-rounded share based on PnL and percentages

**Code Location:** `core/models.py` lines 50-131

---

## 5. VIEWS AND BUSINESS LOGIC

### 5.1 Exchange List View

**Function:** `exchange_list(request)`

**File:** `core/views.py` lines 786-791

**HTTP Methods:** GET only

**Authentication:** Not required (but typically accessed by authenticated users)

**Logic:**
```python
def exchange_list(request):
    exchanges = Exchange.objects.all().order_by("name")
    return render(request, "core/exchanges/list.html", {"exchanges": exchanges})
```

**What It Does:**
1. Fetches all exchanges from database
2. Orders them alphabetically by name
3. Renders list template with exchanges context

**Template Context:**
- `exchanges`: QuerySet of all Exchange objects

**Code Location:** `core/views.py` lines 786-791

### 5.2 Exchange Create View

**Function:** `exchange_create(request)`

**File:** `core/views.py` lines 1908-1926

**HTTP Methods:** GET, POST

**Authentication:** `@login_required` decorator

**GET Request Logic:**
```python
return render(request, "core/exchanges/create.html")
```
- Renders empty form

**POST Request Logic:**
```python
if request.method == "POST":
    name = request.POST.get("name", "").strip()
    code = request.POST.get("code", "").strip()
    
    if name:
        Exchange.objects.create(
            name=name,
            code=code if code else None,
        )
        messages.success(request, f"Exchange '{name}' has been created successfully.")
        return redirect(reverse("exchange_list"))
    else:
        messages.error(request, "Exchange name is required.")
```

**Step-by-Step Processing:**

1. **Extract Form Data:**
   - `name`: Required, stripped of whitespace
   - `code`: Optional, stripped of whitespace

2. **Validation:**
   - Check if `name` is non-empty after stripping
   - If empty: Show error message, re-render form

3. **Database Insert:**
   - Create Exchange object
   - `code` is set to `None` if empty string (allows NULL in database)

4. **Success Handling:**
   - Create success message
   - Redirect to exchange list page

**Error Handling:**
- Empty name: Error message shown, form re-rendered
- Database constraint violation (e.g., duplicate code): Django raises exception (handled by framework)

**Code Location:** `core/views.py` lines 1908-1926

### 5.3 Link Client to Exchange View

**Function:** `link_client_to_exchange(request)`

**File:** `core/views.py` lines 2991-3083

**HTTP Methods:** GET, POST

**Authentication:** `@login_required` decorator

**GET Request Logic:**
```python
return render(request, "core/exchanges/link_to_client.html", {
    "clients": Client.objects.filter(user=request.user).order_by("name"),
    "exchanges": Exchange.objects.all().order_by("name"),
})
```
- Fetches user's clients and all exchanges
- Renders form with dropdown options

**POST Request Logic:**

**Step 1: Extract Form Data**
```python
client_id = request.POST.get("client")
exchange_id = request.POST.get("exchange")
my_percentage = request.POST.get("my_percentage", "").strip()
friend_percentage = request.POST.get("friend_percentage", "").strip()
my_own_percentage = request.POST.get("my_own_percentage", "").strip()
```

**Step 2: Primary Validation**
```python
if not client_id or not exchange_id or not my_percentage:
    messages.error(request, "Client, Exchange, and My Total % are required.")
    return render(...)  # Re-render form with error
```

**Step 3: Database Lookup**
```python
try:
    client = Client.objects.get(pk=client_id, user=request.user)
    exchange = Exchange.objects.get(pk=exchange_id)
    my_percentage_int = int(my_percentage)
except (Client.DoesNotExist, Exchange.DoesNotExist):
    messages.error(request, "Invalid client or exchange selected.")
    return render(...)
except ValueError:
    messages.error(request, "Invalid percentage value. Please enter numbers only.")
    return render(...)
```

**Step 4: Percentage Range Validation**
```python
if my_percentage_int < 0 or my_percentage_int > 100:
    messages.error(request, "My Total % must be between 0 and 100.")
    return render(...)
```

**Step 5: Duplicate Check**
```python
if ClientExchangeAccount.objects.filter(client=client, exchange=exchange).exists():
    messages.error(request, f"Client '{client.name}' is already linked to '{exchange.name}'.")
    return render(...)
```

**Step 6: Create ClientExchangeAccount**
```python
account = ClientExchangeAccount.objects.create(
    client=client,
    exchange=exchange,
    funding=0,
    exchange_balance=0,
    my_percentage=my_percentage_int,
    loss_share_percentage=my_percentage_int,  # Default to my_percentage
    profit_share_percentage=my_percentage_int,  # Default to my_percentage
)
```

**Step 7: Create Report Config (Optional)**
```python
if friend_percentage or my_own_percentage:
    friend_pct = int(friend_percentage) if friend_percentage else 0
    own_pct = int(my_own_percentage) if my_own_percentage else 0
    
    # Validate: friend % + my own % = my total %
    if friend_pct + own_pct != my_percentage_int:
        messages.warning(
            request,
            f"Friend % ({friend_pct}) + My Own % ({own_pct}) = {friend_pct + own_pct}, "
            f"but My Total % = {my_percentage_int}. Report config not created."
        )
    else:
        ClientExchangeReportConfig.objects.create(
            client_exchange=account,
            friend_percentage=friend_pct,
            my_own_percentage=own_pct,
        )
```

**Step 8: Success Response**
```python
messages.success(request, f"Successfully linked '{client.name}' to '{exchange.name}'.")
return redirect(reverse("client_detail", args=[client.pk]))
```

**Error Handling:**
- Missing required fields: Error message, form re-rendered
- Invalid client/exchange: Error message, form re-rendered
- Invalid percentage format: Error message, form re-rendered
- Percentage out of range: Error message, form re-rendered
- Duplicate link: Error message, form re-rendered
- Report config validation failure: Warning message, account still created

**Code Location:** `core/views.py` lines 2991-3083

---

## 6. FORMS AND VALIDATION

### 6.1 ExchangeForm

**File:** `core/forms.py` lines 22-30

```python
class ExchangeForm(forms.ModelForm):
    """Form for creating/editing exchanges"""
    class Meta:
        model = Exchange
        fields = ['name', 'code']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'field-input'}),
            'code': forms.TextInput(attrs={'class': 'field-input'}),
        }
```

**Note:** This form is defined but not currently used in views (views use raw POST data instead).

**Fields:**
- `name`: TextInput, required (model field has no blank=True)
- `code`: TextInput, optional (model field has blank=True, null=True)

**Validation:**
- Model-level validation: `code` must be unique if provided
- Django form validation: Standard ModelForm validation

### 6.2 ClientExchangeLinkForm

**File:** `core/forms.py` lines 33-96

```python
class ClientExchangeLinkForm(forms.ModelForm):
    """
    Form for linking client to exchange with percentages.
    This is the CONFIGURATION STEP from the document.
    """
    friend_percentage = forms.IntegerField(
        required=False,
        initial=0,
        min_value=0,
        max_value=100,
        widget=forms.NumberInput(attrs={'class': 'field-input'}),
        help_text="Friend/Student percentage (report only)"
    )
    my_own_percentage = forms.IntegerField(
        required=False,
        initial=0,
        min_value=0,
        max_value=100,
        widget=forms.NumberInput(attrs={'class': 'field-input'}),
        help_text="Your own percentage (report only)"
    )
    
    class Meta:
        model = ClientExchangeAccount
        fields = ['client', 'exchange', 'my_percentage']
        widgets = {
            'client': forms.Select(attrs={'class': 'field-input'}),
            'exchange': forms.Select(attrs={'class': 'field-input'}),
            'my_percentage': forms.NumberInput(attrs={'class': 'field-input'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        my_percentage = cleaned_data.get('my_percentage', 0)
        friend_percentage = cleaned_data.get('friend_percentage', 0)
        my_own_percentage = cleaned_data.get('my_own_percentage', 0)
        
        # Validation Rule: Friend % + My Own % = My Total %
        if friend_percentage + my_own_percentage != my_percentage:
            raise ValidationError(
                f"Friend % ({friend_percentage}) + My Own % ({my_own_percentage}) "
                f"must equal My Total % ({my_percentage})"
            )
        
        return cleaned_data
```

**Note:** This form is defined but not currently used in views (views use raw POST data instead).

**Validation Rules:**
1. `my_percentage`: Required, 0-100
2. `friend_percentage`: Optional, 0-100
3. `my_own_percentage`: Optional, 0-100
4. **Custom Validation:** `friend_percentage + my_own_percentage = my_percentage` (if both provided)

---

## 7. URL ROUTING

### 7.1 URL Configuration

**File:** `core/urls.py`

**Exchange-Related URLs:**

```python
# Exchange List
path('exchanges/', views.exchange_list, name='exchange_list'),

# Exchange Create
path('exchanges/create/', views.exchange_create, name='exchange_create'),

# Link Client to Exchange
path('exchanges/link/', views.link_client_to_exchange, name='exchange_link'),

# Exchange Account Detail
path('exchanges/account/<int:pk>/', views.exchange_account_detail, name='exchange_account_detail'),
```

**Code Location:** `core/urls.py` lines 21-24

### 7.2 URL Patterns

| URL Pattern | View Function | Name | Purpose |
|------------|---------------|------|---------|
| `/exchanges/` | `exchange_list` | `exchange_list` | List all exchanges |
| `/exchanges/create/` | `exchange_create` | `exchange_create` | Create new exchange |
| `/exchanges/link/` | `link_client_to_exchange` | `exchange_link` | Link client to exchange |
| `/exchanges/account/<pk>/` | `exchange_account_detail` | `exchange_account_detail` | View account details |

---

## 8. TEMPLATES AND UI COMPONENTS

### 8.1 Exchange List Template

**File:** `core/templates/core/exchanges/list.html`

**Structure:**
```html
{% extends "core/base.html" %}

{% block title %}Exchanges · Transaction Hub{% endblock %}
{% block page_title %}Exchanges{% endblock %}
{% block page_subtitle %}All exchanges configured for all clients{% endblock %}

{% block page_actions %}
    <a href="{% url 'exchange_create' %}" class="btn btn-primary">Add Exchange</a>
    <a href="{% url 'exchange_link' %}" class="btn btn-primary" style="margin-left: 8px;">Link Client to Exchange</a>
{% endblock %}

{% block content %}
<div class="table-wrapper">
    <div class="table-header">
        <div>Total: {{ exchanges|length }} exchanges</div>
    </div>
    <table>
        <thead>
        <tr>
            <th>Exchange Name</th>
            <th>Code</th>
            <th>Status</th>
            <th>Actions</th>
        </tr>
        </thead>
        <tbody>
        {% for exchange in exchanges %}
            <tr>
                <td><strong>{{ exchange.name }}</strong></td>
                <td>{% if exchange.code %}{{ exchange.code }}{% else %}-{% endif %}</td>
                <td>
                    <span class="badge badge-success">Active</span>
                </td>
                <td>
                    <span class="pill">{{ exchange.client_accounts.count }} clients</span>
                </td>
            </tr>
        {% empty %}
            <tr>
                <td colspan="4">No exchanges created yet.</td>
            </tr>
        {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
```

**Key Components:**
- **Page Actions:** Two buttons (Add Exchange, Link Client to Exchange)
- **Table:** Shows exchange name, code, status, client count
- **Empty State:** Message when no exchanges exist

**Code Location:** `core/templates/core/exchanges/list.html` lines 1-46

### 8.2 Exchange Create Template

**File:** `core/templates/core/exchanges/create.html`

**Structure:**
```html
{% extends "core/base.html" %}

{% block title %}Add Exchange · Transaction Hub{% endblock %}
{% block page_title %}Add Exchange{% endblock %}
{% block page_subtitle %}Create a new exchange platform{% endblock %}

{% block content %}
<div class="card" style="max-width: 420px;">
    {% if messages %}
        {% for message in messages %}
            <div style="padding: 12px 16px; border-radius: 8px; margin-bottom: 20px; 
                {% if message.tags == 'success' %}background: #d1fae5; color: #065f46; border: 1px solid #10b981;
                {% elif message.tags == 'error' %}background: #fee2e2; color: #991b1b; border: 1px solid #dc2626;
                {% else %}background: #dbeafe; color: #1e40af; border: 1px solid #3b82f6;{% endif %}">
                {{ message }}
            </div>
        {% endfor %}
    {% endif %}
    
    <form method="post">
        {% csrf_token %}
        <div class="form-row">
            <label class="field-label">Exchange Name *</label>
            <input type="text" name="name" class="field-input" required>
        </div>
        <div class="form-row">
            <label class="field-label">Exchange Code <span style="color: var(--muted); font-weight: normal;">(Optional)</span></label>
            <input type="text" name="code" class="field-input" placeholder="Leave blank if not needed">
        </div>
        <div style="display: flex; gap: 12px; margin-top: 20px;">
            <button type="submit" class="btn btn-primary">Save Exchange</button>
            <a href="{% url 'exchange_list' %}" class="btn">Cancel</a>
        </div>
    </form>
</div>
{% endblock %}
```

**Key Components:**
- **Message Display:** Shows success/error messages with color coding
- **Form Fields:**
  - Exchange Name (required text input)
  - Exchange Code (optional text input)
- **Form Actions:** Submit button, Cancel link

**Code Location:** `core/templates/core/exchanges/create.html` lines 1-33

### 8.3 Link Client to Exchange Template

**File:** `core/templates/core/exchanges/link_to_client.html`

**Structure:**
```html
{% extends "core/base.html" %}

{% block title %}Link Client to Exchange · Transaction Hub{% endblock %}
{% block page_title %}Link Client to Exchange{% endblock %}
{% block page_subtitle %}Configure client-exchange account with percentages{% endblock %}

{% block content %}
<div class="card" style="max-width: 500px;">
    {% if messages %}
        {% for message in messages %}
            <!-- Message display with color coding -->
        {% endfor %}
    {% endif %}
    
    <form method="post">
        {% csrf_token %}
        
        <div class="form-row">
            <label class="field-label">Client *</label>
            <select name="client" class="field-input" required>
                <option value="">-- Select Client --</option>
                {% for client in clients %}
                    <option value="{{ client.pk }}">{{ client.name }}{% if client.code %} ({{ client.code }}){% endif %}</option>
                {% endfor %}
            </select>
        </div>
        
        <div class="form-row">
            <label class="field-label">Exchange *</label>
            <select name="exchange" class="field-input" required>
                <option value="">-- Select Exchange --</option>
                {% for exchange in exchanges %}
                    <option value="{{ exchange.pk }}">{{ exchange.name }}{% if exchange.code %} ({{ exchange.code }}){% endif %}</option>
                {% endfor %}
            </select>
        </div>
        
        <div class="form-row">
            <label class="field-label">My Total % *</label>
            <input type="number" name="my_percentage" class="field-input" min="0" max="100" required>
            <div style="font-size: 13px; color: var(--muted); margin-top: 4px;">
                Your total percentage share (0-100). Used for system logic.
            </div>
        </div>
        
        <div style="border-top: 1px solid var(--border); margin: 20px 0; padding-top: 20px;">
            <div style="font-size: 14px; color: var(--muted); margin-bottom: 12px;">
                <strong>Report Configuration (Optional)</strong><br>
                These percentages are used ONLY for reports, not system logic.
            </div>
            
            <div class="form-row">
                <label class="field-label">Friend % (Report Only)</label>
                <input type="number" name="friend_percentage" class="field-input" min="0" max="100" placeholder="Leave blank if not needed">
                <div style="font-size: 13px; color: var(--muted); margin-top: 4px;">
                    Friend/Student percentage. Must equal: My Total % - My Own %
                </div>
            </div>
            
            <div class="form-row">
                <label class="field-label">My Own % (Report Only)</label>
                <input type="number" name="my_own_percentage" class="field-input" min="0" max="100" placeholder="Leave blank if not needed">
                <div style="font-size: 13px; color: var(--muted); margin-top: 4px;">
                    Your own percentage. Friend % + My Own % must equal My Total %
                </div>
            </div>
        </div>
        
        <button type="submit" class="btn btn-primary mt-3">Link Client to Exchange</button>
        <a href="{% url 'exchange_list' %}" class="btn mt-3" style="margin-left: 8px;">Cancel</a>
    </form>
</div>
{% endblock %}
```

**Key Components:**
- **Required Fields:**
  - Client dropdown (filtered to user's clients)
  - Exchange dropdown (all exchanges)
  - My Total % (0-100)
- **Optional Report Config:**
  - Friend % (report only)
  - My Own % (report only)
  - Visual separator with explanation

**Code Location:** `core/templates/core/exchanges/link_to_client.html` lines 1-75

---

## 9. EDGE CASES AND VALIDATION RULES

### 9.1 Exchange Creation Edge Cases

#### Case 1: Empty Exchange Name
**Scenario:** User submits form with empty name field
**Validation:** HTML5 `required` attribute prevents submission
**Backend Check:** `if name:` check fails
**Result:** Error message "Exchange name is required.", form re-rendered

#### Case 2: Duplicate Exchange Code
**Scenario:** User tries to create exchange with code that already exists
**Validation:** Database unique constraint on `code` field
**Result:** Django raises `IntegrityError`, handled by framework (shows error page)

#### Case 3: Whitespace-Only Name
**Scenario:** User enters only spaces in name field
**Validation:** `.strip()` removes whitespace, then `if name:` check fails
**Result:** Error message "Exchange name is required.", form re-rendered

#### Case 4: Very Long Exchange Name
**Scenario:** User enters name longer than 200 characters
**Validation:** Database `VARCHAR(200)` constraint
**Result:** Database truncation or error (depends on database settings)

#### Case 5: Empty Code Field
**Scenario:** User leaves code field blank
**Validation:** `.strip()` returns empty string, converted to `None`
**Result:** `code` stored as NULL in database (allowed)

**Code Location:** `core/views.py` lines 1910-1921

### 9.2 Client-Exchange Link Edge Cases

#### Case 1: Missing Required Fields
**Scenario:** User submits form without client, exchange, or my_percentage
**Validation:** `if not client_id or not exchange_id or not my_percentage:`
**Result:** Error message "Client, Exchange, and My Total % are required.", form re-rendered

#### Case 2: Invalid Client ID
**Scenario:** User manipulates form to submit non-existent client ID
**Validation:** `Client.objects.get(pk=client_id, user=request.user)`
**Result:** `Client.DoesNotExist` exception, error message "Invalid client or exchange selected."

#### Case 3: Client Not Belonging to User
**Scenario:** User tries to link another user's client
**Validation:** `Client.objects.get(pk=client_id, user=request.user)`
**Result:** `Client.DoesNotExist` exception (filtered by user), error message shown

#### Case 4: Invalid Exchange ID
**Scenario:** User manipulates form to submit non-existent exchange ID
**Validation:** `Exchange.objects.get(pk=exchange_id)`
**Result:** `Exchange.DoesNotExist` exception, error message "Invalid client or exchange selected."

#### Case 5: Percentage Out of Range
**Scenario:** User enters percentage < 0 or > 100
**Validation:** `if my_percentage_int < 0 or my_percentage_int > 100:`
**Result:** Error message "My Total % must be between 0 and 100.", form re-rendered

#### Case 6: Invalid Percentage Format
**Scenario:** User enters non-numeric value in percentage field
**Validation:** `int(my_percentage)` raises `ValueError`
**Result:** Error message "Invalid percentage value. Please enter numbers only."

#### Case 7: Duplicate Client-Exchange Link
**Scenario:** User tries to link same client to same exchange twice
**Validation:** `ClientExchangeAccount.objects.filter(client=client, exchange=exchange).exists()`
**Result:** Error message "Client '{client.name}' is already linked to '{exchange.name}'."

#### Case 8: Report Config Validation Failure
**Scenario:** User enters Friend % + My Own % ≠ My Total %
**Validation:** `if friend_pct + own_pct != my_percentage_int:`
**Result:** Warning message shown, account still created, report config NOT created

#### Case 9: Partial Report Config
**Scenario:** User enters only Friend % or only My Own %
**Validation:** `if friend_percentage or my_own_percentage:`
**Result:** If only one provided, validation fails (sum ≠ my_percentage), warning shown, config not created

#### Case 10: Exchange Deleted After Selection
**Scenario:** User selects exchange, exchange is deleted before form submission
**Validation:** `Exchange.objects.get(pk=exchange_id)` raises `DoesNotExist`
**Result:** Error message "Invalid client or exchange selected."

**Code Location:** `core/views.py` lines 2993-3077

### 9.3 Database Constraint Edge Cases

#### Case 1: Unique Constraint Violation (Client-Exchange Pair)
**Scenario:** Race condition - two requests try to create same link simultaneously
**Validation:** Database unique constraint on `(client_id, exchange_id)`
**Result:** `IntegrityError` raised, handled by Django framework

#### Case 2: Foreign Key Constraint Violation
**Scenario:** Client or Exchange deleted while form is being submitted
**Validation:** Foreign key constraints with CASCADE DELETE
**Result:** If deleted before creation, `DoesNotExist` exception
**If deleted after creation:** Account automatically deleted (CASCADE)

#### Case 3: NULL Code Uniqueness
**Scenario:** Multiple exchanges with NULL code
**Validation:** Database allows multiple NULL values in unique column
**Result:** Multiple exchanges can have NULL code (allowed)

---

## 10. CODE MAPPING REFERENCE

### 10.1 Complete File Structure

```
core/
├── models.py                    # Database models (Exchange, ClientExchangeAccount)
├── views.py                     # View functions (exchange_list, exchange_create, link_client_to_exchange)
├── urls.py                      # URL routing configuration
├── forms.py                     # Form classes (ExchangeForm, ClientExchangeLinkForm)
├── admin.py                     # Django admin configuration
└── templates/
    └── core/
        └── exchanges/
            ├── list.html        # Exchange list page
            ├── create.html      # Create exchange form
            └── link_to_client.html  # Link client to exchange form
```

### 10.2 Model Code Locations

| Model | File | Lines |
|-------|------|-------|
| `Exchange` | `core/models.py` | 36-47 |
| `ClientExchangeAccount` | `core/models.py` | 50-91 |
| `TimeStampedModel` | `core/models.py` | 10-16 |
| `Client` | `core/models.py` | 19-33 |

### 10.3 View Code Locations

| View Function | File | Lines | Purpose |
|---------------|------|-------|---------|
| `exchange_list` | `core/views.py` | 786-791 | List all exchanges |
| `exchange_create` | `core/views.py` | 1908-1926 | Create new exchange |
| `link_client_to_exchange` | `core/views.py` | 2991-3083 | Link client to exchange |
| `exchange_edit` | `core/views.py` | 1932-1943 | Edit existing exchange |
| `exchange_account_detail` | `core/views.py` | 3090+ | View account details |

### 10.4 Template Code Locations

| Template | File | Purpose |
|---------|------|---------|
| Exchange List | `core/templates/core/exchanges/list.html` | Display all exchanges |
| Exchange Create | `core/templates/core/exchanges/create.html` | Create exchange form |
| Link Client to Exchange | `core/templates/core/exchanges/link_to_client.html` | Link form with percentages |

### 10.5 URL Pattern Code Locations

| URL Pattern | File | Line | View Function |
|------------|------|------|---------------|
| `/exchanges/` | `core/urls.py` | 21 | `exchange_list` |
| `/exchanges/create/` | `core/urls.py` | 22 | `exchange_create` |
| `/exchanges/link/` | `core/urls.py` | 23 | `link_client_to_exchange` |
| `/exchanges/account/<pk>/` | `core/urls.py` | 24 | `exchange_account_detail` |

### 10.6 Form Code Locations

| Form Class | File | Lines | Purpose |
|-----------|------|-------|---------|
| `ExchangeForm` | `core/forms.py` | 22-30 | Exchange create/edit form |
| `ClientExchangeLinkForm` | `core/forms.py` | 33-96 | Link client to exchange form |

### 10.7 Database Table Mappings

| Model | Database Table | Primary Key | Unique Constraints |
|-------|----------------|-------------|-------------------|
| `Exchange` | `core_exchange` | `id` | `code` (if not NULL) |
| `ClientExchangeAccount` | `core_clientexchangeaccount` | `id` | `(client_id, exchange_id)` |
| `ClientExchangeReportConfig` | `core_clientexchangereportconfig` | `id` | `client_exchange_id` (one-to-one) |

### 10.8 Key Database Operations

| Operation | Model Method | Code Location |
|-----------|--------------|---------------|
| Create Exchange | `Exchange.objects.create()` | `core/views.py` line 1915 |
| Create Client-Exchange Link | `ClientExchangeAccount.objects.create()` | `core/views.py` line 3035 |
| Check Duplicate Link | `ClientExchangeAccount.objects.filter().exists()` | `core/views.py` line 3024 |
| Create Report Config | `ClientExchangeReportConfig.objects.create()` | `core/views.py` line 3059 |
| List All Exchanges | `Exchange.objects.all().order_by()` | `core/views.py` line 789 |
| Filter User's Clients | `Client.objects.filter(user=request.user)` | `core/views.py` line 3005 |

---

## SUMMARY

### Key Takeaways

1. **Two-Step Process:**
   - First create exchange platform
   - Then link client to exchange with percentages

2. **Data Storage:**
   - Exchange stored in `core_exchange` table
   - Client-exchange link stored in `core_clientexchangeaccount` table
   - Report config (optional) stored in `core_clientexchangereportconfig` table

3. **Initial State:**
   - New accounts start with `funding=0` and `exchange_balance=0`
   - Percentages default to `my_percentage` for both loss and profit

4. **Validation:**
   - Exchange name required, code optional but unique
   - Client-exchange pair must be unique
   - Percentages must be 0-100
   - Report config percentages must sum to My Total %

5. **UI Flow:**
   - Exchange List → Add Exchange → Create Form → Success → Exchange List
   - Exchange List → Link Client → Link Form → Success → Client Detail

6. **Error Handling:**
   - All validation errors shown as messages
   - Forms re-rendered with error messages
   - Database constraints handled by Django framework

---

**Document Version:** 1.0  
**Last Updated:** 2024  
**Related Documentation:** `PENDING_PAYMENTS_COMPLETE_DOCUMENTATION.md`


