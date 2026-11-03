"""Deterministic data fixes for anomaly classes. NO LLM: a fix is a rule applied to the data.

Each fix writes to the working data directly and records before/after in the audit table. The model's original
mapping proposal (mappings.proposed_json) is never modified, because the held-out evaluation scores it.
"""
from __future__ import annotations

import json

import db

ROOM_FIELDS = ("category", "bed", "view", "max_occupancy")


def _effective(m) -> dict:
    return json.loads(m["final_json"] or m["proposed_json"])


def _target_room(anomaly) -> str:
    applies = json.loads(anomaly["evidence_json"]).get("plan_applies_to", [])
    if len(applies) != 1:
        raise ValueError(f"cannot fix automatically: plan lists {len(applies)} eligible rooms")
    return applies[0]


def preview(conn, anomaly) -> str | None:
    """Short description of what the fix would do, or None if this anomaly has no automatic fix."""
    if (anomaly["class"] if "class" in anomaly.keys() else None) != "rate-plan-on-wrong-room":
        return None
    rec = conn.execute("SELECT * FROM records WHERE id=?", (anomaly["record_id"],)).fetchone()
    try:
        return f"Move plan {rec['plan_key']} from room {rec['room_key']} to room {_target_room(anomaly)}"
    except ValueError:
        return None


def apply_fix(conn, anomaly_id: int, actor: str = "reviewer", note: str = "") -> dict:
    a = conn.execute("SELECT * FROM anomalies WHERE id=?", (anomaly_id,)).fetchone()
    if a is None or a["status"] != "open":
        raise ValueError("anomaly not open")
    if a["class"] != "rate-plan-on-wrong-room":
        raise ValueError(f"no automatic fix for class {a['class']!r}")
    target = _target_room(a)
    rec = conn.execute("SELECT * FROM records WHERE id=?", (a["record_id"],)).fetchone()
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
    conn.execute("UPDATE anomalies SET status='fixed', final_class=class WHERE id=?", (anomaly_id,))
    after = {"room_key": target, "room_fields": {f: new[f] for f in ROOM_FIELDS}}
    db.audit(conn, f"anom:{anomaly_id}", "anomaly", a["model_version"], a["class_confidence"], {"class": a["class"]},
             "approve_and_apply_fix", {"record_id": rec["id"], "before": before, "after": after}, note, actor)
    conn.commit()
    return {"record_id": rec["id"], "before": before, "after": after}
