import ast
import json
import re
from pathlib import Path

import pytest

import config
import db
import ingest
import llm
import pipeline
from detect import rules
from evaluation import heldout
from mapping import mapper
from triage import queue

ROOT = Path(__file__).resolve().parent.parent


def _imports(path):
    tree = ast.parse(path.read_text())
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            names |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            names.add(n.module.split(".")[0])
    return names


def test_detection_has_no_llm_imports():
    for p in (ROOT / "detect").glob("*.py"):
        assert not _imports(p) & {"llm", "anthropic", "mapping", "triage"}, p


def test_only_llm_module_imports_anthropic():
    offenders = [p for p in ROOT.rglob("*.py")
                 if ".venv" not in p.parts and p.name != "llm.py" and "anthropic" in _imports(p)]
    assert offenders == []


def test_heldout_labels_only_read_by_evaluation():
    readers = [p for p in ROOT.rglob("*.py")
               if ".venv" not in p.parts and "heldout_labels" in p.read_text() and p.parts[-2] not in ("evaluation", "tests", "data")]
    assert readers == [], readers


def test_prompts_contain_no_label_content():
    labels = heldout.load_labels()
    for r in ingest.load_all():
        prompt = mapper.build_prompt(r["view"])
        assert "truth" not in prompt and "expected_anomalies" not in prompt and "heldout" not in prompt.lower()
        assert "rate_cents" not in prompt and str(r["rate_cents"]) not in prompt


def test_twenty_records_two_formats_eight_heldout():
    recs = ingest.load_all()
    assert len(recs) == 20
    assert {r["source_format"] for r in recs} == {"A", "B"}
    assert len(heldout.load_labels()) == 8


def test_detectors_flag_exactly_the_planted_anomalies():
    found = {(a["record_id"], a["rule"]) for a in rules.detect_all(ingest.load_all())}
    assert found == {
        ("R03", "wrong-room-plan"), ("R04", "schema-drift"), ("R06", "iqr-outlier"), ("R08", "duplicate"),
        ("R09", "missing-cancellation"), ("R10", "stale"), ("R15", "parity-break"), ("R20", "occupancy-mismatch"),
    }


def test_threshold_splits_review_queue(conn):
    pipeline.set_threshold(conn, 0.85)
    n_auto = conn.execute("SELECT COUNT(*) FROM mappings WHERE status='auto_confirmed'").fetchone()[0]
    pipeline.set_threshold(conn, 0.99)
    n_auto_high = conn.execute("SELECT COUNT(*) FROM mappings WHERE status='auto_confirmed'").fetchone()[0]
    assert n_auto_high < n_auto
    assert conn.execute("SELECT COUNT(*) FROM mappings WHERE status='review'").fetchone()[0] == 20 - n_auto_high


def test_queue_sorted_by_priority(conn):
    q = queue.build_queue(conn)
    assert [i["priority"] for i in q] == sorted((i["priority"] for i in q), reverse=True)
    assert q[0]["kind"] == "anomaly"  # wrong-room plan has the top severity


def test_every_decision_is_audited(conn):
    q = queue.build_queue(conn)
    item = next(i for i in q if i["kind"] == "mapping")
    queue.decide(conn, item["item_id"], "override", {"prepaid": True}, note="checked with hotel")
    row = conn.execute("SELECT * FROM audit WHERE item_id=?", (item["item_id"],)).fetchone()
    assert row["human_action"] == "override" and row["model_version"] and row["model_confidence"] is not None and row["ts"]
    assert json.loads(row["final"])["prepaid"] is True


def test_override_outside_ontology_rejected(conn):
    item = next(i for i in queue.build_queue(conn) if i["kind"] == "mapping")
    with pytest.raises(ValueError):
        queue.decide(conn, item["item_id"], "override", {"view": "moon"})


def test_new_class_needs_human_approval(conn):
    parity = next(i for i in queue.build_queue(conn) if i["kind"] == "anomaly" and i["proposed"]["class"] == "parity-break")
    assert parity["new_class_pending"]
    with pytest.raises(ValueError):
        queue.decide(conn, parity["item_id"], "approve")
    queue.approve_new_class(conn, "parity-break")
    queue.decide(conn, parity["item_id"], "approve")
    assert conn.execute("SELECT status FROM taxonomy WHERE name='parity-break'").fetchone()[0] == "approved"


def test_eval_matches_manual_computation(conn):
    ev = heldout.evaluate(conn, 0.85)
    labels = heldout.load_labels()
    auto = correct = 0
    all_correct = 0
    for rid, lab in labels.items():
        m = conn.execute("SELECT * FROM mappings WHERE record_id=?", (rid,)).fetchone()
        ok = json.loads(m["proposed_json"]) == lab["truth"]
        all_correct += ok
        if m["confidence"] >= 0.85:
            auto += 1
            correct += ok
    assert ev["current"]["precision"] == correct / auto
    assert ev["current"]["recall"] == correct / all_correct


def test_eval_precision_undefined_when_nothing_auto_confirmed(conn):
    assert heldout.evaluate(conn, 1.01)["current"]["precision"] is None


def test_eval_scores_the_model_not_the_human(conn):
    before = heldout.evaluate(conn, 0.85)["current"]
    item = next(i for i in queue.build_queue(conn) if i["item_id"] == "map:R12")
    queue.decide(conn, item["item_id"], "override", {"prepaid": False})
    assert heldout.evaluate(conn, 0.85)["current"] == before


def test_fixture_miss_raises_not_invents():
    with pytest.raises(llm.FixtureMissing):
        llm.complete("map_record", "a prompt with no fixture")


def test_invalid_model_output_cannot_auto_confirm():
    mapping, conf, note = mapper.validate({"category": "palace", "bed": "king", "view": "city", "max_occupancy": 2,
                                           "meal_plan": "breakfast", "cancellation": "free_48h", "prepaid": False, "confidence": 0.99})
    assert conf <= 0.3 and "category" in note
