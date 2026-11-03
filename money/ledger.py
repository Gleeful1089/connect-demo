"""Booking ledger and hotel statement. Deterministic. No LLM. Integer minor units only."""
from __future__ import annotations

from money import fee as feemod
from money import pricing, vcard


def build_statement(booking_id: str, nightly_cents: int, nights: int, hotel_ccy: str, buyer_ccy: str,
                    scenario: str, retained_cents: int | None = None) -> dict:
    net = nightly_cents * nights
    booked = pricing.quote_stay(nightly_cents, nights, hotel_ccy, buyer_ccy)
    card = vcard.issue(booking_id, booked["total_cents"], buyer_ccy)
    retained = 0
    if scenario == "cancelled_retained":
        retained = retained_cents if retained_cents is not None else nightly_cents  # default: first night
    fee = feemod.platform_fee_cents(hotel_ccy, scenario, net, retained)

    if scenario == "completed":
        hotel_gross, buyer_charge = net, booked
    elif scenario == "cancelled_retained":
        hotel_gross, buyer_charge = retained, pricing.quote_amount(retained, hotel_ccy, buyer_ccy)
    else:
        hotel_gross, buyer_charge = 0, {"lines": [], "total_cents": 0, "currency": buyer_ccy}

    fx_margin = next((l["amount_cents"] for l in buyer_charge["lines"] if l["kind"] == "fx_margin"), 0)
    converted = next((l["amount_cents"] for l in buyer_charge["lines"] if l["kind"] == "converted"),
                     buyer_charge["total_cents"])
    entries = [
        {"account": "buyer_card_captured", "amount_cents": buyer_charge["total_cents"], "currency": buyer_ccy},
        {"account": "hotel_gross", "amount_cents": hotel_gross, "currency": hotel_ccy},
        {"account": "platform_fee", "amount_cents": fee["fee_cents"], "currency": hotel_ccy},
        {"account": "hotel_net_payout", "amount_cents": hotel_gross - fee["fee_cents"], "currency": hotel_ccy},
        {"account": "platform_fx_margin", "amount_cents": fx_margin, "currency": buyer_ccy},
    ]
    # Invariants that must always hold.
    assert buyer_charge["total_cents"] == converted + fx_margin or hotel_ccy == buyer_ccy
    assert hotel_gross - fee["fee_cents"] >= 0
    return {
        "booking_id": booking_id, "scenario": scenario, "nights": nights, "hotel_currency": hotel_ccy, "buyer_currency": buyer_ccy,
        "pre_tax_net_rate_cents": net, "retained_cents": retained, "fee": fee,
        "hotel_net_payout_cents": hotel_gross - fee["fee_cents"], "buyer_charge": buyer_charge,
        "virtual_card": vcard.settle(card, buyer_charge["total_cents"]), "ledger": entries,
        "note": "Rates are treated as pre-tax. Taxes are collected at the property and are out of scope.",
    }
