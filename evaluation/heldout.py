"""Held-out evaluation. The ONLY module allowed to read data/heldout_labels.json.

Every number shown in the UI's evaluation panel comes from here, computed on the 8 held-out records.
Definitions (n is tiny, so read them as illustrations, not statistics):
  correct   : the model's original proposal matches the label on all 7 canonical fields
  auto      : proposals with confidence >= threshold (human edits are ignored here, we score the model)
  precision : correct among auto-confirmed
  recall    : correct and auto-confirmed, over all correct proposals
"""
from __future__ import annotations

import json
from pathlib import Path

import ontology

LABELS = Path(__file__).resolve().parent.parent / "data" / "heldout_labels.json"
THRESHOLDS = [round(0.5 + 0.05 * i, 2) for i in range(11)]


def load_labels() -> dict:
    return json.loads(LABELS.read_text())


def _rows(conn):
    labels = load_labels()
    rows = []
    for rid, lab in sorted(labels.items()):
        m = conn.execute("SELECT * FROM mappings WHERE record_id=?", (rid,)).fetchone()
        if m is None:
            continue
        proposed = json.loads(m["proposed_json"])
        wrong = [f for f in ontology.FIELDS if proposed.get(f) != lab["truth"][f]]
        rows.append({"record_id": rid, "confidence": m["confidence"], "correct": not wrong, "wrong_fields": wrong,
                     "proposed": proposed, "truth": lab["truth"], "provenance": m["provenance"],
                     "model_version": m["model_version"]})
    return rows


def at_threshold(rows, t):
    auto = [r for r in rows if r["confidence"] >= t]
    tp = [r for r in auto if r["correct"]]
    total_correct = sum(r["correct"] for r in rows)
    return {
        "threshold": t, "n_auto": len(auto), "n_total": len(rows),
        "precision": (len(tp) / len(auto)) if auto else None,
        "recall": (len(tp) / total_correct) if total_correct else None,
        "coverage": len(auto) / len(rows) if rows else None,
    }


def classification_accuracy(conn):
    labels = load_labels()
    expected, hits, detail = 0, 0, []
    for rid, lab in sorted(labels.items()):
        for cls in lab["expected_anomalies"]:
            expected += 1
            got = [a["class"] for a in conn.execute("SELECT class FROM anomalies WHERE record_id=?", (rid,))]
            ok = cls in got
            hits += ok
            detail.append({"record_id": rid, "expected": cls, "got": got, "ok": ok})
    return {"expected": expected, "correct": hits, "accuracy": (hits / expected) if expected else None, "detail": detail}


def evaluate(conn, threshold: float):
    rows = _rows(conn)
    provs = sorted({r["provenance"] for r in rows})
    per_field = {f: sum(1 for r in rows if f not in r["wrong_fields"]) / len(rows) for f in ontology.FIELDS} if rows else {}
    return {
        "n_heldout": len(rows), "provenance": provs, "model_versions": sorted({r["model_version"] for r in rows}),
        "current": at_threshold(rows, threshold),
        "curve": [at_threshold(rows, t) for t in THRESHOLDS],
        "per_field_accuracy": per_field,
        "records": rows,
        "classification": classification_accuracy(conn),
    }
