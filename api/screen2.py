"""Screen 2 routes: Muse, Connect search, booking, hotel statement. No LLM anywhere in this path."""
from __future__ import annotations

import json

from fastapi import APIRouter
from pydantic import BaseModel

import db
from buyer import muse
from money import ledger
from search import connect_search
from triage import queue

router = APIRouter()


def _conn():
    from api.main import conn
    return conn()


@router.get("/api/muse")
def get_muse():
    return muse.muse_turn()


@router.post("/api/connect/search")
def search(req: dict):
    return connect_search.search(_conn(), req)


class BookReq(BaseModel):
    offer_id: str
    request: dict
    scenario: str = "completed"
    retained_cents: int | None = None


@router.post("/api/connect/book")
def book(b: BookReq):
    c = _conn()
    result = connect_search.search(c, b.request)
    offer = next((o for o in result["offers"] if o["offer_id"] == b.offer_id), None)
    if offer is None:
        raise ValueError("offer is not in the current search results")
    rec = c.execute("SELECT * FROM records WHERE id=?", (b.offer_id,)).fetchone()
    n = c.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] + 1
    booking_id = f"BK-{n:04d}"
    st = ledger.build_statement(booking_id, rec["rate_cents"], result["nights"], rec["currency"],
                                b.request["buyer_currency"], b.scenario, b.retained_cents)
    c.execute("INSERT INTO bookings VALUES(?,?,?,?,?)", (booking_id, db.now_iso(), b.offer_id, b.scenario, json.dumps(st)))
    c.commit()
    return {"offer": offer, "statement": st}


@router.post("/api/demo/approve-all-review")
def approve_all_review():
    """DEMO SHORTCUT: approve every pending item so Screen 2 has confirmed inventory. Audited with actor=demo-shortcut."""
    c = _conn()
    done, skipped = 0, []
    for item in queue.build_queue(c):
        try:
            if item["kind"] == "anomaly" and item.get("new_class_pending"):
                queue.approve_new_class(c, item["proposed"]["class"], True, actor="demo-shortcut")
            queue.decide(c, item["item_id"], "approve", note="demo shortcut", actor="demo-shortcut")
            done += 1
        except ValueError as e:
            skipped.append({"item": item["item_id"], "why": str(e)})
    return {"approved": done, "skipped": skipped}
