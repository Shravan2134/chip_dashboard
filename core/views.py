from datetime import date, datetime, timedelta
from decimal import Decimal
import json

from django.contrib.auth import logout, login, authenticate
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum, Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .models import Client, Exchange, ClientExchange, Transaction, CompanyShareRecord, SystemSettings, ClientDailyBalance, PendingAmount


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


def get_pending_amount(client_exchange, as_of_date=None):
    """
    Get pending amount (separate ledger for unpaid losses) as of a specific date.
    Pending = Sum of losses - Sum of client payments (settlements) up to as_of_date.
    
    Args:
        client_exchange: ClientExchange instance
        as_of_date: Optional date to calculate as of. If None, uses current PendingAmount record.
    
    Returns:
        Pending amount as of the specified date
    """
    if as_of_date is None:
        # Use current pending amount record
        pending, _ = PendingAmount.objects.get_or_create(
            client_exchange=client_exchange,
            defaults={"pending_amount": Decimal(0)}
        )
        return pending.pending_amount
    
    # Calculate historical pending: losses minus client payments up to as_of_date
    # Losses create pending
    loss_filter = {
        "client_exchange": client_exchange,
        "transaction_type": Transaction.TYPE_LOSS,
        "date__lte": as_of_date
    }
    total_losses = Transaction.objects.filter(**loss_filter).aggregate(total=Sum("amount"))["total"] or Decimal(0)
    
    # Client payments (settlements where client pays) reduce pending
    # Settlement transactions where client_share_amount is 0 and your_share_amount > 0 means client paid
    settlement_filter = {
        "client_exchange": client_exchange,
        "transaction_type": Transaction.TYPE_SETTLEMENT,
        "date__lte": as_of_date,
        "client_share_amount": 0,  # Client pays
        "your_share_amount__gt": 0  # Admin receives
    }
    client_payments = Transaction.objects.filter(**settlement_filter).aggregate(total=Sum("your_share_amount"))["total"] or Decimal(0)
    
    # Historical pending = losses - client payments
    historical_pending = max(Decimal(0), total_losses - client_payments)
    return historical_pending


def update_pending_from_balance_change(client_exchange, previous_balance, new_balance):
    """
    Update pending amount when exchange balance changes.
    If balance decreases, add the difference to pending (loss).
    If balance increases, it's profit (doesn't affect pending).
    Pending is a separate ledger - only losses create pending.
    """
    if new_balance < previous_balance:
        # Balance decreased = loss, add to pending
        loss = previous_balance - new_balance
        pending, _ = PendingAmount.objects.get_or_create(
            client_exchange=client_exchange,
            defaults={"pending_amount": Decimal(0)}
        )
        pending.pending_amount += loss
        pending.save()
        return loss
    return Decimal(0)


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
        - pending_amount: Unpaid losses (separate ledger)
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
    
    # Get pending amount as of date (losses minus settlements up to that date)
    if as_of_date:
        pending_amount = get_pending_amount(client_exchange, as_of_date=as_of_date)
    else:
        pending_amount = get_pending_amount(client_exchange)
    
    # Calculate profit/loss (exchange balance change from funding)
    client_profit_loss = exchange_balance - total_funding
    is_profit = client_profit_loss > 0
    
    return {
        "total_funding": total_funding,
        "exchange_balance": exchange_balance,
        "pending_amount": pending_amount,
        "client_profit_loss": client_profit_loss,
        "is_profit": is_profit,
        "latest_balance_record": latest_balance_record,
    }


def calculate_admin_profit_loss(client_profit_loss, settings, admin_profit_share_pct=None, client_exchange=None):
    """
    Calculate admin profit/loss and company share based on client profit/loss.
    
    NEW LOGIC:
    - On LOSS: Admin earns X% of loss, Company earns Y% of loss (independent)
    - On PROFIT: Admin pays X% of profit, Company pays Y% of profit (independent)
    - For company clients: Company share is calculated from CLIENT's share using client_exchange.company_share_pct
    - For my clients: No company share
    
    Args:
        client_profit_loss: Client's profit (positive) or loss (negative)
        settings: SystemSettings instance
        admin_profit_share_pct: Optional admin profit share percentage. If None, uses settings.admin_profit_share_pct
        client_exchange: Optional ClientExchange instance for company share calculation
    
    Returns:
        dict with:
        - admin_earns: Admin earnings on client loss (if client in loss)
        - admin_pays: Admin payment on client profit (if client in profit)
        - company_earns: Company earnings on client loss
        - company_pays: Company payment on client profit
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
        # Client in LOSS - Admin and Company EARN (independent shares from loss)
        client_loss = abs(client_profit_loss)
        admin_earns = (client_loss * settings.admin_loss_share_pct) / Decimal(100)
        
        # Company share on loss: use system settings (percentage of total loss)
        company_earns = (client_loss * settings.company_loss_share_pct) / Decimal(100)
        
        return {
            "admin_earns": admin_earns,
            "admin_pays": Decimal(0),
            "company_earns": company_earns,
            "company_pays": Decimal(0),
            "admin_net": admin_earns,  # Admin earns, no deduction
            "admin_bears": Decimal(0),  # No loss when client is in loss
            "admin_profit_share_pct_used": admin_profit_share_pct,
            # Legacy fields for backward compatibility
            "admin_profit": admin_earns,
            "admin_loss": Decimal(0),
            "company_share_profit": company_earns,
            "company_share_loss": Decimal(0),
        }
    else:
        # Client in PROFIT - Admin and Company PAY (independent shares from profit)
        client_profit = client_profit_loss
        admin_pays = (client_profit * admin_profit_share_pct) / Decimal(100)
        
        # Calculate company share based on client type
        if client_exchange and client_exchange.client.is_company_client:
            # For company clients: company share is percentage of CLIENT's share
            # Client's share = total profit - admin's share
            client_share = client_profit - admin_pays
            company_pays = (client_share * client_exchange.company_share_pct) / Decimal(100)
        else:
            # For my clients or no client_exchange: use system settings (percentage of total profit)
            company_pays = (client_profit * settings.company_profit_share_pct) / Decimal(100)
        
        return {
            "admin_earns": Decimal(0),
            "admin_pays": admin_pays,
            "company_earns": Decimal(0),
            "company_pays": company_pays,
            "admin_net": -admin_pays,  # Negative because admin pays
            "admin_bears": admin_pays,  # Amount admin pays (company pays separately)
            "admin_profit_share_pct_used": admin_profit_share_pct,
            # Legacy fields for backward compatibility
            "admin_profit": Decimal(0),
            "admin_loss": admin_pays,
            "company_share_profit": Decimal(0),
            "company_share_loss": company_pays,
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
    client_type_filter = request.GET.get("client_type", "")  # "company", "my", or ""
    
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

    # Pending sections - use PendingAmount model for accurate tracking
    # Clients owe you = sum of all pending amounts (unpaid losses)
    pending_amounts_qs = PendingAmount.objects.filter(client_exchange__client__user=request.user)
    if client_id:
        pending_amounts_qs = pending_amounts_qs.filter(client_exchange__client_id=client_id)
    elif client_type_filter == "company":
        pending_amounts_qs = pending_amounts_qs.filter(client_exchange__client__is_company_client=True)
    elif client_type_filter == "my":
        pending_amounts_qs = pending_amounts_qs.filter(client_exchange__client__is_company_client=False)
    
    pending_clients_owe = pending_amounts_qs.aggregate(total=Sum("pending_amount"))["total"] or Decimal(0)
    
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
        amount = Decimal(request.POST.get("amount", 0))
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
        amount = Decimal(request.POST.get("amount", 0))
        tx_date = request.POST.get("date")
        note = request.POST.get("note", "")
        payment_type = request.POST.get("payment_type", "client_pays")  # client_pays or admin_pays_profit
        
        # Get report_type from POST or GET to preserve it in redirect
        report_type = request.POST.get("report_type") or request.GET.get("report_type", "weekly")
        
        # Debug logging
        print(f"settle_payment POST data: client_id={client_id}, client_exchange_id={client_exchange_id}, amount={amount}, tx_date={tx_date}, payment_type={payment_type}")
        
        if client_id and client_exchange_id and amount > 0 and tx_date:
            try:
                client = get_object_or_404(Client, pk=client_id, user=request.user)
                client_exchange = get_object_or_404(ClientExchange, pk=client_exchange_id, client=client)
                
                # payment_type should be either "client_pays" or "admin_pays_profit"
                if payment_type == "client_pays":
                    # Client pays pending amount - reduces pending (partial or full payment)
                    pending, _ = PendingAmount.objects.get_or_create(
                        client_exchange=client_exchange,
                        defaults={"pending_amount": Decimal(0)}
                    )
                    
                    # Get current pending amount
                    current_pending = pending.pending_amount
                    
                    # Reduce pending by payment amount (can't go below 0)
                    # Allow partial payments - any amount up to pending
                    payment_amount = min(amount, current_pending)  # Don't allow overpayment
                    pending.pending_amount = max(Decimal(0), current_pending - payment_amount)
                    pending.save()
                    
                    # Create SETTLEMENT transaction for client payment
                    transaction = Transaction.objects.create(
                        client_exchange=client_exchange,
                        date=datetime.strptime(tx_date, "%Y-%m-%d").date(),
                        transaction_type=Transaction.TYPE_SETTLEMENT,
                        amount=payment_amount,
                        client_share_amount=Decimal(0),  # Client pays, so negative for client
                        your_share_amount=payment_amount,  # Admin receives
                        company_share_amount=Decimal(0),
                        note=note or f"Client payment against pending amount (₹{payment_amount} of ₹{current_pending})",
                    )
                    
                    from django.contrib import messages
                    messages.success(request, f"Payment of ₹{payment_amount} recorded successfully for {client.name} - {client_exchange.exchange.name}. Remaining pending: ₹{pending.pending_amount}")
                    
                    return redirect(reverse("pending:summary") + f"?section=clients-owe&report_type={report_type}")
                elif payment_type == "admin_pays_profit":
                    # Admin pays client profit - doesn't affect pending or exchange balance
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
                    
                    return redirect(reverse("pending:summary") + f"?section=you-owe&report_type={report_type}")
                else:
                    # Invalid payment type
                    from django.contrib import messages
                    messages.error(request, f"Invalid payment type: {payment_type}")
                    return redirect(reverse("pending:summary") + f"?section=you-owe&report_type={report_type}")
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
                return redirect(reverse("pending:summary") + f"?section={section}&report_type={report_type}")
    
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
        client.delete()
        from django.contrib import messages
        messages.success(request, f"Client '{client_name}' has been deleted successfully.")
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
    
    transactions = Transaction.objects.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").filter(client_exchange__client__user=request.user)
    
    if client_id:
        transactions = transactions.filter(client_exchange__client_id=client_id)
    if exchange_id:
        transactions = transactions.filter(client_exchange__exchange_id=exchange_id)
    if start_date_str:
        transactions = transactions.filter(date__gte=date.fromisoformat(start_date_str))
    if end_date_str:
        transactions = transactions.filter(date__lte=date.fromisoformat(end_date_str))
    if tx_type:
        transactions = transactions.filter(transaction_type=tx_type)
    if search_query:
        transactions = transactions.filter(
            Q(client_exchange__client__name__icontains=search_query) |
            Q(client_exchange__client__code__icontains=search_query) |
            Q(client_exchange__exchange__name__icontains=search_query) |
            Q(note__icontains=search_query)
        )
    
    transactions = transactions.order_by("-date", "-created_at")[:200]
    
    return render(request, "core/transactions/list.html", {
        "transactions": transactions,
        "all_clients": Client.objects.filter(user=request.user, is_active=True).order_by("name"),
        "all_exchanges": Exchange.objects.filter(is_active=True).order_by("name"),
        "selected_client": int(client_id) if client_id else None,
        "selected_exchange": int(exchange_id) if exchange_id else None,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "selected_type": tx_type,
        "search_query": search_query,
    })


@login_required
def pending_summary(request):
    """
    Pending payments view based on separate ledgers:
    - Clients owe you: Clients with pending amount (unpaid losses)
    - You owe clients: Clients in profit (exchange balance > total funding)
    
    Separate Ledgers:
    - Exchange Balance: Client's playing balance (separate)
    - Pending Amount: Unpaid losses (separate, only affected by losses and client payments)
    - Funding: Chips given (only affects exchange balance)
    - Settlement: Actual payments (client pays pending OR admin pays profit)
    
    Supports report types: daily, weekly, monthly
    """
    from datetime import timedelta
    
    today = date.today()
    report_type = request.GET.get("report_type", "daily")  # daily, weekly, monthly
    
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
    
    # Get system settings
    settings = SystemSettings.load()
    
    # Separate lists based on separate ledgers
    clients_owe_list = []  # Clients with pending amount (unpaid losses)
    you_owe_list = []  # Clients in profit (admin owes)
    
    for client_exchange in client_exchanges:
        # Get data from separate ledgers
        profit_loss_data = calculate_client_profit_loss(client_exchange)
        pending_amount = profit_loss_data["pending_amount"]
        client_profit_loss = profit_loss_data["client_profit_loss"]
        
        # Clients with pending amount (unpaid losses)
        if pending_amount > 0:
            clients_owe_list.append({
                "client_id": client_exchange.client.pk,
                "client_name": client_exchange.client.name,
                "client_code": client_exchange.client.code,
                "exchange_name": client_exchange.exchange.name,
                "exchange_id": client_exchange.exchange.pk,
                "client_exchange_id": client_exchange.pk,
                "pending_amount": pending_amount,
                "total_funding": profit_loss_data["total_funding"],
                "exchange_balance": profit_loss_data["exchange_balance"],
            })
        
        # Clients in profit (admin owes)
        # Calculate unpaid profit: client profit shares minus settlements where admin paid
        if client_profit_loss > 0:
            # Get client profit shares from PROFIT transactions
            profit_transactions = Transaction.objects.filter(
                client_exchange=client_exchange,
                transaction_type=Transaction.TYPE_PROFIT
            )
            client_profit_shares = profit_transactions.aggregate(total=Sum("client_share_amount"))["total"] or Decimal(0)
            
            # If no PROFIT transactions but client has profit, calculate client share from profit_loss
            if client_profit_shares == 0:
                # Calculate client's share based on share percentages
                my_share_pct = client_exchange.my_share_pct
                
                # For "my clients": company is not involved, so client gets (100 - my_share_pct)%
                # For "company clients": client gets (100 - my_share_pct) * (100 - company_share_pct) / 100
                if client_exchange.client.is_company_client:
                    company_share_pct = client_exchange.company_share_pct
                    client_share_pct = (Decimal(100) - my_share_pct) * (Decimal(100) - company_share_pct) / Decimal(100)
                else:
                    # My clients: company not involved, client gets remaining share
                    client_share_pct = Decimal(100) - my_share_pct
                
                client_profit_shares = client_profit_loss * client_share_pct / Decimal(100)
            
            # Get settlements where admin paid client (client receives, admin pays)
            settlement_transactions = Transaction.objects.filter(
                client_exchange=client_exchange,
                transaction_type=Transaction.TYPE_SETTLEMENT,
                client_share_amount__gt=0,  # Client receives
                your_share_amount=0  # Admin pays, doesn't receive
            )
            settlements_paid = settlement_transactions.aggregate(total=Sum("client_share_amount"))["total"] or Decimal(0)
            
            # Unpaid profit = client profit shares - settlements already paid
            unpaid_profit = max(Decimal(0), client_profit_shares - settlements_paid)
            
            # Calculate admin's share (my share) from total profit
            my_share_pct = client_exchange.my_share_pct
            my_share = client_profit_loss * my_share_pct / Decimal(100)
            
            # Only show if there's unpaid profit
            if unpaid_profit > 0:
                you_owe_list.append({
                    "client_id": client_exchange.client.pk,
                    "client_name": client_exchange.client.name,
                    "client_code": client_exchange.client.code,
                    "exchange_name": client_exchange.exchange.name,
                    "exchange_id": client_exchange.exchange.pk,
                    "client_exchange_id": client_exchange.pk,
                    "client_profit": unpaid_profit,  # Show unpaid amount, not total profit
                    "my_share": my_share,  # Admin's share of total profit
                    "total_funding": profit_loss_data["total_funding"],
                    "exchange_balance": profit_loss_data["exchange_balance"],
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
        "start_date": start_date,
        "end_date": end_date,
        "date_range_label": date_range_label,
        "settings": settings,
    }
    return render(request, "core/pending/summary.html", context)


@login_required
def report_overview(request):
    """High-level reporting screen with simple totals and graphs."""
    from datetime import timedelta
    from collections import defaultdict

    today = date.today()
    report_type = request.GET.get("report_type", "monthly")  # Default to monthly
    client_type_filter = request.GET.get("client_type", "")  # "company", "my", or "" for all
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
    
    # Determine date range
    if start_date_str and end_date_str:
        # Use date range
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
        as_of = end_date  # For display purposes
        qs = Transaction.objects.filter(client_exchange__client__user=request.user, date__gte=start_date, date__lte=end_date)
        date_range_mode = True
    elif as_of_str:
        # Legacy: single date (up to that date)
        as_of = date.fromisoformat(as_of_str)
        qs = Transaction.objects.filter(client_exchange__client__user=request.user, date__lte=as_of)
        date_range_mode = False
        start_date = None
        end_date = None
    else:
        # Default: today
        as_of = date.today()
        qs = Transaction.objects.filter(client_exchange__client__user=request.user, date__lte=as_of)
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
    if date_range_mode:
        # For date range, calculate pending as of end_date
        client_exchanges_in_range = ClientExchange.objects.filter(
            client__user=request.user,
            transactions__date__gte=start_date,
            transactions__date__lte=end_date
        ).distinct()
        pending_clients_owe = Decimal(0)
        for ce in client_exchanges_in_range:
            pending_amount = get_pending_amount(ce, as_of_date=end_date)
            pending_clients_owe += pending_amount
    else:
        # For single date, calculate pending as of that date
        client_exchanges_up_to = ClientExchange.objects.filter(
            client__user=request.user,
            transactions__date__lte=as_of
        ).distinct()
        pending_clients_owe = Decimal(0)
        for ce in client_exchanges_up_to:
            pending_amount = get_pending_amount(ce, as_of_date=as_of)
            pending_clients_owe += pending_amount
    
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
            
            # Auto-calculate shares based on client-exchange percentages
            # Company share is taken from CLIENT's share, not from admin's share
            # Only calculate company share for company clients
            is_company_client = client_exchange.client.is_company_client
            
            if tx_type == Transaction.TYPE_PROFIT:
                your_share = amount * (client_exchange.my_share_pct / 100)
                client_share = amount - your_share
                # Only calculate company share for company clients
                if is_company_client:
                    company_share = client_share * (client_exchange.company_share_pct / 100)
                else:
                    company_share = Decimal(0)  # No company share for "my clients"
                your_share_after_company = your_share  # Admin keeps full share, company takes from client
            elif tx_type == Transaction.TYPE_LOSS:
                your_share = amount * (client_exchange.my_share_pct / 100)
                client_share = amount - your_share
                company_share = Decimal(0)  # No company share on losses
                your_share_after_company = your_share
            else:  # FUNDING or SETTLEMENT
                client_share = amount
                your_share = Decimal(0)
                company_share = Decimal(0)
                your_share_after_company = Decimal(0)
            
            # Client share amount should be after company deduction (for profit transactions)
            client_share_after_company = client_share - company_share if tx_type == Transaction.TYPE_PROFIT else client_share
            
            transaction = Transaction.objects.create(
                client_exchange=client_exchange,
                date=datetime.strptime(tx_date, "%Y-%m-%d").date(),
                transaction_type=tx_type,
                amount=amount,
                client_share_amount=client_share_after_company,
                your_share_amount=your_share_after_company,
                company_share_amount=company_share,
                note=note,
            )
            
            # Update pending amount when LOSS transaction is created
            # Losses create pending (unpaid losses that client owes)
            if tx_type == Transaction.TYPE_LOSS:
                pending, _ = PendingAmount.objects.get_or_create(
                    client_exchange=client_exchange,
                    defaults={"pending_amount": Decimal(0)}
                )
                # Add the full loss amount to pending (client owes this)
                pending.pending_amount += amount
                pending.save()
            
            # Create company share record if applicable (only for company clients)
            if company_share > 0 and is_company_client:
                CompanyShareRecord.objects.create(
                    client_exchange=client_exchange,
                    transaction=transaction,
                    date=transaction.date,
                    company_amount=company_share,
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
    
    # Get pending amount before transaction
    pending_before = get_pending_amount(client_exchange, as_of_date=before_date)
    
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
    
    # Get pending amount after transaction
    if transaction.transaction_type == Transaction.TYPE_LOSS:
        pending_after = pending_before + transaction.amount
    elif transaction.transaction_type == Transaction.TYPE_SETTLEMENT and transaction.client_share_amount == 0 and transaction.your_share_amount > 0:
        # Client payment reduces pending
        pending_after = max(Decimal(0), pending_before - transaction.your_share_amount)
    else:
        pending_after = pending_before
    
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
    pending_change = pending_after - pending_before
    
    # Determine client type for URL routing
    client_type = "company" if client.is_company_client else "my"
    
    context = {
        "transaction": transaction,
        "client": client,
        "client_exchange": client_exchange,
        "client_type": client_type,
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
        "pending_before": pending_before,
        "pending_after": pending_after,
        "pending_change": pending_change,
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
            
            # Recalculate shares
            # Company share is taken from CLIENT's share, not from admin's share
            # Only calculate company share for company clients
            is_company_client = client_exchange.client.is_company_client
            
            if tx_type == Transaction.TYPE_PROFIT:
                your_share = amount * (client_exchange.my_share_pct / 100)
                client_share = amount - your_share
                # Only calculate company share for company clients
                if is_company_client:
                    company_share = client_share * (client_exchange.company_share_pct / 100)
                else:
                    company_share = Decimal(0)  # No company share for "my clients"
                your_share_after_company = your_share  # Admin keeps full share, company takes from client
            elif tx_type == Transaction.TYPE_LOSS:
                your_share = amount * (client_exchange.my_share_pct / 100)
                client_share = amount - your_share
                company_share = Decimal(0)
                your_share_after_company = your_share
            else:
                client_share = amount
                your_share = Decimal(0)
                company_share = Decimal(0)
                your_share_after_company = Decimal(0)
            
            # Client share amount should be after company deduction (for profit transactions)
            client_share_after_company = client_share - company_share if tx_type == Transaction.TYPE_PROFIT else client_share
            
            # Track old transaction type and amount for pending updates
            old_tx_type = transaction.transaction_type
            old_amount = transaction.amount
            
            transaction.date = datetime.strptime(tx_date, "%Y-%m-%d").date()
            transaction.transaction_type = tx_type
            transaction.amount = amount
            transaction.client_share_amount = client_share_after_company
            transaction.your_share_amount = your_share_after_company
            transaction.company_share_amount = company_share
            transaction.note = note
            transaction.save()
            
            # Update pending amount when transaction type or amount changes
            pending, _ = PendingAmount.objects.get_or_create(
                client_exchange=client_exchange,
                defaults={"pending_amount": Decimal(0)}
            )
            
            # If old transaction was a loss, remove it from pending
            if old_tx_type == Transaction.TYPE_LOSS:
                pending.pending_amount = max(Decimal(0), pending.pending_amount - old_amount)
            
            # If new transaction is a loss, add it to pending
            if tx_type == Transaction.TYPE_LOSS:
                pending.pending_amount += amount
            
            pending.save()
            
            # Update company share record (only for company clients)
            if company_share > 0 and is_company_client:
                csr, _ = CompanyShareRecord.objects.get_or_create(
                    transaction=transaction,
                    defaults={"client_exchange": client_exchange, "date": transaction.date, "company_amount": company_share}
                )
                if csr.company_amount != company_share:
                    csr.company_amount = company_share
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
    
    qs = Transaction.objects.filter(client_exchange__client__user=request.user, date=report_date)
    
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
            
            # Get previous balance before updating
            previous_balance = get_exchange_balance(client_exchange)
            
            if balance_id:
                # Edit existing balance
                balance = get_object_or_404(ClientDailyBalance, pk=balance_id, client_exchange__client=client)
                # Get previous balance from this record
                old_balance = balance.remaining_balance + (balance.extra_adjustment or Decimal(0))
                balance.date = date.fromisoformat(balance_date)
                balance.client_exchange = client_exchange
                balance.remaining_balance = remaining_balance
                balance.extra_adjustment = extra_adjustment
                balance.note = note
                balance.save()
                
                # Calculate new balance
                new_balance = remaining_balance + extra_adjustment
                
                # Update pending if balance decreased
                if new_balance < old_balance:
                    update_pending_from_balance_change(client_exchange, old_balance, new_balance)
            else:
                # Create new balance
                new_balance = remaining_balance + extra_adjustment
                balance, created = ClientDailyBalance.objects.update_or_create(
                    client_exchange=client_exchange,
                    date=date.fromisoformat(balance_date),
                    defaults={
                        "remaining_balance": remaining_balance,
                        "extra_adjustment": extra_adjustment,
                        "note": note,
                    }
                )
                
                # Update pending if balance decreased from previous
                if new_balance < previous_balance:
                    update_pending_from_balance_change(client_exchange, previous_balance, new_balance)
            
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
        
        # For "my clients", use 10% for admin profit share instead of system default
        # For company clients, use system default
        if client.is_company_client:
            admin_profit_share_pct = None  # Use system default
        else:
            admin_profit_share_pct = Decimal("10.00")  # Use 10% for my clients
        
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
            "client_net": client_net,
            "you_net": you_net,
            # Use actual pending amount from PendingAmount model
            "pending_client_owes": profit_loss_data["pending_amount"],
            # You owe client = client profit share minus settlements where admin paid
            "pending_you_owe": pending_you_owe,
            "daily_balances": daily_balances,
            "latest_balance_record": latest_balance_record,
            "total_balance_in_exchange": total_balance_in_exchange,
            # New profit/loss calculations with separate ledgers
            "client_profit_loss": profit_loss_data["client_profit_loss"],
            "is_profit": profit_loss_data["is_profit"],
            "pending_amount": profit_loss_data["pending_amount"],  # Separate ledger
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
        # Get the recorded balance for this transaction's date and client_exchange
        recorded_balance = ClientDailyBalance.objects.filter(
            client_exchange=tx.client_exchange,
            date=tx.date
        ).first()
        
        # Create a dict-like object or add attribute to transaction
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


