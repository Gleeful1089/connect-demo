"""Deterministic data fixes for anomaly classes. NO LLM: a fix is a rule applied to the data.

Each fix writes to the working data directly and records before/after in the audit table. The model's original
mapping proposal (mappings.proposed_json) is never modified, because the held-out evaluation scores it.
Fixes: rate-plan-on-wrong-room, duplicate-availability, schema-drift.
"""
from __future__ import annotations

import json

import db

ROOM_FIELDS = ("category", "bed", "view", "max_occupancy")


def _effective(m) -> dict:
    return json.loads(m["final_json"] or m["proposed_json"])


def _record(conn, rid):
    return conn.execute("SELECT * FROM records WHERE id=?", (rid,)).fetchone()


# ---------- rate-plan-on-wrong-room ----------
def _wrong_room_target(a) -> str:
    applies = json.loads(a["evidence_json"]).get("plan_applies_to", [])
    if len(applies) != 1:
        raise ValueError(f"cannot fix automatically: plan lists {len(applies)} eligible rooms")
    return applies[0]


def _preview_wrong_room(conn, a):
    rec = _record(conn, a["record_id"])
    return f"Move plan {rec['plan_key']} from room {rec['room_key']} to room {_wrong_room_target(a)}"


def _apply_wrong_room(conn, a, actor, note):
    target = _wrong_room_target(a)
    rec = _record(conn, a["record_id"])
    sibling = conn.execute(
        "SELECT * FROM records WHERE hotel_id=? AND room_key=? AND id!=? ORDER BY id LIMIT 1",
        (rec["hotel_id"], target, rec["id"])).fetchone()
    if sibling is None:
        raise ValueError(f"cannot fix automatically: room {target} has no other listing to take room attributes from")
    sib_map = conn.execute("SELECT * FROM mappings WHERE record_id=?", (sibling["id"],)).fetchone()
    mapping = conn.execute("SELECT * FROM mappings WHERE record_id=?", (rec["id"],)).fetchone()
    old = _effective(mapping)
    new = {**old, **{f: _effective(sib_map)[f] for f in ROOM_FIELDS}}
    view = json.loads(rec["view_json"]); extra = json.loads(rec["extra_json"])
    before = {"room_key": rec["room_key"], "room_fields": {f: old[f] for f in ROOM_FIELDS}}
    view["room_code"] = target
    extra["max_occ"] = json.loads(sibling["extra_json"]).get("max_occ")
    conn.execute("UPDATE records SET room_key=?, view_json=?, extra_json=? WHERE id=?",
                 (target, json.dumps(view), json.dumps(extra), rec["id"]))
    # Room attributes changed, so a human must re-confirm the mapping. proposed_json stays as the model wrote it.
    conn.execute("UPDATE mappings SET final_json=?, status='review', parse_note=? WHERE record_id=?",
                 (json.dumps(new), f"room reassigned to {target} by fix; room attributes copied from {sibling['id']}; confirm",
                  rec["id"]))
    conn.execute("UPDATE anomalies SET status='fixed', final_class=class WHERE id=?", (a["id"],))
    after = {"room_key": target, "room_fields": {f: new[f] for f in ROOM_FIELDS}}
    db.audit(conn, f"anom:{a['id']}", "anomaly", a["model_version"], a["class_confidence"], {"class": a["class"]},
             "approve_and_apply_fix", {"record_id": rec["id"], "before": before, "after": after}, note, actor)
    return {"record_id": rec["id"], "before": before, "after": after}


# ---------- duplicate-availability ----------
def _dup_original(conn, a):
    orig_id = json.loads(a["evidence_json"]).get("duplicate_of")
    orig = _record(conn, orig_id) if orig_id else None
    if orig is None:
        raise ValueError("cannot fix automatically: the original listing is missing")
    return orig


def _preview_duplicate(conn, a):
    orig = _dup_original(conn, a)
    return f"Suppress {a['record_id']} (exact duplicate of {orig['id']}); {orig['id']} stays listed"


def _apply_duplicate(conn, a, actor, note):
    orig = _dup_original(conn, a)
    dup = _record(conn, a["record_id"])
    same = all(orig[k] == dup[k] for k in ("hotel_id", "room_key", "plan_key", "rate_cents"))
    if not same:
        raise ValueError("cannot fix automatically: the two listings no longer match")
    if orig["suppressed_reason"]:
        raise ValueError("cannot fix automatically: the original listing is itself suppressed")
    reason = f"duplicate of {orig['id']}"
    conn.execute("UPDATE records SET suppressed_reason=? WHERE id=?", (reason, dup["id"]))
    conn.execute("UPDATE anomalies SET status='fixed', final_class=class WHERE id=?", (a["id"],))
    db.audit(conn, f"anom:{a['id']}", "anomaly", a["model_version"], a["class_confidence"], {"class": a["class"]},
             "approve_and_apply_fix",
             {"record_id": dup["id"], "before": {"suppressed_reason": None}, "after": {"suppressed_reason": reason}},
             note, actor)
    return {"record_id": dup["id"], "before": {"suppressed_reason": None}, "after": {"suppressed_reason": reason}}


# ---------- schema-drift ----------
def _drift_alias(a) -> tuple[str, str]:
    ev = json.loads(a["evidence_json"])
    if len(ev.get("unexpected", [])) != 1 or len(ev.get("missing", [])) != 1:
        raise ValueError("cannot fix automatically: drift is not a single renamed field")
    return ev["unexpected"][0], ev["missing"][0]


def _preview_drift(conn, a):
    u, c = _drift_alias(a)
    rec = _record(conn, a["record_id"])
    return f"Register field alias '{u}' as '{c}' for {rec['hotel_name']} (format {rec['source_format']}) and clear the drift flag"


def _apply_drift(conn, a, actor, note):
    u, c = _drift_alias(a)
    rec = _record(conn, a["record_id"])
    conn.execute("INSERT OR REPLACE INTO connector_aliases VALUES(?,?,?,?,?)",
                 (rec["hotel_id"], rec["source_format"], u, c, db.now_iso()))
    fixed = []
    # The alias belongs to the connector, so it clears every open drift anomaly it explains.
    for other in conn.execute("SELECT * FROM anomalies WHERE class='schema-drift' AND status='open'").fetchall():
        r = _record(conn, other["record_id"])
        if r["hotel_id"] != rec["hotel_id"] or r["source_format"] != rec["source_format"]:
            continue
        ev = json.loads(other["evidence_json"])
        if u not in ev.get("unexpected", []):
            continue
        extra = json.loads(r["extra_json"])
        extra["drift"] = {"unexpected": [k for k in extra["drift"]["unexpected"] if k != u],
                          "missing": [k for k in extra["drift"]["missing"] if k != c]}
        conn.execute("UPDATE records SET extra_json=? WHERE id=?", (json.dumps(extra), r["id"]))
        conn.execute("UPDATE anomalies SET status='fixed', final_class=class WHERE id=?", (other["id"],))
        db.audit(conn, f"anom:{other['id']}", "anomaly", other["model_version"], other["class_confidence"],
                 {"class": other["class"]}, "approve_and_apply_fix",
                 {"record_id": r["id"], "before": {"drift": ev}, "after": {"alias_registered": {u: c}}}, note, actor)
        fixed.append(r["id"])
    return {"alias": {u: c}, "records_cleared": fixed}


FIXES = {
    "rate-plan-on-wrong-room": (_preview_wrong_room, _apply_wrong_room),
    "duplicate-availability": (_preview_duplicate, _apply_duplicate),
    "schema-drift": (_preview_drift, _apply_drift),
}


def preview(conn, anomaly) -> str | None:
    """Short description of what the fix would do, or None if this anomaly has no automatic fix."""
    entry = FIXES.get(anomaly["class"])
    if entry is None:
        return None
    try:
        return entry[0](conn, anomaly)
    except ValueError:
        return None


def registered_aliases(conn, hotel_id: str, source_format: str) -> dict:
    return {r["unexpected"]: r["canonical"] for r in conn.execute(
        "SELECT * FROM connector_aliases WHERE hotel_id=? AND source_format=?", (hotel_id, source_format))}


def apply_fix(conn, anomaly_id: int, actor: str = "reviewer", note: str = "") -> dict:
    a = conn.execute("SELECT * FROM anomalies WHERE id=?", (anomaly_id,)).fetchone()
    if a is None or a["status"] != "open":
        raise ValueError("anomaly not open")
    entry = FIXES.get(a["class"])
    if entry is None:
        raise ValueError(f"no automatic fix for class {a['class']!r}")
    result = entry[1](conn, a, actor, note)
    conn.commit()
    return result
