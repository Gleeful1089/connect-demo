"""Onboarding pipeline: ingest, map (model), detect (rules), classify (model). Synthetic data. Demo only."""
from __future__ import annotations

import json

import config
import db
import ingest
import ontology
from detect import rules
from mapping import mapper
from triage import classify, queue


def run(threshold: float | None = None):
    conn = db.reset()
    if threshold is None:
        threshold = config.CONFIDENCE_THRESHOLD
    db.set_setting(conn, "threshold", threshold)
    records = ingest.load_all()
    for r in records:
        conn.execute(
            "INSERT INTO records(id,hotel_id,hotel_name,currency,city,source_format,room_key,plan_key,rate_cents,"
            "public_cents,avail,updated_at,view_json,extra_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r["id"], r["hotel_id"], r["hotel_name"], r["currency"], r["city"], r["source_format"], r["room_key"],
             r["plan_key"], r["rate_cents"], r["public_cents"], r["avail"], r["updated_at"],
             json.dumps(r["view"]), json.dumps(r["extra"])))
    for r in records:
        mapping, conf, note, res = mapper.map_record(r["view"])
        db.log_call(conn, "map_record", res)
        status = "auto_confirmed" if conf >= threshold else "review"
        conn.execute("INSERT INTO mappings VALUES(?,?,?,?,?,?,?,?)",
                     (r["id"], json.dumps(mapping), conf, res.model, res.provenance, status, None, note))
    taxonomy = {n: d for n, d in ontology.TAXONOMY.items()}
    by_id = {r["id"]: r for r in records}
    for a in rules.detect_all(records):
        r = by_id[a["record_id"]]
        tags = {"source_format": r["source_format"], "hotel_id": r["hotel_id"]}
        cls, conf, why, new, res = classify.classify(a, tags, taxonomy)
        db.log_call(conn, "classify_anomaly", res)
        if new:
            conn.execute("INSERT OR IGNORE INTO taxonomy VALUES(?,?,?,?)", (new["name"], new.get("description", ""), "proposed", res.model))
        conn.execute(
            "INSERT INTO anomalies(record_id,rule,evidence_json,class,class_confidence,rationale,model_version,provenance) VALUES(?,?,?,?,?,?,?,?)",
            (a["record_id"], a["rule"], json.dumps(a["evidence"]), cls, conf, why, res.model, res.provenance))
    conn.commit()
    return conn


def set_threshold(conn, threshold: float):
    """Re-split mappings not yet decided by a human."""
    db.set_setting(conn, "threshold", threshold)
    conn.execute("UPDATE mappings SET status='auto_confirmed' WHERE status IN('review','auto_confirmed') AND confidence>=?", (threshold,))
    conn.execute("UPDATE mappings SET status='review' WHERE status IN('review','auto_confirmed') AND confidence<?", (threshold,))
    conn.commit()
