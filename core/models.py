from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal


class TimeStampedModel(models.Model):
    """Abstract base to track created/updated timestamps."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Client(TimeStampedModel):
    """Represents an end client that receives funds via different exchanges."""

    user = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="clients", null=True, blank=True, help_text="User who owns this client")
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, blank=True, null=True, help_text="Client code (unique per user)")
    referred_by = models.CharField(max_length=255, blank=True, null=True, help_text="Name of person who referred this client")
    is_active = models.BooleanField(default=True)
    is_company_client = models.BooleanField(default=False, help_text="If True, this is a company client. If False, this is your personal client.")
    security_deposit = models.DecimalField(
        max_digits=14, 
        decimal_places=2, 
        default=Decimal('0'), 
        help_text='One-time security deposit paid by company client (only for company clients)'
    )
    security_deposit_paid_date = models.DateField(
        blank=True, 
        null=True, 
        help_text='Date when security deposit was paid (one-time payment)'
    )

    class Meta:
        unique_together = [("user", "code")]  # Code must be unique per user
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["user", "is_company_client"]),
            models.Index(fields=["is_company_client", "is_active"]),
            models.Index(fields=["code"]),  # For client code searches
        ]

    def __str__(self) -> str:
        if self.code:
            return f"{self.name} ({self.code})"
        return self.name


class Exchange(TimeStampedModel):
    """
    Standalone exchange (A, B, C, D, etc.).
    Exchanges are created independently and then linked to clients with specific percentages.
    """

    name = models.CharField(max_length=255, unique=True)
    code = models.CharField(max_length=50, unique=True, blank=True, null=True, help_text="Optional exchange code")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ClientExchange(TimeStampedModel):
    """
    Links a Client to an Exchange with specific my share and company share percentages.
    This allows the same exchange to have different percentages for different clients.
    """

    client = models.ForeignKey(Client, related_name="client_exchanges", on_delete=models.CASCADE)
    exchange = models.ForeignKey(Exchange, related_name="client_exchanges", on_delete=models.CASCADE)

    my_share_pct = models.DecimalField(max_digits=5, decimal_places=2, help_text="Your share of profits (%)")
    company_share_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Company share percentage FROM CLIENT's share (%). Example: If your share is 30% and company share is 9%, company gets 9% of the client's 70% share. Must be less than 100.",
    )

    is_active = models.BooleanField(default=True)
    
    # Cached/denormalized fields for performance optimization
    # These are updated via signals when transactions/balances change
    cached_current_balance = models.DecimalField(
        max_digits=14, 
        decimal_places=2, 
        default=Decimal(0),
        help_text="Cached current exchange balance (updated automatically)"
    )
    cached_old_balance = models.DecimalField(
        max_digits=14, 
        decimal_places=2, 
        default=Decimal(0),
        help_text="Cached old balance after last settlement (updated automatically)"
    )
    cached_total_funding = models.DecimalField(
        max_digits=14, 
        decimal_places=2, 
        default=Decimal(0),
        help_text="Cached total funding amount (updated automatically)"
    )
    balance_last_updated = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Timestamp when cached balance fields were last updated"
    )

    class Meta:
        unique_together = ("client", "exchange")
        ordering = ["client__name", "exchange__name"]
        indexes = [
            models.Index(fields=["client", "is_active"]),
            models.Index(fields=["exchange", "is_active"]),
            models.Index(fields=["is_active"]),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.company_share_pct >= 100:
            raise ValidationError("Company share must be less than 100%")

    def __str__(self) -> str:
        return f"{self.client.name} - {self.exchange.name}"


class Transaction(TimeStampedModel):
    """
    Atomic financial activity per client per exchange.

    This is the core source-of-truth used for:
    - Daily P&L
    - Pending payments (client owes you / you owe client)
    - Time‑travel reporting (snapshots are derived by date filtering)
    """

    TYPE_FUNDING = "FUNDING"
    TYPE_PROFIT = "PROFIT"
    TYPE_LOSS = "LOSS"
    TYPE_SETTLEMENT = "SETTLEMENT"
    TYPE_BALANCE_RECORD = "BALANCE_RECORD"

    TRANSACTION_TYPES = [
        (TYPE_FUNDING, "Funding (You give money to client)"),
        (TYPE_PROFIT, "Profit"),
        (TYPE_LOSS, "Loss"),
        (TYPE_SETTLEMENT, "Settlement / Payout"),
        (TYPE_BALANCE_RECORD, "Balance Record"),
    ]

    client_exchange = models.ForeignKey("ClientExchange", related_name="transactions", on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)

    # Positive values; semantic meaning comes from transaction_type
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    # Computed shares at the time of transaction (denormalized for snapshot consistency)
    client_share_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    your_share_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    company_share_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["client_exchange", "transaction_type"]),
            models.Index(fields=["client_exchange", "date"]),
            models.Index(fields=["transaction_type", "date"]),
            models.Index(fields=["date"]),
            # Composite index for common query pattern: client_exchange + transaction_type + date
            models.Index(fields=["client_exchange", "transaction_type", "date"]),
        ]

    def __str__(self) -> str:
        return f"{self.client_exchange} {self.transaction_type} {self.amount} on {self.date}"
    
    @property
    def exchange(self):
        """Backward compatibility property."""
        return self.client_exchange.exchange
    
    @property
    def client(self):
        """Backward compatibility property."""
        return self.client_exchange.client


class DailyBalanceSnapshot(TimeStampedModel):
    """
    Per client + exchange daily balance snapshot.

    This enables fast time‑travel reporting by date without recomputing
    aggregates across the full history every time.
    """

    client_exchange = models.ForeignKey("ClientExchange", related_name="daily_snapshots", on_delete=models.CASCADE)
    
    @property
    def client(self):
        return self.client_exchange.client
    
    @property
    def exchange(self):
        return self.client_exchange.exchange
    date = models.DateField()

    # Cumulative fields up to and including `date`
    total_funding = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_profit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_loss = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    client_net_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    you_net_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    company_net_profit = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    pending_client_owes_you = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pending_you_owe_client = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        unique_together = ("client_exchange", "date")
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["client_exchange", "date"]),
            models.Index(fields=["date"]),
        ]

    def __str__(self) -> str:
        code_part = f"{self.client_exchange.client.code} " if self.client_exchange.client.code else ""
        return f"Snapshot {code_part}{self.client_exchange.exchange.name} on {self.date}"


class CompanyShareRecord(TimeStampedModel):
    """
    Denormalized record of company share amounts for transparency and reporting.
    """

    client_exchange = models.ForeignKey("ClientExchange", related_name="company_shares", on_delete=models.CASCADE)
    transaction = models.ForeignKey(Transaction, related_name="company_shares", on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)

    company_amount = models.DecimalField(max_digits=14, decimal_places=2)

    def __str__(self) -> str:
        return f"{self.client_exchange} company share {self.company_amount} on {self.date}"


class ClientDailyBalance(TimeStampedModel):
    """
    Manual daily balance record for client-exchange combinations.
    Records the remaining balance in client's account for a specific exchange on a specific date.
    Example: Muktesh's remaining balance in Diamond exchange on 2024-01-15
    """
    client_exchange = models.ForeignKey("ClientExchange", related_name="daily_balances", on_delete=models.CASCADE, null=True, blank=True)
    # Legacy field - will be removed after migration
    client = models.ForeignKey(Client, related_name="daily_balances_legacy", on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateField()
    remaining_balance = models.DecimalField(max_digits=14, decimal_places=2, help_text="Remaining balance in client's account for this exchange")
    extra_adjustment = models.DecimalField(
        max_digits=14, 
        decimal_places=2, 
        default=0,
        help_text="Extra money adjustment if exchange balance is low (positive amount)"
    )
    note = models.TextField(blank=True, help_text="Optional note about the balance")
    
    class Meta:
        unique_together = [("client_exchange", "date"), ("client", "date")]  # Support both during migration
        ordering = ["-date", "client_exchange__exchange__name"]
        verbose_name_plural = "Client Daily Balances"
        indexes = [
            models.Index(fields=["client_exchange", "date"]),
            models.Index(fields=["client", "date"]),  # For legacy support
            models.Index(fields=["date"]),
        ]
    
    @property
    def client_obj(self):
        """Get client from either client_exchange or legacy client field."""
        if self.client_exchange:
            return self.client_exchange.client
        return self.client
    
    @property
    def exchange_obj(self):
        """Get exchange from client_exchange."""
        if self.client_exchange:
            return self.client_exchange.exchange
        return None
    
    def __str__(self):
        if self.client_exchange:
            return f"{self.client_exchange.client.name} - {self.client_exchange.exchange.name} - ₹{self.remaining_balance} on {self.date}"
        elif self.client:
            return f"{self.client.name} - ₹{self.remaining_balance} on {self.date}"
        return f"Balance - ₹{self.remaining_balance} on {self.date}"


class PendingAmount(TimeStampedModel):
    """
    Separate ledger for client's unpaid losses.
    Pending is created only from losses and reduced only when client pays.
    Pending is NOT affected by funding, profit, or profit payout.
    """
    client_exchange = models.ForeignKey("ClientExchange", related_name="pending_amounts", on_delete=models.CASCADE)
    pending_amount = models.DecimalField(
        max_digits=14, 
        decimal_places=2, 
        default=0,
        help_text="Total pending amount (unpaid losses) for this client-exchange"
    )
    note = models.TextField(blank=True, help_text="Optional note about pending amount")
    
    class Meta:
        unique_together = ("client_exchange",)
        verbose_name_plural = "Pending Amounts"
    
    def __str__(self):
        return f"{self.client_exchange} - Pending: ₹{self.pending_amount}"


class OutstandingAmount(TimeStampedModel):
    """
    Netted ledger for MY CLIENTS only.
    Tracks the net payable amount of YOUR SHARE (losses and profits are netted).
    
    Outstanding = Net payable of YOUR SHARE
    - Positive: Client owes you (unpaid loss share) → Client pays you
    - Negative: You owe client (unpaid profit share) → Auto-settles and resets to 0
    - Zero: All settled
    
    This is ONLY for My Clients (not company clients).
    Company clients use PendingAmount (separate ledgers).
    
    Key Logic:
    - Loss: Outstanding += your_share (client owes you more)
    - Profit: Outstanding -= your_share (you owe client less, or client owes you less)
    - If Outstanding < 0: Auto-create settlement (you pay client) and reset to 0
    """
    client_exchange = models.OneToOneField(
        "ClientExchange", 
        related_name="outstanding_amount_ledger", 
        on_delete=models.CASCADE,
        unique=True,
        help_text="One outstanding ledger per client-exchange (My Clients only)"
    )
    outstanding_amount = models.DecimalField(
        max_digits=14, 
        decimal_places=2, 
        default=Decimal(0),
        help_text="Net outstanding amount (Your Share only). Positive = client owes you, negative = you owe client (auto-settles)"
    )
    note = models.TextField(blank=True, help_text="Optional note about outstanding amount")
    
    class Meta:
        verbose_name_plural = "Outstanding Amounts"
    
    def __str__(self):
        return f"{self.client_exchange} - Outstanding: ₹{self.outstanding_amount}"


class TallyLedger(TimeStampedModel):
    """
    Tally ledger for COMPANY CLIENTS only.
    Tracks separate amounts owed between you, client, and company.
    Nothing is paid immediately - we only remember (tally) who owes whom.
    Later, when profit comes, we adjust. At the end, we pay only the difference.
    
    For COMPANY CLIENTS:
    - client_owes_you: Your direct share from losses (e.g., 10% of loss)
    - company_owes_you: Company's portion from losses that you're owed (9% of loss)
    - you_owe_client: Your direct share from profits (e.g., 10% of profit)
    - you_owe_company: Company's portion from profits that you need to pay (9% of profit)
    
    Earnings (not paid, just recorded):
    - Your earnings from losses: 1% of loss (from company share)
    - Your earnings from profits: 1% of profit (from company share)
    
    Final payments are calculated as net amounts:
    - Net to client = you_owe_client - client_owes_you
    - Net to company = you_owe_company - company_owes_you
    """
    client_exchange = models.OneToOneField(
        "ClientExchange",
        related_name="tally_ledger",
        on_delete=models.CASCADE,
        unique=True,
        help_text="One tally ledger per client-exchange (Company Clients only)"
    )
    client_owes_you = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal(0),
        help_text="Client owes you (your direct share from losses, e.g., 10% of loss)"
    )
    company_owes_you = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal(0),
        help_text="Company owes you (company's portion from losses, 9% of loss)"
    )
    you_owe_client = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal(0),
        help_text="You owe client (your direct share from profits, e.g., 10% of profit)"
    )
    you_owe_company = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal(0),
        help_text="You owe company (company's portion from profits, 9% of profit)"
    )
    note = models.TextField(blank=True, help_text="Optional note about tally ledger")
    
    class Meta:
        verbose_name_plural = "Tally Ledgers"
    
    @property
    def net_client_payable(self):
        """Net amount you need to pay client (positive) or client owes you (negative)."""
        return self.you_owe_client - self.client_owes_you
    
    @property
    def net_company_payable(self):
        """Net amount you need to pay company (positive) or company owes you (negative)."""
        return self.you_owe_company - self.company_owes_you
    
    def __str__(self):
        return f"{self.client_exchange} - Client: {self.net_client_payable}, Company: {self.net_company_payable}"


class SystemSettings(models.Model):
    """
    System-wide settings for the transaction hub.
    Singleton pattern - only one settings record should exist.
    """
    
    weekly_report_day = models.IntegerField(
        default=0,
        help_text="Day of week for auto weekly reports (0=Monday, 6=Sunday)",
        choices=[(0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"), (4, "Friday"), (5, "Saturday"), (6, "Sunday")]
    )
    auto_generate_weekly_reports = models.BooleanField(default=False, help_text="Automatically generate weekly reports")
    
    # Loss Share Configuration (Admin & Company EARN from client loss)
    admin_loss_share_pct = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=5.00,
        help_text="Admin share percentage of client loss (admin earns this % of loss)"
    )
    company_loss_share_pct = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=10.00,
        help_text="Company share percentage of client loss (company earns this % of loss)"
    )
    
    # Profit Share Configuration (Admin & Company PAY on client profit)
    admin_profit_share_pct = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=5.00,
        help_text="Admin share percentage of client profit (admin pays this % of profit)"
    )
    company_profit_share_pct = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=10.00,
        help_text="Company share percentage of client profit (company pays this % of profit)"
    )
    
    class Meta:
        verbose_name_plural = "System Settings"
    
    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
    
    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj
    
    def __str__(self) -> str:
        return "System Settings"

