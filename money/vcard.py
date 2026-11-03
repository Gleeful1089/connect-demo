"""Simulated single-use virtual card. No real payment integration, no real card numbers."""
from __future__ import annotations

import hashlib


def issue(booking_id: str, total_cents: int, currency: str) -> dict:
    if isinstance(total_cents, bool) or not isinstance(total_cents, int) or total_cents < 0:
        raise ValueError("total must be a non-negative integer in minor units")
    return {
        "card_id": "VC-" + hashlib.sha256(booking_id.encode()).hexdigest()[:10].upper(),
        "display": "**** **** **** 0000 (simulated)",
        "single_use": True, "limit_cents": total_cents, "currency": currency, "status": "ISSUED_SIMULATED",
    }


def settle(card: dict, captured_cents: int) -> dict:
    if captured_cents > card["limit_cents"]:
        raise ValueError("capture exceeds the single-use limit")
    return {**card, "captured_cents": captured_cents, "status": "CAPTURED_SIMULATED" if captured_cents else "VOIDED_SIMULATED"}
