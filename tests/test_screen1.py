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


# ---- fix action and override semantics ----
def _anom(conn, record_id):
    return next(i for i in queue.build_queue(conn) if i["kind"] == "anomaly" and i["record_id"] == record_id)


def test_only_three_classes_have_a_fix(conn):
    previews = {i["record_id"]: i["fix_preview"] for i in queue.build_queue(conn) if i["kind"] == "anomaly"}
    assert previews["R03"] == "Move plan FAM-HB from room DLX-KG-OV to room FAM-2Q-GD"
    assert previews["R08"] == "Suppress R08 (exact duplicate of R07); R07 stays listed"
    assert previews["R04"].startswith("Register field alias 'price' as 'rate' for Harbor Grand")
    assert {k for k, v in previews.items() if v} == {"R03", "R04", "R08"}


def test_apply_fix_moves_the_plan_and_writes_audit_before_after(conn):
    from triage import fixes
    item = _anom(conn, "R03")
    out = fixes.apply_fix(conn, int(item["item_id"].split(":")[1]))
    rec = conn.execute("SELECT * FROM records WHERE id='R03'").fetchone()
    assert rec["room_key"] == "FAM-2Q-GD" and json.loads(rec["view_json"])["room_code"] == "FAM-2Q-GD"
    assert out["before"]["room_key"] == "DLX-KG-OV" and out["after"]["room_key"] == "FAM-2Q-GD"
    assert out["after"]["room_fields"]["max_occupancy"] == 5 and out["after"]["room_fields"]["category"] == "family"
    audit_row = conn.execute("SELECT * FROM audit WHERE item_id=?", (item["item_id"],)).fetchone()
    assert audit_row["human_action"] == "approve_and_apply_fix" and "DLX-KG-OV" in audit_row["final"]
    m = conn.execute("SELECT * FROM mappings WHERE record_id='R03'").fetchone()
    assert m["status"] == "review"                      # room attributes changed, so a human re-confirms


def test_fix_never_touches_the_model_proposal_or_the_eval(conn):
    from triage import fixes
    before_prop = conn.execute("SELECT proposed_json FROM mappings WHERE record_id='R03'").fetchone()[0]
    before_eval = heldout.evaluate(conn, 0.85)["current"]
    fixes.apply_fix(conn, int(_anom(conn, "R03")["item_id"].split(":")[1]))
    assert conn.execute("SELECT proposed_json FROM mappings WHERE record_id='R03'").fetchone()[0] == before_prop
    assert heldout.evaluate(conn, 0.85)["current"] == before_eval


def test_threshold_change_does_not_undo_a_fixed_mapping(conn):
    from triage import fixes
    fixes.apply_fix(conn, int(_anom(conn, "R03")["item_id"].split(":")[1]))
    pipeline.set_threshold(conn, 0.0)
    assert conn.execute("SELECT status FROM mappings WHERE record_id='R03'").fetchone()[0] == "review"


def test_fixed_record_becomes_searchable_once_remapped_and_confirmed(conn):
    from buyer import muse
    from search import connect_search as cs
    from triage import fixes
    fixes.apply_fix(conn, int(_anom(conn, "R03")["item_id"].split(":")[1]))
    assert "R03" not in [o["offer_id"] for o in cs.search(conn, muse.STRUCTURED_REQUEST)["offers"]]  # mapping unconfirmed
    queue.decide(conn, "map:R03", "approve")
    offers = cs.search(conn, muse.STRUCTURED_REQUEST)["offers"]
    o = next(o for o in offers if o["offer_id"] == "R03")
    assert o["room"]["max_occupancy"] == 5 and o["rate_plan"]["meal_plan"] == "half_board"


def test_fix_cannot_run_twice_or_on_unfixable_classes(conn):
    from triage import fixes
    aid = int(_anom(conn, "R03")["item_id"].split(":")[1])
    fixes.apply_fix(conn, aid)
    with pytest.raises(ValueError):
        fixes.apply_fix(conn, aid)
    with pytest.raises(ValueError):
        fixes.apply_fix(conn, int(_anom(conn, "R10")["item_id"].split(":")[1]))


def test_fixes_module_has_no_llm_imports():
    assert not _imports(ROOT / "triage" / "fixes.py") & {"llm", "anthropic", "mapping", "classify"}


def test_override_without_class_records_triage_and_override(conn):
    item = _anom(conn, "R10")
    queue.decide(conn, item["item_id"], "override", None, note="not actually stale")
    row = conn.execute("SELECT * FROM audit WHERE item_id=?", (item["item_id"],)).fetchone()
    assert json.loads(row["proposed"]) == {"class": "stale-availability"} and row["human_action"] == "override"
    assert json.loads(row["final"]) == {"class": None, "overridden": True} and row["model_confidence"] is not None
    a = conn.execute("SELECT status, final_class FROM anomalies WHERE id=?", (int(item["item_id"].split(":")[1]),)).fetchone()
    assert (a["status"], a["final_class"]) == ("overridden", None)
    assert item["item_id"] not in [i["item_id"] for i in queue.build_queue(conn)]


def test_mapping_override_with_no_fields_is_rejected_clearly(conn):
    item = next(i for i in queue.build_queue(conn) if i["kind"] == "mapping")
    with pytest.raises(ValueError, match="pick at least one field"):
        queue.decide(conn, item["item_id"], "override", None)


# ---- duplicate, drift, undo ----
def _aid(conn, rid):
    return int(_anom(conn, rid)["item_id"].split(":")[1])


def test_duplicate_fix_suppresses_the_copy_and_keeps_the_original(conn):
    from buyer import muse
    from search import connect_search as cs
    from triage import fixes
    fixes.apply_fix(conn, _aid(conn, "R08"))
    assert conn.execute("SELECT suppressed_reason FROM records WHERE id='R08'").fetchone()[0] == "duplicate of R07"
    assert conn.execute("SELECT suppressed_reason FROM records WHERE id='R07'").fetchone()[0] is None
    r = cs.search(conn, muse.STRUCTURED_REQUEST)
    ids = [o["offer_id"] for o in r["offers"]]
    assert "R08" not in ids and "R07" in ids
    assert any(e["record_id"] == "R08" and e["reason"] == "suppressed: duplicate of R07" for e in r["excluded"])


def test_duplicate_fix_refuses_when_listings_diverged(conn):
    from triage import fixes
    conn.execute("UPDATE records SET rate_cents=rate_cents+100 WHERE id='R08'")
    with pytest.raises(ValueError, match="no longer match"):
        fixes.apply_fix(conn, _aid(conn, "R08"))


def test_drift_fix_registers_alias_and_clears_the_flag(conn):
    from triage import fixes
    aid = _aid(conn, "R04")
    out = fixes.apply_fix(conn, aid)
    assert out["alias"] == {"price": "rate"} and out["records_cleared"] == ["R04"]
    assert fixes.registered_aliases(conn, "HG1", "A") == {"price": "rate"}
    assert json.loads(conn.execute("SELECT extra_json FROM records WHERE id='R04'").fetchone()[0])["drift"] == {"unexpected": [], "missing": []}
    assert conn.execute("SELECT status FROM anomalies WHERE id=?", (aid,)).fetchone()[0] == "fixed"
    audit_row = conn.execute("SELECT * FROM audit WHERE item_id=?", (f"anom:{aid}",)).fetchone()
    assert audit_row["human_action"] == "approve_and_apply_fix"


def test_registered_alias_means_a_resync_no_longer_reports_drift():
    before = [a for a in rules.detect_all(ingest.load_all()) if a["rule"] == "schema-drift"]
    after = [a for a in rules.detect_all(ingest.load_all(registered_a={"price": "rate"})) if a["rule"] == "schema-drift"]
    assert len(before) == 1 and after == []
    assert next(r for r in ingest.load_all(registered_a={"price": "rate"}) if r["id"] == "R04")["rate_cents"] == 21500


def test_drift_fix_refuses_ambiguous_drift(conn):
    from triage import fixes
    ev = {"unexpected": ["price", "cost"], "missing": ["rate"]}
    conn.execute("UPDATE anomalies SET evidence_json=? WHERE record_id='R04'", (json.dumps(ev),))
    with pytest.raises(ValueError, match="not a single renamed field"):
        fixes.apply_fix(conn, _aid(conn, "R04"))


def test_undo_reverts_state_and_appends_instead_of_deleting(conn):
    item = _anom(conn, "R03")
    queue.decide(conn, item["item_id"], "approve")
    first = conn.execute("SELECT id FROM audit WHERE item_id=?", (item["item_id"],)).fetchone()[0]
    queue.undo_decision(conn, first)
    rows = conn.execute("SELECT human_action FROM audit WHERE item_id=? ORDER BY id", (item["item_id"],)).fetchall()
    assert [r[0] for r in rows] == ["approve", "undo"]
    assert item["item_id"] in [i["item_id"] for i in queue.build_queue(conn)]
    queue.decide(conn, item["item_id"], "approve")   # can be decided again


def test_undo_refuses_applied_fixes_and_superseded_decisions(conn):
    from triage import fixes
    fixes.apply_fix(conn, _aid(conn, "R03"))
    fix_row = conn.execute("SELECT id FROM audit WHERE human_action='approve_and_apply_fix'").fetchone()[0]
    with pytest.raises(ValueError):
        queue.undo_decision(conn, fix_row)


def test_old_database_without_new_column_is_migrated(tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "old.db")
    old = sqlite3.connect(config.DB_PATH)
    old.execute("CREATE TABLE records(id TEXT PRIMARY KEY, hotel_id TEXT, hotel_name TEXT, currency TEXT, city TEXT, source_format TEXT, room_key TEXT, plan_key TEXT, rate_cents INTEGER, public_cents INTEGER, avail INTEGER, updated_at TEXT, view_json TEXT, extra_json TEXT, heldout INTEGER DEFAULT 0)")
    old.commit(); old.close()
    c = db.connect()
    assert "suppressed_reason" in {r[1] for r in c.execute("PRAGMA table_info(records)")}
