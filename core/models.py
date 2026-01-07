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

    class Meta:
        unique_together = [("user", "code")]  # Code must be unique per user
        indexes = [
            models.Index(fields=["user", "is_active"]),
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
    
    # For SETTLEMENT transactions: capital_closed (audit trail)
    capital_closed = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Capital closed by this settlement (for audit trail, only for SETTLEMENT transactions)"
    )

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
    
    def clean(self):
        """
        Validate transaction before saving.
        
        ✅ FIX ISSUE 6: Prevent SETTLEMENT without active loss.
        """
        from django.core.exceptions import ValidationError
        from .models import LossSnapshot
        
        if self.transaction_type == Transaction.TYPE_SETTLEMENT:
            # Check if active loss exists for this client_exchange
            if not LossSnapshot.objects.filter(
                client_exchange=self.client_exchange,
                is_settled=False
            ).exists():
                raise ValidationError(
                    "Cannot create SETTLEMENT transaction: No active loss exists for this client-exchange. "
                    "A loss must be recorded before settlements can be made."
                )
    
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


class OutstandingAmount(TimeStampedModel):
    """
    Netted ledger for MY CLIENTS only.
    Tracks the net payable amount of YOUR SHARE (losses and profits are netted).
    
    Outstanding = Net payable of YOUR SHARE
    - Positive: Client owes you (unpaid loss share) → Client pays you
    - Negative: You owe client (unpaid profit share) → Auto-settles and resets to 0
    - Zero: All settled
    
    This is ONLY for My Clients.
    
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


class LossSnapshot(TimeStampedModel):
    """
    Frozen snapshot of loss state for a client-exchange.
    
    🔒 CRITICAL: LOSS is FROZEN at creation time and NEVER recalculated.
    Only SETTLEMENT transactions can reduce the frozen loss amount.
    
    Key Rules:
    1. Only ONE active LossSnapshot per client_exchange (is_settled=False)
    2. Loss amount is frozen - never recalculated from Old Balance - Current Balance
    3. Current Balance is frozen - new balance records don't affect loss calculations
    4. Share percentages are frozen - historical correctness guaranteed
    5. Loss reduced ONLY by SETTLEMENT transactions
    """
    client_exchange = models.ForeignKey(
        "ClientExchange",
        related_name="loss_snapshots",
        on_delete=models.CASCADE,
        help_text="Client-exchange combination this loss snapshot belongs to"
    )
    balance_record = models.ForeignKey(
        "ClientDailyBalance",
        related_name="loss_snapshots",
        on_delete=models.PROTECT,
        help_text="Frozen balance record at time of loss creation (CB is frozen)"
    )
    loss_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="ORIGINAL frozen loss amount - IMMUTABLE, NEVER changed after creation"
    )
    my_share_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Frozen my share percentage at loss creation time"
    )
    is_settled = models.BooleanField(
        default=False,
        help_text="True when loss is fully settled (remaining_loss = 0)"
    )
    note = models.TextField(
        blank=True,
        help_text="Optional note about this loss snapshot"
    )
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["client_exchange", "is_settled"]),
            models.Index(fields=["is_settled"]),
        ]
        constraints = [
            # HARD DB constraint: Only ONE active (is_settled=False) LossSnapshot per client_exchange
            models.UniqueConstraint(
                fields=["client_exchange"],
                condition=models.Q(is_settled=False),
                name="one_active_loss_per_exchange"
            )
        ]
    
    def __str__(self):
        status = "Settled" if self.is_settled else "Active"
        return f"{self.client_exchange} - Loss: ₹{self.loss_amount} ({status})"
    
    def get_remaining_loss(self):
        """
        Calculate remaining loss from original frozen loss minus all settlements.
        
        🔒 CRITICAL: LossSnapshot.loss_amount is IMMUTABLE (original loss).
        Remaining loss is DERIVED from settlements, never stored.
        
        ✅ FIX: Uses transaction date (not created_at) to handle backdated settlements.
        
        Returns:
            Decimal: Remaining loss amount
        """
        from .models import Transaction
        from django.db.models import Sum
        
        # Get total capital closed from all SETTLEMENT transactions for this loss
        # ✅ FIX: Use transaction date (not created_at) to handle backdated settlements
        # ✅ CRITICAL: Only count transactions with dates (date__isnull=False)
        # Only count settlements that occurred on or after the loss snapshot date
        total_capital_closed = Transaction.objects.filter(
            client_exchange=self.client_exchange,
            transaction_type=Transaction.TYPE_SETTLEMENT,
            capital_closed__isnull=False,
            date__isnull=False,  # ✅ CRITICAL: Only count transactions with dates
            date__gte=self.balance_record.date  # Use transaction date, not created_at
        ).aggregate(total=Sum("capital_closed"))["total"] or Decimal(0)
        
        # ✅ CRITICAL: Ensure all values are Decimal (prevents int/float mixing)
        total_capital_closed = Decimal(str(total_capital_closed))
        loss_amount = Decimal(str(self.loss_amount))
        
        return max(self.loss_amount - total_capital_closed, Decimal(0))
    
    def clean(self):
        from django.core.exceptions import ValidationError
        # Guard: Only one active loss snapshot per client_exchange
        if not self.is_settled:
            existing = LossSnapshot.objects.filter(
                client_exchange=self.client_exchange,
                is_settled=False
            ).exclude(pk=self.pk if self.pk else None)
            if existing.exists():
                raise ValidationError("Only one active LossSnapshot allowed per client_exchange")


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

