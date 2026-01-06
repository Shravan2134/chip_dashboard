"""
Centralized Money Rounding Utilities

🔒 CRITICAL FINANCIAL RULES:
1. SHARE-SPACE values ALWAYS round DOWN (prevents over-collection)
2. CAPITAL-SPACE values use ROUND_HALF_UP (standard accounting)

This ensures:
- Clients never pay more than their actual share
- Capital calculations are mathematically correct
- Zero rounding mistakes across the entire codebase
"""

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP


# =========================
# SHARE-SPACE ROUNDING
# =========================
def round_share(amount: Decimal, decimals: int = 1) -> Decimal:
    """
    Share-space rounding (client payable, my share, company share)

    RULE:
    - ALWAYS round DOWN
    - NEVER round up
    - Prevents over-collection from clients
    - ✅ BULLETPROOF: Auto-converts int/float to Decimal (prevents quantize errors)

    Examples:
    8.55 → 8.5
    8.56 → 8.5
    8.88 → 8.8
    9.00 → 9.0

    Args:
        amount: Decimal amount to round (can be int, float, or Decimal)
        decimals: Number of decimal places (default: 1 for share space)

    Returns:
        Rounded Decimal (always rounded DOWN)
    """
    if amount is None:
        return Decimal("0")
    
    # ✅ BULLETPROOF: Auto-convert int/float to Decimal (prevents 'int' object has no attribute 'quantize')
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))

    quant = Decimal("1").scaleb(-decimals)  # 0.1 for 1 decimal, 0.01 for 2 decimals
    return amount.quantize(quant, rounding=ROUND_DOWN)


# =========================
# CAPITAL-SPACE ROUNDING
# =========================
def round_capital(amount: Decimal, decimals: int = 2) -> Decimal:
    """
    Capital-space rounding (capital, loss, capital_closed, old balance)

    RULE:
    - ROUND_HALF_UP is allowed (standard accounting)
    - Used for ledger values and capital calculations
    - ✅ BULLETPROOF: Auto-converts int/float to Decimal (prevents quantize errors)

    Examples:
    8.555 → 8.56
    8.554 → 8.55
    8.555 → 8.56 (rounds up)

    Args:
        amount: Decimal amount to round (can be int, float, or Decimal)
        decimals: Number of decimal places (default: 2 for capital space)

    Returns:
        Rounded Decimal (ROUND_HALF_UP)
    """
    if amount is None:
        return Decimal("0")
    
    # ✅ BULLETPROOF: Auto-convert int/float to Decimal (prevents 'int' object has no attribute 'quantize')
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))

    quant = Decimal("1").scaleb(-decimals)  # 0.01 for 2 decimals
    return amount.quantize(quant, rounding=ROUND_HALF_UP)


# =========================
# AUTO-CLOSE THRESHOLD
# =========================
AUTO_CLOSE_THRESHOLD = Decimal("0.01")


def is_effectively_zero(amount: Decimal, threshold: Decimal = None) -> bool:
    """
    Check if amount is effectively zero (below threshold).

    Args:
        amount: Decimal amount to check
        threshold: Threshold value (default: AUTO_CLOSE_THRESHOLD)

    Returns:
        True if amount < threshold, False otherwise
    """
    if threshold is None:
        threshold = AUTO_CLOSE_THRESHOLD
    return abs(amount) < threshold


# =========================
# SHARE SPLIT CALCULATION
# =========================
def calculate_share_split(
    loss: Decimal,
    my_pct: Decimal,
    company_pct: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    """
    Calculate share split from loss amount with guaranteed no leakage.
    
    🔥 CRITICAL: This is the ONLY correct way to split shares.
    
    Algorithm:
    1. Calculate RAW share-space amounts
    2. Round TOTAL first (client-facing amount)
    3. Round ONLY ONE SIDE (my_amount)
    4. Give remainder to the other side (NO ROUNDING)
    
    This guarantees:
    - total_payable is rounded DOWN (prevents over-collection)
    - my_amount is rounded DOWN
    - company_amount absorbs remainder (no rounding)
    - my_amount + company_amount == total_payable (ALWAYS)
    - No money "disappears" due to double rounding
    
    Args:
        loss: Loss amount (capital-space)
        my_pct: My share percentage (e.g., 1 for 1%)
        company_pct: Company share percentage (e.g., 9 for 9%)
    
    Returns:
        tuple: (my_amount, company_amount, total_payable)
        - my_amount: Your share (rounded DOWN)
        - company_amount: Company share (remainder, no rounding)
        - total_payable: Total client pays (rounded DOWN)
    
    Example:
        loss = 95, my_pct = 1, company_pct = 9
        Returns: (0.9, 8.6, 9.5)
        Verification: 0.9 + 8.6 = 9.5 ✅
    """
    # ✅ BULLETPROOF: Auto-convert inputs to Decimal (prevents quantize errors)
    if loss is None:
        return Decimal(0), Decimal(0), Decimal(0)
    
    if not isinstance(loss, Decimal):
        loss = Decimal(str(loss))
    
    if loss < 0:
        return Decimal(0), Decimal(0), Decimal(0)
    
    if my_pct is None:
        my_pct = Decimal(0)
    elif not isinstance(my_pct, Decimal):
        my_pct = Decimal(str(my_pct))
    
    if company_pct is None:
        company_pct = Decimal(0)
    elif not isinstance(company_pct, Decimal):
        company_pct = Decimal(str(company_pct))
    
    total_pct = my_pct + company_pct
    if total_pct <= 0:
        raise ValueError("Invalid share percentage: total_pct must be > 0")
    
    # 1️⃣ RAW share-space amounts
    raw_total = (loss * total_pct) / Decimal(100)
    raw_my = (loss * my_pct) / Decimal(100)
    
    # 2️⃣ Round TOTAL first (client-facing amount) - ROUND DOWN
    total_payable = round_share(raw_total)
    
    # 3️⃣ Round ONLY ONE SIDE (my_amount) - ROUND DOWN
    my_amount = round_share(raw_my)
    
    # 4️⃣ Give remainder to the other side (NO ROUNDING)
    # This ensures: my_amount + company_amount == total_payable (ALWAYS)
    company_amount = total_payable - my_amount
    
    return my_amount, company_amount, total_payable

