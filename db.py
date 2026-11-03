"""SQLite storage. Money is stored as integer minor units. Synthetic data. Demo only."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import config
import ontology

SCHEMA = """
CREATE TABLE IF NOT EXISTS records(
  id TEXT PRIMARY KEY, hotel_id TEXT, hotel_name TEXT, currency TEXT, city TEXT, source_format TEXT,
  room_key TEXT, plan_key TEXT, rate_cents INTEGER, public_cents INTEGER, avail INTEGER,
  updated_at TEXT, view_json TEXT, extra_json TEXT, heldout INTEGER DEFAULT 0, suppressed_reason TEXT);
CREATE TABLE IF NOT EXISTS connector_aliases(
  hotel_id TEXT, source_format TEXT, unexpected TEXT, canonical TEXT, created_at TEXT,
  PRIMARY KEY(hotel_id, source_format, unexpected));
CREATE TABLE IF NOT EXISTS mappings(
  record_id TEXT PRIMARY KEY, proposed_json TEXT, confidence REAL, model_version TEXT, provenance TEXT,
  status TEXT, final_json TEXT, parse_note TEXT);
CREATE TABLE IF NOT EXISTS anomalies(
  id INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT, rule TEXT, evidence_json TEXT,
  class TEXT, class_confidence REAL, rationale TEXT, model_version TEXT, provenance TEXT,
  status TEXT DEFAULT 'open', final_class TEXT);
CREATE TABLE IF NOT EXISTS taxonomy(name TEXT PRIMARY KEY, description TEXT, status TEXT, proposed_by TEXT);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, item_id TEXT, kind TEXT, model_version TEXT,
  model_confidence REAL, proposed TEXT, human_action TEXT, final TEXT, note TEXT, actor TEXT);
CREATE TABLE IF NOT EXISTS model_calls(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, task TEXT, model TEXT, source TEXT, provenance TEXT,
  latency_ms INTEGER, prompt_tokens INTEGER, completion_tokens INTEGER);
CREATE TABLE IF NOT EXISTS bookings(
  id TEXT PRIMARY KEY, ts TEXT, record_id TEXT, scenario TEXT, payload_json TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    if "suppressed_reason" not in {r[1] for r in conn.execute("PRAGMA table_info(records)")}:
        conn.execute("ALTER TABLE records ADD COLUMN suppressed_reason TEXT")   # databases created before this column
        conn.commit()
    return conn


def reset() -> sqlite3.Connection:
    if config.DB_PATH.exists():
        config.DB_PATH.unlink()
    conn = connect()
    for name, desc in ontology.TAXONOMY.items():
        conn.execute("INSERT INTO taxonomy VALUES(?,?,?,?)", (name, desc, "approved", "seed"))
    conn.commit()
    return conn


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_setting(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(value)))
    conn.commit()


def log_call(conn, task, res):
    conn.execute(
        "INSERT INTO model_calls(ts,task,model,source,provenance,latency_ms,prompt_tokens,completion_tokens) VALUES(?,?,?,?,?,?,?,?)",
        (now_iso(), task, res.model, res.source, res.provenance, res.latency_ms, res.prompt_tokens, res.completion_tokens))


def audit(conn, item_id, kind, model_version, confidence, proposed, action, final, note="", actor="reviewer"):
    conn.execute(
        "INSERT INTO audit(ts,item_id,kind,model_version,model_confidence,proposed,human_action,final,note,actor) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (now_iso(), item_id, kind, model_version, confidence, json.dumps(proposed), action, json.dumps(final), note, actor))
