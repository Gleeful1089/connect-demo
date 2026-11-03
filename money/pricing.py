"""Itemized buyer price. Deterministic. No LLM. All amounts are integer minor units."""
from __future__ import annotations

from decimal import Decimal

import config
from money.rounding import pct_of, round_cents


def quote_amount(contracted_cents: int, hotel_ccy: str, buyer_ccy: str) -> dict:
    """Itemize what the buyer pays for a contracted hotel amount.

    Same currency: contracted rate only. Different currency: contracted rate (hotel currency, for reference),
    the amount converted at the synthetic mid rate, a 1.5% FX margin on the converted amount, and the total.
    """
    lines = [{"label": "Hotel contracted rate", "amount_cents": contracted_cents, "currency": hotel_ccy, "kind": "contracted"}]
    if hotel_ccy == buyer_ccy:
        total = contracted_cents
    else:
        rate = config.FX_RATES[(hotel_ccy, buyer_ccy)]
        converted = round_cents(Decimal(contracted_cents) * rate)
        margin = pct_of(converted, config.FX_MARGIN)
        lines += [
            {"label": f"Converted at {rate} ({hotel_ccy} to {buyer_ccy}, synthetic mid rate)", "amount_cents": converted,
             "currency": buyer_ccy, "kind": "converted"},
            {"label": f"FX margin {config.FX_MARGIN * 100:.1f}% (paid by buyer)", "amount_cents": margin,
             "currency": buyer_ccy, "kind": "fx_margin"},
        ]
        total = converted + margin
    lines.append({"label": "Total", "amount_cents": total, "currency": buyer_ccy, "kind": "total"})
    return {"lines": lines, "total_cents": total, "currency": buyer_ccy}


def quote_stay(nightly_cents: int, nights: int, hotel_ccy: str, buyer_ccy: str) -> dict:
    if nights < 1:
        raise ValueError("nights must be at least 1")
    q = quote_amount(nightly_cents * nights, hotel_ccy, buyer_ccy)
    q["nights"] = nights
    q["nightly_cents"] = nightly_cents
    return q
