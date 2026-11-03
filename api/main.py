"""FastAPI app for the onboarding workbench. Synthetic data. Demo only."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import db
import llm
import pipeline
from evaluation import heldout
from triage import fixes, queue

app = FastAPI(title="Connect demo", version="0.1")
WEB = Path(__file__).resolve().parent.parent / "web"
_conn = None


def conn():
    global _conn
    if _conn is None:
        _conn = pipeline.run() if not config.DB_PATH.exists() else db.connect()
    return _conn


@app.exception_handler(llm.FixtureMissing)
async def _fixture_missing(request, exc):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def _value_error(request, exc):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def _threshold():
    return db.get_setting(conn(), "threshold", config.CONFIDENCE_THRESHOLD)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/meta")
def meta():
    mode = llm._mode()
    provs = [r[0] for r in conn().execute("SELECT DISTINCT provenance FROM mappings")]
    return {"banner": "Synthetic data. Demo only.", "llm_mode": mode, "provenance": provs,
            "simulated": "simulated" in provs, "threshold": _threshold()}


@app.post("/api/pipeline/run")
def run_pipeline():
    global _conn
    if _conn is not None:
        _conn.close()
    _conn = pipeline.run()
    return {"ok": True}


@app.get("/api/records")
def records():
    c = conn()
    out = []
    for r in c.execute("SELECT * FROM records ORDER BY id"):
        m = c.execute("SELECT * FROM mappings WHERE record_id=?", (r["id"],)).fetchone()
        out.append({
            "id": r["id"], "hotel": r["hotel_name"], "format": r["source_format"], "room": r["room_key"], "plan": r["plan_key"],
            "currency": r["currency"], "rate_cents": r["rate_cents"], "status": m["status"], "confidence": m["confidence"],
            "proposed": json.loads(m["proposed_json"]), "final": json.loads(m["final_json"]) if m["final_json"] else None,
            "anomalies": ([f"suppressed: {r['suppressed_reason']}"] if r["suppressed_reason"] else [])
            + [a["class"] or a["rule"] for a in c.execute("SELECT * FROM anomalies WHERE record_id=? AND status='open'", (r["id"],))]})
    return out


@app.get("/api/queue")
def get_queue():
    c = conn()
    taxonomy = [dict(t) for t in c.execute("SELECT * FROM taxonomy ORDER BY status, name")]
    return {"items": queue.build_queue(c), "taxonomy": taxonomy, "threshold": _threshold()}


class Decision(BaseModel):
    action: str
    override: dict | None = None
    note: str = ""


@app.post("/api/queue/{item_id}/decide")
def decide(item_id: str, d: Decision):
    queue.decide(conn(), item_id, d.action, d.override, d.note)
    return {"ok": True}


class FixReq(BaseModel):
    note: str = ""


@app.post("/api/queue/{item_id}/fix")
def apply_fix(item_id: str, d: FixReq):
    kind, ident = item_id.split(":", 1)
    if kind != "anom":
        raise ValueError("only anomalies have fixes")
    return fixes.apply_fix(conn(), int(ident), note=d.note)


class ClassDecision(BaseModel):
    approve: bool


@app.post("/api/taxonomy/{name}")
def taxonomy_decision(name: str, d: ClassDecision):
    queue.approve_new_class(conn(), name, d.approve)
    return {"ok": True}


class Threshold(BaseModel):
    threshold: float


@app.post("/api/threshold")
def set_threshold(t: Threshold):
    if not 0 <= t.threshold <= 1:
        raise HTTPException(400, "threshold must be between 0 and 1")
    pipeline.set_threshold(conn(), t.threshold)
    return {"ok": True}


@app.get("/api/eval")
def evaluation(threshold: float | None = None):
    return heldout.evaluate(conn(), _threshold() if threshold is None else threshold)


@app.get("/api/audit")
def audit():
    return [dict(r) for r in conn().execute("SELECT * FROM audit ORDER BY id DESC")]


@app.get("/api/model-calls")
def model_calls():
    return [dict(r) for r in conn().execute("SELECT task, model, source, provenance, COUNT(*) n FROM model_calls GROUP BY 1,2,3,4")]




@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
