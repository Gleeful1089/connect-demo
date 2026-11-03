"""Single place for model tiers and thresholds. Synthetic data. Demo only."""
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).parent


def _load_dotenv(path):
    """Minimal .env reader (no dependency). Real environment variables win. .env is gitignored."""
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")
DB_PATH = Path(os.environ.get("CONNECT_DB", ROOT / "connect.db"))
FIXTURE_PATH = ROOT / "fixtures" / "calls.json"
SIM_FIXTURE_PATH = ROOT / "tests" / "data" / "simulated_calls.json"   # simulated outputs, used by tests

# Fixed "now" so the demo and tests are deterministic.
AS_OF = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)

# Model tiers. Names live here only.
MODEL_TIERS = {"fast": "claude-haiku-5-5", "powerful": "claude-sonnet-5-5"}

# Mapping review
CONFIDENCE_THRESHOLD = 0.85

# Detection (no LLM)
STALE_DAYS = 7
PARITY_TOLERANCE = Decimal("0.02")   # rate above public rate by more than 2% is a parity break
IQR_K = 1.5
IQR_MIN = 0.06                        # floor on the IQR so tight peer groups do not over-flag
MIN_PEERS = 4

