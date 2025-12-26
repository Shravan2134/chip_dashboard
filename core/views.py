from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import json

from django.contrib.auth import logout, login, authenticate
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum, Count, F
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .models import Client, Exchange, ClientExchange, Transaction, CompanyShareRecord, SystemSettings, ClientDailyBalance, OutstandingAmount


def get_exchange_balance(client_exchange, as_of_date=None):
    """
    Get exchange balance (separate ledger) as of a specific date.
    Exchange balance = latest recorded balance + extra adjustment up to as_of_date.
    
    Args:
        client_exchange: ClientExchange instance
        as_of_date: Optional date to calculate as of. If None, uses current state.
    """
    balance_filter = {"client_exchange": client_exchange}
    if as_of_date:
        balance_filter["date__lte"] = as_of_date
    
    latest_balance_record = ClientDailyBalance.objects.filter(**balance_filter).order_by("-date").first()
    
    if latest_balance_record:
        return latest_balance_record.remaining_balance + (latest_balance_record.extra_adjustment or Decimal(0))
    else:
        # If no balance recorded, start with total funding up to as_of_date
        funding_filter = {"client_exchange": client_exchange, "transaction_type": Transaction.TYPE_FUNDING}
        if as_of_date:
            funding_filter["date__lte"] = as_of_date
        total_funding = Transaction.objects.filter(**funding_filter).aggregate(total=Sum("amount"))["total"] or Decimal(0)
        return total_funding


def get_old_balance_after_settlement(client_exchange, as_of_date=None):
    """
    Get Old Balance for MY CLIENTS - balance after the last settlement.
    
    📘 MY CLIENTS – OLD BALANCE CALCULATION
    
    BUSINESS RULES:
    1. Old Balance is NEVER set manually - calculated automatically from transactions
    2. IF no SETTLEMENT transaction exists:
       Old Balance = SUM of all FUNDING transactions
    3. IF one or more SETTLEMENT transactions exist:
       Old Balance = balance recorded immediately AFTER the latest settlement
                   + SUM of FUNDING transactions AFTER that settlement
    4. LOSS, PROFIT, and BALANCE_RECORD transactions MUST NOT affect Old Balance
    5. Old Balance must NEVER be 0 if at least one FUNDING exists and no settlement exists
    
    Args:
        client_exchange: ClientExchange instance (must be My Client)
        as_of_date: Optional date to calculate as of. If None, uses current state.
    
    Returns:
        Old Balance (balance after last settlement + funding after settlement, or total funding if no settlement)
    """
    if client_exchange.client.is_company_client:
        # Company clients don't use this logic
        return get_old_balance(client_exchange, balance_record_date=as_of_date)
    
    # Step 1: Find the last SETTLEMENT transaction before/on as_of_date
    # Only check SETTLEMENT transactions - ignore LOSS, PROFIT, BALANCE_RECORD
    settlement_query = Transaction.objects.filter(
        client_exchange=client_exchange,
        transaction_type=Transaction.TYPE_SETTLEMENT  # Exact match: "SETTLEMENT"
    )
    if as_of_date:
        settlement_query = settlement_query.filter(date__lte=as_of_date)
    
    last_settlement = settlement_query.order_by("-date", "-created_at").first()
    
    if last_settlement:
        # Settlement exists - calculate balance from transactions as of settlement date
        # CRITICAL: Do NOT use BALANCE_RECORD or ClientDailyBalance - only use transactions
        # BALANCE_RECORD is ONLY for showing current exchange balance, NOT for Old Balance
        # CRITICAL: Old Balance is ONLY affected by FUNDING and SETTLEMENT - NOT by PROFIT or LOSS
        
        # Get all FUNDING transactions up to and including settlement date
        funding_up_to_settlement = Transaction.objects.filter(
            client_exchange=client_exchange,
            transaction_type=Transaction.TYPE_FUNDING,  # Exact match: "FUNDING"
            date__lte=last_settlement.date
        ).aggregate(total=Sum("amount"))["total"] or Decimal(0)
        
        # Get all SETTLEMENT transactions up to and including settlement date
        # Settlements affect Old Balance:
        # - If admin receives (your_share_amount > 0): reduces Old Balance (client paid you)
        # - If admin pays (client_share_amount > 0, your_share_amount = 0): increases Old Balance (you paid client)
        settlements_up_to_settlement = Transaction.objects.filter(
            client_exchange=client_exchange,
            transaction_type=Transaction.TYPE_SETTLEMENT,  # Exact match: "SETTLEMENT"
            date__lte=last_settlement.date
        )
        
        # Calculate net settlement impact on Old Balance
        # If admin receives: your_share_amount > 0 (client pays admin) → reduces Old Balance
        # If admin receives: your_share_amount > 0 (client pays admin) → reduces Old Balance
        settlement_received = settlements_up_to_settlement.filter(
            your_share_amount__gt=0  # Admin receives, client pays
        ).aggregate(total=Sum("your_share_amount"))["total"] or Decimal(0)
        
        # If admin pays: client_share_amount > 0, your_share_amount = 0 (admin pays client) → increases Old Balance
        settlement_paid = settlements_up_to_settlement.filter(
            client_share_amount__gt=0,
            your_share_amount=0  # Admin pays, client receives
        ).aggregate(total=Sum("client_share_amount"))["total"] or Decimal(0)
        
        # Balance immediately AFTER settlement = Funding - Settlements where admin received + Settlements where admin paid
        # This represents the Old Balance right after the last settlement
        base_old_balance = funding_up_to_settlement - settlement_received + settlement_paid
        
        # DEBUG: Print all funding and settlement transactions used
        funding_txns = list(Transaction.objects.filter(
            client_exchange=client_exchange,
            transaction_type=Transaction.TYPE_FUNDING,
            date__lte=last_settlement.date
        ).values('date', 'amount', 'id', 'transaction_type'))
        settlement_txns = list(settlements_up_to_settlement.values('date', 'amount', 'your_share_amount', 'client_share_amount', 'id', 'transaction_type'))
        print(f"[DEBUG] Old Balance Calculation for {client_exchange.client.name} - {client_exchange.exchange.name}:")
        print(f"  - Settlement found: {last_settlement.date} (ID: {last_settlement.id}, Amount: {last_settlement.amount})")
        print(f"  - All SETTLEMENT transactions up to settlement: {settlement_txns}")
        print(f"  - All FUNDING transactions up to settlement: {funding_txns}")
        print(f"  - Funding total: {funding_up_to_settlement}")
        print(f"  - Settlement received (admin gets): {settlement_received}")
        print(f"  - Settlement paid (admin pays): {settlement_paid}")
        print(f"  - Base Old Balance (Funding - Settlement Received + Settlement Paid): {base_old_balance}")
        
        # Step 2: Add funding AFTER settlement (Funding After Settlement rule)
        # Only count FUNDING transactions - ignore LOSS, PROFIT, BALANCE_RECORD
        funding_after_query = Transaction.objects.filter(
            client_exchange=client_exchange,
            transaction_type=Transaction.TYPE_FUNDING,  # Exact match: "FUNDING"
            date__gt=last_settlement.date  # Funding AFTER settlement (strictly after)
        )
        if as_of_date:
            funding_after_query = funding_after_query.filter(date__lte=as_of_date)
        
        funding_after_settlement = funding_after_query.aggregate(total=Sum("amount"))["total"] or Decimal(0)
        
        # DEBUG: Print funding after settlement
        funding_after_txns = list(funding_after_query.values('date', 'amount', 'id', 'transaction_type'))
        print(f"  - Funding transactions after settlement: {funding_after_txns}")
        print(f"  - Funding after settlement total: {funding_after_settlement}")
        
        final_old_balance = base_old_balance + funding_after_settlement
        print(f"  - Final Old Balance: {final_old_balance}")
        
        # Old Balance = Base Old Balance + Funding After Settlement
        return final_old_balance
    else:
        # No settlement exists - Old Balance = SUM of ALL FUNDING transactions
        # Only count FUNDING transactions - ignore LOSS, PROFIT, BALANCE_RECORD
        funding_query = Transaction.objects.filter(
            client_exchange=client_exchange,
            transaction_type=Transaction.TYPE_FUNDING  # Exact match: "FUNDING"
        )
        if as_of_date:
            funding_query = funding_query.filter(date__lte=as_of_date)
        
        total_funding = funding_query.aggregate(total=Sum("amount"))["total"] or Decimal(0)
        
        # DEBUG: Print all funding transactions
        funding_txns = list(funding_query.values('date', 'amount', 'id', 'transaction_type'))
        settlement_check = Transaction.objects.filter(
            client_exchange=client_exchange,
            transaction_type=Transaction.TYPE_SETTLEMENT
        )
        if as_of_date:
            settlement_check = settlement_check.filter(date__lte=as_of_date)
        settlement_txns = list(settlement_check.values('date', 'amount', 'id', 'transaction_type'))
        
        print(f"[DEBUG] Old Balance Calculation for {client_exchange.client.name} - {client_exchange.exchange.name} (NO SETTLEMENT):")
        print(f"  - No settlement found (checked {len(settlement_txns)} settlement transactions)")
        print(f"  - Settlement transactions checked: {settlement_txns}")
        print(f"  - All FUNDING transactions: {funding_txns}")
        print(f"  - Total FUNDING: {total_funding}")
        
        # Ensure Old Balance is NEVER 0 if at least one FUNDING exists
        # This is a safety check - if funding exists but sum is 0, something is wrong
        if total_funding == 0:
            # Double-check: maybe there's a date issue, try without date filter
            all_funding_query = Transaction.objects.filter(
                client_exchange=client_exchange,
                transaction_type=Transaction.TYPE_FUNDING  # Exact match: "FUNDING"
            )
            all_funding = all_funding_query.aggregate(total=Sum("amount"))["total"] or Decimal(0)
            all_funding_txns = list(all_funding_query.values('date', 'amount', 'id', 'transaction_type'))
            print(f"  - WARNING: Date filter returned 0, checking all funding: {all_funding_txns}")
            print(f"  - All funding total: {all_funding}")
            if all_funding > 0:
                # Funding exists but was excluded by date filter - use all funding
                print(f"  - Using all funding (date filter issue): {all_funding}")
                return all_funding
        
        print(f"  - Final Old Balance: {total_funding}")
        return total_funding


def get_old_balance(client_exchange, balance_record_date=None, balance_record_created_at=None, current_balance=None, combined_share=None, combined_share_pct=None):
    """
    Get the exchange balance immediately BEFORE a profit/loss event.
    
    📘 OLD BALANCE CALCULATION (Final Rules)
    
    Definition: Old Balance = Exchange balance immediately BEFORE the profit/loss event
    This is a time-based value, not a derived percentage value.
    
    🚫 WHAT OLD BALANCE IS NOT (VERY IMPORTANT):
    - ❌ NOT latest balance
    - ❌ NOT current exchange balance
    - ❌ NOT pending amount
    - ❌ NOT share amount
    - ❌ NOT (current + share)
    - ❌ NOT including future funding
    
    ✅ FORMULA (GENERAL):
    Step 1: Identify the event date (D) - The date of LOSS or PROFIT or Balance Record
    Step 2: Find the last balance record before date D
            LastBalanceBeforeD = latest BALANCE_RECORD where record.date < D
            If it exists → use it
            If not → fallback to funding
    Step 3: Find total funding before date D
            FundingBeforeD = SUM(FUNDING.amount) where funding.date < D
    Step 4: Compute OLD BALANCE
            IF LastBalanceBeforeD exists:
                Old Balance = LastBalanceBeforeD.amount
            ELSE:
                Old Balance = FundingBeforeD
    
    🟢 PROFIT / 🔴 LOSS DOES NOT CHANGE OLD BALANCE FORMULA:
    The same Old Balance formula applies for:
    - Profit case
    - Loss case
    - My Client
    - Company Client
    Only the difference sign changes.
    
    🧮 DIFFERENCE (AFTER OLD BALANCE):
    Once Old Balance is known:
    Difference = Current Balance - Old Balance
    - If Difference > 0 → PROFIT (you pay share)
    - If Difference < 0 → LOSS (client pays share)
    
    ⚠️ SPECIAL REVERSE FORMULA (LOSS ONLY — OPTIONAL):
    Use ONLY if Old Balance cannot be found from history:
    100% Loss = CombinedShare ÷ CombinedShare%
    Old Balance = Current Balance + 100% Loss
    ❌ Never use this for profit
    ❌ Never use if history exists
    
    🧠 ONE-LINE RULE:
    Old Balance comes from the PAST, never from the CURRENT state.
    
    Args:
        client_exchange: ClientExchange instance
        balance_record_date: Date of the profit/loss event (D). If None, uses the latest balance record date.
        balance_record_created_at: Optional datetime when the balance record was created (for ordering)
        current_balance: Optional current balance (for reverse calculation in LOSS case only)
        combined_share: Optional combined share amount (for reverse calculation in LOSS case only)
        combined_share_pct: Optional combined share percentage (for reverse calculation in LOSS case only)
    
    Returns:
        Old balance (the exchange balance just before the profit/loss event - always 100% exchange money)
        
    Examples:
        - Event date = Dec 1, Last balance before Dec 1 = ₹100 → Old Balance = ₹100
        - Event date = Dec 1, No balance before, Funding before Dec 1 = ₹100 → Old Balance = ₹100
        - For LOSS reverse: Current = ₹120, Combined Share = ₹5.5, Share % = 11%, Old Balance = ₹170
    """
    # If no date specified, get the latest balance record
    if balance_record_date is None:
        latest_balance = ClientDailyBalance.objects.filter(
            client_exchange=client_exchange
        ).order_by("-date", "-created_at").first()
        
        if latest_balance:
            balance_record_date = latest_balance.date
            balance_record_created_at = latest_balance.created_at
        else:
            # No balance records exist, calculate from transactions
            return get_exchange_balance(client_exchange)
    
    # Convert date string to date object if needed
    if isinstance(balance_record_date, str):
        balance_record_date = date.fromisoformat(balance_record_date)
    
    # Find the previous balance record (the one immediately before this one)
    # Order by date descending, then created_at descending
    previous_balance_query = ClientDailyBalance.objects.filter(
        client_exchange=client_exchange
    ).order_by("-date", "-created_at")
    
    # If we have created_at, filter to get records before this one
    if balance_record_created_at:
        previous_balance_query = previous_balance_query.filter(
            Q(date__lt=balance_record_date) | 
            Q(date=balance_record_date, created_at__lt=balance_record_created_at)
        )
    else:
        # Just filter by date
        previous_balance_query = previous_balance_query.filter(date__lt=balance_record_date)
    
    previous_balance = previous_balance_query.first()
    
    if previous_balance:
        # Return the balance from the previous record
        # Previous balance already reflects all transactions up to that point
        return previous_balance.remaining_balance + (previous_balance.extra_adjustment or Decimal(0))
    else:
        # No previous balance record exists, calculate from transactions up to this date
        # This handles the case where this is the first balance record
        # Old Balance = Total funding up to that moment (100% exchange money)
        if balance_record_date:
            # Calculate total funding BEFORE this date (not including this date)
            # Old Balance = Total funding (100% exchange money before play)
            # We use ONLY funding, not profit/loss, because:
            # - Funding is the actual money given
            # - Profit/Loss transactions are created FROM balance changes, not before
            # IMPORTANT: Use date < D (strictly before), not date <= D
            funding_filter = {
                "client_exchange": client_exchange,
                "transaction_type": Transaction.TYPE_FUNDING,
                "date__lt": balance_record_date  # Strictly before event date D
            }
            
            total_funding = Transaction.objects.filter(**funding_filter).aggregate(total=Sum("amount"))["total"] or Decimal(0)
            
            # Old Balance = Total funding (100% exchange money)
            # This is the pure exchange money before any profit/loss occurred
            old_balance = total_funding
            
            # SPECIAL CASE: Reverse formula for LOSS ONLY (when old balance not available from funding)
            # This is a fallback when we have current balance and combined share but no funding record
            if old_balance == 0 and current_balance is not None and combined_share is not None and combined_share_pct is not None:
                # This is LOSS case (current balance < old balance would be)
                # Reverse formula: Old Balance = Current Balance + 100% Loss
                # where 100% Loss = Combined Share ÷ Combined Share %
                if combined_share > 0 and combined_share_pct > 0:
                    loss_100_percent = combined_share / (combined_share_pct / Decimal(100))
                    old_balance = current_balance + loss_100_percent
                    old_balance = old_balance.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            
            return old_balance
        else:
            # No date specified, use get_exchange_balance (which handles current state)
            return get_exchange_balance(client_exchange)


def update_outstanding_from_balance_change(client_exchange, old_balance, current_balance, balance_date=None):
    """
    Update Outstanding ledger for MY CLIENTS (netted system).
    
    📘 MY CLIENTS – OUTSTANDING CALCULATION
    
    Outstanding = Net payable of YOUR SHARE
    - Calculated from: Difference = Current Balance - Old Balance
    - My Share = My Share % × Difference
    - Loss (Difference < 0): Outstanding += your_share (client owes you)
    - Profit (Difference > 0): Outstanding -= your_share (you owe client)
    
    ❌ NO AUTO-SETTLEMENT - settlements must be explicit
    
    This is ONLY for My Clients. Company clients use Tally Ledger.
    
    Args:
        client_exchange: ClientExchange instance (must be My Client)
        old_balance: Old Balance (balance after last settlement)
        current_balance: Current Balance (latest balance from exchange)
        balance_date: Date of the balance record (optional)
    
    Returns:
        dict with:
        - your_share: Your share amount (positive for loss, negative for profit)
        - outstanding_before: Outstanding amount before update
        - outstanding_after: Outstanding amount after update
        - difference: Current Balance - Old Balance
    """
    if client_exchange.client.is_company_client:
        # Company clients don't use outstanding ledger
        return {
            "your_share": Decimal(0),
            "outstanding_before": Decimal(0),
            "outstanding_after": Decimal(0),
            "difference": Decimal(0),
        }
    
    # Get or create outstanding record
    outstanding, _ = OutstandingAmount.objects.get_or_create(
        client_exchange=client_exchange,
        defaults={"outstanding_amount": Decimal(0)}
    )
    
    outstanding_before = outstanding.outstanding_amount
    
    # Calculate difference: Current Balance - Old Balance
    difference = current_balance - old_balance
    
    # Calculate your share
    my_share_pct = client_exchange.my_share_pct
    your_share = (difference * my_share_pct) / Decimal(100)
    
    if difference < 0:
        # Loss: Outstanding increases (client owes you more)
        outstanding.outstanding_amount += abs(your_share)
        your_share = abs(your_share)  # Return positive for loss
    elif difference > 0:
        # Profit: Outstanding decreases (you owe client)
        outstanding.outstanding_amount -= abs(your_share)
        your_share = -abs(your_share)  # Return negative for profit
    else:
        # No change
        your_share = Decimal(0)
    
    outstanding_after = outstanding.outstanding_amount
    outstanding.save()
    
    return {
        "your_share": your_share,
        "outstanding_before": outstanding_before,
        "outstanding_after": outstanding_after,
        "difference": difference,
    }


def create_loss_profit_from_balance_change(client_exchange, old_balance, new_balance, balance_date, note_suffix=""):
    """
    Create LOSS or PROFIT transaction from balance movement.
    
    🔐 GOLDEN RULE: Payment ALWAYS happens ONLY on SHARE, never on full profit or full loss.
    - Client loss → client pays ONLY share
    - Client profit → you pay ONLY share
    - For company clients: Share is split internally (1% you, 9% company)
    
    Args:
        client_exchange: ClientExchange instance
        old_balance: Balance before the change
        new_balance: Balance after the change
        balance_date: Date of the balance record
        note_suffix: Optional suffix for transaction note
    
    Returns:
        Transaction object if created, None otherwise
    """
    balance_difference = new_balance - old_balance
    
    if balance_difference < 0:
        # LOSS: Balance decreased
        loss_amount = abs(balance_difference)
        loss_amount = loss_amount.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        
        # Calculate shares for LOSS
        my_share_pct = client_exchange.my_share_pct
        
        # STEP 1: Calculate TOTAL SHARE (this is what client pays)
        # Total Share = my_share_pct% of loss (e.g., 10% of 90 = ₹9)
        total_share = (loss_amount * my_share_pct) / Decimal(100)
        total_share = total_share.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        
        # STEP 2: For company clients, split that share internally
        if client_exchange.client.is_company_client:
            # My cut = 1% of loss
            your_cut = (loss_amount * Decimal(1)) / Decimal(100)
            your_cut = your_cut.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            
            # Company cut = 9% of loss
            company_cut = (loss_amount * Decimal(9)) / Decimal(100)
            company_cut = company_cut.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            
            # Verify: your_cut + company_cut should equal total_share
            # (This ensures we're splitting the share, not calculating separately)
        else:
            # My clients: you get the full share
            your_cut = total_share
            company_cut = Decimal(0)
        
        # Create LOSS transaction
        # client_share_amount = Total Share (what client pays)
        # your_share_amount = Your cut (1% for company clients, full share for my clients)
        # company_share_amount = Company cut (9% for company clients, 0 for my clients)
        return Transaction.objects.create(
            client_exchange=client_exchange,
            date=balance_date,
            transaction_type=Transaction.TYPE_LOSS,
            amount=loss_amount,
            client_share_amount=total_share,  # Client pays ONLY this share amount
            your_share_amount=your_cut,  # Your cut from the share
            company_share_amount=company_cut,  # Company cut from the share
            note=f"Loss from balance movement: ₹{old_balance} → ₹{new_balance} (Balance Record{note_suffix})",
        )
        
    elif balance_difference > 0:
        # PROFIT: Balance increased
        profit_amount = balance_difference
        profit_amount = profit_amount.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        
        # Calculate shares for PROFIT
        my_share_pct = client_exchange.my_share_pct
        
        # STEP 1: Calculate TOTAL SHARE (this is what you pay to client)
        # Total Share = my_share_pct% of profit (e.g., 10% of 990 = ₹99)
        total_share = (profit_amount * my_share_pct) / Decimal(100)
        total_share = total_share.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        
        # STEP 2: For company clients, split that share internally
        if client_exchange.client.is_company_client:
            # My cut = 1% of profit
            your_cut = (profit_amount * Decimal(1)) / Decimal(100)
            your_cut = your_cut.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            
            # Company cut = 9% of profit
            company_cut = (profit_amount * Decimal(9)) / Decimal(100)
            company_cut = company_cut.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            
            # Verify: your_cut + company_cut should equal total_share
            # (This ensures we're splitting the share, not calculating separately)
        else:
            # My clients: you pay the full share
            your_cut = total_share
            company_cut = Decimal(0)
        
        # Create PROFIT transaction
        # client_share_amount = Total Share (what client receives)
        # your_share_amount = Your cut (1% for company clients, full share for my clients)
        # company_share_amount = Company cut (9% for company clients, 0 for my clients)
        return Transaction.objects.create(
            client_exchange=client_exchange,
            date=balance_date,
            transaction_type=Transaction.TYPE_PROFIT,
            amount=profit_amount,
            client_share_amount=total_share,  # Client receives ONLY this share amount
            your_share_amount=your_cut,  # Your cut from the share
            company_share_amount=company_cut,  # Company cut from the share
            note=f"Profit from balance movement: ₹{old_balance} → ₹{new_balance} (Balance Record{note_suffix})",
        )
    
    return None  # No change


def update_tally_from_balance_change(client_exchange, previous_balance, new_balance):
    """
    Update Tally Ledger for COMPANY CLIENTS (tally system - no immediate payments).
    
    🔐 GOLDEN RULE: Payment ALWAYS happens ONLY on SHARE, never on full profit or full loss.
    - Client loss → client pays ONLY share
    - Client profit → you pay ONLY share
    - For company clients: Share is split internally (1% you, 9% company)
    
    Tracks separate amounts:
    - client_owes_you: Total share from losses (what client owes)
    - company_owes_you: Company's portion from losses (9% of loss)
    - you_owe_client: Total share from profits (what you owe client)
    - you_owe_company: Company's portion from profits (9% of profit)
    
    Earnings (recorded but not paid):
    - Your earnings from losses: 1% of loss (from company share)
    - Your earnings from profits: 1% of profit (from company share)
    
    Args:
        client_exchange: ClientExchange instance (must be Company Client)
        previous_balance: Exchange balance before the change
        new_balance: Exchange balance after the change
    
    Returns:
        dict with tally updates
    """
    from core.models import TallyLedger
    
    if not client_exchange.client.is_company_client:
        # My Clients don't use tally ledger
        return {
            "client_owes_you": Decimal(0),
            "company_owes_you": Decimal(0),
            "you_owe_client": Decimal(0),
            "you_owe_company": Decimal(0),
            "your_earnings": Decimal(0),
        }
    
    # Get or create tally ledger
    tally, _ = TallyLedger.objects.get_or_create(
        client_exchange=client_exchange,
        defaults={
            "client_owes_you": Decimal(0),
            "company_owes_you": Decimal(0),
            "you_owe_client": Decimal(0),
            "you_owe_company": Decimal(0),
        }
    )
    
    my_share_pct = client_exchange.my_share_pct
    
    if new_balance < previous_balance:
        # LOSS: Client owes you
        loss = previous_balance - new_balance
        
        # STEP 1: Calculate TOTAL SHARE (this is what client owes)
        # Total Share = my_share_pct% of loss (e.g., 10% of 90 = ₹9)
        total_share = (loss * my_share_pct) / Decimal(100)
        tally.client_owes_you += total_share
        
        # STEP 2: Split that share internally
        # My cut = 1% of loss
        your_cut = (loss * Decimal(1)) / Decimal(100)
        # Company cut = 9% of loss
        company_cut = (loss * Decimal(9)) / Decimal(100)
        
        tally.company_owes_you += company_cut
        
        your_earnings = your_cut
        
        print(f"Tally updated for LOSS: Loss={loss}, Total Share={total_share}, "
              f"Your Cut={your_cut}, Company Cut={company_cut}")
        
    elif new_balance > previous_balance:
        # PROFIT: You owe client
        profit = new_balance - previous_balance
        
        # STEP 1: Calculate TOTAL SHARE (this is what you owe client)
        # Total Share = my_share_pct% of profit (e.g., 10% of 990 = ₹99)
        total_share = (profit * my_share_pct) / Decimal(100)
        tally.you_owe_client += total_share
        
        # STEP 2: Split that share internally
        # My cut = 1% of profit
        your_cut = (profit * Decimal(1)) / Decimal(100)
        # Company cut = 9% of profit
        company_cut = (profit * Decimal(9)) / Decimal(100)
        
        tally.you_owe_company += company_cut
        
        your_earnings = your_cut
        
        print(f"Tally updated for PROFIT: Profit={profit}, Total Share={total_share}, "
              f"Your Cut={your_cut}, Company Cut={company_cut}")
    else:
        # No change
        your_earnings = Decimal(0)
    
    tally.save()
    
    return {
        "client_owes_you": tally.client_owes_you,
        "company_owes_you": tally.company_owes_you,
        "you_owe_client": tally.you_owe_client,
        "you_owe_company": tally.you_owe_company,
        "your_earnings": your_earnings,
        "net_client_payable": tally.net_client_payable,
        "net_company_payable": tally.net_company_payable,
    }


def calculate_client_profit_loss(client_exchange, as_of_date=None):
    """
    Calculate client profit/loss based on separate ledgers:
    - Total funding (chips given)
    - Current exchange balance
    - Pending amount (separate, unpaid losses)
    
    Args:
        client_exchange: ClientExchange instance
        as_of_date: Optional date to calculate as of (for time-travel). If None, uses current state.
    
    Returns:
        dict with:
        - total_funding: Total money given to client (turnover)
        - exchange_balance: Current exchange balance
        - client_profit_loss: Exchange balance change (profit if positive, loss if negative)
        - is_profit: Boolean indicating if client is in profit
        - latest_balance_record: Latest ClientDailyBalance record
    """
    # Filter transactions up to as_of_date if provided
    funding_filter = {"client_exchange": client_exchange, "transaction_type": Transaction.TYPE_FUNDING}
    if as_of_date:
        funding_filter["date__lte"] = as_of_date
    
    # Get total funding (turnover = chips given) up to as_of_date
    total_funding = Transaction.objects.filter(**funding_filter).aggregate(total=Sum("amount"))["total"] or Decimal(0)
    
    # Get latest balance record up to as_of_date
    balance_filter = {"client_exchange": client_exchange}
    if as_of_date:
        balance_filter["date__lte"] = as_of_date
    latest_balance_record = ClientDailyBalance.objects.filter(**balance_filter).order_by("-date").first()
    
    # Get exchange balance as of date
    if as_of_date:
        exchange_balance = get_exchange_balance(client_exchange, as_of_date=as_of_date)
    else:
        exchange_balance = get_exchange_balance(client_exchange)
    
    # Calculate profit/loss (exchange balance change from funding)
    client_profit_loss = exchange_balance - total_funding
    is_profit = client_profit_loss > 0
    
    return {
        "total_funding": total_funding,
        "exchange_balance": exchange_balance,
        "client_profit_loss": client_profit_loss,
        "is_profit": is_profit,
        "latest_balance_record": latest_balance_record,
    }


def calculate_admin_profit_loss(client_profit_loss, settings, admin_profit_share_pct=None, client_exchange=None):
    """
    Calculate admin profit/loss and company share based on client profit/loss.
    
    🔐 GOLDEN RULE: Payment ALWAYS happens ONLY on SHARE, never on full profit or full loss.
    - Client loss → client pays ONLY share
    - Client profit → you pay ONLY share
    - For company clients: Share is split internally (1% you, 9% company)
    
    Args:
        client_profit_loss: Client's profit (positive) or loss (negative)
        settings: SystemSettings instance
        admin_profit_share_pct: Optional admin profit share percentage. If None, uses settings.admin_profit_share_pct
        client_exchange: Optional ClientExchange instance for company share calculation
    
    Returns:
        dict with:
        - admin_earns: Admin earnings on client loss (if client in loss) - your cut from share
        - admin_pays: Admin payment on client profit (if client in profit) - your cut from share
        - company_earns: Company earnings on client loss - company cut from share
        - company_pays: Company payment on client profit - company cut from share
        - admin_net: Net amount for admin (earns - pays)
        - admin_profit_share_pct_used: The percentage actually used for calculation
        - Legacy fields for backward compatibility
    """
    # Use provided admin_profit_share_pct or fall back to settings
    if admin_profit_share_pct is None:
        admin_profit_share_pct = settings.admin_profit_share_pct
    else:
        admin_profit_share_pct = Decimal(str(admin_profit_share_pct))
    
    if client_profit_loss < 0:
        # Client in LOSS - Client pays ONLY share
        client_loss = abs(client_profit_loss)
        
        # STEP 1: Calculate TOTAL SHARE (this is what client pays)
        # Total Share = admin_profit_share_pct% of loss (e.g., 10% of 90 = ₹9)
        total_share = (client_loss * admin_profit_share_pct) / Decimal(100)
        
        # STEP 2: For company clients, split that share internally
        if client_exchange and client_exchange.client.is_company_client:
            # My cut = 1% of loss
            your_cut = (client_loss * Decimal(1)) / Decimal(100)
            # Company cut = 9% of loss
            company_cut = (client_loss * Decimal(9)) / Decimal(100)
        else:
            # For my clients: you get the full share
            your_cut = total_share
            company_cut = Decimal(0)
        
        return {
            "admin_earns": your_cut,  # Your cut from share
            "admin_pays": Decimal(0),
            "company_earns": company_cut,  # Company cut from share
            "company_pays": Decimal(0),
            "admin_net": your_cut,  # Admin earns, no deduction
            "admin_bears": Decimal(0),  # No loss when client is in loss
            "admin_profit_share_pct_used": admin_profit_share_pct,
            # Legacy fields for backward compatibility
            "admin_profit": your_cut,
            "admin_loss": Decimal(0),
            "company_share_profit": company_cut,
            "company_share_loss": Decimal(0),
        }
    else:
        # Client in PROFIT - You pay ONLY share
        client_profit = client_profit_loss
        
        # STEP 1: Calculate TOTAL SHARE (this is what you pay to client)
        # Total Share = admin_profit_share_pct% of profit (e.g., 10% of 990 = ₹99)
        total_share = (client_profit * admin_profit_share_pct) / Decimal(100)
        
        # STEP 2: For company clients, split that share internally
        if client_exchange and client_exchange.client.is_company_client:
            # My cut = 1% of profit
            your_cut = (client_profit * Decimal(1)) / Decimal(100)
            # Company cut = 9% of profit
            company_cut = (client_profit * Decimal(9)) / Decimal(100)
        else:
            # For my clients: you pay the full share
            your_cut = total_share
            company_cut = Decimal(0)
        
        return {
            "admin_earns": Decimal(0),
            "admin_pays": your_cut,  # Your cut from share
            "company_earns": Decimal(0),
            "company_pays": company_cut,  # Company cut from share
            "admin_net": -your_cut,  # Negative because admin pays
            "admin_bears": your_cut,  # Amount admin pays (company pays separately)
            "admin_profit_share_pct_used": admin_profit_share_pct,
            # Legacy fields for backward compatibility
            "admin_profit": Decimal(0),
            "admin_loss": your_cut,
            "company_share_profit": Decimal(0),
            "company_share_loss": company_cut,
        }


def login_view(request):
    """Login view."""
    if request.user.is_authenticated:
        return redirect("dashboard")
    
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect("dashboard")
        else:
            return render(request, "core/auth/login.html", {
                "error": "Invalid username or password."
            })
    
    return render(request, "core/auth/login.html")


def logout_view(request):
    """Logout view that redirects to login."""
    logout(request)
    return redirect("login")


@login_required
def dashboard(request):
    """Minimal dashboard view summarizing key metrics with filters."""

    today = date.today()

    # Filters
    client_id = request.GET.get("client")
    exchange_id = request.GET.get("exchange")
    search_query = request.GET.get("search", "")
    # Get client_type from GET (to update session) or from session
    client_type_filter = request.GET.get("client_type") or request.session.get('client_type_filter', 'all')
    if client_type_filter == '':
        client_type_filter = 'all'
    
    # Base queryset
    transactions_qs = Transaction.objects.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").filter(client_exchange__client__user=request.user)
    
    # Filter by client type (company or my clients)
    if client_type_filter == "company":
        transactions_qs = transactions_qs.filter(client_exchange__client__is_company_client=True)
    elif client_type_filter == "my":
        transactions_qs = transactions_qs.filter(client_exchange__client__is_company_client=False)
    
    if client_id:
        transactions_qs = transactions_qs.filter(client_exchange__client_id=client_id)
    if exchange_id:
        transactions_qs = transactions_qs.filter(client_exchange__exchange_id=exchange_id)
    if search_query:
        transactions_qs = transactions_qs.filter(
            Q(client_exchange__client__name__icontains=search_query) |
            Q(client_exchange__client__code__icontains=search_query) |
            Q(client_exchange__exchange__name__icontains=search_query)
        )

    total_turnover = transactions_qs.aggregate(total=Sum("amount"))["total"] or 0
    your_profit = (
        transactions_qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))[
            "total"
        ]
        or 0
    )
    company_profit = (
        transactions_qs.aggregate(total=Sum("company_share_amount"))["total"] or 0
    )

    # Pending sections removed - no longer using PendingAmount model
    pending_clients_owe = Decimal(0)
    
    # You owe clients = client profit shares minus settlements where admin paid client
    # This tracks unpaid profit shares that admin needs to pay out
    profit_qs = Transaction.objects.filter(transaction_type=Transaction.TYPE_PROFIT, client_exchange__client__user=request.user)
    settlement_qs = Transaction.objects.filter(
        client_exchange__client__user=request.user,
        transaction_type=Transaction.TYPE_SETTLEMENT,
        client_share_amount__gt=0,  # Admin pays client
        your_share_amount=0  # Admin pays, doesn't receive
    )
    
    if client_id:
        profit_qs = profit_qs.filter(client_exchange__client_id=client_id)
        settlement_qs = settlement_qs.filter(client_exchange__client_id=client_id)
    elif client_type_filter == "company":
        profit_qs = profit_qs.filter(client_exchange__client__is_company_client=True)
        settlement_qs = settlement_qs.filter(client_exchange__client__is_company_client=True)
    elif client_type_filter == "my":
        profit_qs = profit_qs.filter(client_exchange__client__is_company_client=False)
        settlement_qs = settlement_qs.filter(client_exchange__client__is_company_client=False)
    
    total_client_profit_shares = profit_qs.aggregate(total=Sum("client_share_amount"))["total"] or Decimal(0)
    total_settlements_paid = settlement_qs.aggregate(total=Sum("client_share_amount"))["total"] or Decimal(0)
    pending_you_owe_clients = max(Decimal(0), total_client_profit_shares - total_settlements_paid)

    # Filter clients list by type
    clients_qs = Client.objects.filter(user=request.user, is_active=True)
    if client_type_filter == "company":
        clients_qs = clients_qs.filter(is_company_client=True)
    elif client_type_filter == "my":
        clients_qs = clients_qs.filter(is_company_client=False)
    
    # Active clients count (filtered by type)
    active_clients_count = clients_qs.count()
    
    # Calculate current balance for selected client(s) and exchange
    current_balance = Decimal(0)
    has_transactions = False
    
    if client_id:
        # Single client selected
        client = Client.objects.filter(pk=client_id, user=request.user).first()
        if client:
            if exchange_id:
                # Specific exchange selected - show balance for that exchange only
                client_exchange = client.client_exchanges.filter(exchange_id=exchange_id).first()
                if client_exchange:
                    # Check if there are any transactions for this exchange
                    has_transactions = Transaction.objects.filter(client_exchange=client_exchange).exists()
                    if has_transactions:
                        current_balance = get_exchange_balance(client_exchange)
            else:
                # No exchange selected - calculate total balance across all exchanges
                client_exchanges = client.client_exchanges.all()
                for ce in client_exchanges:
                    # Only include exchanges that have transactions
                    if Transaction.objects.filter(client_exchange=ce).exists():
                        has_transactions = True
                        current_balance += get_exchange_balance(ce)
    elif client_type_filter:
        # Filtered by client type
        filtered_clients = clients_qs
        for client in filtered_clients:
            if exchange_id:
                # Specific exchange selected
                client_exchange = client.client_exchanges.filter(exchange_id=exchange_id).first()
                if client_exchange:
                    if Transaction.objects.filter(client_exchange=client_exchange).exists():
                        has_transactions = True
                        current_balance += get_exchange_balance(client_exchange)
            else:
                # All exchanges
                client_exchanges = client.client_exchanges.all()
                for ce in client_exchanges:
                    if Transaction.objects.filter(client_exchange=ce).exists():
                        has_transactions = True
                        current_balance += get_exchange_balance(ce)

    context = {
        "today": today,
        "total_turnover": total_turnover,
        "your_profit": your_profit,
        "company_profit": company_profit,
        "pending_clients_owe": pending_clients_owe,
        "pending_you_owe_clients": pending_you_owe_clients,
        "active_clients_count": active_clients_count,
        "total_exchanges_count": Exchange.objects.count(),
        "recent_transactions": transactions_qs[:10],
        "all_clients": clients_qs.order_by("name"),
        "all_exchanges": Exchange.objects.filter(is_active=True).order_by("name"),
        "selected_client": int(client_id) if client_id else None,
        "selected_exchange": int(exchange_id) if exchange_id else None,
        "search_query": search_query,
        "client_type_filter": client_type_filter,
        "current_balance": current_balance,
        "has_transactions": has_transactions,
    }
    return render(request, "core/dashboard.html", context)


@login_required
def client_list(request):
    """List all clients (both company and my clients)"""
    client_search = request.GET.get("client_search", "")
    exchange_id = request.GET.get("exchange", "")
    
    clients = Client.objects.filter(user=request.user).order_by("name")
    
    # Filter by client name or code
    if client_search:
        clients = clients.filter(
            Q(name__icontains=client_search) | Q(code__icontains=client_search)
        )
    
    # Filter by exchange
    if exchange_id:
        clients = clients.filter(
            client_exchanges__exchange_id=exchange_id
        ).distinct()
    
    # Get all exchanges for dropdown
    all_exchanges = Exchange.objects.filter(is_active=True).order_by("name")
    
    return render(request, "core/clients/list.html", {
        "clients": clients,
        "client_search": client_search,
        "selected_exchange": int(exchange_id) if exchange_id else None,
        "all_exchanges": all_exchanges,
        "client_type": "all",
    })


def company_clients_list(request):
    """List only company clients"""
    client_search = request.GET.get("client_search", "")
    exchange_id = request.GET.get("exchange", "")
    
    clients = Client.objects.filter(user=request.user, is_company_client=True).order_by("name")
    
    # Filter by client name or code
    if client_search:
        clients = clients.filter(
            Q(name__icontains=client_search) | Q(code__icontains=client_search)
        )
    
    # Filter by exchange
    if exchange_id:
        clients = clients.filter(
            client_exchanges__exchange_id=exchange_id
        ).distinct()
    
    # Get all exchanges for dropdown
    all_exchanges = Exchange.objects.filter(is_active=True).order_by("name")
    
    return render(request, "core/clients/list.html", {
        "clients": clients,
        "client_search": client_search,
        "selected_exchange": int(exchange_id) if exchange_id else None,
        "all_exchanges": all_exchanges,
        "client_type": "company",
    })


@login_required
@login_required
def my_clients_list(request):
    """List only my (personal) clients"""
    client_search = request.GET.get("client_search", "")
    exchange_id = request.GET.get("exchange", "")
    
    clients = Client.objects.filter(user=request.user, is_company_client=False).order_by("name")
    
    # Filter by client name or code
    if client_search:
        clients = clients.filter(
            Q(name__icontains=client_search) | Q(code__icontains=client_search)
        )
    
    # Filter by exchange
    if exchange_id:
        clients = clients.filter(
            client_exchanges__exchange_id=exchange_id
        ).distinct()
    
    # Get all exchanges for dropdown
    all_exchanges = Exchange.objects.filter(is_active=True).order_by("name")
    
    return render(request, "core/clients/list.html", {
        "clients": clients,
        "client_search": client_search,
        "selected_exchange": int(exchange_id) if exchange_id else None,
        "all_exchanges": all_exchanges,
        "client_type": "my",
    })


@login_required
def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk, user=request.user)
    active_client_exchanges = client.client_exchanges.select_related("exchange").filter(is_active=True).all()
    inactive_client_exchanges = client.client_exchanges.select_related("exchange").filter(is_active=False).all()
    transactions = (
        Transaction.objects.filter(client_exchange__client=client)
        .select_related("client_exchange", "client_exchange__exchange")
        .order_by("-date", "-created_at")[:50]
    )
    # Determine client type for URL namespace
    client_type = "company" if client.is_company_client else "my"
    return render(
        request,
        "core/clients/detail.html",
        {
            "client": client,
            "client_exchanges": active_client_exchanges,
            "inactive_client_exchanges": inactive_client_exchanges,
            "transactions": transactions,
            "client_type": client_type,
        },
    )


@login_required
def client_give_money(request, client_pk):
    """
    Give money to a client for a specific exchange (FUNDING transaction).
    Funding ONLY increases exchange balance. It does NOT affect pending.
    """
    client = get_object_or_404(Client, pk=client_pk, user=request.user)
    
    if request.method == "POST":
        client_exchange_id = request.POST.get("client_exchange")
        tx_date = request.POST.get("date")
        amount = Decimal(request.POST.get("amount", 0) or 0).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        note = request.POST.get("note", "")
        
        if client_exchange_id and tx_date and amount > 0:
            client_exchange = get_object_or_404(ClientExchange, pk=client_exchange_id, client=client)
            
            # Get current exchange balance
            current_balance = get_exchange_balance(client_exchange)
            
            # Create FUNDING transaction
            transaction = Transaction.objects.create(
                client_exchange=client_exchange,
                date=datetime.strptime(tx_date, "%Y-%m-%d").date(),
                transaction_type=Transaction.TYPE_FUNDING,
                amount=amount,
                client_share_amount=amount,  # Client gets the full amount
                your_share_amount=Decimal(0),
                company_share_amount=Decimal(0),
                note=note,
            )
            
            # Update exchange balance by creating/updating balance record
            # Funding increases exchange balance
            new_balance = current_balance + amount
            ClientDailyBalance.objects.update_or_create(
                client_exchange=client_exchange,
                date=datetime.strptime(tx_date, "%Y-%m-%d").date(),
                defaults={
                    "remaining_balance": new_balance,
                    "extra_adjustment": Decimal(0),
                    "note": note or f"Funding: +₹{amount}",
                }
            )
            
            # Funding does NOT affect pending (separate ledger)
            
            # Redirect to appropriate namespace based on client type
            if client.is_company_client:
                return redirect(reverse("company_clients:detail", args=[client.pk]))
            else:
                return redirect(reverse("my_clients:detail", args=[client.pk]))
    
    # If GET or validation fails, redirect back to client detail
    if client.is_company_client:
        return redirect(reverse("company_clients:detail", args=[client.pk]))
    else:
        return redirect(reverse("my_clients:detail", args=[client.pk]))


@login_required
def settle_payment(request):
    """
    Handle two types of settlements:
    1. Client pays pending amount (reduces pending - partial or full payment allowed)
    2. Admin pays client profit (doesn't affect pending)
    
    Partial payments are fully supported - client can pay any amount up to pending.
    
    NOTE: This action is only allowed for current date, not for time-travel views.
    """
    if request.method == "POST":
        client_id = request.POST.get("client_id")
        client_exchange_id = request.POST.get("client_exchange_id")
        amount = Decimal(request.POST.get("amount", 0) or 0).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        tx_date = request.POST.get("date")
        note = request.POST.get("note", "")
        payment_type = request.POST.get("payment_type", "client_pays")  # client_pays or admin_pays_profit
        
        # Get report_type and client_type from POST or GET to preserve them in redirect
        report_type = request.POST.get("report_type") or request.GET.get("report_type", "weekly")
        client_type_filter = request.POST.get("client_type") or request.GET.get("client_type") or request.session.get('client_type_filter', 'all')
        if client_type_filter == '':
            client_type_filter = 'all'
        
        # Update session to preserve client_type_filter for navigation bar
        request.session['client_type_filter'] = client_type_filter
        
        # Debug logging
        print(f"settle_payment POST data: client_id={client_id}, client_exchange_id={client_exchange_id}, amount={amount}, tx_date={tx_date}, payment_type={payment_type}")
        print(f"All POST data: {dict(request.POST)}")
        
        if client_id and client_exchange_id and amount > 0 and tx_date:
            try:
                client = get_object_or_404(Client, pk=client_id, user=request.user)
                client_exchange = get_object_or_404(ClientExchange, pk=client_exchange_id, client=client)
                
                # payment_type should be either "client_pays" or "admin_pays_profit"
                if payment_type == "client_pays":
                    # For MY CLIENTS: Use Outstanding (netted system)
                    # For COMPANY CLIENTS: Use Tally Ledger
                    if not client_exchange.client.is_company_client:
                        # My Clients: Use Outstanding ledger
                        outstanding, _ = OutstandingAmount.objects.get_or_create(
                            client_exchange=client_exchange,
                            defaults={"outstanding_amount": Decimal(0)}
                        )
                        current_outstanding = outstanding.outstanding_amount
                        current_pending = current_outstanding  # For compatibility with rest of code
                    else:
                        # Company Clients: Use Tally Ledger (no pending amount)
                        from core.models import TallyLedger
                        tally, _ = TallyLedger.objects.get_or_create(
                            client_exchange=client_exchange,
                            defaults={
                                "client_owes_you": Decimal(0),
                                "company_owes_you": Decimal(0),
                                "you_owe_client": Decimal(0),
                                "you_owe_company": Decimal(0),
                            }
                        )
                        # For company clients, calculate from tally
                        current_pending = tally.net_client_payable
                    
                    # For MY CLIENTS: Outstanding is already the net payable amount (netted)
                    # For COMPANY CLIENTS: Calculate from losses
                    if not client_exchange.client.is_company_client:
                        # My Clients: Outstanding is the net amount (already netted losses and profits)
                        # No need to calculate from losses - just use outstanding directly
                        my_share_from_loss = current_outstanding  # Outstanding IS the net payable
                        company_share_from_loss = Decimal(0)
                    else:
                        # Company Clients: Calculate from losses (separate ledgers)
                        # Get total loss from LOSS transactions
                        loss_transactions = Transaction.objects.filter(
                            client_exchange=client_exchange,
                            transaction_type=Transaction.TYPE_LOSS
                        )
                        total_loss = loss_transactions.aggregate(total=Sum("amount"))["total"] or Decimal(0)
                        
                        # Calculate total loss from transactions only
                        if total_loss == 0:
                            settlement_transactions = Transaction.objects.filter(
                                client_exchange=client_exchange,
                                transaction_type=Transaction.TYPE_SETTLEMENT,
                                client_share_amount=0,
                                your_share_amount__gt=0
                            )
                            settlements_paid = settlement_transactions.aggregate(total=Sum("your_share_amount"))["total"] or Decimal(0)
                            total_loss = current_pending + settlements_paid
                        
                        # Calculate Company Share from total loss (NEW RULE)
                        # Company Share = Total × 10% (company_share_pct should be 10)
                        # Your Cut from Company = Total × 1%
                        # Company Net = Total × 9%
                        company_share_pct = client_exchange.company_share_pct
                        company_share_total = (total_loss * company_share_pct) / Decimal(100)  # Should be 10% of total
                        your_cut_from_company = (total_loss * Decimal(1)) / Decimal(100)  # Always 1% of total
                        company_net = company_share_total - your_cut_from_company  # Should be 9% of total
                        
                        # For company clients: Combined share = Your Cut from Company (1% of total)
                        my_share_from_loss = your_cut_from_company  # Your cut is 1% of total
                        company_share_from_loss = company_share_total  # Company share total is 10% of total
                    
                    # For MY CLIENTS: Use Outstanding (netted system)
                    # Outstanding = Net payable of Your Share (already netted losses and profits)
                    if not client_exchange.client.is_company_client:
                        # My clients: Payment reduces Outstanding
                        # Outstanding is already the net amount (losses netted against profits)
                        my_share_amount = min(amount, current_outstanding)  # Can't pay more than outstanding
                        company_share_amount = Decimal(0)
                        
                        # Round to 2 decimal places
                        my_share_amount = my_share_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        
                        # Reduce Outstanding by payment
                        outstanding.outstanding_amount = max(Decimal(0), current_outstanding - my_share_amount)
                        outstanding.save()
                        
                        # Update current_pending for message display
                        current_pending = outstanding.outstanding_amount
                    else:
                        # Company clients: Payment split according to NEW RULE
                        # Client pays: Company Share Total (10% of total loss)
                        # Split: Your Cut (1% of total) + Company Net (9% of total)
                        # Payment is split 1:9 (Your Cut : Company Net)
                        from core.models import TallyLedger
                        tally, _ = TallyLedger.objects.get_or_create(
                            client_exchange=client_exchange,
                            defaults={
                                "client_owes_you": Decimal(0),
                                "company_owes_you": Decimal(0),
                                "you_owe_client": Decimal(0),
                                "you_owe_company": Decimal(0),
                            }
                        )
                        payment_amount = min(amount, tally.net_client_payable)  # Don't allow overpayment
                        
                        # Split payment: Your Cut (1%) vs Company Net (9%) = 1:9 ratio
                        # So Your Cut gets 1/10 of payment, Company Net gets 9/10 of payment
                        if company_share_from_loss > 0:
                            # Your cut ratio = 1% / 10% = 0.1 (you get 10% of company share payment)
                            your_cut_ratio = Decimal(1) / Decimal(10)  # Always 1:9 split
                            my_share_amount = payment_amount * your_cut_ratio  # You get 1/10 of payment
                            company_share_amount = payment_amount * (Decimal(9) / Decimal(10))  # Company gets 9/10 of payment
                        else:
                            # Fallback if no company share
                            my_share_amount = Decimal(0)
                            company_share_amount = Decimal(0)
                        
                        # Round to 2 decimal places
                        my_share_amount = my_share_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        company_share_amount = company_share_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        
                        # For company clients, update tally ledger
                        if client_exchange.client.is_company_client:
                            from core.models import TallyLedger
                            tally, _ = TallyLedger.objects.get_or_create(
                                client_exchange=client_exchange,
                                defaults={
                                    "client_owes_you": Decimal(0),
                                    "company_owes_you": Decimal(0),
                                    "you_owe_client": Decimal(0),
                                    "you_owe_company": Decimal(0),
                                }
                            )
                            # Reduce client_owes_you by payment amount
                            tally.client_owes_you = max(Decimal(0), tally.client_owes_you - payment_amount)
                            tally.save()
                            current_pending = tally.net_client_payable
                    
                    # Create SETTLEMENT transaction for client payment
                    # Record My Share and Company Share separately
                    if not client_exchange.client.is_company_client:
                        # My clients: Only record My Share (reduces Outstanding)
                        note_text = note or f"Client payment: Outstanding ₹{my_share_amount}. Remaining outstanding: ₹{current_pending}"
                        success_msg = f"Payment of ₹{my_share_amount} recorded for {client.name} - {client_exchange.exchange.name}. Remaining outstanding: ₹{current_pending}"
                        transaction_amount = my_share_amount
                    else:
                        # Company clients: Record both shares
                        from core.models import TallyLedger
                        tally, _ = TallyLedger.objects.get_or_create(
                            client_exchange=client_exchange,
                            defaults={
                                "client_owes_you": Decimal(0),
                                "company_owes_you": Decimal(0),
                                "you_owe_client": Decimal(0),
                                "you_owe_company": Decimal(0),
                            }
                        )
                        remaining_net = tally.net_client_payable
                        note_text = note or f"Client payment: My Share ₹{my_share_amount} + Company Share ₹{company_share_amount}. Remaining net: ₹{remaining_net}"
                        success_msg = f"Payment of ₹{my_share_amount + company_share_amount} recorded (My Share: ₹{my_share_amount}, Company Share: ₹{company_share_amount}) for {client.name} - {client_exchange.exchange.name}. Remaining net: ₹{remaining_net}"
                        transaction_amount = my_share_amount + company_share_amount
                    
                    transaction = Transaction.objects.create(
                        client_exchange=client_exchange,
                        date=datetime.strptime(tx_date, "%Y-%m-%d").date(),
                        transaction_type=Transaction.TYPE_SETTLEMENT,
                        amount=transaction_amount,
                        client_share_amount=Decimal(0),  # Client pays, so negative for client
                        your_share_amount=my_share_amount,  # Admin receives My Share
                        company_share_amount=company_share_amount,  # Company receives Company Share (0 for my clients)
                        note=note_text,
                    )
                    
                    from django.contrib import messages
                    messages.success(request, success_msg)
                    
                    # Ensure session is saved before redirect
                    request.session.modified = True
                    
                    redirect_url = f"?section=clients-owe&report_type={report_type}"
                    if client_type_filter and client_type_filter != 'all':
                        redirect_url += f"&client_type={client_type_filter}"
                    return redirect(reverse("pending:summary") + redirect_url)
                elif payment_type == "admin_pays_profit":
                    # Admin pays client profit - doesn't affect pending or exchange balance
                    # Round amount to 1 decimal place
                    amount = amount.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                    
                    # Create SETTLEMENT transaction where admin pays client
                    transaction = Transaction.objects.create(
                        client_exchange=client_exchange,
                        date=datetime.strptime(tx_date, "%Y-%m-%d").date(),
                        transaction_type=Transaction.TYPE_SETTLEMENT,
                        amount=amount,
                        client_share_amount=amount,  # Client receives
                        your_share_amount=Decimal(0),  # Admin pays, doesn't receive
                        company_share_amount=Decimal(0),
                        note=note or f"Admin payment for client profit",
                    )
                    
                    from django.contrib import messages
                    messages.success(request, f"Payment of ₹{amount} recorded successfully for {client.name} - {client_exchange.exchange.name}")
                    
                    # Ensure session is saved before redirect
                    request.session.modified = True
                    
                    redirect_url = f"?section=you-owe&report_type={report_type}"
                    if client_type_filter and client_type_filter != 'all':
                        redirect_url += f"&client_type={client_type_filter}"
                    return redirect(reverse("pending:summary") + redirect_url)
                else:
                    # Invalid payment type
                    from django.contrib import messages
                    messages.error(request, f"Invalid payment type: {payment_type}")
                    redirect_url = f"?section=you-owe&report_type={report_type}"
                    if client_type_filter:
                        redirect_url += f"&client_type={client_type_filter}"
                    return redirect(reverse("pending:summary") + redirect_url)
            except Exception as e:
                # Log error and redirect with error message
                import traceback
                from django.contrib import messages
                error_msg = f"Error recording payment: {str(e)}"
                # Log full traceback for debugging
                print(f"Error in settle_payment: {traceback.format_exc()}")
                messages.error(request, error_msg)
                # Determine which section to redirect to based on payment type
                section = "you-owe" if payment_type == "admin_pays_profit" else "clients-owe"
                
                # Ensure session is saved before redirect
                request.session.modified = True
                
                redirect_url = f"?section={section}&report_type={report_type}"
                if client_type_filter and client_type_filter != 'all':
                    redirect_url += f"&client_type={client_type_filter}"
                return redirect(reverse("pending:summary") + redirect_url)
    
    # If GET or validation fails, redirect to pending summary
    report_type = request.GET.get("report_type", "weekly")
    return redirect(reverse("pending:summary") + f"?report_type={report_type}")


@login_required
def client_create(request):
    """Legacy view - redirects to appropriate create view based on context"""
    # Default to my clients if no context
    return redirect(reverse("clients:add_my"))


@login_required
def company_client_create(request):
    """Create a company client"""
    if request.method == "POST":
        name = request.POST.get("name")
        code = request.POST.get("code", "").strip()
        referred_by = request.POST.get("referred_by", "").strip()
        if name:
            client = Client.objects.create(
                user=request.user,
                name=name,
                code=code if code else None,
                referred_by=referred_by if referred_by else None,
                is_company_client=True
            )
            return redirect(reverse("company_clients:list"))
    return render(request, "core/clients/create_company.html")


@login_required
def my_client_create(request):
    """Create a my (personal) client"""
    if request.method == "POST":
        name = request.POST.get("name")
        code = request.POST.get("code", "").strip()
        referred_by = request.POST.get("referred_by", "").strip()
        if name:
            client = Client.objects.create(
                user=request.user,
                name=name,
                code=code if code else None,
                referred_by=referred_by if referred_by else None,
                is_company_client=False
            )
            return redirect(reverse("my_clients:list"))
    return render(request, "core/clients/create_my.html")


@login_required
def client_delete(request, pk):
    """Delete a client"""
    client = get_object_or_404(Client, pk=pk, user=request.user)
    
    if request.method == "POST":
        client_name = client.name
        client_type = "company" if client.is_company_client else "my"
        
        try:
            client.delete()
            from django.contrib import messages
            messages.success(request, f"Client '{client_name}' has been deleted successfully.")
            
            # Redirect to the appropriate list based on client type
            if client_type == "company":
                return redirect(reverse("company_clients:list"))
            elif client_type == "my":
                return redirect(reverse("my_clients:list"))
            else:
                return redirect(reverse("clients:list"))
        except Exception as e:
            from django.contrib import messages
            import traceback
            error_msg = f"Error deleting client '{client_name}': {str(e)}"
            print(f"Error in client_delete: {traceback.format_exc()}")
            messages.error(request, error_msg)
            
            # Redirect back to the appropriate list
            if client_type == "company":
                return redirect(reverse("company_clients:list"))
            elif client_type == "my":
                return redirect(reverse("my_clients:list"))
            else:
                return redirect(reverse("clients:list"))
    
    # If GET, show confirmation or redirect
    return redirect(reverse("clients:detail", args=[client.pk]))


@login_required
def exchange_list(request):
    exchanges = Exchange.objects.all().order_by("name")
    return render(request, "core/exchanges/list.html", {"exchanges": exchanges})


@login_required
def transaction_list(request):
    """Transaction list with filtering options."""
    client_id = request.GET.get("client")
    exchange_id = request.GET.get("exchange")
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    tx_type = request.GET.get("type")
    search_query = request.GET.get("search", "")
    # Get client_type from GET (to update session) or from session
    client_type = request.GET.get("client_type") or request.session.get('client_type_filter', 'all')
    if client_type == '':
        client_type = 'all'
    
    transactions = Transaction.objects.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").filter(client_exchange__client__user=request.user)
    
    # Filter by client type (my clients or company clients)
    if client_type == "my":
        transactions = transactions.filter(client_exchange__client__is_company_client=False)
    elif client_type == "company":
        transactions = transactions.filter(client_exchange__client__is_company_client=True)
    
    if client_id:
        transactions = transactions.filter(client_exchange__client_id=client_id)
    if exchange_id:
        transactions = transactions.filter(client_exchange__exchange_id=exchange_id)
    if start_date_str:
        transactions = transactions.filter(date__gte=date.fromisoformat(start_date_str))
    if end_date_str:
        transactions = transactions.filter(date__lte=date.fromisoformat(end_date_str))
    if tx_type:
        if tx_type == "RECORDED_BALANCE":
            # Filter transactions that have a recorded balance for the same date and client_exchange
            transactions = transactions.filter(
                client_exchange__daily_balances__date=F('date')
            ).distinct()
        else:
            transactions = transactions.filter(transaction_type=tx_type)
    if search_query:
        transactions = transactions.filter(
            Q(client_exchange__client__name__icontains=search_query) |
            Q(client_exchange__client__code__icontains=search_query) |
            Q(client_exchange__exchange__name__icontains=search_query) |
            Q(note__icontains=search_query)
        )
    
    transactions = transactions.order_by("-date", "-created_at")[:200]
    
    # Filter clients based on client_type for the dropdown
    all_clients_qs = Client.objects.filter(user=request.user, is_active=True)
    if client_type == "my":
        all_clients_qs = all_clients_qs.filter(is_company_client=False)
    elif client_type == "company":
        all_clients_qs = all_clients_qs.filter(is_company_client=True)
    # If client_type is empty, show all clients (no additional filter)
    
    # Validate that selected client matches the client_type filter
    selected_client_obj = None
    if client_id:
        try:
            selected_client_obj = Client.objects.get(pk=client_id, user=request.user, is_active=True)
            # If client_type filter is active, check if selected client matches
            if client_type == "my" and selected_client_obj.is_company_client:
                # Selected client is a company client but filter is for my clients - clear selection
                client_id = None
            elif client_type == "company" and not selected_client_obj.is_company_client:
                # Selected client is a my client but filter is for company clients - clear selection
                client_id = None
        except Client.DoesNotExist:
            client_id = None
    
    return render(request, "core/transactions/list.html", {
        "transactions": transactions,
        "all_clients": all_clients_qs.order_by("name"),
        "all_exchanges": Exchange.objects.filter(is_active=True).order_by("name"),
        "selected_client": int(client_id) if client_id else None,
        "selected_exchange": int(exchange_id) if exchange_id else None,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "selected_type": tx_type,
        "search_query": search_query,
        "client_type": client_type,
        "client_type_filter": client_type,  # For template conditional display
    })


def calculate_net_tallies_from_transactions(client_exchange, as_of_date=None):
    """
    Calculate NET TALLIES from transactions (not from stored pending amounts).
    
    This is the NEW SYSTEM that calculates:
    - Net Client Tally = (Your share from losses) - (Your share from profits)
    - Net Company Tally = (Company 9% from losses) - (Company 9% from profits)
    
    Args:
        client_exchange: ClientExchange instance
        as_of_date: Optional date to calculate as of. If None, uses all transactions.
    
    Returns:
        dict with:
        - net_client_tally: Net amount (positive = client owes you, negative = you owe client)
        - net_company_tally: Net amount (positive = company owes you, negative = you owe company)
        - your_earnings: Your earnings from company split (1% of losses + 1% of profits)
    """
    # Filter transactions up to as_of_date if provided
    tx_filter = {"client_exchange": client_exchange}
    if as_of_date:
        tx_filter["date__lte"] = as_of_date
    
    # Get all LOSS transactions
    loss_transactions = Transaction.objects.filter(
        **tx_filter,
        transaction_type=Transaction.TYPE_LOSS
    )
    
    # Get all PROFIT transactions
    profit_transactions = Transaction.objects.filter(
        **tx_filter,
        transaction_type=Transaction.TYPE_PROFIT
    )
    
    # Get all SETTLEMENT transactions (to subtract payments)
    settlement_filter = {**tx_filter, "transaction_type": Transaction.TYPE_SETTLEMENT}
    
    # Calculate your share from losses
    your_share_from_losses = loss_transactions.aggregate(
        total=Sum("your_share_amount")
    )["total"] or Decimal(0)
    
    # Calculate your share from profits
    your_share_from_profits = profit_transactions.aggregate(
        total=Sum("your_share_amount")
    )["total"] or Decimal(0)
    
    # Calculate company share from losses (9% portion that company owes you)
    company_share_from_losses = loss_transactions.aggregate(
        total=Sum("company_share_amount")
    )["total"] or Decimal(0)
    
    # Calculate company share from profits (9% portion that you owe company)
    company_share_from_profits = profit_transactions.aggregate(
        total=Sum("company_share_amount")
    )["total"] or Decimal(0)
    
    # Get settlements where client paid you (reduces what client owes you)
    client_payments = Transaction.objects.filter(
        **settlement_filter,
        client_share_amount=0,  # Client pays
        your_share_amount__gt=0  # You receive
    ).aggregate(total=Sum("your_share_amount"))["total"] or Decimal(0)
    
    # Get settlements where you paid client (reduces what you owe client)
    admin_payments_to_client = Transaction.objects.filter(
        **settlement_filter,
        client_share_amount__gt=0,  # Client receives
        your_share_amount=0  # You pay
    ).aggregate(total=Sum("client_share_amount"))["total"] or Decimal(0)
    
    # Get settlements where company paid you (reduces what company owes you)
    # Company payments are tracked in company_share_amount when company pays
    # For now, settlements don't directly track company payments separately
    # Company payments would reduce company_share_from_losses
    company_payments_to_you = Decimal(0)  # TODO: Track company payments separately if needed
    
    # Get settlements where you paid company (reduces what you owe company)
    # This would be tracked in company_share_amount when you pay company
    admin_payments_to_company = Decimal(0)  # TODO: Track admin payments to company separately if needed
    
    # Calculate NET CLIENT TALLY
    # Net = (Your share from losses) - (Your share from profits) - (Client payments) + (Admin payments to client)
    net_client_tally = (your_share_from_losses - your_share_from_profits - client_payments + admin_payments_to_client)
    net_client_tally = net_client_tally.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    
    # Calculate NET COMPANY TALLY
    # Net = (Company 9% from losses) - (Company 9% from profits) - (Company payments to you) + (Admin payments to company)
    # Note: admin_payments_to_company is currently always 0 (not tracked separately yet)
    net_company_tally = company_share_from_losses - company_share_from_profits - company_payments_to_you
    # If admin_payments_to_company is negative, it means you paid company, so subtract it
    if admin_payments_to_company < 0:
        net_company_tally = net_company_tally - abs(admin_payments_to_company)
    elif admin_payments_to_company > 0:
        # If positive, it means company paid you (unlikely with current structure)
        net_company_tally = net_company_tally + admin_payments_to_company
    net_company_tally = net_company_tally.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    
    # Calculate YOUR EARNINGS (1% of losses + 1% of profits)
    # This is the 1% cut you get from company share
    total_loss = loss_transactions.aggregate(total=Sum("amount"))["total"] or Decimal(0)
    total_profit = profit_transactions.aggregate(total=Sum("amount"))["total"] or Decimal(0)
    your_earnings_from_losses = (total_loss * Decimal(1)) / Decimal(100)  # 1% of losses
    your_earnings_from_profits = (total_profit * Decimal(1)) / Decimal(100)  # 1% of profits
    your_earnings = (your_earnings_from_losses + your_earnings_from_profits).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    
    return {
        "net_client_tally": net_client_tally,
        "net_company_tally": net_company_tally,
        "your_earnings": your_earnings,
        "your_share_from_losses": your_share_from_losses,
        "your_share_from_profits": your_share_from_profits,
        "company_share_from_losses": company_share_from_losses,
        "company_share_from_profits": company_share_from_profits,
    }


@login_required
def pending_summary(request):
    """
    Pending payments view based on NET TALLY calculations from transactions.
    
    NEW SYSTEM: Calculates net tallies from transactions:
    - Net Client Tally = (Your share from losses) - (Your share from profits) - payments
    - Net Company Tally = (Company 9% from losses) - (Company 9% from profits) - payments
    
    This replaces the old system that only looked at PendingAmount table.
    
    Supports report types: daily, weekly, monthly
    """
    from datetime import timedelta
    
    today = date.today()
    report_type = request.GET.get("report_type", "daily")  # daily, weekly, monthly
    # Get client_type from GET (to update session) or from session
    client_type_filter = request.GET.get("client_type") or request.session.get('client_type_filter', 'all')
    if client_type_filter == '':
        client_type_filter = 'all'
    
    # Update session to preserve client_type_filter for navigation bar
    request.session['client_type_filter'] = client_type_filter
    request.session.modified = True
    
    # Calculate date range based on report type (always current date)
    if report_type == "daily":
        start_date = today
        end_date = today
        date_range_label = f"Today ({today.strftime('%B %d, %Y')})"
    elif report_type == "weekly":
        start_date = today - timedelta(days=7)
        end_date = today
        weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        today_weekday = today.weekday()
        date_range_label = f"Weekly ({weekday_names[today_weekday]} to {weekday_names[today_weekday]}): {start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
    elif report_type == "monthly":
        day_of_month = today.day
        if today.month == 1:
            start_date = date(today.year - 1, 12, min(day_of_month, 31))
        else:
            last_month = today.month - 1
            last_month_days = (date(today.year, today.month, 1) - timedelta(days=1)).day
            start_date = date(today.year, last_month, min(day_of_month, last_month_days))
        end_date = today
        date_range_label = f"Monthly ({start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')})"
    else:
        start_date = today
        end_date = today
        date_range_label = f"Today ({today.strftime('%B %d, %Y')})"
    
    # Get all active client exchanges
    client_exchanges = ClientExchange.objects.filter(
        client__user=request.user,
        is_active=True
    ).select_related("client", "exchange").all()
    
    # Filter by client type if specified
    if client_type_filter == "my":
        client_exchanges = client_exchanges.filter(client__is_company_client=False)
    elif client_type_filter == "company":
        client_exchanges = client_exchanges.filter(client__is_company_client=True)
    
    # Get system settings
    settings = SystemSettings.load()
    
    # Check if admin wants to combine my share and company share (for client sharing)
    # Default to true (checked) if not specified in URL
    combine_shares_param = request.GET.get("combine_shares")
    if combine_shares_param is None:
        # Default to true if not specified
        combine_shares = True
    else:
        combine_shares = combine_shares_param.lower() == "true"
    
    # Separate lists based on separate ledgers
    clients_owe_list = []  # Clients with pending amount (unpaid losses)
    you_owe_list = []  # Clients in profit (admin owes)
    
    for client_exchange in client_exchanges:
        # Calculate NET TALLIES from transactions (NEW SYSTEM)
        # This calculates net amounts from all LOSS and PROFIT transactions
        net_tallies = calculate_net_tallies_from_transactions(client_exchange)
        
        net_client_tally = net_tallies["net_client_tally"]
        net_company_tally = net_tallies["net_company_tally"]
        your_earnings = net_tallies["your_earnings"]
        
        # Get data from separate ledgers for display purposes
        profit_loss_data = calculate_client_profit_loss(client_exchange)
        client_profit_loss = profit_loss_data["client_profit_loss"]
        
        # Clients with net tally > 0 (client owes you)
        # 📘 PENDING AMOUNT (Client Owes You) = Σ (Your Share from LOSS transactions) − Σ (Settlements received)
        # 
        # Rule: Profit does NOT reduce pending
        # Rule: Balance records do NOT affect pending
        # Rule: Funding does NOT affect pending
        # Rule: Only LOSS transactions and SETTLEMENT transactions affect pending
        
        if net_client_tally > 0:
            # For MY CLIENTS: Calculate pending from NET LOSS (Old Balance - Current Balance)
            # For COMPANY CLIENTS: Use net_client_tally (which already accounts for company share)
            
            if not client_exchange.client.is_company_client:
                # MY CLIENTS: Pending = My Share × (Old Balance - Current Balance) - Settlements received
                # 📘 CORRECT FORMULA: Pending = My Share % × (Old Balance - Current Balance) when client is in loss
                # 
                # This is the NET LOSS approach - the real-world, normal accounting way
                # Net Loss already includes all losses, profits, and fluctuations
                # We must NOT sum individual LOSS transactions (that would double-count)
                
                # Get Old Balance (from FUNDING + SETTLEMENT only)
                old_balance = get_old_balance_after_settlement(client_exchange)
                
                # Get Current Balance (from latest BALANCE_RECORD)
                current_balance = profit_loss_data["exchange_balance"]
                
                # Calculate NET LOSS = Old Balance - Current Balance
                # If positive: client is in loss (Old Balance > Current Balance)
                # If negative: client is in profit (Old Balance < Current Balance)
                net_loss = old_balance - current_balance
                
                if net_loss > 0:
                    # Client is in LOSS
                    # Get my_share_pct from client_exchange
                    my_share_pct = client_exchange.my_share_pct
                    
                    # Calculate My Share = Net Loss × My Share %
                    my_share_from_net_loss = (net_loss * my_share_pct) / Decimal(100)
                    my_share_from_net_loss = my_share_from_net_loss.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                    
                    # Get settlements where client paid you (reduces pending)
                    # Σ settlement_received = settlements where you receive (your_share_amount > 0, client_share_amount = 0)
                    client_payments = Transaction.objects.filter(
                        client_exchange=client_exchange,
                        transaction_type=Transaction.TYPE_SETTLEMENT,
                        client_share_amount=0,  # Client pays
                        your_share_amount__gt=0  # You receive
                    ).aggregate(total=Sum("your_share_amount"))["total"] or Decimal(0)
                    
                    # Pending = My Share from Net Loss - Settlements Received
                    # This is the net amount client still owes you
                    my_share = max(Decimal(0), my_share_from_net_loss - client_payments)
                    my_share = my_share.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                else:
                    # Client is in profit or break-even - no pending
                    my_share = Decimal(0)
            else:
                # COMPANY CLIENTS: Use net_client_tally (which already accounts for company share)
                my_share = net_client_tally
            
            # Get the raw amounts from net_tallies for company clients
            your_share_from_losses = net_tallies["your_share_from_losses"]
            company_share_from_losses = net_tallies["company_share_from_losses"]
            
            # For company clients: Show company net tally (what company owes you after netting)
            if client_exchange.client.is_company_client:
                # Net Company Tally = (Company 9% from losses) - (Company 9% from profits) - payments
                # If positive: Company owes you (show it)
                # If negative: You owe company (don't show in "Clients Owe You" section)
                company_share = net_company_tally if net_company_tally > 0 else Decimal(0)
                combined_share = my_share + company_share
            else:
                # My clients: No company share
                company_share = Decimal(0)
                combined_share = my_share
            
            # Calculate old balance (balance before the loss)
            # CRITICAL: For MY CLIENTS, use get_old_balance_after_settlement()
            # This calculates Old Balance from FUNDING + SETTLEMENT only, NOT from BALANCE_RECORD
            # For COMPANY CLIENTS, use get_old_balance() (different logic)
            current_balance = profit_loss_data["exchange_balance"]
            
            if not client_exchange.client.is_company_client:
                # MY CLIENTS: Old Balance = SUM of FUNDING (or balance after settlement + funding after)
                # NEVER use BALANCE_RECORD for Old Balance
                old_balance = get_old_balance_after_settlement(client_exchange)
            else:
                # COMPANY CLIENTS: Use existing logic
                old_balance = get_old_balance(client_exchange)
            
            # For my clients: net_amount is outstanding (Your Share only)
            # For company clients: net_amount is net client tally
            clients_owe_list.append({
                "client_id": client_exchange.client.pk,
                "client_name": client_exchange.client.name,
                "client_code": client_exchange.client.code,
                "exchange_name": client_exchange.exchange.name,
                "exchange_id": client_exchange.exchange.pk,
                "client_exchange_id": client_exchange.pk,
                "old_balance": old_balance,  # Balance before loss occurred
                "exchange_balance": current_balance,  # Current balance (renamed for clarity)
                "pending_amount": my_share,  # Pending amount (client owes you) - calculated from LOSS transactions for MY CLIENTS
                "company_pending": net_company_tally if client_exchange.client.is_company_client else Decimal(0),  # Net company tally
                "your_earnings": your_earnings,  # Your earnings from company split (1% of losses + 1% of profits)
                "my_share": my_share,  # Admin's share of loss (admin earns this)
                "company_share": company_share,  # Company's share of loss (company earns this, 0 for my clients)
                "combined_share": combined_share,  # For my clients: my_share only; For company clients: my_share + company_share
                "is_company_client": client_exchange.client.is_company_client,  # Client type flag
            })
            # IMPORTANT: Skip "You Owe Clients" section if client has pending losses
            # A client should only appear in ONE section, not both
            continue
        
        # Clients where you owe them (net client tally < 0)
        # Net Client Tally = (Your share from losses) - (Your share from profits) - payments
        # If negative: You owe client
        if net_client_tally < 0:
            unpaid_profit = abs(net_client_tally)  # Amount you owe client
            
            # Calculate shares for display
            if client_exchange.client.is_company_client:
                # Company clients: For PROFIT, you pay ONLY your cut (1% of profit)
                # NOT the company's retained share (9% of profit)
                # 
                # Example: Profit = ₹900
                # - Company Share (10%) = ₹90
                #   - Your cut (1% of total) = ₹9 ← This is what YOU pay
                #   - Company keeps (9% of total) = ₹81 ← This is NOT your payment
                #
                # The net_client_tally already accounts for your share from profits
                # But we need to ensure it's showing 1% of profit, not 10%
                
                # Get total profit from transactions
                profit_transactions = Transaction.objects.filter(
                    client_exchange=client_exchange,
                    transaction_type=Transaction.TYPE_PROFIT
                )
                total_profit = profit_transactions.aggregate(total=Sum("amount"))["total"] or Decimal(0)
                
                # Your payable = 1% of total profit (your cut from company share)
                # This is what you actually owe, not the company's retained portion
                your_payable = (total_profit * Decimal(1)) / Decimal(100)
                your_payable = your_payable.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                
                # Subtract any payments already made (admin payments to client)
                admin_payments_to_client = Transaction.objects.filter(
                    client_exchange=client_exchange,
                    transaction_type=Transaction.TYPE_SETTLEMENT,
                    client_share_amount__gt=0,  # Client receives
                    your_share_amount=0  # You pay
                ).aggregate(total=Sum("client_share_amount"))["total"] or Decimal(0)
                
                # Net payable = Your cut (1%) - payments made
                my_share = max(Decimal(0), your_payable - admin_payments_to_client)
                my_share = my_share.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                
                # For display purposes:
                # - my_share = Your payable (1% of profit) = ₹9 - This is what YOU pay
                # - company_share = Company's retained portion (9% of profit) = ₹81 - Informational only
                # - combined_share = Total company portion (10% of profit) = ₹90 - For display in "Combined Share" column
                company_share_pct = client_exchange.company_share_pct
                company_share_total = (total_profit * company_share_pct) / Decimal(100)  # 10% of profit = ₹90
                company_share_total = company_share_total.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                
                # Company's retained portion (9% of profit) = ₹81
                company_portion = company_share_total - your_payable  # ₹90 - ₹9 = ₹81
                company_portion = company_portion.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                
                # Subtract payments made
                company_share = max(Decimal(0), company_portion - admin_payments_to_client)
                company_share = company_share.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                
                # Combined Share = Total company portion (10% of profit) = ₹90
                # This is for display in "Combined Share" column
                # The actual payment is still my_share (₹9) - your 1% cut
                combined_share = max(Decimal(0), company_share_total - admin_payments_to_client)
                combined_share = combined_share.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            else:
                # My clients: Calculate from PROFIT transactions (per specification)
                # 📘 YOU OWE CLIENT (Profit Payable) = Σ (Your Share from PROFIT transactions) − Σ (Settlements paid)
                # 
                # Rule: Profit does NOT reduce pending
                # Rule: You Owe is calculated from PROFIT transactions, not from balance comparison
                
                # Get all PROFIT transactions
                profit_transactions = Transaction.objects.filter(
                    client_exchange=client_exchange,
                    transaction_type=Transaction.TYPE_PROFIT
                )
                
                # Calculate your share from profits = Σ PROFIT.your_share
                your_share_from_profits = profit_transactions.aggregate(
                    total=Sum("your_share_amount")
                )["total"] or Decimal(0)
                
                # Get settlements where you paid client (reduces what you owe)
                # Σ settlement_paid = settlements where client receives (client_share_amount > 0, your_share_amount = 0)
                admin_payments_to_client = Transaction.objects.filter(
                    client_exchange=client_exchange,
                    transaction_type=Transaction.TYPE_SETTLEMENT,
                    client_share_amount__gt=0,  # Client receives
                    your_share_amount=0  # You pay
                ).aggregate(total=Sum("client_share_amount"))["total"] or Decimal(0)
                
                # You Owe = Your Share from Profits - Settlements Paid
                # This is the net amount you still owe the client
                combined_share = max(Decimal(0), your_share_from_profits - admin_payments_to_client)
                combined_share = combined_share.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                
                # For MY CLIENTS: my_share = combined_share (no company share)
                my_share = combined_share
                company_share = Decimal(0)
            
            # Only show if there's unpaid amount
            # For MY CLIENTS: Check combined_share > 0 (calculated from PROFIT transactions)
            # For COMPANY CLIENTS: Check unpaid_profit > 0 (from net_client_tally)
            should_show = combined_share > 0 if not client_exchange.client.is_company_client else unpaid_profit > 0
            
            if should_show:
                # For company clients: Recalculate combined share (Your Cut + Company Net)
                # For my clients: combined_share is already calculated correctly above
                if client_exchange.client.is_company_client:
                    combined_share = my_share + company_share
                
                you_owe_list.append({
                    "client_id": client_exchange.client.pk,
                    "client_name": client_exchange.client.name,
                    "client_code": client_exchange.client.code,
                    "exchange_name": client_exchange.exchange.name,
                    "exchange_id": client_exchange.exchange.pk,
                    "client_exchange_id": client_exchange.pk,
                    "client_profit": my_share if client_exchange.client.is_company_client else combined_share,  # For company clients: your payable (₹9), for my clients: combined_share (₹10)
                    "my_share": my_share,  # Net amount you owe client (for company clients: 1% of profit = ₹9, for my clients: combined_share = ₹10)
                    "company_share": company_share,  # Company's retained portion (9% of profit = ₹81, informational only)
                    "combined_share": combined_share,  # For my clients: profit × my_share_pct (₹10), for company clients: total company portion (10% of profit = ₹90)
                    "is_company_client": client_exchange.client.is_company_client,  # Client type flag
                    "total_funding": profit_loss_data["total_funding"],
                    "exchange_balance": profit_loss_data["exchange_balance"],
                    "old_balance": old_balance if not client_exchange.client.is_company_client else None,  # Old Balance for MY CLIENTS (for display/debugging)
                    "company_pending": abs(net_company_tally) if net_company_tally < 0 else Decimal(0),  # Net amount you owe company
                    "your_earnings": your_earnings,  # Your earnings from company split
                })
    
    # Sort by amount (descending)
    clients_owe_list.sort(key=lambda x: x["pending_amount"], reverse=True)
    you_owe_list.sort(key=lambda x: x["client_profit"], reverse=True)
    
    # Calculate totals
    total_pending = sum(item["pending_amount"] for item in clients_owe_list)
    total_profit = sum(item["client_profit"] for item in you_owe_list)
    
    context = {
        "clients_owe": clients_owe_list,
        "you_owe": you_owe_list,
        "total_pending": total_pending,
        "total_profit": total_profit,
        "today": today,
        "report_type": report_type,
        "client_type_filter": client_type_filter,
        "start_date": start_date,
        "end_date": end_date,
        "date_range_label": date_range_label,
        "settings": settings,
        "combine_shares": combine_shares,  # Flag to show combined shares
    }
    return render(request, "core/pending/summary.html", context)


@login_required
def report_overview(request):
    """High-level reporting screen with simple totals and graphs."""
    from datetime import timedelta
    from collections import defaultdict

    today = date.today()
    report_type = request.GET.get("report_type", "monthly")  # Default to monthly
    # Get client_type from GET (to update session) or from session
    client_type_filter = request.GET.get("client_type") or request.session.get('client_type_filter', 'all')
    if client_type_filter == '':
        client_type_filter = 'all'
    client_id = request.GET.get("client")  # Specific client ID
    
    # Time travel parameters
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    as_of_str = request.GET.get("date")
    time_travel_mode = False
    date_filter = {}
    
    if start_date_str and end_date_str:
        time_travel_mode = True
        start_date_filter = date.fromisoformat(start_date_str)
        end_date_filter = date.fromisoformat(end_date_str)
        date_filter = {"date__gte": start_date_filter, "date__lte": end_date_filter}
    elif as_of_str:
        time_travel_mode = True
        as_of_filter = date.fromisoformat(as_of_str)
        date_filter = {"date__lte": as_of_filter}
    
    # Base queryset with time travel filter if applicable, always filtered by user
    user_filter = {"client_exchange__client__user": request.user}
    
    # Add client type filter if specified
    if client_type_filter == "company":
        user_filter["client_exchange__client__is_company_client"] = True
    elif client_type_filter == "my":
        user_filter["client_exchange__client__is_company_client"] = False
    
    # Add specific client filter if specified
    if client_id:
        user_filter["client_exchange__client_id"] = client_id
    
    if date_filter:
        base_qs = Transaction.objects.filter(**user_filter, **date_filter)
    else:
        base_qs = Transaction.objects.filter(**user_filter)
    
    # Get clients for dropdown (filtered by client_type if applicable)
    clients_qs = Client.objects.filter(user=request.user, is_active=True)
    if client_type_filter == "company":
        clients_qs = clients_qs.filter(is_company_client=True)
    elif client_type_filter == "my":
        clients_qs = clients_qs.filter(is_company_client=False)
    all_clients = clients_qs.order_by("name")
    
    # Get selected client if specified
    selected_client = None
    if client_id:
        try:
            selected_client = Client.objects.get(pk=client_id, user=request.user)
        except Client.DoesNotExist:
            pass
    
    # Overall totals (filtered by time travel if applicable)
    total_turnover = base_qs.aggregate(total=Sum("amount"))["total"] or 0
    your_total_profit = (
        base_qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))[
            "total"
        ]
        or 0
    )
    company_profit = (
        base_qs.aggregate(total=Sum("company_share_amount"))["total"] or 0
    )

    # Daily trends for last 30 days (or filtered by time travel)
    if time_travel_mode and start_date_str and end_date_str:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
        # Limit to 30 days or the actual range, whichever is smaller
        days_diff = (end_date - start_date).days
        if days_diff > 30:
            start_date = end_date - timedelta(days=30)
    else:
        start_date = today - timedelta(days=30)
        end_date = today
    
    daily_data = defaultdict(lambda: {"profit": 0, "loss": 0, "turnover": 0})
    
    daily_transactions = base_qs.filter(
        date__gte=start_date,
        date__lte=end_date
    ).values("date", "transaction_type").annotate(
        profit_sum=Sum("your_share_amount", filter=Q(transaction_type=Transaction.TYPE_PROFIT)),
        loss_sum=Sum("your_share_amount", filter=Q(transaction_type=Transaction.TYPE_LOSS)),
        turnover_sum=Sum("amount")
    )
    
    for item in daily_transactions:
        tx_date = item["date"]
        daily_data[tx_date]["profit"] += float(item["profit_sum"] or 0)
        daily_data[tx_date]["loss"] += float(item["loss_sum"] or 0)
        daily_data[tx_date]["turnover"] += float(item["turnover_sum"] or 0)
    
    # Create sorted date list and data arrays
    # Only include dates up to end_date
    date_labels = []
    profit_data = []
    loss_data = []
    turnover_data = []
    
    current_date = start_date
    days_count = 0
    while current_date <= end_date and days_count < 30:
        date_labels.append(current_date.strftime("%b %d"))
        # Access defaultdict directly - it will return default dict if key doesn't exist
        day_data = daily_data[current_date]
        profit_data.append(float(day_data.get("profit", 0)))
        loss_data.append(float(day_data.get("loss", 0)))
        turnover_data.append(float(day_data.get("turnover", 0)))
        current_date += timedelta(days=1)
        days_count += 1
    
    # Transaction type breakdown (filtered by time travel if applicable)
    type_breakdown = base_qs.values("transaction_type").annotate(
        count=Count("id"),
        total_amount=Sum("amount")
    )
    type_labels = []
    type_counts = []
    type_amounts = []
    type_colors = []
    
    type_map = {
        Transaction.TYPE_PROFIT: ("Profit", "#6b7280"),
        Transaction.TYPE_LOSS: ("Loss", "#9ca3af"),
        Transaction.TYPE_FUNDING: ("Funding", "#4b5563"),
        Transaction.TYPE_SETTLEMENT: ("Settlement", "#6b7280"),
    }
    
    for item in type_breakdown:
        tx_type = item["transaction_type"]
        if tx_type in type_map:
            label, color = type_map[tx_type]
            type_labels.append(label)
            type_counts.append(item["count"])
            type_amounts.append(float(item["total_amount"] or 0))
            type_colors.append(color)
    
    # Monthly trends (last 6 months)
    monthly_labels = []
    monthly_profit = []
    monthly_loss = []
    monthly_turnover = []
    
    for i in range(6):
        # Calculate month start date
        month_date = today.replace(day=1)
        for _ in range(i):
            if month_date.month == 1:
                month_date = month_date.replace(year=month_date.year - 1, month=12)
            else:
                month_date = month_date.replace(month=month_date.month - 1)
        
        # Calculate month end date
        if month_date.month == 12:
            month_end = month_date.replace(year=month_date.year + 1, month=1) - timedelta(days=1)
        else:
            month_end = month_date.replace(month=month_date.month + 1) - timedelta(days=1)
        
        monthly_labels.insert(0, month_date.strftime("%b %Y"))
        
        # Get transactions for this month (filtered by time travel if applicable)
        month_transactions = base_qs.filter(
            date__gte=month_date,
            date__lte=month_end
        )
        
        month_profit_val = month_transactions.filter(
            transaction_type=Transaction.TYPE_PROFIT
        ).aggregate(total=Sum("your_share_amount"))["total"] or 0
        
        month_loss_val = month_transactions.filter(
            transaction_type=Transaction.TYPE_LOSS
        ).aggregate(total=Sum("your_share_amount"))["total"] or 0
        
        month_turnover_val = month_transactions.aggregate(total=Sum("amount"))["total"] or 0
        
        monthly_profit.insert(0, float(month_profit_val))
        monthly_loss.insert(0, float(month_loss_val))
        monthly_turnover.insert(0, float(month_turnover_val))
    
    # Top clients by profit (last 30 days or filtered)
    top_clients = base_qs.filter(
        date__gte=start_date,
        transaction_type=Transaction.TYPE_PROFIT
    ).values(
        "client_exchange__client__name"
    ).annotate(
        total_profit=Sum("your_share_amount")
    ).order_by("-total_profit")[:10]
    
    client_labels = [item["client_exchange__client__name"] for item in top_clients]
    client_profits = [float(item["total_profit"] or 0) for item in top_clients]

    # Weekly data (last 4 weeks)
    weekly_labels = []
    weekly_profit = []
    weekly_loss = []
    weekly_turnover = []
    
    for i in range(4):
        week_end = today - timedelta(days=i * 7)
        week_start = week_end - timedelta(days=6)
        weekly_labels.insert(0, f"Week {4-i} ({week_start.strftime('%b %d')} - {week_end.strftime('%b %d')})")
        
        week_transactions = base_qs.filter(
            date__gte=week_start,
            date__lte=week_end
        )
        
        week_profit_val = week_transactions.filter(
            transaction_type=Transaction.TYPE_PROFIT
        ).aggregate(total=Sum("your_share_amount"))["total"] or 0
        
        week_loss_val = week_transactions.filter(
            transaction_type=Transaction.TYPE_LOSS
        ).aggregate(total=Sum("your_share_amount"))["total"] or 0
        
        week_turnover_val = week_transactions.aggregate(total=Sum("amount"))["total"] or 0
        
        weekly_profit.insert(0, float(week_profit_val))
        weekly_loss.insert(0, float(week_loss_val))
        weekly_turnover.insert(0, float(week_turnover_val))

    # Time travel data
    time_travel_transactions = base_qs.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").order_by("-date", "-created_at")[:50]
    
    context = {
        "report_type": report_type,
        "client_type_filter": client_type_filter,
        "all_clients": all_clients,
        "selected_client": selected_client,
        "selected_client_id": int(client_id) if client_id else None,
        "total_turnover": total_turnover,
        "your_total_profit": your_total_profit,
        "company_profit": company_profit,
        "daily_labels": json.dumps(date_labels),
        "daily_profit": json.dumps(profit_data),
        "daily_loss": json.dumps(loss_data),
        "daily_turnover": json.dumps(turnover_data),
        "weekly_labels": json.dumps(weekly_labels),
        "weekly_profit": json.dumps(weekly_profit),
        "weekly_loss": json.dumps(weekly_loss),
        "weekly_turnover": json.dumps(weekly_turnover),
        "type_labels": json.dumps(type_labels),
        "type_counts": json.dumps(type_counts),
        "type_amounts": json.dumps(type_amounts),
        "type_colors": json.dumps(type_colors),
        "monthly_labels": json.dumps(monthly_labels),
        "monthly_profit": json.dumps(monthly_profit),
        "monthly_loss": json.dumps(monthly_loss),
        "monthly_turnover": json.dumps(monthly_turnover),
        "client_labels": json.dumps(client_labels),
        "client_profits": json.dumps(client_profits),
        "time_travel_mode": time_travel_mode,
        "start_date_str": start_date_str,
        "end_date_str": end_date_str,
        "as_of_str": as_of_str,
        "time_travel_transactions": time_travel_transactions,
    }
    return render(request, "core/reports/overview.html", context)


@login_required
def time_travel_report(request):
    """
    Time‑travel reporting: filter transactions and aggregates by date range or up to a selected date.
    For now this uses live aggregation over `Transaction`; it can later leverage
    `DailyBalanceSnapshot` for faster queries.
    """
    # Get date parameters
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    as_of_str = request.GET.get("date")  # Legacy single date parameter
    # Get client_type from GET (to update session) or from session
    client_type_filter = request.GET.get("client_type") or request.session.get('client_type_filter', 'all')
    if client_type_filter == '':
        client_type_filter = 'all'
    
    # Base filter
    base_filter = {"client_exchange__client__user": request.user}
    
    # Filter by client type (company or my clients)
    if client_type_filter == "company":
        base_filter["client_exchange__client__is_company_client"] = True
    elif client_type_filter == "my":
        base_filter["client_exchange__client__is_company_client"] = False
    
    # Determine date range
    if start_date_str and end_date_str:
        # Use date range
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
        as_of = end_date  # For display purposes
        qs = Transaction.objects.filter(**base_filter, date__gte=start_date, date__lte=end_date)
        date_range_mode = True
    elif as_of_str:
        # Legacy: single date (up to that date)
        as_of = date.fromisoformat(as_of_str)
        qs = Transaction.objects.filter(**base_filter, date__lte=as_of)
        date_range_mode = False
        start_date = None
        end_date = None
    else:
        # Default: today
        as_of = date.today()
        qs = Transaction.objects.filter(**base_filter, date__lte=as_of)
        date_range_mode = False
        start_date = None
        end_date = None

    total_turnover = qs.aggregate(total=Sum("amount"))["total"] or 0
    your_profit = (
        qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    company_profit = qs.aggregate(total=Sum("company_share_amount"))["total"] or 0

    # Calculate pending amounts correctly
    # Clients owe you = pending amounts for transactions up to as_of date
    client_exchange_filter = {"client__user": request.user}
    if client_type_filter == "company":
        client_exchange_filter["client__is_company_client"] = True
    elif client_type_filter == "my":
        client_exchange_filter["client__is_company_client"] = False
    
    if date_range_mode:
        # For date range, calculate pending as of end_date
        client_exchanges_in_range = ClientExchange.objects.filter(
            **client_exchange_filter,
            transactions__date__gte=start_date,
            transactions__date__lte=end_date
        ).distinct()
        pending_clients_owe = Decimal(0)  # No longer using pending amounts
    else:
        # For single date, calculate pending as of that date
        client_exchanges_up_to = ClientExchange.objects.filter(
            **client_exchange_filter,
            transactions__date__lte=as_of
        ).distinct()
        pending_clients_owe = Decimal(0)  # No longer using pending amounts
    
    # You owe clients = client profit shares minus settlements where admin paid
    profit_qs = qs.filter(transaction_type=Transaction.TYPE_PROFIT)
    settlement_qs = qs.filter(
        transaction_type=Transaction.TYPE_SETTLEMENT,
        client_share_amount__gt=0,
        your_share_amount=0
    )
    total_client_profit_shares = profit_qs.aggregate(total=Sum("client_share_amount"))["total"] or Decimal(0)
    total_settlements_paid = settlement_qs.aggregate(total=Sum("client_share_amount"))["total"] or Decimal(0)
    pending_you_owe_clients = max(Decimal(0), total_client_profit_shares - total_settlements_paid)

    recent_transactions = qs.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").order_by("-date", "-created_at")[:50]

    context = {
        "as_of": as_of,
        "start_date": start_date,
        "end_date": end_date,
        "start_date_str": start_date_str,
        "end_date_str": end_date_str,
        "date_range_mode": date_range_mode,
        "total_turnover": total_turnover,
        "your_profit": your_profit,
        "company_profit": company_profit,
        "pending_clients_owe": pending_clients_owe,
        "pending_you_owe_clients": pending_you_owe_clients,
        "recent_transactions": recent_transactions,
        "client_type_filter": client_type_filter,
    }
    return render(request, "core/reports/time_travel.html", context)


@login_required
def company_share_summary(request):
    from .models import CompanyShareRecord

    # Get filter parameters
    client_id = request.GET.get("client")
    selected_client = None
    
    # Base queryset - ONLY company clients have company share
    records_qs = CompanyShareRecord.objects.select_related(
        "client_exchange", 
        "client_exchange__client", 
        "client_exchange__exchange"
    ).filter(client_exchange__client__user=request.user, client_exchange__client__is_company_client=True)
    
    # Filter by client if selected
    if client_id:
        selected_client = get_object_or_404(Client, pk=client_id, user=request.user, is_company_client=True)
        records_qs = records_qs.filter(client_exchange__client=selected_client)

    total_company_profit = (
        records_qs.aggregate(total=Sum("company_amount"))["total"] or 0
    )

    per_client = (
        CompanyShareRecord.objects.filter(client_exchange__client__user=request.user, client_exchange__client__is_company_client=True)
        .values("client_exchange__client__id", "client_exchange__client__name")
        .annotate(total=Sum("company_amount"))
        .order_by("-total")
    )

    per_exchange = (
        records_qs.values(
            "client_exchange__exchange__id",
            "client_exchange__exchange__name",
            "client_exchange__client__name",
        )
        .annotate(total=Sum("company_amount"))
        .order_by("-total")
    )
    
    # Detailed breakdown for selected client (exchange-wise)
    client_exchange_details = None
    if selected_client:
        client_exchange_details = (
            records_qs.values(
                "client_exchange__exchange__name",
                "client_exchange__exchange__code",
            )
            .annotate(
                total=Sum("company_amount"),
                transaction_count=Count("id")
            )
            .order_by("-total")
        )

    # Get only company clients for filter dropdown
    all_clients = Client.objects.filter(user=request.user, is_active=True, is_company_client=True).order_by("name")

    context = {
        "total_company_profit": total_company_profit,
        "per_client": per_client,
        "per_exchange": per_exchange,
        "selected_client": selected_client,
        "client_exchange_details": client_exchange_details,
        "all_clients": all_clients,
        "client_id": client_id,
    }
    return render(request, "core/company/share_summary.html", context)


# Exchange Management Views
@login_required
def exchange_create(request):
    """Create a new standalone exchange (A, B, C, D, etc.)."""
    if request.method == "POST":
        name = request.POST.get("name")
        code = request.POST.get("code", "").strip()
        is_active = request.POST.get("is_active") == "on"
        
        if name:
            exchange = Exchange.objects.create(
                name=name,
                code=code if code else None,
                is_active=is_active,
            )
            return redirect(reverse("exchanges:list"))
    
    return render(request, "core/exchanges/create.html")


@login_required
def exchange_edit(request, pk):
    """Edit an existing standalone exchange."""
    exchange = get_object_or_404(Exchange, pk=pk)
    if request.method == "POST":
        exchange.name = request.POST.get("name")
        exchange.code = request.POST.get("code", "").strip() or None
        exchange.is_active = request.POST.get("is_active") == "on"
        exchange.save()
        return redirect(reverse("exchanges:list"))
    
    return render(request, "core/exchanges/edit.html", {"exchange": exchange})


@login_required
def client_exchange_create(request, client_pk):
    """Link a client to an exchange with specific percentages."""
    client = get_object_or_404(Client, pk=client_pk, user=request.user)
    exchanges = Exchange.objects.filter(is_active=True).order_by("name")
    
    if request.method == "POST":
        exchange_id = request.POST.get("exchange")
        my_share = request.POST.get("my_share_pct")
        company_share = request.POST.get("company_share_pct")
        is_active = request.POST.get("is_active") == "on"
        
        if exchange_id and my_share and company_share:
            exchange = get_object_or_404(Exchange, pk=exchange_id)
            my_share_decimal = Decimal(my_share)
            company_share_decimal = Decimal(company_share)
            
            # Validate company share is less than 100%
            if company_share_decimal >= 100:
                client_type = "company" if client.is_company_client else "my"
                return render(request, "core/exchanges/link_to_client.html", {
                    "client": client,
                    "exchanges": exchanges,
                    "client_type": client_type,
                    "error": "Company share must be less than 100%",
                })
            
            client_exchange = ClientExchange.objects.create(
                client=client,
                exchange=exchange,
                my_share_pct=my_share_decimal,
                company_share_pct=company_share_decimal,
                is_active=is_active,
            )
            # Redirect to appropriate namespace based on client type
            if client.is_company_client:
                return redirect(reverse("company_clients:detail", args=[client.pk]))
            else:
                return redirect(reverse("my_clients:detail", args=[client.pk]))
    
    client_type = "company" if client.is_company_client else "my"
    return render(request, "core/exchanges/link_to_client.html", {
        "client": client,
        "exchanges": exchanges,
        "client_type": client_type,
    })


@login_required
def company_client_exchange_create(request, client_pk):
    """Link an exchange to a company client."""
    client = get_object_or_404(Client, pk=client_pk, user=request.user, is_company_client=True)
    exchanges = Exchange.objects.filter(is_active=True).order_by("name")
    
    if request.method == "POST":
        exchange_id = request.POST.get("exchange")
        my_share = request.POST.get("my_share_pct")
        company_share = request.POST.get("company_share_pct")
        is_active = request.POST.get("is_active") == "on"
        
        if exchange_id and my_share and company_share:
            exchange = get_object_or_404(Exchange, pk=exchange_id)
            my_share_decimal = Decimal(my_share)
            company_share_decimal = Decimal(company_share)
            
            # Validate company share is less than 100%
            if company_share_decimal >= 100:
                return render(request, "core/exchanges/link_to_client.html", {
                    "client": client,
                    "exchanges": exchanges,
                    "client_type": "company",
                    "error": "Company share must be less than 100%",
                })
            
            client_exchange = ClientExchange.objects.create(
                client=client,
                exchange=exchange,
                my_share_pct=my_share_decimal,
                company_share_pct=company_share_decimal,
                is_active=is_active,
            )
            return redirect(reverse("company_clients:detail", args=[client.pk]))
    
    return render(request, "core/exchanges/link_to_client.html", {
        "client": client,
        "exchanges": exchanges,
        "client_type": "company",
    })


@login_required
def my_client_exchange_create(request, client_pk):
    """Link an exchange to a my (personal) client."""
    client = get_object_or_404(Client, pk=client_pk, user=request.user, is_company_client=False)
    exchanges = Exchange.objects.filter(is_active=True).order_by("name")
    
    if request.method == "POST":
        exchange_id = request.POST.get("exchange")
        my_share = request.POST.get("my_share_pct")
        is_active = request.POST.get("is_active") == "on"
        
        if exchange_id and my_share:
            exchange = get_object_or_404(Exchange, pk=exchange_id)
            my_share_decimal = Decimal(my_share)
            # For my clients, company share is always 0
            company_share_decimal = Decimal("0")
            
            client_exchange = ClientExchange.objects.create(
                client=client,
                exchange=exchange,
                my_share_pct=my_share_decimal,
                company_share_pct=company_share_decimal,
                is_active=is_active,
            )
            return redirect(reverse("my_clients:detail", args=[client.pk]))
    
    return render(request, "core/exchanges/link_to_client.html", {
        "client": client,
        "exchanges": exchanges,
        "client_type": "my",
    })


@login_required
def client_exchange_edit(request, pk):
    """Edit client-exchange link percentages. Exchange can be edited within 10 days of creation."""
    client_exchange = get_object_or_404(ClientExchange, pk=pk, client__user=request.user)
    
    # Check if exchange can be edited (within 10 days of creation)
    days_since_creation = (date.today() - client_exchange.created_at.date()).days
    can_edit_exchange = days_since_creation <= 10
    
    if request.method == "POST":
        my_share = Decimal(request.POST.get("my_share_pct"))
        # For my clients, company share is always 0; for company clients, get from POST
        if client_exchange.client.is_company_client:
            company_share = Decimal(request.POST.get("company_share_pct", 0))
            # Validate company share is less than 100%
            if company_share >= 100:
                exchanges = Exchange.objects.filter(is_active=True).order_by("name")
                days_remaining = (10 - days_since_creation) if can_edit_exchange else 0
                client_type = "company" if client_exchange.client.is_company_client else "my"
                return render(request, "core/exchanges/edit_client_link.html", {
                    "client_exchange": client_exchange,
                    "exchanges": exchanges,
                    "can_edit_exchange": can_edit_exchange,
                    "days_since_creation": days_since_creation,
                    "days_remaining": days_remaining,
                    "client_type": client_type,
                    "error": "Company share must be less than 100%",
                })
        else:
            company_share = Decimal("0")
        
        # Update exchange if within 10 days and exchange was provided
        # Double-check can_edit_exchange to prevent manipulation
        if can_edit_exchange and request.POST.get("exchange"):
            new_exchange_id = request.POST.get("exchange")
            new_exchange = get_object_or_404(Exchange, pk=new_exchange_id)
            
            # Check if this exchange-client combination already exists (excluding current)
            existing = ClientExchange.objects.filter(
                client=client_exchange.client,
                exchange=new_exchange
            ).exclude(pk=client_exchange.pk).first()
            
            if existing:
                exchanges = Exchange.objects.filter(is_active=True).order_by("name")
                days_remaining = (10 - days_since_creation) if can_edit_exchange else 0
                client_type = "company" if client_exchange.client.is_company_client else "my"
                return render(request, "core/exchanges/edit_client_link.html", {
                    "client_exchange": client_exchange,
                    "exchanges": exchanges,
                    "can_edit_exchange": can_edit_exchange,
                    "days_since_creation": days_since_creation,
                    "days_remaining": days_remaining,
                    "client_type": client_type,
                    "error": f"This client already has a link to {new_exchange.name}. Please edit that link instead.",
                })
            
            client_exchange.exchange = new_exchange
        elif request.POST.get("exchange") and not can_edit_exchange:
            # Security check: prevent exchange update if beyond 10 days
            exchanges = Exchange.objects.filter(is_active=True).order_by("name")
            days_remaining = 0
            client_type = "company" if client_exchange.client.is_company_client else "my"
            return render(request, "core/exchanges/edit_client_link.html", {
                "client_exchange": client_exchange,
                "exchanges": exchanges,
                "can_edit_exchange": can_edit_exchange,
                "days_since_creation": days_since_creation,
                "days_remaining": days_remaining,
                "client_type": client_type,
                "error": "Exchange cannot be modified after 10 days from creation.",
            })
        
        client_exchange.my_share_pct = my_share
        client_exchange.company_share_pct = company_share
        client_exchange.is_active = request.POST.get("is_active") == "on"
        client_exchange.save()
        # Redirect to appropriate namespace based on client type
        if client_exchange.client.is_company_client:
            return redirect(reverse("company_clients:detail", args=[client_exchange.client.pk]))
        else:
            return redirect(reverse("my_clients:detail", args=[client_exchange.client.pk]))
    
    # GET request - prepare context
    exchanges = Exchange.objects.filter(is_active=True).order_by("name") if can_edit_exchange else None
    days_remaining = (10 - days_since_creation) if can_edit_exchange else 0
    client_type = "company" if client_exchange.client.is_company_client else "my"
    
    return render(request, "core/exchanges/edit_client_link.html", {
        "client_exchange": client_exchange,
        "exchanges": exchanges,
        "can_edit_exchange": can_edit_exchange,
        "days_since_creation": days_since_creation,
        "days_remaining": days_remaining,
        "client_type": client_type,
    })


# Transaction Management Views
@login_required
def transaction_create(request):
    """Create a new transaction with auto-calculation."""
    from datetime import date as date_today
    clients = Client.objects.filter(user=request.user, is_active=True).order_by("name")
    
    if request.method == "POST":
        client_exchange_id = request.POST.get("client_exchange")
        tx_date = request.POST.get("date")
        tx_type = request.POST.get("transaction_type")
        amount = Decimal(request.POST.get("amount", 0))
        note = request.POST.get("note", "")
        
        if client_exchange_id and tx_date and tx_type and amount > 0:
            client_exchange = get_object_or_404(ClientExchange, pk=client_exchange_id, client__user=request.user)
            
            # 🔐 GOLDEN RULE: Payment ALWAYS happens ONLY on SHARE, never on full profit or full loss.
            # - Client loss → client pays ONLY share
            # - Client profit → you pay ONLY share
            # - For company clients: Share is split internally (1% you, 9% company)
            
            is_company_client = client_exchange.client.is_company_client
            my_share_pct = client_exchange.my_share_pct
            
            if tx_type == Transaction.TYPE_PROFIT:
                # STEP 1: Calculate TOTAL SHARE (this is what you pay to client)
                # Total Share = my_share_pct% of profit (e.g., 10% of 990 = ₹99)
                total_share = amount * (my_share_pct / 100)
                
                # STEP 2: For company clients, split that share internally
                if is_company_client:
                    # My cut = 1% of profit
                    your_cut = amount * (Decimal(1) / 100)
                    # Company cut = 9% of profit
                    company_cut = amount * (Decimal(9) / 100)
                else:
                    # My clients: you pay the full share
                    your_cut = total_share
                    company_cut = Decimal(0)
                
                client_share_amount = total_share  # Client receives ONLY this share amount
                your_share_amount = your_cut  # Your cut from the share
                company_share_amount = company_cut  # Company cut from the share
                
            elif tx_type == Transaction.TYPE_LOSS:
                # STEP 1: Calculate TOTAL SHARE (this is what client pays)
                # Total Share = my_share_pct% of loss (e.g., 10% of 90 = ₹9)
                total_share = amount * (my_share_pct / 100)
                
                # STEP 2: For company clients, split that share internally
                if is_company_client:
                    # My cut = 1% of loss
                    your_cut = amount * (Decimal(1) / 100)
                    # Company cut = 9% of loss
                    company_cut = amount * (Decimal(9) / 100)
                else:
                    # My clients: you get the full share
                    your_cut = total_share
                    company_cut = Decimal(0)
                
                client_share_amount = total_share  # Client pays ONLY this share amount
                your_share_amount = your_cut  # Your cut from the share
                company_share_amount = company_cut  # Company cut from the share
                
            else:  # FUNDING or SETTLEMENT
                client_share_amount = amount
                your_share_amount = Decimal(0)
                company_share_amount = Decimal(0)
            
            transaction = Transaction.objects.create(
                client_exchange=client_exchange,
                date=datetime.strptime(tx_date, "%Y-%m-%d").date(),
                transaction_type=tx_type,
                amount=amount,
                client_share_amount=client_share_amount,
                your_share_amount=your_share_amount,
                company_share_amount=company_share_amount,
                note=note,
            )
            
            
            # Create company share record if applicable (only for company clients)
            if company_share_amount > 0 and is_company_client:
                CompanyShareRecord.objects.create(
                    client_exchange=client_exchange,
                    transaction=transaction,
                    date=transaction.date,
                    company_amount=company_share_amount,
                )
            
            return redirect(reverse("transactions:list"))
    
    # Get client-exchanges for selected client (if provided)
    client_id = request.GET.get("client")
    client_exchanges = ClientExchange.objects.filter(client__user=request.user, is_active=True).select_related("client", "exchange")
    if client_id:
        client_exchanges = client_exchanges.filter(client_id=client_id)
    client_exchanges = client_exchanges.order_by("client__name", "exchange__name")
    
    return render(request, "core/transactions/create.html", {
        "clients": clients,
        "client_exchanges": client_exchanges,
        "selected_client": int(client_id) if client_id else None,
        "today": date_today.today(),
    })


@login_required
def transaction_detail(request, pk):
    """Show detailed view of a transaction with balance before and after."""
    transaction = get_object_or_404(Transaction, pk=pk, client_exchange__client__user=request.user)
    client_exchange = transaction.client_exchange
    client = client_exchange.client
    
    # Get transactions before this one (same date but created before, or earlier dates)
    transactions_before = Transaction.objects.filter(
        client_exchange=client_exchange,
    ).filter(
        Q(date__lt=transaction.date) | 
        (Q(date=transaction.date) & Q(created_at__lt=transaction.created_at))
    )
    
    # Calculate balance before transaction based on transactions
    # Balance = funding + profit - loss (from transactions)
    funding_before = transactions_before.filter(transaction_type=Transaction.TYPE_FUNDING).aggregate(total=Sum("amount"))["total"] or Decimal(0)
    profit_before = transactions_before.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("amount"))["total"] or Decimal(0)
    loss_before = transactions_before.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("amount"))["total"] or Decimal(0)
    
    # Exchange balance = funding + profit - loss
    balance_before = funding_before + profit_before - loss_before
    
    # Also check if there's a recorded balance before this transaction date
    before_date = transaction.date - timedelta(days=1)
    recorded_balance = get_exchange_balance(client_exchange, as_of_date=before_date)
    # Use recorded balance if it exists and is different (more accurate)
    if recorded_balance != funding_before:  # If there's a recorded balance, use it
        balance_before = recorded_balance
    
    # Calculate totals before transaction (recalculate in case we used recorded balance)
    funding_before = transactions_before.filter(transaction_type=Transaction.TYPE_FUNDING).aggregate(total=Sum("amount"))["total"] or Decimal(0)
    profit_before = transactions_before.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("amount"))["total"] or Decimal(0)
    loss_before = transactions_before.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("amount"))["total"] or Decimal(0)
    client_profit_share_before = transactions_before.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("client_share_amount"))["total"] or Decimal(0)
    client_loss_share_before = transactions_before.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("client_share_amount"))["total"] or Decimal(0)
    client_net_before = funding_before + client_profit_share_before - client_loss_share_before
    
    # Calculate balance AFTER this transaction (including this transaction)
    # For balance after, we need to account for this transaction's impact
    if transaction.transaction_type == Transaction.TYPE_FUNDING:
        balance_after = balance_before + transaction.amount
        client_net_after = client_net_before + transaction.client_share_amount
    elif transaction.transaction_type == Transaction.TYPE_PROFIT:
        # Profit increases balance
        balance_after = balance_before + transaction.amount
        client_net_after = client_net_before + transaction.client_share_amount
    elif transaction.transaction_type == Transaction.TYPE_LOSS:
        # Loss decreases balance
        balance_after = balance_before - transaction.amount
        client_net_after = client_net_before - transaction.client_share_amount
    else:  # SETTLEMENT
        # Settlement doesn't affect exchange balance directly
        balance_after = balance_before
        if transaction.client_share_amount > 0 and transaction.your_share_amount == 0:
            # Admin pays client - doesn't affect exchange balance
            client_net_after = client_net_before
        else:
            # Client pays - doesn't affect exchange balance
            client_net_after = client_net_before
    
    # Calculate funding after
    funding_after = funding_before
    if transaction.transaction_type == Transaction.TYPE_FUNDING:
        funding_after += transaction.amount
    
    # Calculate profit/loss totals after
    profit_after = profit_before
    loss_after = loss_before
    if transaction.transaction_type == Transaction.TYPE_PROFIT:
        profit_after += transaction.amount
    elif transaction.transaction_type == Transaction.TYPE_LOSS:
        loss_after += transaction.amount
    
    # Calculate differences
    balance_change = balance_after - balance_before
    client_net_change = client_net_after - client_net_before
    
    # Determine client type for URL routing
    client_type = "company" if client.is_company_client else "my"
    
    # Calculate shares based on client_exchange configuration (use stored values if available, otherwise recalculate)
    calculated_your_share = transaction.your_share_amount
    calculated_company_share = transaction.company_share_amount
    calculated_client_share = transaction.client_share_amount
    
    # If shares are 0, recalculate based on client_exchange configuration
    if calculated_your_share == 0 and calculated_client_share == 0:
        if transaction.transaction_type == Transaction.TYPE_PROFIT:
            calculated_your_share = transaction.amount * (client_exchange.my_share_pct / 100)
            calculated_client_share = transaction.amount - calculated_your_share
            if client.is_company_client:
                calculated_company_share = calculated_client_share * (client_exchange.company_share_pct / 100)
            else:
                calculated_company_share = Decimal(0)
        elif transaction.transaction_type == Transaction.TYPE_LOSS:
            calculated_your_share = transaction.amount * (client_exchange.my_share_pct / 100)
            calculated_client_share = transaction.amount - calculated_your_share
            calculated_company_share = Decimal(0)  # No company share on losses
        else:
            # FUNDING or SETTLEMENT
            calculated_client_share = transaction.amount
            calculated_your_share = Decimal(0)
            calculated_company_share = Decimal(0)
    
    context = {
        "transaction": transaction,
        "client": client,
        "client_exchange": client_exchange,
        "client_type": client_type,
        "calculated_your_share": calculated_your_share,
        "calculated_company_share": calculated_company_share,
        "calculated_client_share": calculated_client_share,
        "balance_before": balance_before,
        "balance_after": balance_after,
        "balance_change": balance_change,
        "client_net_before": client_net_before,
        "client_net_after": client_net_after,
        "client_net_change": client_net_change,
        "funding_before": funding_before,
        "funding_after": funding_after,
        "profit_before": profit_before,
        "profit_after": profit_after,
        "loss_before": loss_before,
        "loss_after": loss_after,
    }
    return render(request, "core/transactions/detail.html", context)


@login_required
def transaction_edit(request, pk):
    """Edit an existing transaction."""
    transaction = get_object_or_404(Transaction, pk=pk, client_exchange__client__user=request.user)
    
    if request.method == "POST":
        tx_date = request.POST.get("date")
        tx_type = request.POST.get("transaction_type")
        amount = Decimal(request.POST.get("amount", 0))
        note = request.POST.get("note", "")
        
        if tx_date and tx_type and amount > 0:
            client_exchange = transaction.client_exchange
            
            # 🔐 GOLDEN RULE: Payment ALWAYS happens ONLY on SHARE, never on full profit or full loss.
            # - Client loss → client pays ONLY share
            # - Client profit → you pay ONLY share
            # - For company clients: Share is split internally (1% you, 9% company)
            
            is_company_client = client_exchange.client.is_company_client
            my_share_pct = client_exchange.my_share_pct
            
            # Track old transaction type and share amount for pending updates
            old_tx_type = transaction.transaction_type
            old_share_amount = transaction.client_share_amount  # Old share amount
            
            if tx_type == Transaction.TYPE_PROFIT:
                # STEP 1: Calculate TOTAL SHARE (this is what you pay to client)
                # Total Share = my_share_pct% of profit (e.g., 10% of 990 = ₹99)
                total_share = amount * (my_share_pct / 100)
                
                # STEP 2: For company clients, split that share internally
                if is_company_client:
                    # My cut = 1% of profit
                    your_cut = amount * (Decimal(1) / 100)
                    # Company cut = 9% of profit
                    company_cut = amount * (Decimal(9) / 100)
                else:
                    # My clients: you pay the full share
                    your_cut = total_share
                    company_cut = Decimal(0)
                
                client_share_amount = total_share  # Client receives ONLY this share amount
                your_share_amount = your_cut  # Your cut from the share
                company_share_amount = company_cut  # Company cut from the share
                
            elif tx_type == Transaction.TYPE_LOSS:
                # STEP 1: Calculate TOTAL SHARE (this is what client pays)
                # Total Share = my_share_pct% of loss (e.g., 10% of 90 = ₹9)
                total_share = amount * (my_share_pct / 100)
                
                # STEP 2: For company clients, split that share internally
                if is_company_client:
                    # My cut = 1% of loss
                    your_cut = amount * (Decimal(1) / 100)
                    # Company cut = 9% of loss
                    company_cut = amount * (Decimal(9) / 100)
                else:
                    # My clients: you get the full share
                    your_cut = total_share
                    company_cut = Decimal(0)
                
                client_share_amount = total_share  # Client pays ONLY this share amount
                your_share_amount = your_cut  # Your cut from the share
                company_share_amount = company_cut  # Company cut from the share
                
            else:  # FUNDING or SETTLEMENT
                client_share_amount = amount
                your_share_amount = Decimal(0)
                company_share_amount = Decimal(0)
            
            transaction.date = datetime.strptime(tx_date, "%Y-%m-%d").date()
            transaction.transaction_type = tx_type
            transaction.amount = amount
            transaction.client_share_amount = client_share_amount
            transaction.your_share_amount = your_share_amount
            transaction.company_share_amount = company_share_amount
            transaction.note = note
            transaction.save()
            
            
            # Update company share record (only for company clients)
            if company_share_amount > 0 and is_company_client:
                csr, _ = CompanyShareRecord.objects.get_or_create(
                    transaction=transaction,
                    defaults={"client_exchange": client_exchange, "date": transaction.date, "company_amount": company_share_amount}
                )
                if csr.company_amount != company_share_amount:
                    csr.company_amount = company_share_amount
                    csr.save()
            else:
                CompanyShareRecord.objects.filter(transaction=transaction).delete()
            
            return redirect(reverse("transactions:list"))
    
    return render(request, "core/transactions/edit.html", {"transaction": transaction})


@login_required
def get_exchanges_for_client(request):
    """AJAX endpoint to get client-exchanges for a client."""
    client_id = request.GET.get("client_id")
    if client_id:
        client_exchanges = ClientExchange.objects.filter(client__user=request.user, client_id=client_id, is_active=True).select_related("exchange").values("id", "exchange__name", "exchange__id")
        return JsonResponse(list(client_exchanges), safe=False)
    return JsonResponse([], safe=False)


@login_required
def get_latest_balance_for_exchange(request, client_pk):
    """AJAX endpoint to get latest balance data for a client-exchange."""
    client = get_object_or_404(Client, pk=client_pk, user=request.user)
    client_exchange_id = request.GET.get("client_exchange_id")
    
    if client_exchange_id:
        try:
            client_exchange = ClientExchange.objects.get(pk=client_exchange_id, client=client)
            
            # Get latest balance record
            latest_balance = ClientDailyBalance.objects.filter(
                client_exchange=client_exchange
            ).order_by("-date").first()
            
            # Get calculated balance from transactions
            transactions = Transaction.objects.filter(client_exchange=client_exchange)
            total_funding = transactions.filter(transaction_type=Transaction.TYPE_FUNDING).aggregate(total=Sum("amount"))["total"] or 0
            client_profit_share = transactions.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("client_share_amount"))["total"] or 0
            client_loss_share = transactions.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("client_share_amount"))["total"] or 0
            calculated_balance = total_funding + client_profit_share - client_loss_share
            
            if latest_balance:
                return JsonResponse({
                    "success": True,
                    "date": latest_balance.date.isoformat(),
                    "remaining_balance": str(latest_balance.remaining_balance),
                    "note": latest_balance.note or "",
                    "calculated_balance": str(calculated_balance),
                    "has_recorded_balance": True,
                    "total_funding": str(total_funding),
                })
            else:
                return JsonResponse({
                    "success": True,
                    "date": date.today().isoformat(),
                    "remaining_balance": str(calculated_balance),
                    "note": "",
                    "calculated_balance": str(calculated_balance),
                    "has_recorded_balance": False,
                    "total_funding": str(total_funding),
                })
        except ClientExchange.DoesNotExist:
            return JsonResponse({"success": False, "error": "Exchange not found"}, status=404)
    
    return JsonResponse({"success": False, "error": "Exchange ID required"}, status=400)


# Period-based Reports
@login_required
def report_daily(request):
    """Daily report for a specific date with graphs and analysis."""
    report_date_str = request.GET.get("date", date.today().isoformat())
    report_date = date.fromisoformat(report_date_str)
    # Get client_type from GET (to update session) or from session
    client_type_filter = request.GET.get("client_type") or request.session.get('client_type_filter', 'all')
    if client_type_filter == '':
        client_type_filter = 'all'
    
    # Base filter
    base_filter = {"client_exchange__client__user": request.user, "date": report_date}
    
    # Filter by client type (company or my clients)
    if client_type_filter == "company":
        base_filter["client_exchange__client__is_company_client"] = True
    elif client_type_filter == "my":
        base_filter["client_exchange__client__is_company_client"] = False
    
    qs = Transaction.objects.filter(**base_filter)
    
    total_turnover = qs.aggregate(total=Sum("amount"))["total"] or 0
    your_profit = (
        qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    company_profit = qs.aggregate(total=Sum("company_share_amount"))["total"] or 0
    your_loss = (
        qs.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    
    transactions = qs.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").order_by("-created_at")
    
    # Chart data - transaction type breakdown
    type_data = qs.values("transaction_type").annotate(
        count=Count("id"),
        total_amount=Sum("amount")
    )
    type_labels = []
    type_amounts = []
    type_colors = []
    type_map = {
        Transaction.TYPE_PROFIT: ("Profit", "#6b7280"),
        Transaction.TYPE_LOSS: ("Loss", "#9ca3af"),
        Transaction.TYPE_FUNDING: ("Funding", "#4b5563"),
        Transaction.TYPE_SETTLEMENT: ("Settlement", "#6b7280"),
    }
    for item in type_data:
        tx_type = item["transaction_type"]
        if tx_type in type_map:
            label, color = type_map[tx_type]
            type_labels.append(label)
            type_amounts.append(float(item["total_amount"] or 0))
            type_colors.append(color)
    
    # Client-wise breakdown
    client_data = qs.values("client_exchange__client__name").annotate(
        profit=Sum("your_share_amount", filter=Q(transaction_type=Transaction.TYPE_PROFIT)),
        loss=Sum("your_share_amount", filter=Q(transaction_type=Transaction.TYPE_LOSS)),
        turnover=Sum("amount")
    ).order_by("-turnover")[:10]
    
    client_labels = [item["client_exchange__client__name"] for item in client_data]
    client_profits = [float(item["profit"] or 0) for item in client_data]
    
    # Analysis
    net_profit = float(your_profit) - float(your_loss)
    profit_margin = (float(your_profit) / float(total_turnover) * 100) if total_turnover > 0 else 0
    
    context = {
        "report_date": report_date,
        "total_turnover": total_turnover,
        "your_profit": your_profit,
        "your_loss": your_loss,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
        "client_type_filter": client_type_filter,
        "company_profit": company_profit,
        "transactions": transactions,
        "type_labels": json.dumps(type_labels),
        "type_amounts": json.dumps(type_amounts),
        "type_colors": json.dumps(type_colors),
        "client_labels": json.dumps(client_labels),
        "client_profits": json.dumps(client_profits),
    }
    return render(request, "core/reports/daily.html", context)


@login_required
def report_weekly(request):
    """Weekly report for a specific week with graphs and analysis."""
    week_start_str = request.GET.get("week_start", None)
    if week_start_str:
        week_start = date.fromisoformat(week_start_str)
    else:
        # Default to current week (Monday)
        today = date.today()
        days_since_monday = today.weekday()
        week_start = today - timedelta(days=days_since_monday)
    
    week_end = week_start + timedelta(days=6)
    
    qs = Transaction.objects.filter(client_exchange__client__user=request.user, date__gte=week_start, date__lte=week_end)
    
    total_turnover = qs.aggregate(total=Sum("amount"))["total"] or 0
    your_profit = (
        qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    company_profit = qs.aggregate(total=Sum("company_share_amount"))["total"] or 0
    your_loss = (
        qs.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    
    transactions = qs.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").order_by("-date", "-created_at")
    
    # Daily breakdown for the week
    daily_labels = []
    daily_profit = []
    daily_loss = []
    daily_turnover = []
    
    for i in range(7):
        current_date = week_start + timedelta(days=i)
        daily_labels.append(current_date.strftime("%a %d"))
        
        day_qs = qs.filter(date=current_date)
        day_profit = day_qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
        day_loss = day_qs.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("your_share_amount"))["total"] or 0
        day_turnover = day_qs.aggregate(total=Sum("amount"))["total"] or 0
        
        daily_profit.append(float(day_profit))
        daily_loss.append(float(day_loss))
        daily_turnover.append(float(day_turnover))
    
    # Transaction type breakdown
    type_data = qs.values("transaction_type").annotate(
        count=Count("id"),
        total_amount=Sum("amount")
    )
    type_labels = []
    type_amounts = []
    type_colors = []
    type_map = {
        Transaction.TYPE_PROFIT: ("Profit", "#6b7280"),
        Transaction.TYPE_LOSS: ("Loss", "#9ca3af"),
        Transaction.TYPE_FUNDING: ("Funding", "#4b5563"),
        Transaction.TYPE_SETTLEMENT: ("Settlement", "#6b7280"),
    }
    for item in type_data:
        tx_type = item["transaction_type"]
        if tx_type in type_map:
            label, color = type_map[tx_type]
            type_labels.append(label)
            type_amounts.append(float(item["total_amount"] or 0))
            type_colors.append(color)
    
    # Analysis
    net_profit = float(your_profit) - float(your_loss)
    profit_margin = (float(your_profit) / float(total_turnover) * 100) if total_turnover > 0 else 0
    avg_daily_turnover = float(total_turnover) / 7
    
    context = {
        "week_start": week_start,
        "week_end": week_end,
        "total_turnover": total_turnover,
        "your_profit": your_profit,
        "your_loss": your_loss,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
        "avg_daily_turnover": avg_daily_turnover,
        "company_profit": company_profit,
        "transactions": transactions,
        "daily_labels": json.dumps(daily_labels),
        "daily_profit": json.dumps(daily_profit),
        "daily_loss": json.dumps(daily_loss),
        "daily_turnover": json.dumps(daily_turnover),
        "type_labels": json.dumps(type_labels),
        "type_amounts": json.dumps(type_amounts),
        "type_colors": json.dumps(type_colors),
    }
    return render(request, "core/reports/weekly.html", context)


@login_required
def report_monthly(request):
    """Monthly report for a specific month with graphs and analysis."""
    month_str = request.GET.get("month", date.today().strftime("%Y-%m"))
    year, month = map(int, month_str.split("-"))
    
    month_start = date(year, month, 1)
    if month == 12:
        month_end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(year, month + 1, 1) - timedelta(days=1)
    
    qs = Transaction.objects.filter(client_exchange__client__user=request.user, date__gte=month_start, date__lte=month_end)
    
    total_turnover = qs.aggregate(total=Sum("amount"))["total"] or 0
    your_profit = (
        qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    company_profit = qs.aggregate(total=Sum("company_share_amount"))["total"] or 0
    your_loss = (
        qs.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    
    transactions = qs.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").order_by("-date", "-created_at")
    
    # Weekly breakdown for the month
    weekly_labels = []
    weekly_profit = []
    weekly_loss = []
    weekly_turnover = []
    
    current_date = month_start
    week_num = 1
    while current_date <= month_end:
        week_end_date = min(current_date + timedelta(days=6), month_end)
        weekly_labels.append(f"Week {week_num} ({current_date.strftime('%d')}-{week_end_date.strftime('%d %b')})")
        
        week_qs = qs.filter(date__gte=current_date, date__lte=week_end_date)
        week_profit = week_qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
        week_loss = week_qs.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("your_share_amount"))["total"] or 0
        week_turnover = week_qs.aggregate(total=Sum("amount"))["total"] or 0
        
        weekly_profit.append(float(week_profit))
        weekly_loss.append(float(week_loss))
        weekly_turnover.append(float(week_turnover))
        
        current_date = week_end_date + timedelta(days=1)
        week_num += 1
    
    # Transaction type breakdown
    type_data = qs.values("transaction_type").annotate(
        count=Count("id"),
        total_amount=Sum("amount")
    )
    type_labels = []
    type_amounts = []
    type_colors = []
    type_map = {
        Transaction.TYPE_PROFIT: ("Profit", "#6b7280"),
        Transaction.TYPE_LOSS: ("Loss", "#9ca3af"),
        Transaction.TYPE_FUNDING: ("Funding", "#4b5563"),
        Transaction.TYPE_SETTLEMENT: ("Settlement", "#6b7280"),
    }
    for item in type_data:
        tx_type = item["transaction_type"]
        if tx_type in type_map:
            label, color = type_map[tx_type]
            type_labels.append(label)
            type_amounts.append(float(item["total_amount"] or 0))
            type_colors.append(color)
    
    # Top clients
    client_data = qs.values("client_exchange__client__name").annotate(
        profit=Sum("your_share_amount", filter=Q(transaction_type=Transaction.TYPE_PROFIT)),
        turnover=Sum("amount")
    ).order_by("-profit")[:10]
    
    client_labels = [item["client_exchange__client__name"] for item in client_data]
    client_profits = [float(item["profit"] or 0) for item in client_data]
    
    # Analysis
    net_profit = float(your_profit) - float(your_loss)
    profit_margin = (float(your_profit) / float(total_turnover) * 100) if total_turnover > 0 else 0
    days_in_month = (month_end - month_start).days + 1
    avg_daily_turnover = float(total_turnover) / days_in_month if days_in_month > 0 else 0
    
    context = {
        "month_start": month_start,
        "month_end": month_end,
        "total_turnover": total_turnover,
        "your_profit": your_profit,
        "your_loss": your_loss,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
        "avg_daily_turnover": avg_daily_turnover,
        "company_profit": company_profit,
        "transactions": transactions,
        "weekly_labels": json.dumps(weekly_labels),
        "weekly_profit": json.dumps(weekly_profit),
        "weekly_loss": json.dumps(weekly_loss),
        "weekly_turnover": json.dumps(weekly_turnover),
        "type_labels": json.dumps(type_labels),
        "type_amounts": json.dumps(type_amounts),
        "type_colors": json.dumps(type_colors),
        "client_labels": json.dumps(client_labels),
        "client_profits": json.dumps(client_profits),
    }
    return render(request, "core/reports/monthly.html", context)


@login_required
def report_custom(request):
    """Custom period report."""
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    
    if start_date_str and end_date_str:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
    else:
        # Default to last 30 days
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
    
    qs = Transaction.objects.filter(client_exchange__client__user=request.user, date__gte=start_date, date__lte=end_date)
    
    total_turnover = qs.aggregate(total=Sum("amount"))["total"] or 0
    your_profit = (
        qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    company_profit = qs.aggregate(total=Sum("company_share_amount"))["total"] or 0
    
    transactions = qs.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").order_by("-date", "-created_at")
    
    context = {
        "start_date": start_date,
        "end_date": end_date,
        "total_turnover": total_turnover,
        "your_profit": your_profit,
        "company_profit": company_profit,
        "transactions": transactions,
    }
    return render(request, "core/reports/custom.html", context)


# Export Views
@login_required
def export_report_csv(request):
    """Export report as CSV."""
    import csv
    
    report_type = request.GET.get("type", "all")
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    
    if start_date_str and end_date_str:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
        qs = Transaction.objects.filter(client_exchange__client__user=request.user, date__gte=start_date, date__lte=end_date)
    else:
        qs = Transaction.objects.filter(client_exchange__client__user=request.user)
    
    if report_type == "profit":
        qs = qs.filter(transaction_type=Transaction.TYPE_PROFIT)
    elif report_type == "loss":
        qs = qs.filter(transaction_type=Transaction.TYPE_LOSS)
    
    qs = qs.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").order_by("-date", "-created_at")
    
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="report_{date.today()}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(["Date", "Client", "Exchange", "Type", "Amount", "Your Share", "Client Share", "Company Share", "Note"])
    
    for tx in qs:
        writer.writerow([
            tx.date,
            tx.client_exchange.client.name,
            tx.client_exchange.exchange.name,
            tx.get_transaction_type_display(),
            tx.amount,
            tx.your_share_amount,
            tx.client_share_amount,
            tx.company_share_amount,
            tx.note,
        ])
    
    return response


# Client-specific and Exchange-specific Reports
@login_required
def report_client(request, client_pk):
    """Report for a specific client."""
    client = get_object_or_404(Client, pk=client_pk, user=request.user)
    
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    
    if start_date_str and end_date_str:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
        qs = Transaction.objects.filter(client_exchange__client=client, date__gte=start_date, date__lte=end_date)
    else:
        qs = Transaction.objects.filter(client_exchange__client=client)
    
    total_turnover = qs.aggregate(total=Sum("amount"))["total"] or 0
    your_profit = (
        qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    company_profit = qs.aggregate(total=Sum("company_share_amount"))["total"] or 0
    
    transactions = qs.select_related("client_exchange", "client_exchange__exchange", "client_exchange__client").order_by("-date", "-created_at")
    
    context = {
        "client": client,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "total_turnover": total_turnover,
        "your_profit": your_profit,
        "company_profit": company_profit,
        "transactions": transactions,
    }
    return render(request, "core/reports/client.html", context)


@login_required
def report_exchange(request, exchange_pk):
    """Report for a specific exchange with graphs and analysis."""
    from datetime import timedelta
    
    exchange = get_object_or_404(Exchange, pk=exchange_pk)
    today = date.today()
    report_type = request.GET.get("report_type", "weekly")  # daily, weekly, monthly
    
    # Calculate date range based on report type
    if report_type == "daily":
        start_date = today
        end_date = today
        date_range_label = f"Today ({today.strftime('%B %d, %Y')})"
    elif report_type == "weekly":
        # Weekly: from last same weekday to this same weekday (7 days)
        start_date = today - timedelta(days=7)
        end_date = today
        weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        today_weekday = today.weekday()
        date_range_label = f"Weekly ({weekday_names[today_weekday]} to {weekday_names[today_weekday]}): {start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
    elif report_type == "monthly":
        # Monthly: from last month's same day to today
        day_of_month = today.day
        if today.month == 1:
            start_date = date(today.year - 1, 12, min(day_of_month, 31))
        else:
            last_month = today.month - 1
            last_month_days = (date(today.year, today.month, 1) - timedelta(days=1)).day
            start_date = date(today.year, last_month, min(day_of_month, last_month_days))
        end_date = today
        date_range_label = f"Monthly ({start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')})"
    else:
        # Default to daily
        start_date = today
        end_date = today
        date_range_label = f"Today ({today.strftime('%B %d, %Y')})"
    
    # Get date parameter for custom date range (optional override)
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    
    if start_date_str and end_date_str:
        # Custom date range overrides report type
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
        date_range_label = f"Custom: {start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
    
    qs = Transaction.objects.filter(
        client_exchange__client__user=request.user,
        client_exchange__exchange=exchange, 
        date__gte=start_date, 
        date__lte=end_date
    )
    
    total_turnover = qs.aggregate(total=Sum("amount"))["total"] or 0
    your_profit = (
        qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    company_profit = qs.aggregate(total=Sum("company_share_amount"))["total"] or 0
    your_loss = (
        qs.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    
    transactions = qs.select_related(
        "client_exchange", 
        "client_exchange__client", 
        "client_exchange__exchange"
    ).order_by("-date", "-created_at")
    
    # Transaction type breakdown
    type_data = qs.values("transaction_type").annotate(
        count=Count("id"),
        total_amount=Sum("amount")
    )
    type_labels = []
    type_amounts = []
    type_colors = []
    type_map = {
        Transaction.TYPE_PROFIT: ("Profit", "#6b7280"),
        Transaction.TYPE_LOSS: ("Loss", "#9ca3af"),
        Transaction.TYPE_FUNDING: ("Funding", "#4b5563"),
        Transaction.TYPE_SETTLEMENT: ("Settlement", "#6b7280"),
    }
    for item in type_data:
        tx_type = item["transaction_type"]
        if tx_type in type_map:
            label, color = type_map[tx_type]
            type_labels.append(label)
            type_amounts.append(float(item["total_amount"] or 0))
            type_colors.append(color)
    
    # Client-wise breakdown
    client_data = qs.values("client_exchange__client__name").annotate(
        profit=Sum("your_share_amount", filter=Q(transaction_type=Transaction.TYPE_PROFIT)),
        turnover=Sum("amount")
    ).order_by("-profit")[:10]
    
    client_labels = [item["client_exchange__client__name"] for item in client_data]
    client_profits = [float(item["profit"] or 0) for item in client_data]
    
    # Analysis
    net_profit = float(your_profit) - float(your_loss)
    profit_margin = (float(your_profit) / float(total_turnover) * 100) if total_turnover > 0 else 0
    
    # Check if we have data for charts
    has_type_data = len(type_labels) > 0
    has_client_data = len(client_labels) > 0
    
    context = {
        "exchange": exchange,
        "start_date": start_date_str if start_date_str else start_date.strftime('%Y-%m-%d'),
        "end_date": end_date_str if end_date_str else end_date.strftime('%Y-%m-%d'),
        "report_type": report_type,
        "date_range_label": date_range_label,
        "total_turnover": total_turnover,
        "your_profit": your_profit,
        "your_loss": your_loss,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
        "company_profit": company_profit,
        "transactions": transactions,
        "type_labels": json.dumps(type_labels),
        "type_amounts": json.dumps(type_amounts),
        "type_colors": json.dumps(type_colors),
        "client_labels": json.dumps(client_labels),
        "client_profits": json.dumps(client_profits),
        "has_type_data": has_type_data,
        "has_client_data": has_client_data,
    }
    return render(request, "core/reports/exchange.html", context)


# Settings View
@login_required
def settings_view(request):
    """System settings page for configuring weekly reports and other options."""
    settings = SystemSettings.load()
    
    if request.method == "POST":
        settings.weekly_report_day = int(request.POST.get("weekly_report_day", 0))
        settings.auto_generate_weekly_reports = request.POST.get("auto_generate_weekly_reports") == "on"
        
        settings.save()
        return redirect(reverse("settings"))
    
    return render(request, "core/settings.html", {"settings": settings})


# Balance Tracking
@login_required
def client_balance(request, client_pk):
    """Show balance summary for a specific client."""
    client = get_object_or_404(Client, pk=client_pk, user=request.user)
    
    # Handle daily balance recording/editing
    if request.method == "POST" and request.POST.get("action") == "record_balance":
        balance_date = request.POST.get("date")
        client_exchange_id = request.POST.get("client_exchange")
        remaining_balance = Decimal(request.POST.get("remaining_balance", 0))
        extra_adjustment = Decimal(request.POST.get("extra_adjustment", 0) or 0)
        note = request.POST.get("note", "")
        balance_id = request.POST.get("balance_id")
        
        if balance_date and client_exchange_id and remaining_balance >= 0:
            client_exchange = get_object_or_404(ClientExchange, pk=client_exchange_id, client=client)
            
            if balance_id:
                # Edit existing balance
                balance = get_object_or_404(ClientDailyBalance, pk=balance_id, client_exchange__client=client)
                balance_record_date_obj = date.fromisoformat(balance_date)
                
                # Get old balance based on client type
                if not client_exchange.client.is_company_client:
                    # My Clients: Old Balance = balance after last settlement
                    old_balance = get_old_balance_after_settlement(client_exchange, as_of_date=balance_record_date_obj)
                else:
                    # Company Clients: Use existing logic
                    old_balance = get_old_balance(
                        client_exchange, 
                        balance_record_date=balance.date,
                        balance_record_created_at=balance.created_at
                    )
                
                balance.date = balance_record_date_obj
                balance.client_exchange = client_exchange
                balance.remaining_balance = remaining_balance
                balance.extra_adjustment = extra_adjustment
                balance.note = note
                balance.save()
                
                # Calculate new balance
                new_balance = remaining_balance + extra_adjustment
                
                # Always create a new transaction for this balance record update
                # Each update creates a separate transaction entry (no updates to existing transactions)
                from datetime import datetime
                balance_note = note or f"Balance Record: ₹{remaining_balance}"
                if extra_adjustment:
                    balance_note += f" + Adjustment: ₹{extra_adjustment}"
                balance_note += f" (Updated at {datetime.now().strftime('%H:%M:%S')})"
                
                Transaction.objects.create(
                    client_exchange=client_exchange,
                    date=balance_record_date_obj,
                    transaction_type=Transaction.TYPE_BALANCE_RECORD,
                    amount=new_balance,
                    client_share_amount=new_balance,
                    your_share_amount=Decimal(0),
                    company_share_amount=Decimal(0),
                    note=balance_note,
                )
                
                # Create LOSS or PROFIT transactions based on balance movement
                # This will automatically create the appropriate transaction and update tally/outstanding
                create_loss_profit_from_balance_change(
                    client_exchange, 
                    old_balance, 
                    new_balance, 
                    balance_record_date_obj,
                    note_suffix=" Updated"
                )
                
                # Update tally/outstanding if balance changed
                if new_balance != old_balance:
                    if not client_exchange.client.is_company_client:
                        # My Clients: Use outstanding (netted system) with new logic
                        update_outstanding_from_balance_change(
                            client_exchange, 
                            old_balance, 
                            new_balance, 
                            balance_date=balance_record_date_obj
                        )
                    else:
                        # Company Clients: Use tally ledger (tally system)
                        update_tally_from_balance_change(client_exchange, old_balance, new_balance)
            else:
                # Create new balance
                balance_record_date_obj = date.fromisoformat(balance_date)
                
                # Get old balance based on client type
                if not client_exchange.client.is_company_client:
                    # My Clients: Old Balance = balance after last settlement
                    old_balance = get_old_balance_after_settlement(client_exchange, as_of_date=balance_record_date_obj)
                else:
                    # Company Clients: Use existing logic
                    old_balance = get_old_balance(client_exchange, balance_record_date=balance_record_date_obj)
                
                new_balance = remaining_balance + extra_adjustment
                balance, created = ClientDailyBalance.objects.update_or_create(
                    client_exchange=client_exchange,
                    date=balance_record_date_obj,
                    defaults={
                        "remaining_balance": remaining_balance,
                        "extra_adjustment": extra_adjustment,
                        "note": note,
                    }
                )
                
                # Always create a new transaction for this balance record
                # Each recording creates a separate transaction entry (no updates to existing transactions)
                from datetime import datetime
                balance_note = note or f"Balance Record: ₹{remaining_balance}"
                if extra_adjustment:
                    balance_note += f" + Adjustment: ₹{extra_adjustment}"
                balance_note += f" (Recorded at {datetime.now().strftime('%H:%M:%S')})"
                
                Transaction.objects.create(
                    client_exchange=client_exchange,
                    date=balance_record_date_obj,
                    transaction_type=Transaction.TYPE_BALANCE_RECORD,
                    amount=new_balance,
                    client_share_amount=new_balance,
                    your_share_amount=Decimal(0),
                    company_share_amount=Decimal(0),
                    note=balance_note,
                )
                
                # Create LOSS or PROFIT transactions based on balance movement
                # This will automatically create the appropriate transaction and update tally/outstanding
                create_loss_profit_from_balance_change(
                    client_exchange, 
                    old_balance, 
                    new_balance, 
                    balance_record_date_obj,
                    note_suffix=""
                )
                
                # Update tally/outstanding if balance changed
                if new_balance != old_balance:
                    if not client_exchange.client.is_company_client:
                        # My Clients: Use outstanding (netted system) with new logic
                        update_outstanding_from_balance_change(
                            client_exchange, 
                            old_balance, 
                            new_balance, 
                            balance_date=balance_record_date_obj
                        )
                    else:
                        # Company Clients: Use tally ledger (tally system)
                        update_tally_from_balance_change(client_exchange, old_balance, new_balance)
            
            # Redirect to appropriate namespace based on client type
            if client.is_company_client:
                return redirect(reverse("company_clients:balance", args=[client.pk]) + (f"?exchange={client_exchange_id}" if client_exchange_id else ""))
            else:
                return redirect(reverse("my_clients:balance", args=[client.pk]) + (f"?exchange={client_exchange_id}" if client_exchange_id else ""))
    
    # Check if editing a balance
    edit_balance_id = request.GET.get("edit_balance")
    edit_balance = None
    if edit_balance_id:
        try:
            edit_balance = ClientDailyBalance.objects.get(pk=edit_balance_id, client_exchange__client=client)
        except ClientDailyBalance.DoesNotExist:
            pass
    
    # Get filter for exchange
    selected_exchange_id = request.GET.get("exchange")
    selected_exchange = None
    if selected_exchange_id:
        try:
            selected_exchange = ClientExchange.objects.get(pk=selected_exchange_id, client=client)
        except ClientExchange.DoesNotExist:
            pass
    
    # Calculate balances per client-exchange
    client_exchanges = client.client_exchanges.select_related("exchange").all()
    
    # Filter by selected exchange if provided
    if selected_exchange:
        client_exchanges = client_exchanges.filter(pk=selected_exchange.pk)
    
    # Get system settings for calculations
    settings = SystemSettings.load()
    
    exchange_balances = []
    
    for client_exchange in client_exchanges:
        transactions = Transaction.objects.filter(client_exchange=client_exchange)
        
        total_funding = transactions.filter(transaction_type=Transaction.TYPE_FUNDING).aggregate(total=Sum("amount"))["total"] or 0
        total_profit = transactions.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("amount"))["total"] or 0
        total_loss = transactions.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("amount"))["total"] or 0
        total_turnover = transactions.aggregate(total=Sum("amount"))["total"] or 0
        
        client_profit_share = transactions.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("client_share_amount"))["total"] or 0
        client_loss_share = transactions.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("client_share_amount"))["total"] or 0
        
        your_profit_share = transactions.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
        your_loss_share = transactions.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("your_share_amount"))["total"] or 0
        
        client_net = total_funding + client_profit_share - client_loss_share
        you_net = your_profit_share - your_loss_share
        
        # Get daily balance records for this exchange
        daily_balances = ClientDailyBalance.objects.filter(
            client_exchange=client_exchange
        ).order_by("-date")[:10]  # Last 10 records per exchange
        
        # Get latest daily balance record (most recent)
        latest_balance_record = ClientDailyBalance.objects.filter(
            client_exchange=client_exchange
        ).order_by("-date").first()
        
        # Calculate profit/loss using new logic
        profit_loss_data = calculate_client_profit_loss(client_exchange)
        
        # Use client-specific my_share_pct from ClientExchange configuration
        # This is the percentage configured on the client detail page
        admin_profit_share_pct = client_exchange.my_share_pct
        
        # Calculate admin profit/loss - pass client_exchange for correct company share calculation
        admin_data = calculate_admin_profit_loss(profit_loss_data["client_profit_loss"], settings, admin_profit_share_pct, client_exchange)
        
        # Total balance in exchange account (recorded + extra adjustment)
        if latest_balance_record:
            total_balance_in_exchange = latest_balance_record.remaining_balance + (latest_balance_record.extra_adjustment or Decimal(0))
        else:
            total_balance_in_exchange = client_net
        
        # Calculate you owe client = client profit share minus settlements where admin paid
        client_settlements_paid = transactions.filter(
            transaction_type=Transaction.TYPE_SETTLEMENT,
            client_share_amount__gt=0,
            your_share_amount=0
        ).aggregate(total=Sum("client_share_amount"))["total"] or Decimal(0)
        pending_you_owe = max(Decimal(0), client_profit_share - client_settlements_paid)
        
        exchange_balances.append({
            "client_exchange": client_exchange,
            "exchange": client_exchange.exchange,
            "total_funding": total_funding,
            "total_profit": total_profit,
            "total_loss": total_loss,
            "total_turnover": total_turnover,
            "client_net": client_net,
            "you_net": you_net,
            # Pending amounts removed - no longer using PendingAmount model
            "pending_client_owes": Decimal(0),
            # You owe client = client profit share minus settlements where admin paid
            "pending_you_owe": pending_you_owe,
            "daily_balances": daily_balances,
            "latest_balance_record": latest_balance_record,
            "total_balance_in_exchange": total_balance_in_exchange,
            # New profit/loss calculations
            "client_profit_loss": profit_loss_data["client_profit_loss"],
            "is_profit": profit_loss_data["is_profit"],
            "admin_profit": admin_data["admin_profit"],
            "admin_loss": admin_data["admin_loss"],
            "company_share_profit": admin_data["company_share_profit"],
            "company_share_loss": admin_data["company_share_loss"],
            "admin_net": admin_data["admin_net"],
            "admin_bears": admin_data.get("admin_bears", Decimal(0)),
            "admin_profit_share_pct_used": admin_data.get("admin_profit_share_pct_used", settings.admin_profit_share_pct),
            "admin_earns": admin_data.get("admin_earns", Decimal(0)),
            "admin_pays": admin_data.get("admin_pays", Decimal(0)),
            "company_earns": admin_data.get("company_earns", Decimal(0)),
            "company_pays": admin_data.get("company_pays", Decimal(0)),
            "company_share_pct": client_exchange.company_share_pct if client.is_company_client else Decimal(0),
            "my_share_pct": client_exchange.my_share_pct,
        })
    
    # Get all daily balances for the client (for summary view)
    daily_balance_qs = ClientDailyBalance.objects.filter(
        client_exchange__client=client
    ).select_related("client_exchange", "client_exchange__exchange")
    
    # Filter daily balances by selected exchange if provided
    if selected_exchange:
        daily_balance_qs = daily_balance_qs.filter(client_exchange=selected_exchange)
    
    all_daily_balances = daily_balance_qs.order_by("-date")[:30]
    
    # Get all transactions for the selected exchange (or all exchanges if none selected)
    if selected_exchange:
        all_transactions = Transaction.objects.filter(
            client_exchange=selected_exchange
        ).select_related("client_exchange", "client_exchange__exchange").order_by("-date", "-created_at")
    else:
        all_transactions = Transaction.objects.filter(
            client_exchange__client=client
        ).select_related("client_exchange", "client_exchange__exchange").order_by("-date", "-created_at")
    
    # Annotate transactions with recorded balances for their dates
    transactions_with_balances = []
    for tx in all_transactions:
        # For balance record transactions, the transaction amount IS the recorded balance
        if tx.transaction_type == Transaction.TYPE_BALANCE_RECORD:
            # Create a mock balance object with the transaction amount
            class MockBalance:
                def __init__(self, amount):
                    self.remaining_balance = amount
                    self.extra_adjustment = Decimal(0)
            tx.recorded_balance = MockBalance(tx.amount)
        else:
            # For other transactions, find the balance record created closest to (but before or at) this transaction's time
            # First, try to find balance records on the same date, created before or at this transaction's time
            recorded_balance = ClientDailyBalance.objects.filter(
                client_exchange=tx.client_exchange,
                date=tx.date,
                created_at__lte=tx.created_at
            ).order_by('-created_at').first()
            
            # If no balance on same date before this transaction, get the most recent balance before this date
            if not recorded_balance:
                recorded_balance = ClientDailyBalance.objects.filter(
                    client_exchange=tx.client_exchange,
                    date__lt=tx.date
                ).order_by('-date', '-created_at').first()
            
            # If still no balance record found, calculate from transactions
            if not recorded_balance:
                # Calculate balance from transactions up to this point
                balance_amount = get_exchange_balance(tx.client_exchange, as_of_date=tx.date)
                class MockBalance:
                    def __init__(self, amount):
                        self.remaining_balance = amount
                        self.extra_adjustment = Decimal(0)
                tx.recorded_balance = MockBalance(balance_amount)
            else:
                tx.recorded_balance = recorded_balance
        
        transactions_with_balances.append(tx)
    
    all_transactions = transactions_with_balances
    
    # Calculate total balance across all exchanges (or selected exchange)
    total_balance_all_exchanges = Decimal(0)
    for bal in exchange_balances:
        total_balance_all_exchanges += Decimal(str(bal["total_balance_in_exchange"]))
    
    # Get all client exchanges for the dropdown (not filtered)
    all_client_exchanges = client.client_exchanges.select_related("exchange").all()
    
    # Get selected exchange name for display
    selected_exchange_name = None
    if selected_exchange and exchange_balances:
        selected_exchange_name = exchange_balances[0]["exchange"].name
    
    # Determine client type for URL namespace
    client_type = "company" if client.is_company_client else "my"
    
    context = {
        "client": client,
        "exchange_balances": exchange_balances,
        "all_daily_balances": all_daily_balances,
        "total_balance_all_exchanges": total_balance_all_exchanges,
        "today": date.today(),
        "edit_balance": edit_balance,
        "edit_balance_id": edit_balance_id,
        "client_exchanges": client_exchanges,  # Filtered exchanges for display
        "all_client_exchanges": all_client_exchanges,  # All exchanges for dropdown
        "selected_exchange_id": int(selected_exchange_id) if selected_exchange_id else None,
        "selected_exchange_name": selected_exchange_name,
        "settings": settings,
        "client_type": client_type,
        "all_transactions": all_transactions,
    }
    return render(request, "core/clients/balance.html", context)


