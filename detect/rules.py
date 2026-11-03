"""Anomaly detection. Statistical and rule based. NO LLM, and no import of llm or anthropic."""
from __future__ import annotations

import re
import statistics
from collections import defaultdict
from datetime import datetime

import config

NONREF = re.compile(r"non[\s-]?refund|nonref", re.I)
CATEGORY_RULES = [  # (regex on room text, min occ, max occ)
    (re.compile(r"family|^fam", re.I), 4, None),
    (re.compile(r"suite|^ste", re.I), None, 4),
    (re.compile(r"deluxe|dlx", re.I), None, 3),
    (re.compile(r"superior|^sup", re.I), None, 3),
    (re.compile(r"standard|^std", re.I), None, 3),
]


def _is_nonref(rec: dict) -> bool:
    raw = rec["extra"].get("cancel_raw") or ""
    return bool(NONREF.search(raw)) or raw == "NONREF" or bool(NONREF.search(rec["plan_key"]))


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def detect_iqr(records: list[dict]) -> list[dict]:
    """Rate / public-rate ratio vs peers (same refundability), IQR fences.

    The ratio is unitless, so peers are pooled across currencies. Grouping by currency as well left the
    non-refundable group with 3 members, below MIN_PEERS, and a 2.6x outlier went undetected.
    """
    groups = defaultdict(list)
    for r in records:
        groups[_is_nonref(r)].append(r)
    out = []
    for grp in groups.values():
        if len(grp) < config.MIN_PEERS:
            continue
        ratios = [r["rate_cents"] / r["public_cents"] for r in grp]
        q1, _, q3 = statistics.quantiles(ratios, n=4, method="inclusive")
        iqr = max(q3 - q1, config.IQR_MIN)
        lo, hi = q1 - config.IQR_K * iqr, q3 + config.IQR_K * iqr
        for r, ratio in zip(grp, ratios):
            if ratio < lo or ratio > hi:
                out.append({"record_id": r["id"], "rule": "iqr-outlier", "evidence": {
                    "ratio_to_public": round(ratio, 3), "fence_low": round(lo, 3), "fence_high": round(hi, 3),
                    "peer_count": len(grp), "rate_cents": r["rate_cents"], "public_cents": r["public_cents"]}})
    return out


def detect_parity(records: list[dict]) -> list[dict]:
    out = []
    flagged_outliers = {a["record_id"] for a in detect_iqr(records)}
    for r in records:
        ratio = r["rate_cents"] / r["public_cents"]
        if ratio > 1 + float(config.PARITY_TOLERANCE) and r["id"] not in flagged_outliers:
            out.append({"record_id": r["id"], "rule": "parity-break", "evidence": {
                "ratio_to_public": round(ratio, 3), "tolerance": float(config.PARITY_TOLERANCE),
                "rate_cents": r["rate_cents"], "public_cents": r["public_cents"]}})
    return out


def detect_stale(records: list[dict]) -> list[dict]:
    out = []
    for r in records:
        age = (config.AS_OF - _parse_ts(r["updated_at"])).days
        if age > config.STALE_DAYS:
            out.append({"record_id": r["id"], "rule": "stale", "evidence": {
                "updated_at": r["updated_at"], "age_days": age, "limit_days": config.STALE_DAYS}})
    return out


def detect_drift(records: list[dict]) -> list[dict]:
    out = []
    for r in records:
        d = r["extra"]["drift"]
        if d["unexpected"] or d["missing"]:
            out.append({"record_id": r["id"], "rule": "schema-drift", "evidence": d})
    return out


def detect_duplicates(records: list[dict]) -> list[dict]:
    seen, out = {}, []
    for r in records:
        key = (r["hotel_id"], r["room_key"], r["plan_key"], r["rate_cents"])
        if key in seen:
            out.append({"record_id": r["id"], "rule": "duplicate", "evidence": {"duplicate_of": seen[key]}})
        else:
            seen[key] = r["id"]
    return out


def detect_wrong_room(records: list[dict]) -> list[dict]:
    out = []
    for r in records:
        applies = r["extra"]["applies_to"]
        if applies and r["room_key"] not in applies:
            out.append({"record_id": r["id"], "rule": "wrong-room-plan", "evidence": {
                "attached_to": r["room_key"], "plan_applies_to": applies, "plan": r["plan_key"]}})
    return out


def detect_missing_cancellation(records: list[dict]) -> list[dict]:
    return [{"record_id": r["id"], "rule": "missing-cancellation", "evidence": {"cancel_raw": r["extra"]["cancel_raw"]}}
            for r in records if not r["extra"].get("cancel_raw")]


def detect_occupancy_mismatch(records: list[dict]) -> list[dict]:
    out = []
    for r in records:
        occ = r["extra"].get("max_occ")
        if occ is None:
            continue
        for pat, lo, hi in CATEGORY_RULES:
            if pat.search(r["room_key"]):
                if (lo is not None and occ < lo) or (hi is not None and occ > hi):
                    out.append({"record_id": r["id"], "rule": "occupancy-mismatch", "evidence": {
                        "room_text": r["room_key"], "stated_max_occupancy": occ,
                        "expected_min": lo, "expected_max": hi}})
                break
    return out


DETECTORS = [detect_iqr, detect_parity, detect_stale, detect_drift, detect_duplicates,
             detect_wrong_room, detect_missing_cancellation, detect_occupancy_mismatch]


def detect_all(records: list[dict]) -> list[dict]:
    found = []
    for d in DETECTORS:
        found.extend(d(records))
    return sorted(found, key=lambda a: (a["record_id"], a["rule"]))
