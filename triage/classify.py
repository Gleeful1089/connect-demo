"""Model classification of detected anomalies into the cross-vendor taxonomy.

Vendor, chain and format are passed as metadata tags only. They are not classes.
The model may propose a new class, which is stored as 'proposed' and needs human approval.
"""
from __future__ import annotations

import json
import re

import llm

SYSTEM = "You classify hotel-data anomalies into a taxonomy. Reply with one JSON object and nothing else."


def build_prompt(anomaly: dict, tags: dict, taxonomy: dict) -> str:
    return (
        "Classify this detected anomaly into exactly one taxonomy class. If none fits, set class to 'NEW' and "
        "propose a new class name (kebab-case) and a one-line description in new_class.\n"
        f"Taxonomy: {json.dumps(taxonomy, sort_keys=True)}\n"
        f"Detector rule: {anomaly['rule']}\n"
        f"Evidence: {json.dumps(anomaly['evidence'], sort_keys=True)}\n"
        f"Metadata tags (not part of the class): {json.dumps(tags, sort_keys=True)}\n"
        'Return JSON: {"class":..,"confidence": number 0-1,"rationale":..,"new_class": null or {"name":..,"description":..}}'
    )


def classify(anomaly: dict, tags: dict, taxonomy: dict):
    """Returns (class_name or None, confidence, rationale, new_class dict or None, LLMResult)."""
    res = llm.complete("classify_anomaly", build_prompt(anomaly, tags, taxonomy), system=SYSTEM, tier="fast")
    try:
        m = re.search(r"\{.*\}", res.text, re.S)
        obj = json.loads(m.group(0))
        cls = obj.get("class")
        conf = max(0.0, min(1.0, float(obj.get("confidence", 0))))
        new = obj.get("new_class") if isinstance(obj.get("new_class"), dict) else None
    except Exception as e:  # unparseable output is treated as unclassified, not guessed
        return None, 0.0, f"unparseable model output: {e}", None, res
    if cls == "NEW" and new and new.get("name"):
        return new["name"], conf, obj.get("rationale", ""), new, res
    if cls not in taxonomy:
        return None, min(conf, 0.3), f"model returned unknown class {cls!r}", None, res
    return cls, conf, obj.get("rationale", ""), None, res
