from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def app(tmp_path, monkeypatch):
    import config
    import sandbox
    monkeypatch.setattr(config, "SANDBOX_DIR", tmp_path / "sandboxes")
    monkeypatch.setattr(config, "MAX_SANDBOXES", 300)
    sandbox._registry.clear()
    import api.main as main
    yield main.app
    for sb in list(sandbox._registry.values()):
        if sb.conn is not None:
            sb.conn.close()
    sandbox._registry.clear()


def baseline(app):
    """Queue size of a fresh, untouched sandbox (depends on which fixtures the tests run on)."""
    return len(TestClient(app).get("/api/queue").json()["items"])


def visitor(app):
    return TestClient(app)   # each TestClient has its own cookie jar, like a separate browser


def test_new_visitor_gets_a_seeded_sandbox_and_a_cookie(app):
    c = visitor(app)
    r = c.get("/api/queue")
    assert r.status_code == 200 and len(r.json()["items"]) == baseline(app) > 0
    cookie = r.headers["set-cookie"]
    assert "connect_sid=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert c.get("/api/meta").json()["sandbox"]["id"] == c.cookies["connect_sid"][:6]


def test_two_visitors_do_not_affect_each_other(app):
    a, b = visitor(app), visitor(app)
    a.get("/api/meta"); b.get("/api/meta")
    first = a.get("/api/queue").json()["items"][0]["item_id"]
    assert a.post(f"/api/queue/{first}/decide", json={"action": "approve"}).status_code == 200
    a.post("/api/threshold", json={"threshold": 0.5})
    assert len(a.get("/api/audit").json()) == 1
    assert b.get("/api/audit").json() == []                                   # B sees no decisions
    assert first in [i["item_id"] for i in b.get("/api/queue").json()["items"]]   # and the item is still open for B
    assert b.get("/api/meta").json()["threshold"] == 0.85                      # and the threshold is B's own


def test_reset_only_resets_the_callers_sandbox(app):
    a, b = visitor(app), visitor(app)
    for c in (a, b):
        c.get("/api/meta")
        c.post(f"/api/queue/{c.get('/api/queue').json()['items'][0]['item_id']}/decide", json={"action": "approve"})
    a.post("/api/pipeline/run")
    assert a.get("/api/audit").json() == []
    assert len(b.get("/api/audit").json()) == 1


def test_state_persists_for_the_same_visitor(app):
    a = visitor(app)
    first = a.get("/api/queue").json()["items"][0]["item_id"]
    a.post(f"/api/queue/{first}/decide", json={"action": "approve"})
    assert len(a.get("/api/audit").json()) == 1 and len(a.get("/api/queue").json()["items"]) == baseline(app) - 1


def test_forged_cookie_cannot_escape_the_sandbox_directory(app, tmp_path):
    for bad in ("../../etc/passwd", "../x", "a" * 5, "x/y" + "z" * 30):
        r = TestClient(app).get("/api/meta", headers={"cookie": f"connect_sid={bad}"})
        assert r.status_code == 200
        assert f"connect_sid={bad}" not in r.headers["set-cookie"] and "connect_sid=" in r.headers["set-cookie"]   # replaced
    files = {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.db")}
    assert all(f.startswith("sandboxes/") and f.count("/") == 1 for f in files)


def test_sandbox_is_rebuilt_if_its_file_disappears(app, tmp_path):
    c = visitor(app)
    c.get("/api/meta")
    for f in (tmp_path / "sandboxes").glob("*.db"):
        f.unlink()                                     # simulates a redeploy that wiped the disk
    assert len(c.get("/api/queue").json()["items"]) == baseline(app)


def test_surplus_sandboxes_are_evicted_oldest_first(app, tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "MAX_SANDBOXES", 3)
    import os, time
    clients = []
    for i in range(5):
        c = visitor(app)
        c.get("/api/meta")
        sid = c.cookies["connect_sid"]
        os.utime(tmp_path / "sandboxes" / f"{sid}.db", (time.time() + i, time.time() + i))   # strictly increasing recency
        clients.append((c, sid))
    files = {p.stem for p in (tmp_path / "sandboxes").glob("*.db")}
    assert len(files) <= 3
    assert clients[-1][1] in files and clients[0][1] not in files
    assert len(clients[0][0].get("/api/queue").json()["items"]) > 0       # an evicted visitor just gets a fresh sandbox


def test_expired_sandboxes_are_removed(app, tmp_path, monkeypatch):
    import config, os, time
    old = visitor(app)
    old.get("/api/meta")
    f = next((tmp_path / "sandboxes").glob("*.db"))
    stale = time.time() - (config.SANDBOX_TTL_DAYS + 1) * 86400
    os.utime(f, (stale, stale))
    visitor(app).get("/api/meta")                      # a new visitor triggers cleanup
    assert not f.exists()


def test_concurrent_requests_in_one_sandbox_and_across_sandboxes(app):
    clients = [visitor(app) for _ in range(4)]
    for c in clients:
        c.get("/api/meta")
    paths = ["/api/queue", "/api/records", "/api/eval?threshold=0.85", "/api/audit", "/api/meta"] * 12
    jobs = [(c, p) for c in clients for p in paths]
    with ThreadPoolExecutor(max_workers=12) as ex:
        codes = list(ex.map(lambda j: j[0].get(j[1]).status_code, jobs))
    assert set(codes) == {200}, {x: codes.count(x) for x in set(codes)}


def test_health_creates_no_sandbox_and_no_cookie(app, tmp_path):
    c = visitor(app)
    r = c.get("/health")
    assert r.status_code == 200 and "set-cookie" not in r.headers
    assert not (tmp_path / "sandboxes").exists() or not list((tmp_path / "sandboxes").glob("*.db"))


def test_building_a_sandbox_makes_no_live_model_calls(app, monkeypatch):
    import llm
    monkeypatch.setattr(llm, "_live", lambda *a, **k: pytest.fail("live model call"))
    assert visitor(app).get("/api/queue").status_code == 200


def test_app_endpoints_and_evaluation(app):
    c = visitor(app)
    assert c.get("/api/meta").json()["simulated"] is True
    assert c.get("/api/eval?threshold=0.85").json()["n_heldout"] == 8
    assert c.post("/api/threshold", json={"threshold": 2}).status_code == 400
    assert c.get("/").status_code == 200


def test_screen_2_is_gone(app):
    c = visitor(app)
    for path in ("/api/muse", "/api/connect/search", "/api/demo/approve-all-review"):
        assert c.get(path).status_code in (404, 405)
    for name in ("index.html", "app.js"):
        assert "screen 2" not in (ROOT / "web" / name).read_text().lower()
    for d in ("money", "search", "buyer"):
        assert not (ROOT / d).exists()


def test_evaluation_lives_on_its_own_tab():
    html = (ROOT / "web" / "index.html").read_text()
    s1 = html[html.index('<div id="s1">'):html.index('<div id="s2"')]
    s2 = html[html.index('<div id="s2"'):]
    assert 'id="eval"' not in s1 and 'id="eval"' in s2
