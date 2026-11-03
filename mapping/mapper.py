"""Model-assisted mapping of raw records to the canonical ontology.

The prompt contains only the raw vendor fields of one record. No labels, no rates, no other records.
"""
from __future__ import annotations

import json
import re

import llm
import ontology

SYSTEM = (
    "You normalize hotel room and rate-plan data from different reservation systems into a canonical ontology. "
    "Reply with one JSON object and nothing else."
)


def build_prompt(view: dict) -> str:
    spec = {
        "category": ontology.ROOM_CATEGORIES, "bed": ontology.BEDS, "view": ontology.VIEWS,
        "max_occupancy": "integer", "meal_plan": ontology.MEALS, "cancellation": ontology.CANCELLATIONS,
        "prepaid": "boolean",
    }
    return (
        "Map this raw record to the canonical fields. Use 'unspecified' for bed or cancellation when the source "
        "does not say, and 'none' for view when no view is stated.\n"
        f"Allowed values: {json.dumps(spec)}\n"
        f"Raw record: {json.dumps(view, sort_keys=True)}\n"
        'Return JSON: {"category":..,"bed":..,"view":..,"max_occupancy":..,"meal_plan":..,'
        '"cancellation":..,"prepaid":..,"confidence": number between 0 and 1}'
    )


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in model output")
    return json.loads(m.group(0))


def validate(obj: dict) -> tuple[dict, float, str]:
    """Coerce to the ontology. Returns (mapping, confidence, parse_note)."""
    notes = []
    mapping = {}
    for f, allowed in ontology.ALLOWED.items():
        v = obj.get(f)
        if v not in allowed:
            notes.append(f"{f}={v!r} not in ontology")
            v = "unspecified" if "unspecified" in allowed else None
        mapping[f] = v
    occ = obj.get("max_occupancy")
    mapping["max_occupancy"] = occ if isinstance(occ, int) and occ > 0 else None
    if mapping["max_occupancy"] is None:
        notes.append("max_occupancy invalid")
    pre = obj.get("prepaid")
    mapping["prepaid"] = pre if isinstance(pre, bool) else None
    if mapping["prepaid"] is None:
        notes.append("prepaid invalid")
    try:
        conf = max(0.0, min(1.0, float(obj.get("confidence", 0.0))))
    except (TypeError, ValueError):
        conf = 0.0
        notes.append("confidence invalid")
    if notes:
        conf = min(conf, 0.3)  # an invalid output can never auto-confirm
    return mapping, conf, "; ".join(notes)


def map_record(view: dict) -> tuple[dict, float, str, llm.LLMResult]:
    res = llm.complete("map_record", build_prompt(view), system=SYSTEM, tier="fast")
    try:
        mapping, conf, note = validate(_extract_json(res.text))
    except (ValueError, json.JSONDecodeError) as e:
        mapping = {f: None for f in ontology.FIELDS}
        conf, note = 0.0, f"unparseable model output: {e}"
    return mapping, conf, note, res
