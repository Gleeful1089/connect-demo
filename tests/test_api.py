from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent


def test_api_endpoints(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
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


def test_screen_2_is_gone(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gone.db")
    import api.main as main
    main._conn = None
    c = TestClient(main.app)
    for path in ("/api/muse", "/api/connect/search", "/api/demo/approve-all-review"):
        assert c.get(path).status_code in (404, 405)
    for name in ("index.html", "app.js"):
        assert "screen 2" not in (ROOT / "web" / name).read_text().lower()
    for d in ("money", "search", "buyer"):
        assert not (ROOT / d).exists()
    main._conn = None


def test_evaluation_lives_on_its_own_tab():
    html = (ROOT / "web" / "index.html").read_text()
    s1 = html[html.index('<div id="s1">'):html.index('<div id="s2"')]
    s2 = html[html.index('<div id="s2"'):]
    assert 'id="eval"' not in s1 and 'id="eval"' in s2
    assert "Workbench" in html and "Evaluation" in html


def test_concurrent_requests_do_not_corrupt_the_shared_connection(tmp_path, monkeypatch):
    """The browser fires several requests at once on page load; they share one SQLite connection."""
    from concurrent.futures import ThreadPoolExecutor
    import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "conc.db")
    import api.main as main
    main._conn = None
    c = TestClient(main.app)
    c.get("/api/meta")   # build the database once
    paths = ["/api/queue", "/api/records", "/api/eval?threshold=0.85", "/api/audit", "/api/meta"] * 30
    with ThreadPoolExecutor(max_workers=10) as ex:
        codes = list(ex.map(lambda p: c.get(p).status_code, paths))
    assert set(codes) == {200}, {x: codes.count(x) for x in set(codes)}
    main._conn = None
