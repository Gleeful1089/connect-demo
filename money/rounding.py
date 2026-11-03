"""Rounding for minor units. Integer cents in, integer cents out. No floats anywhere in money/."""
from decimal import ROUND_HALF_UP, Decimal


def round_cents(value: Decimal) -> int:
    """Round a Decimal amount of cents to an integer, half up."""
    if not isinstance(value, Decimal):
        raise TypeError("round_cents requires a Decimal, never a float")
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def pct_of(cents: int, rate: Decimal) -> int:
    if isinstance(cents, bool) or not isinstance(cents, int):
        raise TypeError("cents must be an int")
    return round_cents(Decimal(cents) * rate)
