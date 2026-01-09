from datetime import date, datetime, timedelta
from decimal import Decimal
import json

from django.contrib.auth import logout, login, authenticate
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum, Count, F
from django.db import transaction as db_transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from .models import (
    Client,
    Exchange,
    ClientExchangeAccount,
    Transaction,
    ClientExchangeReportConfig,
    Settlement,
    )

# TODO: core.utils.money module removed - add back if needed
# Placeholder functions
def round_share(value):
    

    """Placeholder - replace with actual implementation"""
    return Decimal(str(value)) if value else Decimal(0)

def round_capital(value):

    
    """Placeholder - replace with actual implementation"""
    return Decimal(str(value)) if value else Decimal(0)

AUTO_CLOSE_THRESHOLD = Decimal("0.01")


def calculate_share_split(total_share, my_share_pct, friend_share_pct):
    """Placeholder - replace with actual implementation"""
    return Decimal(0), Decimal(0), Decimal(0)


def get_exchange_balance(client_exchange, as_of_date=None, use_cache=True):


    """
    TODO: Add your new calculation logic here.

    Args:
        client_exchange: ClientExchangeAccount instance

        as_of_date: Optional date to calculate as of. If None, uses current state.
        use_cache: If True and as_of_date is None, use cached value if available.
    
    Returns:
        Exchange balance as Decimal (placeholder - replace with your calculation)

    """
    # TODO: Add your new formulas and logic here
    return Decimal(0)



def update_outstanding_from_balance_change(client_exchange, old_balance, current_balance, balance_date=None):


    """
    TODO: Add your new calculation logic here.
    
    Args:
        client_exchange: ClientExchangeAccount instance (must be My Client)

        old_balance: Old Balance (balance after last settlement)
        current_balance: Current Balance (latest balance from exchange)
        balance_date: Date of the balance record (optional)
    
    Returns:
        dict with placeholder values - replace with your calculations

    """
    # TODO: Add your new formulas and logic here
    # Remove all old balance logic, current balance logic, share calculation logic
    return {
        "your_share": Decimal(0),
        "outstanding_before": Decimal(0),
        "outstanding_after": Decimal(0),
        "difference": Decimal(0),
    }


def create_loss_profit_from_balance_change(client_exchange, old_balance, new_balance, balance_date, note_suffix=""):


    """
    TODO: Add your new calculation logic here.
    
    Args:
        client_exchange: ClientExchangeAccount instance

        old_balance: Balance before the change
        new_balance: Balance after the change
        balance_date: Date of the balance record
        note_suffix: Optional suffix for transaction note
    
    Returns:
        Transaction object if created, None otherwise

    """
    # TODO: Add your new formulas and logic here
    # Remove all loss calculation, share calculation, old balance logic
    return None


def calculate_client_profit_loss(client_exchange, as_of_date=None):


    """
    TODO: Add your new calculation logic here.
    
    Args:
        client_exchange: ClientExchangeAccount instance

        as_of_date: Optional date to calculate as of (for time-travel). If None, uses current state.
    
    Returns:
        dict with placeholder values - replace with your calculations

    """
    # TODO: Add your new formulas and logic here
    return {
        "total_funding": Decimal(0),
        "exchange_balance": Decimal(0),
        "client_profit_loss": Decimal(0),
        "is_profit": False,
        "latest_balance_record": None,
    }


def calculate_admin_profit_loss(client_profit_loss, settings, admin_profit_share_pct=None, client_exchange=None):


    """
    TODO: Add your new calculation logic here.
    
    Args:
        client_profit_loss: Client's profit (positive) or loss (negative)

        settings: SystemSettings instance
        admin_profit_share_pct: Optional admin profit share percentage. If None, uses settings.admin_profit_share_pct
        client_exchange: Optional ClientExchangeAccount instance for company share calculation
    
    Returns:
        dict with placeholder values - replace with your calculations

    """
    # TODO: Add your new formulas and logic here
    return {
        "admin_earns": Decimal(0),
        "admin_pays": Decimal(0),
        "company_earns": Decimal(0),
        "company_pays": Decimal(0),
        "admin_net": Decimal(0),
        "admin_bears": Decimal(0),
        "admin_profit_share_pct_used": Decimal(0),
        "admin_profit": Decimal(0),
            "admin_loss": Decimal(0),
            "company_share_profit": Decimal(0),
        "company_share_loss": Decimal(0),
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
    """Logout view."""
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
    
    # All clients are now "my clients" - no filtering needed
    
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
    your_profit = 0  # Computed from accounts, not transactions
    # Company profit removed - no longer applicable
    company_profit = Decimal(0)

    # Pending sections removed - no longer using PendingAmount model
    pending_clients_owe = Decimal(0)
    
    # Pending payments computed from accounts, not transactions
    pending_you_owe_clients = Decimal(0)  # Computed from accounts where Client_PnL > 0

    # All clients
    clients_qs = Client.objects.all()
    
    # Active clients count
    active_clients_count = clients_qs.count()
    
    # Calculate current balance for selected client(s) and exchange
    current_balance = Decimal(0)
    has_transactions = False
    
    if client_id:
        client = Client.objects.filter(pk=client_id, user=request.user).first()
        if client:
                # Specific exchange selected - show balance for that exchange only
                client_exchange = client.exchange_accounts.filter(exchange_id=exchange_id).first()



                if client_exchange:




                    # Check if there are any transactions for this exchange

                    has_transactions = Transaction.objects.filter(client_exchange=client_exchange).exists()




                    if has_transactions:
                        current_balance = get_exchange_balance(client_exchange)
                else:










                # No exchange selected - calculate total balance across all exchanges
                    client_exchanges = client.exchange_accounts.all()
                for ce in client_exchanges:
                    # Only include exchanges that have transactions
                    if Transaction.objects.filter(client_exchange=ce).exists():
                        has_transactions = True
                        current_balance += get_exchange_balance(ce)
    
    if client_type_filter:
        # Filtered by client type

        filtered_clients = clients_qs

        for client in filtered_clients:
            if exchange_id:

                # Specific exchange selected
                client_exchange = client.exchange_accounts.filter(exchange_id=exchange_id).first()


                if client_exchange:
                    if Transaction.objects.filter(client_exchange=client_exchange).exists():
                        has_transactions = True


                        current_balance += get_exchange_balance(client_exchange)
        
        # TODO: Fix else block logic - structure needs to be corrected
        # else:



                # All exchanges
            # TODO: Fix indentation - client_exchanges = client.exchange_accounts.all()


        # TODO: Fix indentation - for ce in client_exchanges:


            # TODO: Fix indentation - if Transaction.objects.filter(client_exchange=ce).exists():


                # TODO: Fix indentation - has_transactions = True



                # TODO: Fix indentation - current_balance += get_exchange_balance(ce)




    # Get all accounts for the current user
    all_accounts = ClientExchangeAccount.objects.filter(client__user=request.user).select_related("client", "exchange")
    
    # Calculate totals from accounts
    total_funding = sum(account.funding for account in all_accounts)
    total_exchange_balance = sum(account.exchange_balance for account in all_accounts)
    total_client_pnl = sum(account.compute_client_pnl() for account in all_accounts)
    total_my_share = sum(account.compute_my_share() for account in all_accounts)
    
    # Count totals
    total_clients = Client.objects.filter(user=request.user).count()
    total_exchanges = Exchange.objects.count()
    total_accounts = all_accounts.count()
    
    # Get recent accounts (last 10 updated)
    recent_accounts = all_accounts.order_by("-updated_at")[:10]
    
    context = {
        "today": today,
        "total_clients": total_clients,
        "total_exchanges": total_exchanges,
        "total_accounts": total_accounts,
        "total_funding": total_funding,
        "total_exchange_balance": total_exchange_balance,
        "total_client_pnl": total_client_pnl,
        "total_my_share": total_my_share,
        "recent_accounts": recent_accounts,
        "total_turnover": total_turnover,
        "your_profit": your_profit,
        "company_profit": company_profit,
        "pending_clients_owe": pending_clients_owe,
        "pending_you_owe_clients": pending_you_owe_clients,
        "active_clients_count": active_clients_count,
        "total_exchanges_count": Exchange.objects.count(),
        "recent_transactions": transactions_qs[:10],
        "all_clients": clients_qs.order_by("name"),
        "all_exchanges": Exchange.objects.all().order_by("name"),
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
    all_exchanges = Exchange.objects.all().order_by("name")
    
    return render(request, "core/clients/list.html", {
        "clients": clients,
        "client_search": client_search,
        "selected_exchange": int(exchange_id) if exchange_id else None,
        "all_exchanges": all_exchanges,
        "client_type": "all",
    })


@login_required


@login_required


def my_clients_list(request):


    """List only my (personal) clients"""
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
    all_exchanges = Exchange.objects.all().order_by("name")
    
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

    # Get all exchange accounts for this client
    accounts = client.exchange_accounts.select_related("exchange").all()

    # Calculate totals
    total_funding = sum(account.funding for account in accounts)
    total_exchange_balance = sum(account.exchange_balance for account in accounts)
    total_client_pnl = sum(account.compute_client_pnl() for account in accounts)

    transactions = (
        Transaction.objects.filter(client_exchange__client=client)
        .select_related("client_exchange", "client_exchange__exchange")
        .order_by("-date", "-created_at")[:50]
    )
    
    return render(
        request,
        "core/clients/detail.html",
        {
            "client": client,
            "accounts": accounts,
            "total_funding": total_funding,
            "total_exchange_balance": total_exchange_balance,
            "total_client_pnl": total_client_pnl,
            "transactions": transactions,
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

        tx_date = request.POST.get("date")
        amount = round_share(Decimal(request.POST.get("amount", 0) or 0))  # Share-space: round DOWN
        note = request.POST.get("note", "")
        
        if client_exchange_id and tx_date and amount > 0:


            
            # Get current exchange balance
            current_balance = get_exchange_balance(client_exchange)

            
            # Create FUNDING transaction
            transaction = Transaction.objects.create(

                client_exchange=client_exchange,

                date=datetime.strptime(tx_date, "%Y-%m-%d").date(),

                type='FUNDING',

                amount=amount,

                client_share_amount=amount,  # Client gets the full amount

                your_share_amount=Decimal(0),

                note=note,

            )

            
            # Update exchange balance by creating/updating balance record
            # Funding increases exchange balance
            new_balance = current_balance + amount

    # TODO: ClientDailyBalance model removed - add back if needed
    # ClientDailyBalance.objects.update_or_create(
    #     client_exchange=client_exchange,
    #     date=datetime.strptime(tx_date, "%Y-%m-%d").date(),
    #     defaults={
    #         "remaining_balance": new_balance,
    #         "extra_adjustment": Decimal(0),
    #         "note": note or f"Funding: +₹{amount}",
    #     }
    # )
            # Funding does NOT affect pending (separate ledger)
            
            # Redirect to client detail
            return redirect("client_detail", pk=client.pk)
    
    # If GET or validation fails, redirect back to client detail
    return redirect("client_detail", pk=client.pk)


@login_required


def settle_payment(request):
    
    
    """
    Simple settlement - creates a SETTLEMENT transaction.
    All partial payment logic, old balance calculations, and formulas have been removed.
    """
    if request.method == "POST":

        from django.shortcuts import get_object_or_404, redirect
        from django.urls import reverse
        from decimal import Decimal
        from core.models import Client, ClientExchangeAccount, Transaction
        from core.utils.money import round_share
        
        client_id = request.POST.get("client_id")
        client_exchange_id = request.POST.get("client_exchange_id")
        amount_raw = request.POST.get("amount", "0") or "0"
        amount = round_share(Decimal(str(amount_raw)))
        tx_date = request.POST.get("date")
        note = request.POST.get("note", "")
        payment_type = request.POST.get("payment_type", "client_pays")
        
        report_type = request.POST.get("report_type") or request.GET.get("report_type", "weekly")
        client_type_filter = request.POST.get("client_type") or request.GET.get("client_type") or request.session.get('client_type_filter', 'all')
        if client_type_filter == '':
            client_type_filter = 'all'

        request.session['client_type_filter'] = client_type_filter
        
        if client_id and client_exchange_id and amount > 0 and tx_date:
            try:
                client = get_object_or_404(Client, pk=client_id, user=request.user)
                client_exchange = get_object_or_404(ClientExchangeAccount, pk=client_exchange_id, client=client)
                
                from django.db import transaction as db_transaction
                from django.contrib import messages
                with db_transaction.atomic():
                    Transaction.objects.create(
    client_exchange=client_exchange,
                        type='RECORD_PAYMENT',
                            amount=amount,
    date=tx_date,
    note=note or f"Settlement: ₹{amount} ({payment_type})"
                    )
                    
                    messages.success(request, f"Settlement of ₹{amount} recorded successfully.")
                    
                    redirect_url = f"?section={'clients-owe' if payment_type == 'client_pays' else 'you-owe'}&report_type={report_type}"
                    if client_type_filter and client_type_filter != 'all':
                        redirect_url += f"&client_type={client_type_filter}"
                    return redirect(reverse("pending_summary") + redirect_url)
            except Exception as e:
                redirect_url = f"?report_type={report_type}"
                if client_type_filter and client_type_filter != 'all':
                    redirect_url += f"&client_type={client_type_filter}"
                return redirect(reverse("pending_summary") + redirect_url)
                    
    
    # If GET or validation fails, redirect to pending summary
    from django.shortcuts import redirect
    from django.urls import reverse
    report_type = request.GET.get("report_type", "weekly")
    return redirect(reverse("pending_summary") + f"?report_type={report_type}")


@login_required


@login_required
def client_create(request):
    """Create a new client
    
    Rules:
    - Client code must be UNIQUE if provided (non-NULL)
    - Client code can be EMPTY/NULL
    - Multiple clients can have the same name
    - If client code is NULL, the index (ID) will always be different
    - Two clients must NEVER have the same non-NULL client code
    """
    if request.method == "POST":
        from django.contrib import messages
        from django.core.exceptions import ValidationError
        from django.db import IntegrityError
        
        name = request.POST.get("name", "").strip()
        code = request.POST.get("code", "").strip()
        referred_by = request.POST.get("referred_by", "").strip()
        is_company_client = request.POST.get("is_company_client") == "on"
        
        if not name:
            messages.error(request, "Client name is required.")
            return render(request, "core/clients/create.html", {
                'code': code,
                'referred_by': referred_by,
                'is_company_client': is_company_client,
            })
        
        # Process code: strip whitespace and convert empty string to None
        if code:
            code = code.strip()
            if not code:
                code = None
        
        # Check for duplicate code BEFORE saving (user-friendly error)
        if code is not None:
            existing_client = Client.objects.filter(code=code).first()
            if existing_client:
                messages.error(
                    request,
                    f"Client code '{code}' is already in use by client '{existing_client.name}'. "
                    f"Please choose a different code or leave it blank."
                )
                return render(request, "core/clients/create.html", {
                    'name': name,
                    'code': code,
                    'referred_by': referred_by,
                    'is_company_client': is_company_client,
                })
        
        try:
            # Create client
            client = Client(
                user=request.user,
                name=name,
                code=code,  # Already None if empty
                referred_by=referred_by if referred_by else None,
                is_company_client=is_company_client,
            )
            # This will call clean() and save()
            client.save()
            
            messages.success(request, f"Client '{name}' has been created successfully.")
            return redirect(reverse("client_list"))
            
        except ValidationError as e:
            # Handle validation errors from model.clean()
            messages.error(request, str(e))
            return render(request, "core/clients/create.html", {
                'name': name,
                'code': code,
                'referred_by': referred_by,
                'is_company_client': is_company_client,
            })
        except IntegrityError as e:
            # Handle database integrity errors (shouldn't happen with pre-check, but safety net)
            if 'unique constraint' in str(e).lower() or 'duplicate' in str(e).lower():
                messages.error(
                    request,
                    f"Client code '{code}' is already in use. Please choose a different code or leave it blank."
                )
            else:
                messages.error(request, f"Error creating client: {str(e)}")
            return render(request, "core/clients/create.html", {
                'name': name,
                'code': code,
                'referred_by': referred_by,
                'is_company_client': is_company_client,
            })
        except Exception as e:
            messages.error(request, f"Error creating client: {str(e)}")
            return render(request, "core/clients/create.html", {
                'name': name,
                'code': code,
                'referred_by': referred_by,
                'is_company_client': is_company_client,
            })
    
    return render(request, "core/clients/create.html")


@login_required


@login_required


def my_client_create(request):
    """Create a my (personal) client
    
    Rules:
    - Client code must be UNIQUE if provided (non-NULL)
    - Client code can be EMPTY/NULL
    - Multiple clients can have the same name
    - If client code is NULL, the index (ID) will always be different
    - Two clients must NEVER have the same non-NULL client code
    """
    if request.method == "POST":
        from django.shortcuts import redirect
        from django.urls import reverse
        from django.contrib import messages
        from django.core.exceptions import ValidationError
        from django.db import IntegrityError
        from core.models import Client

        name = request.POST.get("name", "").strip()
        code = request.POST.get("code", "").strip()
        referred_by = request.POST.get("referred_by", "").strip()
        
        if not name:
            messages.error(request, "Client name is required.")
            return render(request, "core/clients/create_my.html", {
                'code': code,
                'referred_by': referred_by,
            })
        
        # Process code: strip whitespace and convert empty string to None
        if code:
            code = code.strip()
            if not code:
                code = None
        
        # Check for duplicate code BEFORE saving (user-friendly error)
        if code is not None:
            existing_client = Client.objects.filter(code=code).first()
            if existing_client:
                messages.error(
                    request,
                    f"Client code '{code}' is already in use by client '{existing_client.name}'. "
                    f"Please choose a different code or leave it blank."
                )
                return render(request, "core/clients/create_my.html", {
                    'name': name,
                    'code': code,
                    'referred_by': referred_by,
                })
        
        try:
            # Create client
            client = Client(
                user=request.user,
                name=name,
                code=code,  # Already None if empty
                referred_by=referred_by if referred_by else None,
            )
            # This will call clean() and save()
            client.save()
            
            messages.success(request, f"Client '{name}' has been created successfully.")
            return redirect("client_list")
            
        except ValidationError as e:
            # Handle validation errors from model.clean()
            messages.error(request, str(e))
            return render(request, "core/clients/create_my.html", {
                'name': name,
                'code': code,
                'referred_by': referred_by,
            })
        except IntegrityError as e:
            # Handle database integrity errors (shouldn't happen with pre-check, but safety net)
            if 'unique constraint' in str(e).lower() or 'duplicate' in str(e).lower():
                messages.error(
                    request,
                    f"Client code '{code}' is already in use. Please choose a different code or leave it blank."
                )
            else:
                messages.error(request, f"Error creating client: {str(e)}")
            return render(request, "core/clients/create_my.html", {
                'name': name,
                'code': code,
                'referred_by': referred_by,
            })
        except Exception as e:
            messages.error(request, f"Error creating client: {str(e)}")
            return render(request, "core/clients/create_my.html", {
                'name': name,
                'code': code,
                'referred_by': referred_by,
            })

    return render(request, "core/clients/create_my.html")


@login_required


def client_delete(request, pk):


    """
    Permanently delete a client and all related data.

    ⚠️ This is a HARD DELETE:
        - Deletes ClientExchangeAccount rows for this client

       - Cascades to Transactions, LossSnapshots, balances, ledgers, etc.
       - Use only when you truly want to wipe this client from the system.
    """
    # Get client - check if it exists and belongs to the user
    # If client has no user assigned (None), allow deletion (legacy data)
    try:
        client = Client.objects.get(pk=pk)
        # Check if user matches, or if client has no user assigned (allow deletion)
        if client.user is not None and client.user != request.user:
            from django.http import Http404
            raise Http404("Client not found")
    except Client.DoesNotExist:
        from django.contrib import messages
        messages.error(request, "Client not found. It may have been already deleted.")
        return redirect(reverse("client_list"))
    
    if request.method == "POST":
        # Store client name before deletion for success/error messages
        client_name = client.name
        
        try:
            # First delete all related objects for each client-exchange
            client_exchanges = ClientExchangeAccount.objects.filter(client=client)

            for ce in client_exchanges:
                # Delete loss snapshots (must go before ClientDailyBalance if PROTECT is used)
                # LossSnapshot.objects.filter(client_exchange=ce).delete()

                # Delete derived daily balance snapshots (reporting cache)
                # DailyBalanceSnapshot.objects.filter(client_exchange=ce).delete()

                # Delete daily balance records linked via client_exchange
                # ClientDailyBalance.objects.filter(client_exchange=ce).delete()

                # Delete outstanding ledgers
                # OutstandingAmount.objects.filter(client_exchange=ce).delete()

                # Delete all transactions
                Transaction.objects.filter(client_exchange=ce).delete()

                # Finally delete the client-exchange itself
                ce.delete()


            # TODO: ClientDailyBalance model removed
            # Delete legacy ClientDailyBalance rows that reference client directly (no client_exchange)
            # ClientDailyBalance.objects.filter(client=client).delete()

            # Now delete the client itself
            client.delete()

            from django.contrib import messages
            messages.success(request, f"Client '{client_name}' has been deleted permanently.")
            
            return redirect(reverse("client_list"))
        except Exception as e:
            from django.contrib import messages


            import traceback

            error_msg = f"Error deleting client '{client_name}': {str(e)}"

            # Error logging removed to prevent BrokenPipeError - use Django logging instead
            import logging

            logger = logging.getLogger(__name__)

            try:

                logger.error(f"Error in client_delete: {traceback.format_exc()}")

            except:


                pass

            messages.error(request, error_msg)

            return redirect(reverse("client_list"))

    
    # If GET, show confirmation or redirect
    return redirect(reverse("client_detail", args=[client.pk]))


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

    
        pass
    transactions = Transaction.objects.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").filter(client_exchange__client__user=request.user)
    
    # All clients are now "my clients" - no filtering needed
    
    if client_id:
        transactions = transactions.filter(client_exchange__client_id=client_id)

    if exchange_id:
        transactions = transactions.filter(client_exchange__exchange_id=exchange_id)

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            transactions = transactions.filter(date__gte=start_date)
        except ValueError:
            pass

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            transactions = transactions.filter(date__lte=end_date)
        except ValueError:
            pass

    if tx_type:
        # Filter transactions by type
        transactions = transactions.filter(type=tx_type)


    if search_query:
        transactions = transactions.filter(
            Q(client_exchange__client__name__icontains=search_query) |
            Q(client_exchange__client__code__icontains=search_query) |
            Q(client_exchange__exchange__name__icontains=search_query) |
            Q(client_exchange__exchange__code__icontains=search_query) |
            Q(notes__icontains=search_query)
        )
    
    transactions = transactions.order_by("-date", "-created_at")[:200]
    
    # Filter clients based on client_type for the dropdown
    # All clients are now my clients - no filter needed
    all_clients_qs = Client.objects.filter(user=request.user)
    
    # Validate that selected client exists and belongs to the current user
    if client_id:
        try:
            Client.objects.get(pk=client_id, user=request.user)
        except Client.DoesNotExist:
            client_id = None


    
    return render(request, "core/transactions/list.html", {
        "transactions": transactions,
        "all_clients": all_clients_qs.order_by("name"),
        "all_exchanges": Exchange.objects.all().order_by("name"),
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
    TODO: Add your new calculation logic here.
    
    Args:
        client_exchange: ClientExchangeAccount instance

        as_of_date: Optional date to calculate as of. If None, uses all transactions.
    
    Returns:
        dict with placeholder values - replace with your calculations

    """
    # TODO: Add your new formulas and logic here
    return {
        "net_client_tally": Decimal(0),
        "net_company_tally": Decimal(0),
        "your_earnings": Decimal(0),
        "your_share_from_losses": Decimal(0),
        "your_share_from_profits": Decimal(0),
        "company_share_from_losses": Decimal(0),
        "company_share_from_profits": Decimal(0),
    }


@login_required


def pending_summary(request):
    
    
    """
    Pending Payments Summary.
    
    TODO: Add your new formulas and logic here.
    """
    from datetime import timedelta
    
    today = date.today()
    report_type = request.GET.get("report_type", "daily")  # daily, weekly, monthly
    search_query = request.GET.get("search", "").strip()
    # Get client_type from GET (to update session) or from session
    client_type_filter = request.GET.get("client_type") or request.session.get('client_type_filter', 'all')
    if client_type_filter == '':
        pass
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
            last_month = 12
            last_year = today.year - 1
        else:
            last_month = today.month - 1
            last_year = today.year


            last_month_days = (date(today.year, today.month, 1) - timedelta(days=1)).day

            start_date = date(today.year, last_month, min(day_of_month, last_month_days))

        end_date = today
        date_range_label = f"Monthly ({start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')})"
    else:
        start_date = today
        end_date = today
        date_range_label = f"Today ({today.strftime('%B %d, %Y')})"
    
    # Get all active client exchanges
    client_exchanges = ClientExchangeAccount.objects.filter(
        client__user=request.user,
    ).select_related("client", "exchange").all()
    
    # Filter by search query if provided
    if search_query:
        client_exchanges = client_exchanges.filter(
            Q(client__name__icontains=search_query) |
            Q(client__code__icontains=search_query) |
            Q(exchange__name__icontains=search_query) |
            Q(exchange__code__icontains=search_query)
        )
    
    # Filter by client type if specified
    # All clients are now my clients - no filter needed
    # client_exchanges already contains all clients
    
    # TODO: SystemSettings model removed - add back if needed
    # settings = SystemSettings.load()
    settings = None  # Placeholder
    
    # Check if admin wants to combine my share and company share (for client sharing)
    # Default to true (checked) if not specified in URL
    combine_shares_param = request.GET.get("combine_shares")
    if combine_shares_param is None:
        combine_shares = True
    else:

        combine_shares = combine_shares_param.lower() == "true"
    
    
    # Separate lists
    clients_owe_list = []  # Clients Need To Pay Me
    you_owe_list = []  # I Need To Pay Clients
    
    for client_exchange in client_exchanges:
        # Compute Client_PnL using PIN-TO-PIN formula
        client_pnl = client_exchange.compute_client_pnl()
        
        # Determine if client owes you or you owe client
        is_loss_case = client_pnl < 0  # Client owes you (loss)
        is_profit_case = client_pnl > 0  # You owe client (profit)
        
        if is_loss_case:
            # This is the "Clients Owe You" section
            
            # CRITICAL FIX: Lock share and use locked share for remaining calculation
            client_exchange.lock_initial_share_if_needed()
            settlement_info = client_exchange.get_remaining_settlement_amount()
            initial_final_share = settlement_info['initial_final_share']
            remaining_amount = settlement_info['remaining']
            overpaid_amount = settlement_info['overpaid']
            
            # Use initial locked share for display
            final_share = initial_final_share if initial_final_share > 0 else client_exchange.compute_my_share()
            
            # MASKED SHARE SETTLEMENT SYSTEM: Client MUST always appear in pending list
            # If FinalShare = 0, show N.A instead of filtering out
            show_na = (final_share == 0)
            
            # Calculate values using MASKED SHARE formulas
            funding = Decimal(client_exchange.funding)
            exchange_balance = Decimal(client_exchange.exchange_balance)
            total_loss = abs(client_pnl)  # Client_PnL is negative, so abs gives loss amount
            
            # Use loss_share_percentage if set, otherwise fallback to my_percentage
            share_pct = client_exchange.loss_share_percentage if client_exchange.loss_share_percentage > 0 else client_exchange.my_percentage
            
            # Add to list (ALWAYS, even if FinalShare = 0)
            clients_owe_list.append({
                "client": client_exchange.client,
                "exchange": client_exchange.exchange,
                "account": client_exchange,
                "client_pnl": client_pnl,  # Masked in template
                "amount_owed": total_loss,  # Amount owed = total loss (masked in template)
                "my_share_amount": final_share,  # Final share (floor rounded)
                "remaining_amount": remaining_amount,  # Remaining to settle
                "share_percentage": share_pct,
                "show_na": show_na,  # Flag for N.A display
                })
            continue
        
        if is_profit_case:
            # This is the "You Owe Clients" section
            
            # CRITICAL FIX: Lock share and use locked share for remaining calculation
            client_exchange.lock_initial_share_if_needed()
            settlement_info = client_exchange.get_remaining_settlement_amount()
            initial_final_share = settlement_info['initial_final_share']
            remaining_amount = settlement_info['remaining']
            overpaid_amount = settlement_info['overpaid']
            
            # Use initial locked share for display
            final_share = initial_final_share if initial_final_share > 0 else client_exchange.compute_my_share()
            
            # MASKED SHARE SETTLEMENT SYSTEM: Client MUST always appear in pending list
            # If FinalShare = 0, show N.A instead of filtering out
            show_na = (final_share == 0)
            
            # Calculate values using MASKED SHARE formulas
            funding = Decimal(client_exchange.funding)
            exchange_balance = Decimal(client_exchange.exchange_balance)
            unpaid_profit = client_pnl  # Client_PnL is positive (profit)
            
            # Use profit_share_percentage if set, otherwise fallback to my_percentage
            share_pct = client_exchange.profit_share_percentage if client_exchange.profit_share_percentage > 0 else client_exchange.my_percentage
            
            # Add to list (ALWAYS, even if FinalShare = 0)
            you_owe_list.append({
                "client": client_exchange.client,
                "exchange": client_exchange.exchange,
                "account": client_exchange,
                "client_pnl": client_pnl,  # Masked in template
                "amount_owed": unpaid_profit,  # Amount you owe = profit (masked in template)
                "my_share_amount": final_share,  # Final share (floor rounded)
                "remaining_amount": remaining_amount,  # Remaining to settle
                "share_percentage": share_pct,
                "show_na": show_na,  # Flag for N.A display
            })
            continue
    
    # Sort lists by amount (descending)
    # Sort by Final Share or amount_owed, handling N.A cases
    def get_sort_key(item):
        if item.get("show_na", False):
            return 0  # N.A items sort to bottom
        if "my_share_amount" in item:
            return abs(item["my_share_amount"])
        elif "amount_owed" in item:
            return abs(item["amount_owed"])
        elif "client_pnl" in item:
            return abs(item["client_pnl"])
        else:
            return 0
    
    clients_owe_list.sort(key=get_sort_key, reverse=True)
    you_owe_list.sort(key=get_sort_key, reverse=True)
    
    # Calculate totals (using remaining amounts for settlement tracking)
    total_clients_owe = sum(item.get("amount_owed", 0) for item in clients_owe_list)
    total_my_share_clients_owe = sum(item.get("remaining_amount", 0) for item in clients_owe_list)  # Use remaining, not total share
    total_you_owe = sum(item.get("amount_owed", 0) for item in you_owe_list)
    total_my_share_you_owe = sum(item.get("remaining_amount", 0) for item in you_owe_list)  # Use remaining, not total share
    
    # Get all clients for search dropdown
    all_clients = Client.objects.filter(user=request.user).order_by("name")
    
    context = {
        "clients_owe_you": clients_owe_list,
        "you_owe_clients": you_owe_list,
        "total_clients_owe": total_clients_owe,
        "total_my_share_clients_owe": total_my_share_clients_owe,
        "total_you_owe": total_you_owe,
        "total_my_share_you_owe": total_my_share_you_owe,
        "today": today,
        "report_type": report_type,
        "client_type_filter": client_type_filter,
        "start_date": start_date,
        "end_date": end_date,
        "date_range_label": date_range_label,
        "settings": settings,
        "combine_shares": combine_shares,
        "search_query": search_query,
        "all_clients": all_clients,
    }
    return render(request, "core/pending/summary.html", context)


@login_required
def export_pending_csv(request):
    """
    Export pending payments report as CSV.
    Export format mirrors Pending Payments UI table exactly.
    """
    import csv
    
    # Get search query if any
    search_query = request.GET.get("search", "").strip()
    section = request.GET.get("section", "all")  # "clients-owe", "you-owe", or "all"
    
    # Get all client exchanges for the user
    client_exchanges = ClientExchangeAccount.objects.filter(
        client__user=request.user
    ).select_related("client", "exchange")
    
    # Apply search filter if provided
    if search_query:
        client_exchanges = client_exchanges.filter(
            Q(client__name__icontains=search_query) |
            Q(client__code__icontains=search_query) |
            Q(exchange__name__icontains=search_query) |
            Q(exchange__code__icontains=search_query)
        )
    
    # Use EXACT same data building logic as pending_summary
    clients_owe_list = []
    you_owe_list = []
    
    for client_exchange in client_exchanges:
        # Compute Client_PnL using PIN-TO-PIN formula
        client_pnl = client_exchange.compute_client_pnl()
        
        # CRITICAL FIX: Don't show PnL=0 clients in pending sections (FAILURE 4)
        # PnL = 0 means neutral/closed - no liability in either direction
        if client_pnl == 0:
            continue  # Skip clients with PnL = 0
        
        # Determine if client owes you or you owe client
        is_loss_case = client_pnl < 0  # Client owes you (loss)
        is_profit_case = client_pnl > 0  # You owe client (profit)
        
        if is_loss_case:
            # This is the "Clients Owe You" section
            # CRITICAL FIX: Lock share and use locked share for remaining calculation
            client_exchange.lock_initial_share_if_needed()
            settlement_info = client_exchange.get_remaining_settlement_amount()
            initial_final_share = settlement_info['initial_final_share']
            remaining_amount = settlement_info['remaining']
            overpaid_amount = settlement_info['overpaid']
            
            # Use initial locked share for display
            final_share = initial_final_share if initial_final_share > 0 else client_exchange.compute_my_share()
            
            # MASKED SHARE SETTLEMENT SYSTEM: Client MUST always appear in pending list
            # If FinalShare = 0, show N.A instead of filtering out
            show_na = (final_share == 0)
            
            total_loss = abs(client_pnl)  # Client_PnL is negative, so abs gives loss amount
            
            # Use loss_share_percentage if set, otherwise fallback to my_percentage
            share_pct = client_exchange.loss_share_percentage if client_exchange.loss_share_percentage > 0 else client_exchange.my_percentage
            
            # Add to list (ALWAYS, even if FinalShare = 0)
            clients_owe_list.append({
                "client": client_exchange.client,
                "exchange": client_exchange.exchange,
                "account": client_exchange,
                "client_pnl": client_pnl,
                "amount_owed": total_loss,
                "my_share_amount": final_share,
                "remaining_amount": remaining_amount,
                "share_percentage": share_pct,
                "show_na": show_na,  # Flag for N.A display
                })
            continue
        
        if is_profit_case:
            # This is the "You Owe Clients" section
            # CRITICAL FIX: Lock share and use locked share for remaining calculation
            client_exchange.lock_initial_share_if_needed()
            settlement_info = client_exchange.get_remaining_settlement_amount()
            initial_final_share = settlement_info['initial_final_share']
            remaining_amount = settlement_info['remaining']
            overpaid_amount = settlement_info['overpaid']
            
            # Use initial locked share for display
            final_share = initial_final_share if initial_final_share > 0 else client_exchange.compute_my_share()
            
            # MASKED SHARE SETTLEMENT SYSTEM: Client MUST always appear in pending list
            # If FinalShare = 0, show N.A instead of filtering out
            show_na = (final_share == 0)
            
            unpaid_profit = client_pnl  # Client_PnL is positive (profit)
            
            # Use profit_share_percentage if set, otherwise fallback to my_percentage
            share_pct = client_exchange.profit_share_percentage if client_exchange.profit_share_percentage > 0 else client_exchange.my_percentage
            
            # Add to list (ALWAYS, even if FinalShare = 0)
            you_owe_list.append({
                "client": client_exchange.client,
                "exchange": client_exchange.exchange,
                "account": client_exchange,
                "client_pnl": client_pnl,
                "amount_owed": unpaid_profit,
                "my_share_amount": final_share,
                "remaining_amount": remaining_amount,
                "share_percentage": share_pct,
                "show_na": show_na,  # Flag for N.A display
            })
            continue
    
    # Sort lists by amount (descending)
    # Sort by Final Share or amount_owed, handling N.A cases
    def get_csv_sort_key(item):
        if item.get("show_na", False):
            return 0  # N.A items sort to bottom
        if "my_share_amount" in item:
            return abs(item["my_share_amount"])
        elif "amount_owed" in item:
            return abs(item["amount_owed"])
        elif "client_pnl" in item:
            return abs(item["client_pnl"])
        else:
            return 0
    
    clients_owe_list.sort(key=get_csv_sort_key, reverse=True)
    you_owe_list.sort(key=get_csv_sort_key, reverse=True)
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    filename = f"pending_payments_{date.today().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    
    # Write header row
    headers = [
        'Client Name',
        'Client Code',
        'Exchange Name',
        'Exchange Code',
        'Funding',
        'Exchange Balance',
        'Client PnL',
        'Final Share',
        'Remaining',
        'Share %'
    ]
    writer.writerow([h.upper() for h in headers])
    
    # Write Clients Owe You section (if requested)
    if section in ["all", "clients-owe"]:
        for item in clients_owe_list:
            writer.writerow([
                item["client"].name or '',
                item["client"].code or '',
                item["exchange"].name or '',
                item["exchange"].code or '',
                int(item["account"].funding),
                int(item["account"].exchange_balance),
                'N.A' if item.get("show_na", False) else int(item["client_pnl"]),
                'N.A' if item.get("show_na", False) else int(item["my_share_amount"]),
                'N.A' if item.get("show_na", False) else int(item.get("remaining_amount", 0)),
                item.get("share_percentage", item["account"].my_percentage)
            ])
    
    # Write You Owe Clients section (if requested)
    if section in ["all", "you-owe"]:
        for item in you_owe_list:
                writer.writerow([
                item["client"].name or '',
                item["client"].code or '',
                item["exchange"].name or '',
                item["exchange"].code or '',
                int(item["account"].funding),
                int(item["account"].exchange_balance),
                'N.A' if item.get("show_na", False) else int(item["client_pnl"]),
                'N.A' if item.get("show_na", False) else int(item["my_share_amount"]),
                'N.A' if item.get("show_na", False) else int(item.get("remaining_amount", 0)),
                item.get("share_percentage", item["account"].my_percentage)
            ])
    
    return response


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

        pass
    client_id = request.GET.get("client")  # Specific client ID
    
    # Month selection parameter
    month_str = request.GET.get("month", today.strftime("%Y-%m"))
    try:
        year, month = map(int, month_str.split("-"))

        selected_month_start = date(year, month, 1)
        if month == 12:


            pass
        else:

            selected_month_end = date(year, month + 1, 1) - timedelta(days=1)


    except (ValueError, IndexError):

        selected_month_start = date(today.year, today.month, 1)


        if today.month == 12:



            pass
        else:

            selected_month_end = date(today.year, today.month + 1, 1) - timedelta(days=1)



    
    # Month selection parameter
    month_str = request.GET.get("month", today.strftime("%Y-%m"))
    try:
        year, month = map(int, month_str.split("-"))

        selected_month_start = date(year, month, 1)
        if month == 12:


            pass
        else:

            selected_month_end = date(year, month + 1, 1) - timedelta(days=1)


    except (ValueError, IndexError):

        selected_month_start = date(today.year, today.month, 1)


        if today.month == 12:



            pass
        else:

            selected_month_end = date(today.year, today.month + 1, 1) - timedelta(days=1)



    
    # Time travel parameters (override month selection if provided)
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    as_of_str = request.GET.get("date")
    time_travel_mode = False
    date_filter = {}
    
    if start_date_str and end_date_str:

        start_date_filter = date.fromisoformat(start_date_str)
        end_date_filter = date.fromisoformat(end_date_str)
        date_filter = {"date__gte": start_date_filter, "date__lte": end_date_filter}
    elif as_of_str:
        time_travel_mode = True

        as_of_filter = date.fromisoformat(as_of_str)
        date_filter = {"date__lte": as_of_filter}
    elif not time_travel_mode:
        # Apply month filter if no time travel parameters
        date_filter = {"date__gte": selected_month_start, "date__lte": selected_month_end}
    
    # Base queryset with time travel filter if applicable, always filtered by user
    user_filter = {"client_exchange__client__user": request.user}
    
    # All clients are now "my clients" - no filtering needed
    
    # Add specific client filter if specified
    if client_id:

    
        pass
    if date_filter:

        pass
    else:

        base_qs = Transaction.objects.filter(**user_filter)

    
    # Filter to only show transactions after payments are recorded (settled)
    # Get all client_exchanges that have at least one settlement
    settled_client_exchanges = Transaction.objects.filter(
        **user_filter,
        transaction_type=Transaction.TYPE_SETTLEMENT
    ).values_list('client_exchange_id', flat=True).distinct()
    
    # For each settled client_exchange, get the latest settlement date
    # Only include profit/loss transactions up to that settlement date
    settled_data = {}
    for client_exchange_id in settled_client_exchanges:
        latest_settlement = Transaction.objects.filter(
            client_exchange_id=client_exchange_id,
            type='RECORD_PAYMENT'
        ).order_by('-date', '-created_at').first()
        if latest_settlement:


    
            pass
    # Filter base_qs to only include:
    # 1. SETTLEMENT and FUNDING transactions (always include)
    # 2. PROFIT/LOSS transactions only if they're for settled client_exchanges and before/on settlement date
    from django.db.models import Q, F
    settled_filter = Q(transaction_type__in=[Transaction.TYPE_SETTLEMENT, Transaction.TYPE_FUNDING])
    
    # Add profit/loss transactions that are settled
    # Note: This section is for old transaction types that don't exist in PIN-TO-PIN
    # Transactions are now just audit records, not used for profit/loss calculation
    for client_exchange_id, settlement_date in settled_data.items():
        # This logic is deprecated - transactions don't have TYPE_PROFIT or TYPE_LOSS
        pass
    
    # Apply the filter
    base_qs = base_qs.filter(settled_filter)
    
    # Get clients for dropdown (filtered by client_type if applicable)
    # All clients are now my clients - no filter needed
    clients_qs = Client.objects.filter(user=request.user)
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
    
    # 📘 YOUR TOTAL PROFIT Calculation
    # For company clients: your_share_amount = 1% of profit (in profit transactions)
    # For my clients: your_share_amount = full share of profit (in profit transactions)
    # This represents what you OWE clients (expense)
    your_total_profit_from_profits = (
        base_qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))[
            "total"

        ]
        or 0
    )
    
    # 📘 YOUR TOTAL INCOME from Losses
    # For company clients: your_share_amount = 1% of loss (in loss transactions)
    # For my clients: your_share_amount = full share of loss (in loss transactions)
    # This represents what clients OWE you (income)
    your_total_income_from_losses = (
        base_qs.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("your_share_amount"))[
            "total"

        ]
        or 0
    )
    
    # 📘 YOUR NET PROFIT = Income from Losses - Expense from Profits
    # This shows your actual earnings (positive = you earned, negative = you owe)
    your_total_profit = your_total_income_from_losses - your_total_profit_from_profits
    
    # 📘 COMPANY PROFIT Calculation
    # Sum of company_share_amount from ALL transactions (both profit and loss)
    # For company clients: company_share_amount = 9% of movement
    company_profit = (
        Decimal(0)  # All clients are now my clients, company share is always 0
    )

    # Daily trends for last 30 days (or filtered by time travel)
    if time_travel_mode and start_date_str and end_date_str:

        end_date = date.fromisoformat(end_date_str)
        # Limit to 30 days or the actual range, whichever is smaller
        days_diff = (end_date - start_date).days
        if days_diff > 30:
            end_date = start_date + timedelta(days=30)
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

        if tx_type in type_map:


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
        month_date = today.replace(day=1)
        for _ in range(i):
                

                month_date = month_date.replace(year=month_date.year - 1, month=12)

                month_date = month_date.replace(month=month_date.month - 1)

        
        # Calculate month end date
        if month_date.month == 12:


            pass
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
        "today": today,
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
        "selected_month": month_str,
        "selected_month_start": selected_month_start,
        "selected_month_end": selected_month_end,
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

    
        pass
    # Base filter
    base_filter = {"client_exchange__client__user": request.user}
    
    # All clients are now "my clients" - no filtering needed
    
    # Determine date range
    if start_date_str and end_date_str:
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
    company_profit = qsDecimal(0)

    # Calculate pending amounts correctly
    # Clients owe you = pending amounts for transactions up to as_of date
    client_exchange_filter = {"client__user": request.user}
    # All clients are now "my clients" - no filtering needed
    
    if date_range_mode:
        client_exchanges_in_range = ClientExchangeAccount.objects.filter(
            **client_exchange_filter,

            transactions__date__gte=start_date,

            transactions__date__lte=end_date

        ).distinct()
        pending_clients_owe = Decimal(0)  # No longer using pending amounts
    else:

        # For single date, calculate pending as of that date
        client_exchanges_up_to = ClientExchangeAccount.objects.filter(
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


    # Company share summary removed - no longer needed
    from django.contrib import messages
    messages.info(request, "Company share summary is no longer available.")
    return redirect(reverse("client_list"))


# Exchange Management Views
@login_required


def exchange_create(request):
    """Create a new standalone exchange (A, B, C, D, etc.)."""
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        code = request.POST.get("code", "").strip()
        
        if name:
            # Check for case-insensitive duplicate names
            existing = Exchange.objects.filter(name__iexact=name)
            if existing.exists():
                from django.contrib import messages
                messages.error(request, f"'{name}' already exists.")
                return render(request, "core/exchanges/create.html")
            
            try:
                Exchange.objects.create(
                    name=name,
                    code=code if code else None,
                )
                from django.contrib import messages
                messages.success(request, f"Exchange '{name}' has been created successfully.")
                return redirect(reverse("exchange_list"))
            except Exception as e:
                # Handle any other validation errors (including model-level validation)
                from django.contrib import messages
                # Check if it's a duplicate name error
                existing = Exchange.objects.filter(name__iexact=name)
                if existing.exists():
                    messages.error(request, f"'{name}' already exists.")
                else:
                    messages.error(request, f"Error creating exchange: {str(e)}")
                return render(request, "core/exchanges/create.html")
        else:
            from django.contrib import messages
            messages.error(request, "Exchange name is required.")
    
    return render(request, "core/exchanges/create.html")


@login_required


def exchange_edit(request, pk):


    """Edit an existing standalone exchange."""
    exchange = get_object_or_404(Exchange, pk=pk)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        code = request.POST.get("code", "").strip() or None
        
        # If name is being changed, check for case-insensitive duplicate
        if name and name != exchange.name:
            existing = Exchange.objects.filter(name__iexact=name).exclude(pk=exchange.pk)
            if existing.exists():
                from django.contrib import messages
                messages.error(request, f"'{name}' already exists.")
                return render(request, "core/exchanges/edit.html", {"exchange": exchange})
            exchange.name = name
        
        try:
            exchange.code = code
            exchange.save()
            from django.contrib import messages
            messages.success(request, f"Exchange '{exchange.name}' has been updated successfully.")
            return redirect(reverse("exchange_list"))
        except Exception as e:
            from django.contrib import messages
            # Check if it's a duplicate name error
            if name:
                existing = Exchange.objects.filter(name__iexact=name).exclude(pk=exchange.pk)
                if existing.exists():
                    messages.error(request, f"'{name}' already exists.")
                else:
                    messages.error(request, f"Error updating exchange: {str(e)}")
            else:
                messages.error(request, f"Error updating exchange: {str(e)}")
            return render(request, "core/exchanges/edit.html", {"exchange": exchange})
    
    return render(request, "core/exchanges/edit.html", {"exchange": exchange})


@login_required


def client_exchange_create(request, client_pk):


    """Link a client to an exchange with specific percentages."""
    client = get_object_or_404(Client, pk=client_pk, user=request.user)
    exchanges = Exchange.objects.all().order_by("name")
    
    if request.method == "POST":

        my_share = request.POST.get("my_share_pct")
        company_share = request.POST.get("company_share_pct")
        
        if exchange_id and my_share and company_share:


            my_share_decimal = Decimal(my_share)

            company_share_decimal = Decimal(company_share)

            
            # Validate company share is less than 100%
            if company_share_decimal >= 100:
                client_type = "company" if False else "my"

                return render(request, "core/exchanges/link_to_client.html", {

                    "client": client,

                    "exchanges": exchanges,

                    "client_type": client_type,

                    "error": "Company share must be less than 100%",

                })
            
            client_exchange = ClientExchangeAccount.objects.create(
                client=client,
                exchange=exchange,
                my_share_pct=my_share_decimal,
                company_share_pct=company_share_decimal,
            )
            
            # Redirect to appropriate namespace based on client type
            return redirect("client_detail", pk=client.pk)
    
    client_type = "company" if False else "my"
    return render(request, "core/exchanges/link_to_client.html", {
        "client": client,
        "exchanges": exchanges,
        "client_type": client_type,
    })


@login_required


@login_required


def my_client_exchange_create(request, client_pk):


    """Link an exchange to a client."""
    client = get_object_or_404(Client, pk=client_pk, user=request.user)
    exchanges = Exchange.objects.all().order_by("name")
    
    if request.method == "POST":
        my_share = request.POST.get("my_share_pct")
        
        if exchange_id and my_share:
            my_share_decimal = Decimal(my_share)
            
            client_exchange = ClientExchangeAccount.objects.create(
                client=client,
                exchange=exchange,
                my_share_pct=my_share_decimal,
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
    client_exchange = get_object_or_404(ClientExchangeAccount, pk=pk, client__user=request.user)
    
    # Check if exchange can be edited (within 10 days of creation)
    days_since_creation = (date.today() - client_exchange.created_at.date()).days
    can_edit_exchange = days_since_creation <= 10
    
    if request.method == "POST":
        # All clients are now my clients, company share is always 0
        company_share = Decimal("0")
        my_share = Decimal(request.POST.get("my_share_pct", "0"))
        
        # Update exchange if within 10 days and exchange was provided
        # Double-check can_edit_exchange to prevent manipulation
        new_exchange_id = request.POST.get("exchange")
        if can_edit_exchange and new_exchange_id:
            new_exchange = get_object_or_404(Exchange, pk=new_exchange_id)
            
            # Check if this exchange-client combination already exists (excluding current)
            existing = ClientExchangeAccount.objects.filter(
                client=client_exchange.client,
                exchange=new_exchange
            ).exclude(pk=client_exchange.pk).first()
            
            if existing:
                days_remaining = (10 - days_since_creation) if can_edit_exchange else 0
                client_type = "company" if False else "my"
                
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
            exchanges = Exchange.objects.all().order_by("name")
            days_remaining = 0
            client_type = "company" if False else "my"
            
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
        client_exchange.save()
        # Redirect to client detail
        return redirect("client_detail", pk=client_exchange.client.pk)

    
    # GET request - prepare context
    exchanges = Exchange.objects.all().order_by("name") if can_edit_exchange else None
    days_remaining = (10 - days_since_creation) if can_edit_exchange else 0
    client_type = "company" if False else "my"
    
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
    clients = Client.objects.filter(user=request.user).order_by("name")
    
    if request.method == "POST":

        tx_date = request.POST.get("date")
        tx_type = request.POST.get("transaction_type")
        amount = Decimal(request.POST.get("amount", 0))
        note = request.POST.get("note", "")
        
        if client_exchange_id and tx_date and tx_type and amount > 0:

            
            # 🔐 GOLDEN RULE: Payment ALWAYS happens ONLY on SHARE, never on full profit or full loss.
            # - Client loss → client pays ONLY share
            # - Client profit → you pay ONLY share
            # - For company clients: Share is split internally (1% you, 9% company)
            
            is_company_client = False  # All clients are now "my clients"

            my_share_pct = client_exchange.my_share_pct
            
            if tx_type == Transaction.TYPE_PROFIT:
                # Total Share = my_share_pct% of profit (e.g., 10% of 990 = ₹99)
                total_share = amount * (my_share_pct / 100)
                
                # STEP 2: For company clients, split that share internally
                if is_company_client:
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
                
            elif tx_type == 'LOSS':
                # Total Share = my_share_pct% of loss (e.g., 10% of 90 = ₹9)
                total_share = amount * (my_share_pct / 100)
                
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

                note=note,

                )

            
            return redirect(reverse("transaction_list"))

    
    # Get client-exchanges for selected client (if provided)
    client_id = request.GET.get("client")
    client_exchanges = ClientExchangeAccount.objects.filter(client__user=request.user).select_related("client", "exchange")
    if client_id:

        pass
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
            client_net_after = client_net_before

        else:

            # Client pays - doesn't affect exchange balance
            client_net_after = client_net_before

    
    # Calculate funding after
    funding_after = funding_before
    if transaction.transaction_type == Transaction.TYPE_FUNDING:

    
        pass
    # Calculate profit/loss totals after
    # Note: Transaction types PROFIT and LOSS don't exist in PIN-TO-PIN system
    # Transactions are audit-only, profit/loss is computed from accounts
    profit_after = profit_before
    loss_after = loss_before

    
    # Calculate differences
    balance_change = balance_after - balance_before
    client_net_change = client_net_after - client_net_before
    
    # Determine client type for URL routing
    client_type = "company" if False else "my"
    
    # Calculate shares based on client_exchange configuration (use stored values if available, otherwise recalculate)
    calculated_your_share = transaction.your_share_amount
    # All clients are now my clients, company share is always 0
    calculated_company_share = Decimal(0)
    calculated_client_share = transaction.client_share_amount
    
    # If shares are 0, recalculate based on client_exchange configuration
    if calculated_your_share == 0 and calculated_client_share == 0:
        calculated_your_share = transaction.amount * (client_exchange.my_share_pct / 100)
        calculated_client_share = transaction.amount - calculated_your_share
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

        tx_type = request.POST.get("transaction_type")
        amount = Decimal(request.POST.get("amount", 0))
        note = request.POST.get("note", "")
        
        if tx_date and tx_type and amount > 0:


            
            # 🔐 GOLDEN RULE: Payment ALWAYS happens ONLY on SHARE, never on full profit or full loss.
            # - Client loss → client pays ONLY share
            # - Client profit → you pay ONLY share
            # - For company clients: Share is split internally (1% you, 9% company)
            
            is_company_client = False  # All clients are now "my clients"

            my_share_pct = client_exchange.my_share_pct

            
            # Track old transaction type and share amount for pending updates
            old_tx_type = transaction.transaction_type

            old_share_amount = transaction.client_share_amount  # Old share amount

            
            if tx_type == Transaction.TYPE_PROFIT:
                # Total Share = my_share_pct% of profit (e.g., 10% of 990 = ₹99)
                total_share = amount * (my_share_pct / 100)
                
                # STEP 2: For company clients, split that share internally
                if is_company_client:
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
                # Total Share = my_share_pct% of loss (e.g., 10% of 90 = ₹9)
                total_share = amount * (my_share_pct / 100)
                
                # STEP 2: For company clients, split that share internally
                if is_company_client:
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

            # All clients are now my clients, company_share_amount is always 0
            # transaction.company_share_amount = Decimal(0)  # Field removed
            transaction.note = note

            transaction.save()

            
            
            return redirect(reverse("transaction_list"))

    
    return render(request, "core/transactions/edit.html", {"transaction": transaction})


@login_required


def get_exchanges_for_client(request):


    """AJAX endpoint to get client-exchanges for a client."""
    client_id = request.GET.get("client_id")
    if client_id:

        return JsonResponse(list(client_exchanges), safe=False)
    return JsonResponse([], safe=False)


@login_required


def get_latest_balance_for_exchange(request, client_pk):


    """AJAX endpoint to get latest balance data for a client-exchange."""
    client = get_object_or_404(Client, pk=client_pk, user=request.user)
    client_exchange_id = request.GET.get("client_exchange_id")
    
    if client_exchange_id:
        try:
            client_exchange = ClientExchangeAccount.objects.get(pk=client_exchange_id, client=client)
            
            # Get calculated balance from account (not transactions)
            # In PIN-TO-PIN system, balance comes from exchange_balance field
            calculated_balance = client_exchange.exchange_balance
            
            # TODO: ClientDailyBalance model removed - add back if needed
            latest_balance = None
            
            if latest_balance:
                return JsonResponse({
                    "success": True,
                    "date": latest_balance.date.isoformat(),
                    "remaining_balance": str(latest_balance.remaining_balance),
                    "note": latest_balance.note or "",
                    "calculated_balance": str(calculated_balance),
                    "has_recorded_balance": True,
                    "total_funding": str(client_exchange.funding),
                })
            else:
                return JsonResponse({
                    "success": True,
                    "date": date.today().isoformat(),
                    "remaining_balance": str(calculated_balance),
                    "note": "",
                    "calculated_balance": str(calculated_balance),
                    "has_recorded_balance": False,
                    "total_funding": str(client_exchange.funding),
                })
        except ClientExchangeAccount.DoesNotExist:
            pass


    
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

    
        pass
    # Base filter
    base_filter = {"client_exchange__client__user": request.user, "date": report_date}
    
    # All clients are now "my clients" - no filtering needed
    
    qs = Transaction.objects.filter(**base_filter)
    
    total_turnover = qs.aggregate(total=Sum("amount"))["total"] or 0
    your_profit = (
        qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    company_profit = qsDecimal(0)
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

        if tx_type in type_map:


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

        pass
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
    company_profit = qsDecimal(0)
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

        if tx_type in type_map:


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

        pass
    else:

        month_end = date(year, month + 1, 1) - timedelta(days=1)

    
    qs = Transaction.objects.filter(client_exchange__client__user=request.user, date__gte=month_start, date__lte=month_end)
    
    total_turnover = qs.aggregate(total=Sum("amount"))["total"] or 0
    your_profit = (
        qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    company_profit = qsDecimal(0)
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

        if tx_type in type_map:


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
    company_profit = qsDecimal(0)
    
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

        end_date = date.fromisoformat(end_date_str)
        qs = Transaction.objects.filter(client_exchange__client__user=request.user, date__gte=start_date, date__lte=end_date)
    else:

        qs = Transaction.objects.filter(client_exchange__client__user=request.user)

    
    if report_type == "profit":
        # Filter by profit transactions (not used in PIN-TO-PIN)
        pass
    elif report_type == "loss":
        # Filter by loss transactions (not used in PIN-TO-PIN)
        pass

    
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
            tx.your_share_amount or 0,
            tx.client_share_amount or 0,
            Decimal(0),  # company_share_amount - all clients are now my clients
            tx.note or "",
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

        end_date = date.fromisoformat(end_date_str)
        qs = Transaction.objects.filter(client_exchange__client=client, date__gte=start_date, date__lte=end_date)
    else:

        qs = Transaction.objects.filter(client_exchange__client=client)

    
    total_turnover = qs.aggregate(total=Sum("amount"))["total"] or 0
    your_profit = (
        qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    company_profit = qsDecimal(0)
    
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


@login_required
def link_client_to_exchange(request):
    """Link a client to an exchange with percentage configuration."""
    if request.method == "POST":
        client_id = request.POST.get("client")
        exchange_id = request.POST.get("exchange")
        my_percentage = request.POST.get("my_percentage", "").strip()
        friend_percentage = request.POST.get("friend_percentage", "").strip()
        my_own_percentage = request.POST.get("my_own_percentage", "").strip()
        
        # Validation
        if not client_id or not exchange_id or not my_percentage:
            from django.contrib import messages
            messages.error(request, "Client, Exchange, and My Total % are required.")
            return render(request, "core/exchanges/link_to_client.html", {
                "clients": Client.objects.filter(user=request.user).order_by("name"),
                "exchanges": Exchange.objects.all().order_by("name"),
            })
        
        try:
            client = Client.objects.get(pk=client_id, user=request.user)
            exchange = Exchange.objects.get(pk=exchange_id)
            my_percentage_int = int(my_percentage)
            
            # Validate percentage range
            if my_percentage_int < 0 or my_percentage_int > 100:
                from django.contrib import messages
                messages.error(request, "My Total % must be between 0 and 100.")
                return render(request, "core/exchanges/link_to_client.html", {
                    "clients": Client.objects.filter(user=request.user).order_by("name"),
                    "exchanges": Exchange.objects.all().order_by("name"),
                })
            
            # Check if link already exists
            if ClientExchangeAccount.objects.filter(client=client, exchange=exchange).exists():
                from django.contrib import messages
                messages.error(request, f"Client '{client.name}' is already linked to '{exchange.name}'.")
                return render(request, "core/exchanges/link_to_client.html", {
                    "clients": Client.objects.filter(user=request.user).order_by("name"),
                    "exchanges": Exchange.objects.all().order_by("name"),
                })
            
            # Create ClientExchangeAccount
            # MASKED SHARE SETTLEMENT SYSTEM: Set loss and profit share percentages
            # Default to my_percentage for both (can be changed later, but loss % becomes immutable once data exists)
            account = ClientExchangeAccount.objects.create(
                client=client,
                exchange=exchange,
                funding=0,
                exchange_balance=0,
                my_percentage=my_percentage_int,
                loss_share_percentage=my_percentage_int,  # Default to my_percentage
                profit_share_percentage=my_percentage_int,  # Default to my_percentage (can change anytime)
            )
            
            # Create report config if friend/own percentages provided
            if friend_percentage or my_own_percentage:
                friend_pct = int(friend_percentage) if friend_percentage else 0
                own_pct = int(my_own_percentage) if my_own_percentage else 0
                
                # Validate: friend % + my own % = my total %
                if friend_pct + own_pct != my_percentage_int:
                    from django.contrib import messages
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
            
            from django.contrib import messages
            messages.success(request, f"Successfully linked '{client.name}' to '{exchange.name}'.")
            return redirect(reverse("client_detail", args=[client.pk]))
            
        except (Client.DoesNotExist, Exchange.DoesNotExist):
            from django.contrib import messages
            messages.error(request, "Invalid client or exchange selected.")
        except ValueError:
            from django.contrib import messages
            messages.error(request, "Invalid percentage value. Please enter numbers only.")
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f"Error linking client to exchange: {str(e)}")
    
    # GET request - show form
    return render(request, "core/exchanges/link_to_client.html", {
        "clients": Client.objects.filter(user=request.user).order_by("name"),
        "exchanges": Exchange.objects.all().order_by("name"),
    })


@login_required


@login_required
def exchange_account_detail(request, pk):
    """View details of a client-exchange account."""
    account = get_object_or_404(ClientExchangeAccount, pk=pk, client__user=request.user)
    
    # MASKED SHARE SETTLEMENT SYSTEM: Calculate values
    client_pnl = account.compute_client_pnl()
    final_share = account.compute_my_share()
    settlement_info = account.get_remaining_settlement_amount()
    remaining_amount = settlement_info['remaining']
    
    # Get recent transactions for this account
    transactions = Transaction.objects.filter(client_exchange=account).order_by("-date", "-created_at")[:20]
    
    # Get recent settlements
    settlements = Settlement.objects.filter(client_exchange=account).order_by("-date", "-created_at")[:10]
    total_settled = Settlement.objects.filter(client_exchange=account).aggregate(
        total=Sum('amount')
    )['total'] or 0
    
    return render(request, "core/exchanges/account_detail.html", {
        'account': account,
        'transactions': transactions,
        'settlements': settlements,
        'total_settled': total_settled,
        'client_pnl': client_pnl,
        'final_share': final_share,
        'remaining_amount': remaining_amount,
    })


@login_required


@login_required
def add_funding(request, account_id):
    """Add funding to a client-exchange account.
    
    FUNDING RULE: When money is given to client:
    - funding = funding + amount
    - exchange_balance = exchange_balance + amount
    Both must increase by the same amount simultaneously.
    """
    account = get_object_or_404(ClientExchangeAccount, pk=account_id, client__user=request.user)
    
    if request.method == "POST":
        amount_str = request.POST.get("amount", "").strip()
        notes = request.POST.get("notes", "").strip()
        
        if not amount_str:
            from django.contrib import messages
            messages.error(request, "Amount is required.")
            return render(request, "core/exchanges/add_funding.html", {
                'account': account
            })
        
        try:
            amount = int(amount_str)
            if amount <= 0:
                from django.contrib import messages
                messages.error(request, "Amount must be greater than zero.")
                return render(request, "core/exchanges/add_funding.html", {
                    'account': account
                })
            
            # FUNDING RULE: Both funding and exchange_balance increase by the same amount
            old_funding = account.funding
            old_balance = account.exchange_balance
            
            account.funding += amount
            account.exchange_balance += amount
            account.save()
            
            # Create transaction record for audit trail
            Transaction.objects.create(
                client_exchange=account,
                date=timezone.now(),
                type='FUNDING',
                amount=amount,
                exchange_balance_after=account.exchange_balance,
                notes=notes or f"Funding added: {amount}"
            )
            
            from django.contrib import messages
            messages.success(
                request,
                f"Funding of {amount} added successfully. "
                f"Funding: {old_funding} → {account.funding}, "
                f"Balance: {old_balance} → {account.exchange_balance}"
            )
            return redirect(reverse("exchange_account_detail", args=[account.pk]))
            
        except ValueError:
            from django.contrib import messages
            messages.error(request, "Invalid amount. Please enter a valid number.")
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f"Error adding funding: {str(e)}")
    
    return render(request, "core/exchanges/add_funding.html", {
        'account': account
    })


@login_required


@login_required
def update_exchange_balance(request, account_id):
    """Update exchange balance for a client-exchange account.

    Only exchange_balance changes. Funding remains untouched.
    Used for trades, fees, profits, losses.
    """
    account = get_object_or_404(ClientExchangeAccount, pk=account_id, client__user=request.user)
    
    if request.method == "POST":
        new_balance_str = request.POST.get("new_balance", "").strip()
        transaction_type = request.POST.get("transaction_type", "TRADE")
        notes = request.POST.get("notes", "").strip()
        
        if not new_balance_str:
            from django.contrib import messages
            messages.error(request, "New balance is required.")
            return render(request, "core/exchanges/update_balance.html", {
                'account': account
            })
        
        try:
            new_balance = int(new_balance_str)
            if new_balance < 0:
                from django.contrib import messages
                messages.error(request, "Balance cannot be negative.")
                return render(request, "core/exchanges/update_balance.html", {
                    'account': account
                })
            
            old_balance = account.exchange_balance
            balance_change = new_balance - old_balance
            
            # Only exchange_balance changes, funding stays the same
            account.exchange_balance = new_balance
            account.save()
            
            # Create transaction record for audit trail
            Transaction.objects.create(
                client_exchange=account,
                date=timezone.now(),
                type=transaction_type,
                amount=abs(balance_change),  # Store absolute value
                exchange_balance_after=new_balance,
                notes=notes or f"Balance updated: {old_balance} → {new_balance} ({balance_change:+})"
            )
            
            from django.contrib import messages
            messages.success(
                request,
                f"Balance updated successfully. "
                f"Exchange Balance: {old_balance} → {new_balance} ({balance_change:+})"
            )
            return redirect(reverse("exchange_account_detail", args=[account.pk]))
            
        except ValueError:
            from django.contrib import messages
            messages.error(request, "Invalid balance. Please enter a valid number.")
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f"Error updating balance: {str(e)}")
    
    return render(request, "core/exchanges/update_balance.html", {
        'account': account
    })


@login_required


@login_required
def record_payment(request, account_id):
    """Record a payment for a client-exchange account.
    
    MASKED SHARE SETTLEMENT SYSTEM - Settlement Logic:
    - Uses database row locking to prevent concurrent payment race conditions
    - Calculates FinalShare using floor() rounding
    - Blocks settlement when FinalShare = 0
    - Validates against remaining settlement amount (FinalShare - SumOfSettlements)
    - Prevents negative funding/exchange_balance
    - Creates Settlement record to track payments
    - If Client_PnL < 0 (LOSS): funding = funding - MaskedCapital
    - If Client_PnL > 0 (PROFIT): exchange_balance = exchange_balance - MaskedCapital
    - Partial payments allowed
    
    Note: Ensures settlement safety at time of entry.
    Historical settlements may exceed current recalculated share by design.
    """
    # Initial load (no locking needed for GET requests)
    account = get_object_or_404(ClientExchangeAccount, pk=account_id, client__user=request.user)
    client_pnl = account.compute_client_pnl()
    redirect_to = request.GET.get('redirect_to', 'exchange_account_detail')
    
    # Lock share if needed (ensures share doesn't shrink)
    account.lock_initial_share_if_needed()
    
    # Calculate FinalShare using MASKED SHARE SETTLEMENT SYSTEM
    final_share = account.compute_my_share()
    settlement_info = account.get_remaining_settlement_amount()
    remaining_amount = settlement_info['remaining']
    overpaid_amount = settlement_info['overpaid']
    initial_final_share = settlement_info['initial_final_share']
    
    if request.method == "POST":
        paid_amount_str = request.POST.get("amount", "").strip()
        notes = request.POST.get("notes", "").strip()
        
        if not paid_amount_str:
            from django.contrib import messages
            messages.error(request, "Paid amount is required.")
            return render(request, "core/exchanges/record_payment.html", {
                'account': account,
                'client_pnl': client_pnl,
                'final_share': final_share,
                'remaining_amount': remaining_amount,
            })
        
        try:
            paid_amount = int(paid_amount_str)
            if paid_amount <= 0:
                from django.contrib import messages
                messages.error(request, "Paid amount must be greater than zero.")
                return render(request, "core/exchanges/record_payment.html", {
                    'account': account,
                    'client_pnl': client_pnl,
                    'final_share': final_share,
                    'remaining_amount': remaining_amount,
                })
            
            # CRITICAL: Use database row locking to prevent concurrent payment race conditions
            from django.db import transaction
            from django.core.exceptions import ValidationError
            
            try:
                with transaction.atomic():
                    # Lock the account row to prevent concurrent modifications
                    account = (
                        ClientExchangeAccount.objects
                        .select_for_update()
                        .get(pk=account_id, client__user=request.user)
                    )
                    
                    # Recalculate values with locked account (may have changed)
                    client_pnl = account.compute_client_pnl()
                    
                    # CRITICAL FIX: Lock share at first compute per PnL cycle
                    account.lock_initial_share_if_needed()
                    
                    # Get settlement info using LOCKED share
                    settlement_info = account.get_remaining_settlement_amount()
                    initial_final_share = settlement_info['initial_final_share']
                    remaining_amount = settlement_info['remaining']
                    overpaid_amount = settlement_info['overpaid']
                    total_settled = settlement_info['total_settled']
                    
                    # MASKED SHARE SETTLEMENT SYSTEM: Block settlement when InitialFinalShare = 0
                    if initial_final_share == 0:
                        from django.contrib import messages
                        messages.warning(
                            request,
                            "No settlement allowed. Initial final share is zero (share percentage too small or PnL too small)."
                        )
                        if redirect_to == 'pending_summary':
                            return redirect(reverse("pending_summary"))
                        return redirect(reverse("exchange_account_detail", args=[account.pk]))
                    
                    # MASKED SHARE SETTLEMENT SYSTEM: Validate against remaining settlement amount (ATOMIC)
                    if paid_amount > remaining_amount:
                        raise ValidationError(
                            f"Paid amount ({paid_amount}) cannot exceed remaining settlement amount ({remaining_amount}). "
                            f"Initial share: {initial_final_share}, Already settled: {total_settled}"
                        )
                    
                    # Check if PnL = 0 (trading flat, not settlement complete)
                    if client_pnl == 0:
                        from django.contrib import messages
                        messages.warning(request, "Account PnL is zero (trading flat). No settlement needed.")
                        if redirect_to == 'pending_summary':
                            return redirect(reverse("pending_summary"))
                        return redirect(reverse("exchange_account_detail", args=[account.pk]))
                    
                    # Apply RECORD PAYMENT logic (MASKED SHARE SETTLEMENT SYSTEM)
                    old_funding = account.funding
                    old_balance = account.exchange_balance
                    
                    # CRITICAL FIX: Use locked share percentage (prevents historical rewrite)
                    locked_share_pct = account.locked_share_percentage
                    if locked_share_pct is None or locked_share_pct == 0:
                        # Fallback to current share percentage if not locked yet
                        if client_pnl < 0:
                            locked_share_pct = account.loss_share_percentage if account.loss_share_percentage > 0 else account.my_percentage
                        else:
                            locked_share_pct = account.profit_share_percentage if account.profit_share_percentage > 0 else account.my_percentage
                    
                    # CRITICAL FIX: MaskedCapital formula - map linearly back to PnL
                    # Formula: MaskedCapital = (SharePayment × abs(LockedInitialPnL)) / LockedInitialFinalShare
                    # This ensures SharePayment maps back to PnL linearly, not exponentially
                    # This prevents double-counting of share percentage
                    if initial_final_share == 0:
                        raise ValidationError(
                            "Cannot calculate masked capital. Initial final share is zero."
                        )
                    
                    # Use locked initial PnL (must exist if initial_final_share > 0)
                    locked_initial_pnl = account.locked_initial_pnl
                    if locked_initial_pnl is None:
                        # Should not happen if share is locked correctly
                        locked_initial_pnl = abs(client_pnl)
                    
                    # CORRECT FORMULA: MaskedCapital = (SharePayment × abs(LockedInitialPnL)) / LockedInitialFinalShare
                    masked_capital = int((paid_amount * abs(locked_initial_pnl)) / initial_final_share)
                    
                    # CRITICAL: Validate that funding/exchange_balance won't go negative
                    if client_pnl < 0:
                        # LOSS CASE: Masked capital reduces Funding
                        # Formula: Funding = Funding − MaskedCapital
                        if account.funding - int(masked_capital) < 0:
                            raise ValidationError(
                                f"Cannot record payment. Funding would become negative "
                                f"(Current: {account.funding}, Masked Capital: {int(masked_capital)})."
                            )
                        account.funding -= int(masked_capital)
                        action_desc = f"Funding reduced: {old_funding} → {account.funding} (Masked Capital: {int(masked_capital)}, SharePayment: {paid_amount}, Locked Initial PnL: {locked_initial_pnl}, Locked Initial Share: {initial_final_share})"
                    else:
                        # PROFIT CASE: Masked capital reduces Exchange Balance
                        # Formula: ExchangeBalance = ExchangeBalance − MaskedCapital
                        if account.exchange_balance - int(masked_capital) < 0:
                            raise ValidationError(
                                f"Cannot record payment. Exchange balance would become negative "
                                f"(Current: {account.exchange_balance}, Masked Capital: {int(masked_capital)})."
                            )
                        account.exchange_balance -= int(masked_capital)
                        action_desc = f"Exchange balance reduced: {old_balance} → {account.exchange_balance} (Masked Capital: {int(masked_capital)}, SharePayment: {paid_amount}, Locked Initial PnL: {locked_initial_pnl}, Locked Initial Share: {initial_final_share})"
                    
                    # Save account changes
                    account.save()
                    
                    # MASKED SHARE SETTLEMENT SYSTEM: Create Settlement record
                    Settlement.objects.create(
                        client_exchange=account,
                        amount=paid_amount,
                        notes=notes or f"Payment recorded: {paid_amount}. {action_desc}"
                    )
                    
                    # Create transaction record for audit trail
                    Transaction.objects.create(
                        client_exchange=account,
                        date=timezone.now(),
                        type='RECORD_PAYMENT',
                        amount=paid_amount,
                        exchange_balance_after=account.exchange_balance,
                        notes=notes or f"Payment recorded: {paid_amount}. {action_desc}"
                    )
                    
                    # Recompute values after payment
                    new_pnl = account.compute_client_pnl()
                    new_final_share = account.compute_my_share()
                    new_settlement_info = account.get_remaining_settlement_amount()
                    new_remaining = new_settlement_info['remaining']
                    new_overpaid = new_settlement_info['overpaid']
                    
                    from django.contrib import messages
                    if new_pnl == 0:
                        messages.success(
                            request,
                            f"Payment of {paid_amount} recorded successfully. Account PnL is now zero (trading flat)."
                        )
                    elif new_remaining == 0:
                        messages.success(
                            request,
                            f"Payment of {paid_amount} recorded successfully. Settlement complete (remaining share: 0)."
                        )
                    else:
                        messages.success(
                            request,
                            f"Payment of {paid_amount} recorded successfully. "
                            f"Remaining settlement amount: {new_remaining}"
                        )
                    
                    # Redirect based on redirect_to parameter
                    if redirect_to == 'pending_summary':
                        return redirect(reverse("pending_summary"))
                    return redirect(reverse("exchange_account_detail", args=[account.pk]))
                    
            except ValidationError as e:
                from django.contrib import messages
                messages.error(request, str(e))
                return render(request, "core/exchanges/record_payment.html", {
                    'account': account,
                    'client_pnl': client_pnl,
                    'final_share': final_share,
                    'remaining_amount': remaining_amount,
                })
            
        except ValueError:
            from django.contrib import messages
            messages.error(request, "Invalid amount. Please enter a valid number.")
            return render(request, "core/exchanges/record_payment.html", {
                'account': account,
                'client_pnl': client_pnl,
                'final_share': final_share,
                'remaining_amount': remaining_amount,
            })
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f"Error recording payment: {str(e)}")
            return render(request, "core/exchanges/record_payment.html", {
                'account': account,
                'client_pnl': client_pnl,
                'final_share': final_share,
                'remaining_amount': remaining_amount,
            })
    
    # GET request - show form
    return render(request, "core/exchanges/record_payment.html", {
        'account': account,
        'client_pnl': client_pnl,
        'final_share': final_share,
        'remaining_amount': remaining_amount,
    })


@login_required


def report_time_travel(request):


    """Time travel report view."""
    date_str = request.GET.get('date', '')
    # TODO: Add time travel report calculation logic here
    context = {
        'date': date_str,
    }
    return render(request, "core/reports/time_travel.html", context)


@login_required


def report_exchange(request, exchange_pk):


    """Report for a specific exchange with graphs and analysis."""
    from datetime import timedelta
    
    exchange = get_object_or_404(Exchange, pk=exchange_pk)
    today = date.today()
    report_type = request.GET.get("report_type", "weekly")  # daily, weekly, monthly
    
    # Calculate date range based on report type
    if report_type == "daily":

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
        day_of_month = today.day
        if today.month == 1:
            pass
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
    company_profit = qsDecimal(0)
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

        if tx_type in type_map:


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
    # TODO: SystemSettings model removed - add back if needed
    settings = None  # Placeholder
    
    if request.method == "POST":

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

        client_exchange_id = request.POST.get("client_exchange")
        balance_date = request.POST.get("balance_date")
        remaining_balance = Decimal(request.POST.get("remaining_balance", 0))
        extra_adjustment = Decimal(request.POST.get("extra_adjustment", 0) or 0)
        note = request.POST.get("note", "")
        balance_id = request.POST.get("balance_id")
        
        if balance_date and client_exchange_id and remaining_balance >= 0:
            client_exchange = get_object_or_404(ClientExchangeAccount, pk=client_exchange_id, client=client)

            
            if balance_id:
                # Edit existing balance
                balance = get_object_or_404(ClientDailyBalance, pk=balance_id, client_exchange__client=client)

                balance_record_date_obj = date.fromisoformat(balance_date)

                
                # Get old balance based on client type
                # All clients are now my clients
                    # My Clients: Old Balance = balance after last settlement
                    # For BOTH MY CLIENTS and COMPANY CLIENTS: Use the same logic
                    # Old Balance = SUM of FUNDING (or balance after settlement + funding after)
                    # NEVER use BALANCE_RECORD for Old Balance
                    
                
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
                        # My Clients: Use outstanding (netted system) with new logic
                        update_outstanding_from_balance_change(

                            client_exchange, 

                            old_balance, 

                            new_balance, 

                            balance_date=balance_record_date_obj

                        )
            else:
                # Create new balance
                balance_record_date_obj = date.fromisoformat(balance_date)
                
                # Get old balance
                # Old Balance = SUM of FUNDING (or balance after settlement + funding after)
                # NEVER use BALANCE_RECORD for Old Balance
                
                new_balance = remaining_balance + extra_adjustment

                # TODO: ClientDailyBalance model removed - add back if needed
                balance, created = None, False  # ClientDailyBalance.objects.update_or_create(
                #     client_exchange=client_exchange,
                #     date=balance_record_date_obj,
                #     defaults={
                #         "remaining_balance": remaining_balance,
                #         "extra_adjustment": extra_adjustment,
                #         "note": note,
                #     }
                # )
                
                # Always create a new transaction for this balance record
                # Each recording creates a separate transaction entry (no updates to existing transactions)
                from datetime import datetime
                
                balance_note = note or f"Balance Record: ₹{remaining_balance}"
                
                if extra_adjustment:
                    balance_note += f" (Extra: ₹{extra_adjustment})"
                
                balance_note += f" (Recorded at {datetime.now().strftime('%H:%M:%S')})"
                
                Transaction.objects.create(
                    client_exchange=client_exchange,
                    date=balance_record_date_obj,
                    type='ADJUSTMENT',
                    amount=new_balance,
                    exchange_balance_after=new_balance,
                    note=balance_note,
                )
                
                # Note: create_loss_profit_from_balance_change is deprecated in PIN-TO-PIN
                # Profit/loss is computed from accounts, not transactions
                
                # Update exchange balance if balance changed
                if new_balance != old_balance:
                    client_exchange.exchange_balance = new_balance
                    client_exchange.save()
        
        # Redirect to client detail
    from django.shortcuts import redirect
    from django.urls import reverse
    return redirect("client_detail", pk=client.pk)

    
    # Check if editing a balance
    edit_balance_id = request.GET.get("edit_balance")
    edit_balance = None
    if edit_balance_id:
        try:
            # ClientDailyBalance model removed in PIN-TO-PIN
            edit_balance = None
        except Exception:
            pass


    
    # Get filter for exchange
    selected_exchange_id = request.GET.get("exchange")
    selected_exchange = None
    if selected_exchange_id:
        try:
            selected_exchange = ClientExchangeAccount.objects.get(pk=selected_exchange_id, client=client)
        except ClientExchangeAccount.DoesNotExist:
            pass


    
    # Calculate balances per client-exchange
    client_exchanges = client.exchange_accounts.select_related("exchange").all()
    
    # Filter by selected exchange if provided
    if selected_exchange:

    
        pass
    # Get system settings for calculations
    # TODO: SystemSettings model removed - add back if needed
    settings = None  # Placeholder
    
    exchange_balances = []
    
    for client_exchange in client_exchanges:

        
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
        
        # TODO: ClientDailyBalance model removed - add back if needed
        # Get daily balance records for this exchange
        daily_balances = []  # ClientDailyBalance.objects.filter(
        #     client_exchange=client_exchange
        # ).order_by("-date")[:10]  # Last 10 records per exchange
        
        # Get latest daily balance record (most recent)
        latest_balance_record = None  # ClientDailyBalance.objects.filter(
        #     client_exchange=client_exchange
        # ).order_by("-date").first()
        
        # Calculate profit/loss using new logic
        profit_loss_data = calculate_client_profit_loss(client_exchange)
        
        # Use client-specific my_share_pct from ClientExchangeAccount configuration
        # This is the percentage configured on the client detail page
        admin_profit_share_pct = client_exchange.my_share_pct
        
        # Calculate admin profit/loss - pass client_exchange for correct company share calculation
        admin_data = calculate_admin_profit_loss(profit_loss_data["client_profit_loss"], settings, admin_profit_share_pct, client_exchange)
        
        # Total balance in exchange account (recorded + extra adjustment)
        if latest_balance_record:


            pass
        else:

            total_balance_in_exchange = client_net


        
        # Calculate you owe client = client profit share minus settlements where admin paid
        client_settlements_paid = transactions.filter(
            transaction_type=Transaction.TYPE_SETTLEMENT,

            client_share_amount__gt=0,

            your_share_amount=0

        ).aggregate(total=Sum("client_share_amount"))["total"] or Decimal(0)
        # 🚨 CRITICAL: Settlements are already reflected by moving Old Balance
        # So pending is simply the share amount - DO NOT subtract settlements again
        # The Old Balance has already been moved forward by previous settlements
        # So the current profit (current_balance - old_balance) already accounts for settlements
        # Therefore, client_profit_share calculated from this profit is the correct pending amount
        pending_you_owe = max(Decimal(0), client_profit_share)  # Don't subtract settlements - already accounted for
        
        # 🔹 Calculate Your Net Profit from this Client (till now)
        # Formula: (Current Balance - Old Balance) × My Share %
        # This is YOUR money (plus or minus) from this client
        
        current_balance = total_balance_in_exchange
        net_change = current_balance - old_balance
        my_share_pct = client_exchange.my_share_pct
        your_net_profit_raw = (net_change * my_share_pct) / Decimal(100)
        your_net_profit = round_share(your_net_profit_raw)  # Share-space: round DOWN
        
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

            "company_share_pct": client_exchange.company_share_pct if False else Decimal(0),

            "my_share_pct": client_exchange.my_share_pct,

            "your_net_profit": your_net_profit,  # Your Net Profit from this Client (till now)

            "old_balance": old_balance,  # For reference/debugging

            "current_balance": current_balance,  # For reference/debugging

        })
    
    # TODO: ClientDailyBalance model removed - add back if needed
    # Get all daily balances for the client (for summary view)
    daily_balance_qs = []  # ClientDailyBalance.objects.filter(
    #     client_exchange__client=client
    # ).select_related("client_exchange", "client_exchange__exchange")
    
    # Filter daily balances by selected exchange if provided
    # if selected_exchange:
    #     daily_balance_qs = daily_balance_qs.filter(client_exchange=selected_exchange)
    
    all_daily_balances = []  # daily_balance_qs.order_by("-date")[:30]
    
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
        if tx.transaction_type == Transaction.TYPE_BALANCE_RECORD:
            class MockBalance:
                def __init__(self, amount):
                    self.remaining_balance = amount
                    self.extra_adjustment = Decimal(0)
            
            tx.recorded_balance = MockBalance(tx.amount)
        else:
            # TODO: ClientDailyBalance model removed - add back if needed
            # For other transactions, find the balance record created closest to (but before or at) this transaction's time
            # First, try to find balance records on the same date, created before or at this transaction's time
            recorded_balance = None  # ClientDailyBalance.objects.filter(
    #     client_exchange=tx.client_exchange,
    #     date=tx.date,
    #     created_at__lte=tx.created_at
    # ).order_by('-created_at').first()
            
            # If no balance on same date before this transaction, get the most recent balance before this date
            if not recorded_balance:
                # ClientDailyBalance model removed - use exchange_balance from account
                recorded_balance = None
            
            # If still no balance record found, calculate from transactions
            if not recorded_balance:
                # Calculate balance from transactions up to this point
                balance_amount = get_exchange_balance(tx.client_exchange, as_of_date=tx.date)

                class MockBalance:

                    def __init__(self, amount):

                        self.remaining_balance = amount


                        self.extra_adjustment = Decimal(0)

                tx.recorded_balance = MockBalance(balance_amount)

                tx.recorded_balance = recorded_balance

        
        transactions_with_balances.append(tx)
    
    all_transactions = transactions_with_balances
    
    # Calculate total balance across all exchanges (or selected exchange)
    total_balance_all_exchanges = Decimal(0)
    for bal in exchange_balances:
        total_balance_all_exchanges += bal.get('balance', 0)
    
    # Get all client exchanges for the dropdown (not filtered)
    all_client_exchanges = client.exchange_accounts.select_related("exchange").all()
    
    # Get selected exchange name for display
    selected_exchange_name = None
    if selected_exchange and exchange_balances:

    
        pass
    # Determine client type for URL namespace
    client_type = "company" if False else "my"
    
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



