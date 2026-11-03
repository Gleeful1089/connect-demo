"""Per-visitor sandboxes. No logins: a random cookie names a private SQLite file.

First visit: a fresh database is built from the recorded fixtures (no model calls, no cost). Nothing a visitor does
touches another visitor's file. Old and surplus sandboxes are evicted, least recently used first.
"""
from __future__ import annotations

import os
import re
import secrets
import threading
import time

import config
import db
import pipeline

COOKIE = "connect_sid"
_SID = re.compile(r"^[A-Za-z0-9_-]{22,43}$")   # also blocks path traversal: the sid becomes a file name
_registry: dict[str, "Sandbox"] = {}
_reg_lock = threading.Lock()


class Sandbox:
    def __init__(self):
        self.lock = threading.Lock()
        self.conn = None


def new_sid() -> str:
    return secrets.token_urlsafe(16)


def valid(sid) -> bool:
    return bool(sid and _SID.match(sid))


def path_for(sid: str):
    return config.SANDBOX_DIR / f"{sid}.db"


def get(sid: str) -> Sandbox:
    with _reg_lock:
        return _registry.setdefault(sid, Sandbox())


def _delete_files(p):
    for suffix in ("", "-wal", "-shm", "-journal"):
        f = p.with_name(p.name + suffix)
        if f.exists():
            f.unlink()


def _make_room() -> None:
    """Drop expired sandboxes, then the least recently used until there is room for one more."""
    config.SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(config.SANDBOX_DIR.glob("*.db"), key=lambda f: f.stat().st_mtime)
    cutoff = time.time() - config.SANDBOX_TTL_DAYS * 86400
    keep = [f for f in files if f.stat().st_mtime >= cutoff]
    victims = [f for f in files if f not in keep]
    while len(keep) >= config.MAX_SANDBOXES:
        victims.append(keep.pop(0))
    for f in victims:
        sid = f.stem
        with _reg_lock:
            sb = _registry.get(sid)
            if sb is not None and not sb.lock.acquire(blocking=False):
                continue                       # in use right now, leave it
            try:
                if sb is not None:
                    if sb.conn is not None:
                        sb.conn.close()
                        sb.conn = None
                    _registry.pop(sid, None)
                _delete_files(f)
            finally:
                if sb is not None:
                    sb.lock.release()


def open_conn(sid: str, sb: Sandbox):
    """Call with sb.lock held. Creates the sandbox on first use, or again if its file was evicted or lost."""
    p = path_for(sid)
    if sb.conn is not None and not p.exists():
        sb.conn.close()
        sb.conn = None
    if sb.conn is None:
        if p.exists():
            sb.conn = db.connect(p)
        else:
            _make_room()
            sb.conn = pipeline.run(path=p)
    else:
        os.utime(p)                            # recency for eviction
    return sb.conn


def reset(sid: str, sb: Sandbox):
    """Call with sb.lock held. Rebuild only this visitor's data."""
    if sb.conn is not None:
        sb.conn.close()
        sb.conn = None
    sb.conn = pipeline.run(path=path_for(sid))
    return sb.conn
