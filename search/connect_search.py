"""Connect's deterministic search over confirmed, mapped inventory. No LLM, no natural language."""
from __future__ import annotations

import json
from datetime import date

import ontology
from money import pricing

MEAL_RANK = {"room_only": 0, "breakfast": 1, "half_board": 2}
REQUIRED = {"destination", "check_in", "check_out", "occupancy", "budget", "buyer_currency"}


def _nights(req):
    n = (date.fromisoformat(req["check_out"]) - date.fromisoformat(req["check_in"])).days
    if n < 1:
        raise ValueError("check_out must be after check_in")
    return n


def effective_mapping(row):
    return json.loads(row["final_json"]) if row["final_json"] else json.loads(row["proposed_json"])


def search(conn, req: dict) -> dict:
    missing = REQUIRED - set(req)
    if missing:
        raise ValueError(f"missing fields: {sorted(missing)}")
    nights = _nights(req)
    party = req["occupancy"]["adults"] + req["occupancy"].get("children", 0)
    prefs = req.get("preferences", {})
    offers, excluded = [], []
    for r in conn.execute("SELECT * FROM records ORDER BY id"):
        m = conn.execute("SELECT * FROM mappings WHERE record_id=?", (r["id"],)).fetchone()
        why = None
        if r["city"] != req["destination"]:
            continue
        if m["status"] == "review":
            why = "mapping not confirmed"
        else:
            for a in conn.execute("SELECT * FROM anomalies WHERE record_id=?", (r["id"],)):
                cls = a["final_class"] or a["class"]
                blocks = ontology.PLAYBOOK.get(cls, ontology.DEFAULT_PLAYBOOK)[2]
                if a["status"] == "open" and (blocks or cls is None):
                    why = f"open anomaly: {cls or 'unclassified'}"
                elif a["status"] == "resolved" and cls in ontology.SUPPRESS_ON_RESOLVE:
                    why = f"suppressed: {cls}"
        if why is None and r["avail"] < 1:
            why = "no availability"
        mp = effective_mapping(m) if m["status"] != "review" else None
        if why is None and (mp["max_occupancy"] or 0) < party:
            why = f"sleeps {mp['max_occupancy']}, party is {party}"
        if why is not None:
            excluded.append({"record_id": r["id"], "room": r["room_key"], "reason": why})
            continue
        q = pricing.quote_stay(r["rate_cents"], nights, r["currency"], req["buyer_currency"])
        per_night = -(-q["total_cents"] // nights)
        if req["budget"]["currency"] == req["buyer_currency"] and per_night > req["budget"]["max_per_night_cents"]:
            excluded.append({"record_id": r["id"], "room": r["room_key"], "reason": "over budget"})
            continue
        pts, reasons = 0, []
        if MEAL_RANK[mp["meal_plan"]] >= MEAL_RANK[prefs.get("meal_plan_min", "room_only")] and prefs.get("meal_plan_min"):
            pts += 1; reasons.append("meal plan meets preference")
        if prefs.get("free_cancellation") and mp["cancellation"] in ("free_24h", "free_48h"):
            pts += 1; reasons.append("free cancellation")
        offers.append({
            "offer_id": r["id"], "hotel": r["hotel_name"], "room": {k: mp[k] for k in ("category", "bed", "view", "max_occupancy")},
            "rate_plan": {k: mp[k] for k in ("meal_plan", "cancellation", "prepaid")},
            "cancellation_terms": mp["cancellation"], "price": q, "per_night_total_cents": per_night,
            "match_points": pts, "match_reasons": reasons})
    offers.sort(key=lambda o: (-o["match_points"], o["price"]["total_cents"], o["offer_id"]))
    for i, o in enumerate(offers, start=1):
        o["rank"] = i
    return {"nights": nights, "party_size": party, "offers": offers, "excluded": excluded}
