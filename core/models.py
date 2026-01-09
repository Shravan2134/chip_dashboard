"""
Database models for Profit-Loss-Share-Settlement System
Following PIN-TO-PIN master document specifications.
"""
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


class TimeStampedModel(models.Model):
    """Abstract base to track created/updated timestamps."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Client(TimeStampedModel):
    """
    Client entity - trades on exchange, receives FULL profit, pays FULL loss.
    """
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, blank=True, null=True, unique=True)
    referred_by = models.CharField(max_length=200, blank=True, null=True)
    is_company_client = models.BooleanField(default=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


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
    
    # CRITICAL FIX: Lock share at first compute per PnL cycle
    # These fields store the locked values when a PnL cycle starts
    locked_initial_final_share = models.BigIntegerField(
        default=0,
        null=True,
        blank=True,
        help_text="Initial FinalShare locked at start of PnL cycle. Used for remaining calculation."
    )
    locked_share_percentage = models.IntegerField(
        default=0,
        null=True,
        blank=True,
        help_text="Share percentage locked at start of PnL cycle. Prevents historical rewrite."
    )
    locked_initial_pnl = models.BigIntegerField(
        default=0,
        null=True,
        blank=True,
        help_text="Initial PnL when share was locked. Used to detect PnL cycle changes."
    )
    cycle_start_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when current PnL cycle started. Used to filter settlements by cycle."
    )
    locked_initial_funding = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Funding amount when share was locked. Used to detect funding changes that should reset cycle."
    )
    
    class Meta:
        unique_together = [['client', 'exchange']]
        ordering = ['client__name', 'exchange__name']
    
    def __str__(self):
        return f"{self.client.name} - {self.exchange.name}"
    
    def compute_client_pnl(self):
        """
        MASTER PROFIT/LOSS FORMULA
        Client_PnL = exchange_balance - funding
        
        Returns: BIGINT (can be negative for loss)
        """
        return self.exchange_balance - self.funding
    
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
            # LOSS: Use loss_share_percentage (or fallback to my_percentage)
            share_pct = self.loss_share_percentage if self.loss_share_percentage > 0 else self.my_percentage
        else:
            # PROFIT: Use profit_share_percentage (or fallback to my_percentage)
            share_pct = self.profit_share_percentage if self.profit_share_percentage > 0 else self.my_percentage
        
        # Exact Share (NO rounding)
        exact_share = abs(client_pnl) * (share_pct / 100.0)
        
        # Final Share (ONLY rounding step) - FLOOR (round down)
        final_share = math.floor(exact_share)
        
        return int(final_share)
    
    def compute_exact_share(self):
        """
        MASKED SHARE SETTLEMENT SYSTEM - Exact Share (before rounding)
        
        Returns: float (exact share before floor rounding)
        """
        client_pnl = self.compute_client_pnl()
        
        if client_pnl == 0:
            return 0.0
        
        # Determine which percentage to use
        if client_pnl < 0:
            share_pct = self.loss_share_percentage if self.loss_share_percentage > 0 else self.my_percentage
        else:
            share_pct = self.profit_share_percentage if self.profit_share_percentage > 0 else self.my_percentage
        
        # Exact Share (NO rounding)
        exact_share = abs(client_pnl) * (share_pct / 100.0)
        
        return exact_share
    
    def lock_initial_share_if_needed(self):
        """
        CRITICAL FIX: Lock InitialFinalShare at first compute per PnL cycle.
        
        This ensures share doesn't shrink after payments.
        Share is decided by trading outcome, not by settlement.
        
        NEW FIX: Funding change should reset cycle (new exposure = new cycle).
        """
        client_pnl = self.compute_client_pnl()
        
        # CRITICAL FIX: Funding change should reset cycle (new exposure = new cycle)
        # If funding changed after cycle was locked, reset the cycle
        if self.locked_initial_final_share is not None:
            # Check if funding tracking exists (new data) or is missing (old data)
            if self.locked_initial_funding is not None:
                # New data: Compare with tracked funding
                if self.funding != self.locked_initial_funding:
                    # Funding changed → new exposure → new cycle
                    # Reset all locks to force new cycle
                    self.locked_initial_final_share = None
                    self.locked_share_percentage = None
                    self.locked_initial_pnl = None
                    self.cycle_start_date = None
                    self.locked_initial_funding = None
                    # Save reset before continuing
                    self.save(update_fields=['locked_initial_final_share', 'locked_share_percentage', 'locked_initial_pnl', 'cycle_start_date', 'locked_initial_funding'])
            else:
                # Old data: locked_initial_funding is None (from before this fix)
                # We can't compare, but we should set it now for future checks
                # However, if current PnL doesn't match locked PnL, it's likely funding changed
                # For safety, if locked_initial_funding is None, we'll set it to current funding
                # This handles migration from old data gracefully
                # But if PnL changed significantly, we should reset
                current_pnl = self.compute_client_pnl()
                if self.locked_initial_pnl is not None:
                    # Check if PnL changed significantly (more than just trading)
                    # If PnL magnitude changed by more than 50%, likely funding changed
                    pnl_diff_ratio = abs(current_pnl) / abs(self.locked_initial_pnl) if self.locked_initial_pnl != 0 else float('inf')
                    if pnl_diff_ratio > 1.5 or pnl_diff_ratio < 0.67:
                        # Significant PnL change → likely funding changed → reset cycle
                        self.locked_initial_final_share = None
                        self.locked_share_percentage = None
                        self.locked_initial_pnl = None
                        self.cycle_start_date = None
                        self.locked_initial_funding = None
                        self.save(update_fields=['locked_initial_final_share', 'locked_share_percentage', 'locked_initial_pnl', 'cycle_start_date', 'locked_initial_funding'])
        
        # If no locked share exists, or PnL cycle changed (sign flip or zero crossing), lock new share
        if self.locked_initial_final_share is None or self.locked_initial_pnl is None:
            # First time - lock the share
            final_share = self.compute_my_share()
            if final_share > 0:
                # Determine which percentage to use
                if client_pnl < 0:
                    share_pct = self.loss_share_percentage if self.loss_share_percentage > 0 else self.my_percentage
                else:
                    share_pct = self.profit_share_percentage if self.profit_share_percentage > 0 else self.my_percentage
                
                self.locked_initial_final_share = final_share
                self.locked_share_percentage = share_pct
                self.locked_initial_pnl = client_pnl
                self.cycle_start_date = timezone.now()  # Track when this cycle started
                self.locked_initial_funding = self.funding  # Track funding when cycle started
                self.save(update_fields=['locked_initial_final_share', 'locked_share_percentage', 'locked_initial_pnl', 'cycle_start_date', 'locked_initial_funding'])
        elif client_pnl != 0 and self.locked_initial_pnl != 0:
            # Check if PnL cycle changed (sign flip)
            if (client_pnl < 0) != (self.locked_initial_pnl < 0):
                # PnL cycle changed - lock new share
                final_share = self.compute_my_share()
                if final_share > 0:
                    if client_pnl < 0:
                        share_pct = self.loss_share_percentage if self.loss_share_percentage > 0 else self.my_percentage
                    else:
                        share_pct = self.profit_share_percentage if self.profit_share_percentage > 0 else self.my_percentage
                    
                    self.locked_initial_final_share = final_share
                    self.locked_share_percentage = share_pct
                    self.locked_initial_pnl = client_pnl
                    self.cycle_start_date = timezone.now()  # NEW CYCLE: Track when this cycle started
                    self.save(update_fields=['locked_initial_final_share', 'locked_share_percentage', 'locked_initial_pnl', 'cycle_start_date'])
        elif client_pnl == 0:
            # PnL is zero - only reset locks if there are no pending settlements
            # CRITICAL FIX: Don't reset locked share if there's still remaining settlement amount
            # CRITICAL FIX: Only count settlements from current cycle
            if self.cycle_start_date:
                cycle_settled = self.settlements.filter(
                    date__gte=self.cycle_start_date
                ).aggregate(
                    total=models.Sum('amount')
                )['total'] or 0
            else:
                cycle_settled = self.settlements.aggregate(
                    total=models.Sum('amount')
                )['total'] or 0
            
            # Only reset if locked share is fully settled (or no locked share exists)
            if self.locked_initial_final_share is None or cycle_settled >= (self.locked_initial_final_share or 0):
                # Fully settled or no share - safe to reset
                self.locked_initial_final_share = None
                self.locked_share_percentage = None
                self.locked_initial_pnl = None
                self.cycle_start_date = None
                self.locked_initial_funding = None
                self.save(update_fields=['locked_initial_final_share', 'locked_share_percentage', 'locked_initial_pnl', 'cycle_start_date', 'locked_initial_funding'])
            # Otherwise, keep the locked share even if PnL is 0 (settlements may have brought it to zero)
    
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
        # When PnL sign changes (LOSS → PROFIT or PROFIT → LOSS), a NEW cycle starts
        # Old cycle settlements must NOT mix with new cycle shares
        if self.cycle_start_date:
            # Only count settlements that occurred AFTER this cycle started
            total_settled = self.settlements.filter(
                date__gte=self.cycle_start_date
            ).aggregate(
                total=models.Sum('amount')
            )['total'] or 0
        else:
            # No cycle start date - count all settlements (backward compatibility)
            total_settled = self.settlements.aggregate(
                total=models.Sum('amount')
            )['total'] or 0
        
        # CRITICAL: Always use locked share - NEVER recalculate from current PnL
        # If locked share doesn't exist, check if we should lock current share
        if self.locked_initial_final_share is not None:
            initial_final_share = self.locked_initial_final_share
        else:
            # No locked share - check if current share > 0 and should be locked
            current_share = self.compute_my_share()
            if current_share > 0:
                # Current share exists but not locked - lock it now
                client_pnl = self.compute_client_pnl()
                if client_pnl < 0:
                    share_pct = self.loss_share_percentage if self.loss_share_percentage > 0 else self.my_percentage
                else:
                    share_pct = self.profit_share_percentage if self.profit_share_percentage > 0 else self.my_percentage
                
                self.locked_initial_final_share = current_share
                self.locked_share_percentage = share_pct
                self.locked_initial_pnl = client_pnl
                self.cycle_start_date = timezone.now()  # Track when this cycle started
                self.locked_initial_funding = self.funding  # Track funding when cycle started
                self.save(update_fields=['locked_initial_final_share', 'locked_share_percentage', 'locked_initial_pnl', 'cycle_start_date', 'locked_initial_funding'])
                initial_final_share = current_share
            else:
                # No locked share and current share is 0 - no settlement possible
                return {
                    'remaining': 0,
                    'overpaid': 0,
                    'initial_final_share': 0,
                    'total_settled': total_settled
                }
        
        # CORRECT FORMULA: Remaining = LockedInitialFinalShare - TotalSettled
        # Share NEVER shrinks - it's locked at initial compute
        remaining = max(0, initial_final_share - total_settled)
        overpaid = max(0, total_settled - initial_final_share)
        
        return {
            'remaining': remaining,
            'overpaid': overpaid,
            'initial_final_share': initial_final_share,
            'total_settled': total_settled
        }
    
    def get_remaining_settlement_amount_legacy(self):
        """
        Legacy method for backward compatibility.
        Returns just the remaining amount (for existing code).
        """
        result = self.get_remaining_settlement_amount()
        return result['remaining']
    
    def clean(self):
        """
        MASKED SHARE SETTLEMENT SYSTEM - Validation
        
        Prevents loss share % changes after data exists.
        """
        from django.core.exceptions import ValidationError
        
        # If this is an existing record (has pk), check if loss share % is being changed
        if self.pk:
            try:
                old_instance = ClientExchangeAccount.objects.get(pk=self.pk)
                # Check if loss share % is being changed
                if old_instance.loss_share_percentage != self.loss_share_percentage:
                    # Check if there are any transactions or settlements
                    has_transactions = self.transactions.exists()
                    has_settlements = self.settlements.exists()
                    
                    if has_transactions or has_settlements:
                        raise ValidationError(
                            "Loss share percentage cannot be changed after data exists. "
                            "Current value: {}, Attempted value: {}".format(
                                old_instance.loss_share_percentage,
                                self.loss_share_percentage
                            )
                        )
            except ClientExchangeAccount.DoesNotExist:
                pass  # New instance, no validation needed
    
    def is_settled(self):
        """
        Check if client PnL is zero (trading flat).
        
        Note: This does NOT mean "settlement complete".
        PnL = 0 can occur from:
        - Trading result (no settlements)
        - Settlement activity
        - Over-settlement + clamp
        
        Use get_remaining_settlement_amount() == 0 to check if settlement is complete.
        """
        return self.compute_client_pnl() == 0


class ClientExchangeReportConfig(TimeStampedModel):
    """
    REPORT CONFIG TABLE - ISOLATED
    
    Used ONLY for reports, NOT for system logic.
    Stores friend/student share percentages.
    """
    client_exchange = models.OneToOneField(
        ClientExchangeAccount,
        on_delete=models.CASCADE,
        related_name='report_config'
    )
    
    # Report-only percentages (INT as per spec)
    friend_percentage = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Friend/Student percentage (report only)"
    )
    my_own_percentage = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Your own percentage (report only)"
    )
    
    class Meta:
        verbose_name = "Report Configuration"
        verbose_name_plural = "Report Configurations"
    
    def __str__(self):
        return f"Report Config: {self.client_exchange}"
    
    def clean(self):
        """Validation: friend_percentage + my_own_percentage = my_percentage"""
        from django.core.exceptions import ValidationError
        
        if self.client_exchange:
            my_total = self.client_exchange.my_percentage
            friend_plus_own = self.friend_percentage + self.my_own_percentage
            
            if friend_plus_own != my_total:
                raise ValidationError(
                    f"Friend % ({self.friend_percentage}) + My Own % ({self.my_own_percentage}) "
                    f"must equal My Total % ({my_total})"
                )
    
    def compute_friend_share(self):
        """
        Friend share formula (report only)
        Friend_Share = ABS(Client_PnL) × friend_percentage / 100
        """
        client_pnl = abs(self.client_exchange.compute_client_pnl())
        return (client_pnl * self.friend_percentage) // 100
    
    def compute_my_own_share(self):
        """
        My own share formula (report only)
        My_Own_Share = ABS(Client_PnL) × my_own_percentage / 100
        """
        client_pnl = abs(self.client_exchange.compute_client_pnl())
        return (client_pnl * self.my_own_percentage) // 100


class Settlement(TimeStampedModel):
    """
    MASKED SHARE SETTLEMENT SYSTEM - Settlement Tracking
    
    Tracks individual settlement payments to prevent over-settlement.
    Each settlement records a partial or full payment of the admin's share.
    """
    client_exchange = models.ForeignKey(
        ClientExchangeAccount,
        on_delete=models.CASCADE,
        related_name='settlements'
    )
    amount = models.BigIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Settlement amount (integer, > 0)"
    )
    date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True, help_text="Optional notes about this settlement")
    
    class Meta:
        ordering = ['-date', '-id']
    
    def __str__(self):
        return f"Settlement: {self.client_exchange} - {self.amount} - {self.date.strftime('%Y-%m-%d')}"


class Transaction(TimeStampedModel):
    """
    TRANSACTIONS TABLE - AUDIT ONLY
    
    Stores transaction history for audit purposes.
    NEVER used to recompute balances.
    """
    TRANSACTION_TYPES = [
        ('FUNDING', 'Funding'),
        ('TRADE', 'Trade'),
        ('FEE', 'Fee'),
        ('ADJUSTMENT', 'Adjustment'),
        ('RECORD_PAYMENT', 'Record Payment'),
    ]
    
    client_exchange = models.ForeignKey(
        ClientExchangeAccount,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    date = models.DateTimeField()
    type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.BigIntegerField(help_text="Amount in smallest currency unit")
    exchange_balance_after = models.BigIntegerField(
        help_text="Exchange balance after this transaction (for audit)"
    )
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-date', '-id']
    
    def __str__(self):
        return f"{self.type} - {self.client_exchange} - {self.date.strftime('%Y-%m-%d')}"
