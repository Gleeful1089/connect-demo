import ast
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import pipeline
from buyer import muse
from search import connect_search as cs
from triage import queue

ROOT = Path(__file__).resolve().parent.parent


def _imports(path):
    names = set()
    for n in ast.walk(ast.parse(path.read_text())):
        if isinstance(n, ast.Import):
            names |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            names.add(n.module.split(".")[0])
    return names


def test_connect_path_has_no_llm_imports():
    for p in [*(ROOT / "search").glob("*.py"), ROOT / "api" / "screen2.py", *(ROOT / "money").glob("*.py")]:
        assert not _imports(p) & {"llm", "anthropic", "openai", "mapping"}, p


def test_connect_search_takes_structured_json_only(conn):
    with pytest.raises(ValueError):
        cs.search(conn, {"text": muse.REQUEST_TEXT})


def test_search_is_deterministic(conn):
    a = cs.search(conn, muse.STRUCTURED_REQUEST)
    b = cs.search(conn, muse.STRUCTURED_REQUEST)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_family_search_ranks_and_excludes(conn):
    r = cs.search(conn, muse.STRUCTURED_REQUEST)
    ids = [o["offer_id"] for o in r["offers"]]
    assert ids == ["R18", "R14", "R07"]                      # equal match points, then cheapest total first
    reasons = {e["record_id"]: e["reason"] for e in r["excluded"]}
    assert reasons["R08"].startswith("open anomaly: duplicate-availability")
    assert reasons["R03"].startswith("open anomaly: rate-plan-on-wrong-room")
    assert reasons["R09"] == "mapping not confirmed"


def test_unconfirmed_mappings_never_surface(conn):
    pipeline.set_threshold(conn, 1.01)   # nothing auto-confirms
    assert cs.search(conn, muse.STRUCTURED_REQUEST)["offers"] == []


def test_resolved_duplicate_stays_suppressed(conn):
    item = next(i for i in queue.build_queue(conn) if i["record_id"] == "R08" and i["kind"] == "anomaly")
    queue.decide(conn, item["item_id"], "approve")
    r = cs.search(conn, muse.STRUCTURED_REQUEST)
    assert "R08" not in [o["offer_id"] for o in r["offers"]]
    assert any(e["record_id"] == "R08" and e["reason"].startswith("suppressed") for e in r["excluded"])


def test_cross_currency_offer_itemizes_fx(conn):
    o = next(o for o in cs.search(conn, muse.STRUCTURED_REQUEST)["offers"] if o["offer_id"] == "R18")
    assert [l["kind"] for l in o["price"]["lines"]] == ["contracted", "converted", "fx_margin", "total"]
    assert o["price"]["currency"] == "USD" and o["cancellation_terms"] == "free_48h"


def test_over_budget_excluded(conn):
    req = {**muse.STRUCTURED_REQUEST, "budget": {"currency": "USD", "max_per_night_cents": 30000}}
    r = cs.search(conn, req)
    assert r["offers"] == [] and any(e["reason"] == "over budget" for e in r["excluded"])


def test_api_booking_flow(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    import api.main as main
    main._conn = None
    client = TestClient(main.app)
    assert client.get("/api/muse").json()["parsing_done_by"].startswith("BUYER AGENT")
    s = client.post("/api/connect/search", json=muse.STRUCTURED_REQUEST).json()
    assert s["offers"]
    for scenario, fee in [("completed", 1680), ("cancelled_no_charge", 0)]:
        b = client.post("/api/connect/book", json={"offer_id": "R18", "request": muse.STRUCTURED_REQUEST, "scenario": scenario}).json()
        assert b["statement"]["fee"]["fee_cents"] == fee
    b = client.post("/api/connect/book", json={"offer_id": "R18", "request": muse.STRUCTURED_REQUEST, "scenario": "cancelled_retained"}).json()
    assert b["statement"]["fee"]["base_cents"] == 28000
    assert client.post("/api/connect/book", json={"offer_id": "R09", "request": muse.STRUCTURED_REQUEST}).status_code == 400
    main._conn = None


def test_api_screen1_endpoints(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api2.db")
    import api.main as main
    main._conn = None
    c = TestClient(main.app)
    assert c.get("/api/meta").json()["simulated"] is True
    q = c.get("/api/queue").json()["items"]
    assert q and c.post(f"/api/queue/{q[0]['item_id']}/decide", json={"action": "approve"}).status_code in (200, 400)
    assert c.get("/api/eval?threshold=0.85").json()["n_heldout"] == 8
    assert c.post("/api/threshold", json={"threshold": 2}).status_code == 400
    assert c.get("/").status_code == 200
    main._conn = None
