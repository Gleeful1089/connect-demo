"""Record real model outputs as fixtures. Needs ANTHROPIC_API_KEY. Replaces simulated fixtures.

Run: ANTHROPIC_API_KEY=... python scripts/record.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if not os.environ.get("ANTHROPIC_API_KEY"):
    sys.exit("Set ANTHROPIC_API_KEY first.")
os.environ["CONNECT_LLM"] = "record"

import config
import pipeline

if config.FIXTURE_PATH.exists():
    config.FIXTURE_PATH.unlink()   # drop simulated fixtures so nothing stale is mixed in
conn = pipeline.run()
print("recorded", conn.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0], "live calls to", config.FIXTURE_PATH)
