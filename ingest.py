"""Parses the two CRS-style formats into normalized records. No model involved. Synthetic data. Demo only."""
from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

DATA = Path(__file__).parent / "data"

A_EXPECTED = {"code", "rate", "public_rate", "cancel", "prepaid", "applies_to", "avail", "updated"}
A_REQUIRED = {"code", "rate", "public_rate", "avail", "updated"}
A_ALIASES = {"price": "rate"}   # known connector alias, still reported as drift

HOTEL_IDS = {"Seaview Inn": "SV1", "Lakeside Boutique": "LB1"}


def to_cents(value: str) -> int:
    return int((Decimal(value) * 100).to_integral_value())


def parse_format_a(path: Path = DATA / "format_a.json", registered: dict | None = None) -> list[dict]:
    """registered: {unexpected_key: canonical_key} aliases a human has approved. They are not reported as drift."""
    registered = registered or {}
    doc = json.loads(path.read_text())
    prop = doc["property"]
    out = []
    for room in doc["rooms"]:
        for plan in room["ratePlans"]:
            keys = set(plan)
            unexpected = sorted(k for k in keys - A_EXPECTED if k not in registered)
            missing = sorted(k for k in A_REQUIRED - keys if k not in {registered[u] for u in keys & set(registered)})
            p = dict(plan)
            for alias, real in A_ALIASES.items():
                if alias in p and real not in p:
                    p[real] = p.pop(alias)
            out.append({
                "hotel_id": prop["id"], "hotel_name": prop["name"], "currency": prop["currency"], "city": prop["city"],
                "source_format": "A", "room_key": room["code"], "plan_key": p["code"],
                "rate_cents": to_cents(p["rate"]), "public_cents": to_cents(p["public_rate"]),
                "avail": int(p["avail"]), "updated_at": p["updated"],
                "view": {"format": "A", "room_code": room["code"], "max_occ": room["max_occ"], "plan_code": p["code"],
                         "cancel_code": p.get("cancel"), "prepaid_flag": p.get("prepaid")},
                "extra": {"applies_to": p.get("applies_to", []), "drift": {"unexpected": unexpected, "missing": missing},
                          "cancel_raw": p.get("cancel"), "max_occ": room["max_occ"]},
            })
    return out


def parse_format_b(path: Path = DATA / "format_b.csv") -> list[dict]:
    out = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            out.append({
                "hotel_id": HOTEL_IDS[row["hotel"]], "hotel_name": row["hotel"], "currency": row["currency"],
                "city": "Valmora Bay", "source_format": "B", "room_key": row["room_name"], "plan_key": row["rate_plan_name"],
                "rate_cents": to_cents(row["nightly_rate"]), "public_cents": to_cents(row["public_rate"]),
                "avail": int(row["rooms_left"]), "updated_at": row["last_updated"],
                "view": {"format": "B", "room_name": row["room_name"], "plan_name": row["rate_plan_name"],
                         "max_guests": int(row["max_guests"]) if row["max_guests"] else None,
                         "cancel_policy": row["cancel_policy"] or None},
                "extra": {"applies_to": [], "drift": {"unexpected": [], "missing": []},
                          "cancel_raw": row["cancel_policy"] or None, "max_occ": int(row["max_guests"]) if row["max_guests"] else None},
            })
    return out


def load_all(registered_a: dict | None = None) -> list[dict]:
    records = parse_format_a(registered=registered_a) + parse_format_b()
    for i, r in enumerate(records, start=1):
        r["id"] = f"R{i:02d}"
    return records
