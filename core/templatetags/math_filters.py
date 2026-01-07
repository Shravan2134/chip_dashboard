from django import template
from decimal import Decimal

register = template.Library()


@register.filter
def abs(value):
    """
    Return the absolute value of a number.
    Works with Decimal, int, float, and None values.
    """
    if value is None:
        return None
    try:
        if isinstance(value, Decimal):
            return abs(value)
        return abs(float(value))
    except (TypeError, ValueError):
        return value

from decimal import Decimal

register = template.Library()


@register.filter
def abs(value):
    """
    Return the absolute value of a number.
    Works with Decimal, int, float, and None values.
    """
    if value is None:
        return None
    try:
        if isinstance(value, Decimal):
            return abs(value)
        return abs(float(value))
    except (TypeError, ValueError):
        return value


