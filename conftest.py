import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
os.environ["CONNECT_LLM"] = "offline"   # tests never call the network


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    import pipeline
    c = pipeline.run()
    yield c
    c.close()
