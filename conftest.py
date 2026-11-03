import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
os.environ["CONNECT_LLM"] = "offline"   # tests never call the network


@pytest.fixture(autouse=True)
def _simulated_fixtures(monkeypatch):
    """Tests run on fixed simulated model outputs so they do not change when real outputs are re-recorded."""
    import config
    monkeypatch.setattr(config, "FIXTURE_PATH", config.SIM_FIXTURE_PATH)


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    import pipeline
    c = pipeline.run()
    yield c
    c.close()
