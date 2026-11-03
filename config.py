"""Single place for model tiers, thresholds and money parameters. Synthetic data. Demo only."""
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = Path(os.environ.get("CONNECT_DB", ROOT / "connect.db"))
FIXTURE_PATH = ROOT / "fixtures" / "calls.json"

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

# Money (placeholders, configurable)
FEE_RATE = Decimal("0.03")
FEE_FLOOR_CENTS = {"USD": 500, "EUR": 500}
FX_MARGIN = Decimal("0.015")
FX_RATES = {("EUR", "USD"): Decimal("1.0900"), ("USD", "EUR"): Decimal("0.9174")}  # synthetic mid rates
