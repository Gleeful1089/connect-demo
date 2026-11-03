"""Triage queue: priority, class-level playbook fixes, and human decisions with an audit trail."""
from __future__ import annotations

import json

import db
import ontology
from triage import fixes


def _playbook(cls):
    return ontology.PLAYBOOK.get(cls, ontology.DEFAULT_PLAYBOOK)


def _exposure_points(rate_cents, avail):
    # Deterministic: one point per $500 of rate x availability, capped at 20.
    return min(20, (rate_cents * avail) // 50000)


def build_queue(conn) -> list[dict]:
    items = []
    recs = {r["id"]: r for r in conn.execute("SELECT * FROM records")}
    for m in conn.execute("SELECT * FROM mappings WHERE status='review'"):
        r = recs[m["record_id"]]
        pts = 20 + round((1 - m["confidence"]) * 30) + _exposure_points(r["rate_cents"], r["avail"])
        items.append({
            "item_id": f"map:{m['record_id']}", "kind": "mapping", "record_id": m["record_id"], "priority": pts,
            "title": f"Review mapping, {r['room_key']} / {r['plan_key']}",
            "proposed": json.loads(m["final_json"] or m["proposed_json"]), "confidence": m["confidence"],
            "model_version": m["model_version"], "provenance": m["provenance"],
            "fix": "Confirm or correct the proposed canonical fields.", "note": m["parse_note"] or "",
            "hotel": r["hotel_name"]})
    for a in conn.execute("SELECT * FROM anomalies WHERE status='open'"):
        r = recs[a["record_id"]]
        cls = a["class"]
        fix, sev, _ = _playbook(cls)
        pts = sev * 10 + _exposure_points(r["rate_cents"], r["avail"]) + (0 if a["class_confidence"] >= 0.8 else 5)
        taxo = conn.execute("SELECT status FROM taxonomy WHERE name=?", (cls,)).fetchone()
        items.append({
            "item_id": f"anom:{a['id']}", "kind": "anomaly", "record_id": a["record_id"], "priority": pts,
            "title": f"{cls or 'unclassified'}, {r['room_key']} / {r['plan_key']}",
            "proposed": {"class": cls}, "confidence": a["class_confidence"], "model_version": a["model_version"],
            "provenance": a["provenance"], "fix": fix, "rule": a["rule"], "evidence": json.loads(a["evidence_json"]),
            "rationale": a["rationale"], "hotel": r["hotel_name"],
            "new_class_pending": bool(taxo and taxo["status"] == "proposed"),
            "fix_preview": fixes.preview(conn, a)})
    return sorted(items, key=lambda i: (-i["priority"], i["item_id"]))


def decide(conn, item_id: str, action: str, override: dict | None = None, note: str = "", actor: str = "reviewer"):
    if action not in ("approve", "override"):
        raise ValueError("action must be approve or override")
    kind, ident = item_id.split(":", 1)
    if kind == "map":
        m = conn.execute("SELECT * FROM mappings WHERE record_id=?", (ident,)).fetchone()
        if m is None or m["status"] != "review":
            raise ValueError("mapping not awaiting review")
        proposed = json.loads(m["proposed_json"])
        current = json.loads(m["final_json"] or m["proposed_json"])
        if action == "override":
            if not override:
                raise ValueError("pick at least one field to correct (or use Approve)")
            final = {**current, **override}
            for f, allowed in ontology.ALLOWED.items():
                if f in override and override[f] not in allowed:
                    raise ValueError(f"{f}={override[f]!r} not in ontology")
        else:
            final = current
        conn.execute("UPDATE mappings SET status=?, final_json=? WHERE record_id=?",
                     ("confirmed" if action == "approve" else "overridden", json.dumps(final), ident))
        db.audit(conn, item_id, "mapping", m["model_version"], m["confidence"], proposed, action, final, note, actor)
    elif kind == "anom":
        a = conn.execute("SELECT * FROM anomalies WHERE id=?", (int(ident),)).fetchone()
        if a is None or a["status"] != "open":
            raise ValueError("anomaly not open")
        final_cls = a["class"]
        new_status = "resolved"
        if action == "override":
            final_cls = (override or {}).get("class") or None
            if final_cls is None:
                # Override with no class: the human rejects the triage. Record what it said and that it was overridden.
                new_status = "overridden"
            else:
                ok = conn.execute("SELECT 1 FROM taxonomy WHERE name=? AND status='approved'", (final_cls,)).fetchone()
                if not ok:
                    raise ValueError(f"class {final_cls!r} is not an approved taxonomy class")
        else:
            taxo = conn.execute("SELECT status FROM taxonomy WHERE name=?", (final_cls,)).fetchone()
            if final_cls is None or (taxo and taxo["status"] == "proposed"):
                raise ValueError("class is unclassified or a proposed new class; approve the class or override it first")
        conn.execute("UPDATE anomalies SET status=?, final_class=? WHERE id=?", (new_status, final_cls, int(ident)))
        final = {"class": final_cls, "fix": _playbook(final_cls)[0]} if final_cls else {"class": None, "overridden": True}
        db.audit(conn, item_id, "anomaly", a["model_version"], a["class_confidence"], {"class": a["class"]},
                 action, final, note, actor)
    else:
        raise ValueError("unknown item")
    conn.commit()


def approve_new_class(conn, name: str, approve: bool = True, actor: str = "reviewer"):
    row = conn.execute("SELECT * FROM taxonomy WHERE name=? AND status='proposed'", (name,)).fetchone()
    if row is None:
        raise ValueError("no such proposed class")
    if approve:
        conn.execute("UPDATE taxonomy SET status='approved' WHERE name=?", (name,))
    else:
        conn.execute("UPDATE taxonomy SET status='rejected' WHERE name=?", (name,))
        conn.execute("UPDATE anomalies SET class=NULL WHERE class=? AND status='open'", (name,))
    db.audit(conn, f"class:{name}", "taxonomy", row["proposed_by"], None, {"name": name, "description": row["description"]},
             "approve" if approve else "reject", {"status": "approved" if approve else "rejected"}, "", actor)
    conn.commit()
