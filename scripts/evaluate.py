"""Development tool, not part of the app: score the model's mapping proposals on the 8 held-out records.

Run: python scripts/evaluate.py
Builds a throwaway database from the recorded fixtures and prints precision and recall at each threshold.
The answer key is read only by evaluation/heldout.py and never reaches a prompt.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pipeline
from evaluation import heldout

with tempfile.TemporaryDirectory() as d:
    conn = pipeline.run(path=Path(d) / "eval.db")
    ev = heldout.evaluate(conn, 0.85)
    print(f"held-out records: {ev['n_heldout']} | model: {', '.join(ev['model_versions'])} | provenance: {', '.join(ev['provenance'])}")
    print("correct = all 7 canonical fields match. precision = correct among auto-confirmed; recall = correct and auto-confirmed over all correct.")
    print(f"{'threshold':>9} {'auto':>6} {'precision':>10} {'recall':>8}")
    for c in ev["curve"]:
        p = "n/a" if c["precision"] is None else f"{c['precision']:.0%}"
        print(f"{c['threshold']:>9.2f} {c['n_auto']:>3}/{c['n_total']:<2} {p:>10} {c['recall']:>8.0%}")
    for r in ev["records"]:
        if not r["correct"]:
            print("wrong:", r["record_id"], [(f, r["proposed"][f], r["truth"][f]) for f in r["wrong_fields"]])
    cl = ev["classification"]
    print(f"anomaly classification: {cl['correct']}/{cl['expected']} correct")
