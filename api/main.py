"""FastAPI app for the onboarding workbench. Synthetic data. Demo only.

No logins. Each browser gets a random cookie that names its own sandbox database (see sandbox.py), so one visitor's
decisions never touch another's. The sandbox is created automatically on the first visit.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import db
import llm
import pipeline
import sandbox
from evaluation import heldout
from triage import fixes, queue

WEB = Path(__file__).resolve().parent.parent / "web"


def use_sandbox(request: Request):
    """Hold this visitor's sandbox lock for the request. One SQLite connection per sandbox is not safe for
    concurrent use, and the page fires several requests at once. Other visitors are not blocked."""
    sid = request.state.sid
    sb = sandbox.get(sid)
    sb.lock.acquire()
    try:
        request.state.sb = sb
        request.state.conn = sandbox.open_conn(sid, sb)   # first visit: builds the sandbox from fixtures
        yield
    finally:
        sb.lock.release()


app = FastAPI(title="Connect demo", version="0.2")
api = APIRouter(prefix="/api", dependencies=[Depends(use_sandbox)])


@app.middleware("http")
async def sandbox_cookie(request: Request, call_next):
    sid = request.cookies.get(sandbox.COOKIE)
    is_new = not sandbox.valid(sid)
    if is_new:
        sid = sandbox.new_sid()
    request.state.sid = sid
    response = await call_next(request)
    path = request.url.path
    if is_new and (path == "/" or path.startswith("/api/")):
        response.set_cookie(sandbox.COOKIE, sid, max_age=60 * 60 * 24 * 30, httponly=True, samesite="lax",
                            secure=request.headers.get("x-forwarded-proto") == "https")
    return response


@app.exception_handler(llm.FixtureMissing)
async def _fixture_missing(request, exc):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def _value_error(request, exc):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def C(request: Request):
    return request.state.conn


def _threshold(request: Request):
    return db.get_setting(C(request), "threshold", config.CONFIDENCE_THRESHOLD)


@app.get("/health")
def health():
    return {"ok": True}


@api.get("/meta")
def meta(request: Request):
    provs = [r[0] for r in C(request).execute("SELECT DISTINCT provenance FROM mappings")]
    return {"banner": "Synthetic data. Demo only.", "llm_mode": llm._mode(), "provenance": provs,
            "simulated": "simulated" in provs, "threshold": _threshold(request),
            "sandbox": {"id": hashlib.sha256(request.state.sid.encode()).hexdigest()[:6], "ttl_days": config.SANDBOX_TTL_DAYS}}


@api.post("/pipeline/run")
def run_pipeline(request: Request):
    """Reset only this visitor's sandbox."""
    sandbox.reset(request.state.sid, request.state.sb)
    return {"ok": True}


@api.get("/records")
def records(request: Request):
    c = C(request)
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


@api.get("/queue")
def get_queue(request: Request):
    c = C(request)
    taxonomy = [dict(t) for t in c.execute("SELECT * FROM taxonomy ORDER BY status, name")]
    return {"items": queue.build_queue(c), "taxonomy": taxonomy, "threshold": _threshold(request)}


class Decision(BaseModel):
    action: str
    override: dict | None = None
    note: str = ""


@api.post("/queue/{item_id}/decide")
def decide(item_id: str, d: Decision, request: Request):
    queue.decide(C(request), item_id, d.action, d.override, d.note)
    return {"ok": True}


class FixReq(BaseModel):
    note: str = ""


@api.post("/queue/{item_id}/fix")
def apply_fix(item_id: str, d: FixReq, request: Request):
    kind, ident = item_id.split(":", 1)
    if kind != "anom":
        raise ValueError("only anomalies have fixes")
    return fixes.apply_fix(C(request), int(ident), note=d.note)


class ClassDecision(BaseModel):
    approve: bool


@api.post("/taxonomy/{name}")
def taxonomy_decision(name: str, d: ClassDecision, request: Request):
    queue.approve_new_class(C(request), name, d.approve)
    return {"ok": True}


class Threshold(BaseModel):
    threshold: float


@api.post("/threshold")
def set_threshold(t: Threshold, request: Request):
    if not 0 <= t.threshold <= 1:
        raise HTTPException(400, "threshold must be between 0 and 1")
    pipeline.set_threshold(C(request), t.threshold)
    return {"ok": True}


@api.get("/eval")
def evaluation(request: Request, threshold: float | None = None):
    return heldout.evaluate(C(request), _threshold(request) if threshold is None else threshold)


@api.get("/audit")
def audit(request: Request):
    return [dict(r) for r in C(request).execute("SELECT * FROM audit ORDER BY id DESC")]


app.include_router(api)


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
