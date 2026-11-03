"""Writes SIMULATED fixtures (see simulated_model.py) for every model call the pipeline makes offline.

Run: python scripts/author_fixtures.py
To record real model output instead: ANTHROPIC_API_KEY=... CONNECT_LLM=record python run.py --pipeline
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import ingest
import llm
import ontology
import simulated_model as sim
from detect import rules
from mapping import mapper
from triage import classify


def main():
    config.FIXTURE_PATH = config.SIM_FIXTURE_PATH   # simulated fixtures never overwrite recorded ones
    if config.FIXTURE_PATH.exists():
        config.FIXTURE_PATH.unlink()
    records = ingest.load_all()
    n = 0
    for r in records:
        p = mapper.build_prompt(r["view"])
        llm.save_fixture("map_record", p, sim.simulate_map(p), sim.MODEL_VERSION, "simulated")
        n += 1
    taxonomy = dict(ontology.TAXONOMY)
    by_id = {r["id"]: r for r in records}
    for a in rules.detect_all(records):
        r = by_id[a["record_id"]]
        tags = {"source_format": r["source_format"], "hotel_id": r["hotel_id"]}
        p = classify.build_prompt(a, tags, taxonomy)
        llm.save_fixture("classify_anomaly", p, sim.simulate_classify(p), sim.MODEL_VERSION, "simulated")
        n += 1
    print(f"wrote {n} simulated fixtures to {config.FIXTURE_PATH}")


if __name__ == "__main__":
    main()
