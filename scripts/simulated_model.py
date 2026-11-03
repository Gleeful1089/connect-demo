"""SIMULATED stand-in for the model. This is NOT a language model.

It is a small keyword heuristic used to author offline fixtures when no ANTHROPIC_API_KEY is available.
It reads only the prompt text, never the held-out labels. Its errors and its confidence scores are whatever
the heuristic produces; nothing here was tuned against the held-out set. Fixtures it writes are marked
provenance="simulated" and the UI says so. Re-record with a real key to replace them.
"""
from __future__ import annotations

import json
import re

MODEL_VERSION = "simulated-heuristic-v1"

A_CATEGORY = {"DLX": "deluxe", "STE": "suite", "FAM": "family", "STD": "standard", "SUP": "superior"}
A_BED = {"KG": "king", "QN": "queen", "TW": "twin", "2Q": "two_queens"}
A_VIEW = {"OV": "ocean", "CV": "city", "GD": "garden", "LV": "lake"}
A_MEAL = {"BB": "breakfast", "HB": "half_board", "RO": "room_only"}
A_CANCEL = {"FREE48": "free_48h", "FREE24": "free_24h", "NONREF": "non_refundable"}

# (state, value): state is explicit | inferred | default
def _score(states):
    conf = 0.98
    for s in states:
        conf -= {"explicit": 0.0, "inferred": 0.07, "default": 0.2}[s]
    return round(max(0.2, conf), 2)


def _map_a(v):
    parts = v["room_code"].split("-")
    cat = A_CATEGORY.get(parts[0]); bed = A_BED.get(parts[1]); view = A_VIEW.get(parts[2])
    st = []
    st.append("explicit" if cat else "default"); cat = cat or "standard"
    st.append("explicit" if bed else "default"); bed = bed or "unspecified"
    st.append("explicit" if view else "default"); view = view or "none"
    st.append("explicit"); occ = v["max_occ"]
    meal = A_MEAL.get(v["plan_code"].split("-")[-1])
    st.append("explicit" if meal else "default"); meal = meal or "room_only"
    cancel = A_CANCEL.get(v["cancel_code"] or "")
    st.append("explicit" if cancel else "default"); cancel = cancel or "unspecified"
    pre = v["prepaid_flag"]
    st.append("explicit" if pre is not None else "default"); pre = bool(pre)
    return dict(category=cat, bed=bed, view=view, max_occupancy=occ, meal_plan=meal, cancellation=cancel, prepaid=pre), st


def _map_b(v):
    room = v["room_name"].lower(); plan = v["plan_name"].lower(); pol = (v["cancel_policy"] or "").lower()
    st = []
    cat = next((c for pat, c in [(r"family", "family"), (r"suite", "suite"), (r"deluxe|dlx", "deluxe"),
                                  (r"superior", "superior"), (r"standard", "standard")] if re.search(pat, room)), None)
    st.append("explicit" if cat else "default"); cat = cat or "standard"
    bed = next((b for pat, b in [(r"2 queen|two queen", "two_queens"), (r"king", "king"), (r"queen", "queen"),
                                 (r"twin", "twin"), (r"double", "double")] if re.search(pat, room)), None)
    st.append("explicit" if bed else "inferred"); bed = bed or "unspecified"
    view = next((x for pat, x in [(r"ocean|sea", "ocean"), (r"city", "city"), (r"garden", "garden"), (r"lake", "lake")]
                 if re.search(pat, room)), None)
    st.append("explicit" if view else "inferred"); view = view or "none"
    occ = v["max_guests"]
    m = re.search(r"(?:sleeps|up to) (\d)", room)
    if occ is None and m:
        occ = int(m.group(1)); st.append("inferred")
    elif occ is None:
        occ = 2; st.append("default")
    else:
        st.append("explicit")
    meal = next((x for pat, x in [(r"half board", "half_board"), (r"breakfast|b&b|bed & breakfast", "breakfast"),
                                  (r"room only", "room_only")] if re.search(pat, plan)), None)
    st.append("explicit" if meal else "default"); meal = meal or "room_only"
    if re.search(r"non[- ]?refund", pol + " " + plan):
        cancel = "non_refundable"; st.append("explicit")
    elif re.search(r"48", pol):
        cancel = "free_48h"; st.append("explicit")
    elif re.search(r"24", pol):
        cancel = "free_24h"; st.append("explicit")
    else:
        cancel = "unspecified"; st.append("default")
    if "prepaid" in pol:
        pre = True; st.append("explicit")
    elif cancel == "non_refundable":
        pre = True; st.append("inferred")   # assumes non-refundable implies prepaid
    else:
        pre = False; st.append("explicit")
    return dict(category=cat, bed=bed, view=view, max_occupancy=occ, meal_plan=meal, cancellation=cancel, prepaid=pre), st


def simulate_map(prompt: str) -> str:
    view = json.loads(re.search(r"Raw record: (\{.*\})", prompt).group(1))
    mapping, states = _map_a(view) if view["format"] == "A" else _map_b(view)
    mapping["confidence"] = _score(states)
    return json.dumps(mapping)


RULE_TO_CLASS = {
    "iqr-outlier": ("rate-outlier", 0.93, "Rate/public ratio is outside the peer IQR fence."),
    "stale": ("stale-availability", 0.95, "Record not updated within the freshness window."),
    "schema-drift": ("schema-drift", 0.9, "Payload keys differ from the connector's expected schema."),
    "duplicate": ("duplicate-availability", 0.94, "Same room, plan and rate already listed."),
    "wrong-room-plan": ("rate-plan-on-wrong-room", 0.92, "Plan lists eligible rooms and this room is not one."),
    "missing-cancellation": ("missing-cancellation-policy", 0.96, "Cancellation field is empty."),
    "occupancy-mismatch": ("room-mismatch", 0.7, "Stated occupancy conflicts with the room type text."),
}


def simulate_classify(prompt: str) -> str:
    rule = re.search(r"Detector rule: (\S+)", prompt).group(1)
    if rule == "parity-break":
        return json.dumps({"class": "NEW", "confidence": 0.62,
                           "rationale": "Rate is above the hotel's public rate, which no existing class covers.",
                           "new_class": {"name": "parity-break",
                                         "description": "Rate through the platform exceeds the hotel's own public rate."}})
    cls, conf, why = RULE_TO_CLASS[rule]
    return json.dumps({"class": cls, "confidence": conf, "rationale": why, "new_class": None})
