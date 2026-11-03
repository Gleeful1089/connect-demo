"""Platform fee charged to the hotel. Deterministic. No LLM.

fee = 3% of the pre-tax net rate, with a per-booking floor, capped at the amount it is charged on.
  completed stay                 : base = full pre-tax net rate
  cancelled, no charge           : fee is zero (no floor)
  cancelled, retained charge     : base = the retained amount (floor and cap apply to it)
"""
from __future__ import annotations

import config
from money.rounding import pct_of

SCENARIOS = ("completed", "cancelled_no_charge", "cancelled_retained")


def platform_fee_cents(currency: str, scenario: str, net_rate_cents: int, retained_cents: int = 0) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}")
    for v in (net_rate_cents, retained_cents):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError("amounts must be non-negative integers (minor units)")
    if scenario == "cancelled_no_charge":
        return {"fee_cents": 0, "base_cents": 0, "rule": "cancelled with no charge: no fee"}
    base = net_rate_cents if scenario == "completed" else retained_cents
    if scenario == "cancelled_retained" and not 0 < retained_cents <= net_rate_cents:
        raise ValueError("retained charge must be positive and no more than the net rate")
    pct = pct_of(base, config.FEE_RATE)
    floor = config.FEE_FLOOR_CENTS[currency]
    fee = min(max(pct, floor), base)
    rule = "floor applied" if pct < floor <= base else ("capped at base" if floor > base else "3% of base")
    return {"fee_cents": fee, "base_cents": base, "pct_cents": pct, "floor_cents": floor, "rule": rule}
