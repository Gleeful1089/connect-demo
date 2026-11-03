"""Generates the synthetic inventory files. Synthetic data. Demo only.

Run: python data/synth.py
Writes format_a.json (nested, coded), format_b.csv (flat, free text) and heldout_labels.json.
Only evaluation/ may read heldout_labels.json. Nothing in this module is imported by the app.
Record ids are assigned by parse order: format A first (rooms in order), then format B rows.
"""
import csv
import json
from pathlib import Path

OUT = Path(__file__).parent

# ---- Format A: Harbor Grand (USD), nested JSON with codes ----
A_ROOMS = [
    ("DLX-KG-OV", 2, [
        dict(code="BAR-BB", rate="240.00", public_rate="250.00", cancel="FREE48", prepaid=False, applies_to=["DLX-KG-OV"], avail=5, updated="2026-11-01T09:00:00Z"),
        dict(code="NR-RO", rate="205.00", public_rate="250.00", cancel="NONREF", prepaid=True, applies_to=["DLX-KG-OV"], avail=3, updated="2026-11-01T09:00:00Z"),
        # adversarial: family half-board plan attached to a deluxe king room
        dict(code="FAM-HB", rate="340.00", public_rate="360.00", cancel="FREE48", prepaid=False, applies_to=["FAM-2Q-GD"], avail=2, updated="2026-11-01T09:00:00Z"),
    ]),
    ("DLX-TW-CV", 2, [
        # adversarial: schema drift, "price" instead of "rate"
        dict(code="BAR-BB", price="215.00", public_rate="225.00", cancel="FREE48", prepaid=False, applies_to=["DLX-TW-CV"], avail=4, updated="2026-11-01T09:00:00Z"),
    ]),
    ("STE-KG-OV", 4, [
        dict(code="BAR-BB", rate="420.00", public_rate="440.00", cancel="FREE48", prepaid=False, applies_to=["STE-KG-OV"], avail=2, updated="2026-11-01T09:00:00Z"),
        # adversarial: rate outlier
        dict(code="NR-RO", rate="1150.00", public_rate="440.00", cancel="NONREF", prepaid=True, applies_to=["STE-KG-OV"], avail=2, updated="2026-11-01T09:00:00Z"),
    ]),
    ("FAM-2Q-GD", 5, [
        dict(code="BAR-HB", rate="340.00", public_rate="360.00", cancel="FREE48", prepaid=False, applies_to=["FAM-2Q-GD"], avail=2, updated="2026-11-01T09:00:00Z"),
        # adversarial: exact duplicate of the line above
        dict(code="BAR-HB", rate="340.00", public_rate="360.00", cancel="FREE48", prepaid=False, applies_to=["FAM-2Q-GD"], avail=2, updated="2026-11-01T09:00:00Z"),
    ]),
    ("STD-QN-CV", 2, [
        # adversarial: missing cancellation policy
        dict(code="BAR-RO", rate="165.00", public_rate="170.00", cancel=None, prepaid=False, applies_to=["STD-QN-CV"], avail=6, updated="2026-11-01T09:00:00Z"),
        # adversarial: stale record, last updated 19 days before the demo "now"
        dict(code="BAR-BB", rate="189.00", public_rate="195.00", cancel="FREE24", prepaid=False, applies_to=["STD-QN-CV"], avail=4, updated="2026-10-14T09:00:00Z"),
    ]),
]

# ---- Format B: flat CSV, free text ----
B_COLUMNS = ["hotel", "room_name", "rate_plan_name", "nightly_rate", "currency", "public_rate",
             "max_guests", "rooms_left", "last_updated", "cancel_policy"]
B_ROWS = [
    ["Seaview Inn", "Deluxe King Room - Ocean View", "Flexible rate incl. breakfast", "230.00", "USD", "245.00", "2", "4", "2026-11-01T10:00:00Z", "Free cancellation until 48h before arrival"],
    ["Seaview Inn", "Dlx King w/ sea view", "Advance Purchase (non refundable)", "198.00", "USD", "245.00", "2", "3", "2026-11-01T10:00:00Z", "Non-refundable, prepaid"],
    ["Seaview Inn", "Standard Queen, city side", "Room Only Flex", "150.00", "USD", "155.00", "2", "6", "2026-11-01T10:00:00Z", "Free cancel 24 hrs before arrival"],
    ["Seaview Inn", "Family Room 2 Queen Beds (sleeps 5)", "Half Board Flex", "330.00", "USD", "345.00", "5", "2", "2026-11-01T10:00:00Z", "Free cancel until 48 hours"],
    # adversarial: 2.9% above the public rate (parity break), inside the outlier fence
    ["Seaview Inn", "Garden Twin", "Bed & Breakfast", "180.00", "USD", "175.00", "2", "3", "2026-11-01T10:00:00Z", "free cancellation 24h"],
    ["Lakeside Boutique", "Superior Double Lake View", "Breakfast Included Flexible", "160.00", "EUR", "170.00", "3", "4", "2026-11-01T11:00:00Z", "Free cancellation up to 48 hours before check-in"],
    ["Lakeside Boutique", "Superior Twin Lake View", "Room only non-refundable", "135.00", "EUR", "170.00", "2", "5", "2026-11-01T11:00:00Z", "Non refundable"],
    ["Lakeside Boutique", "Family Suite Lake View (up to 5 guests)", "Half board flexible", "280.00", "EUR", "295.00", "5", "2", "2026-11-01T11:00:00Z", "Free cancellation until 48 hours before arrival"],
    ["Lakeside Boutique", "Classic Double Garden", "Breakfast Included Flexible", "120.00", "EUR", "128.00", "2", "6", "2026-11-01T11:00:00Z", "Free cancellation 24h"],
    # adversarial: a "Standard Double" that claims to sleep 6
    ["Lakeside Boutique", "Standard Double", "Room Only Flex", "110.00", "EUR", "118.00", "6", "3", "2026-11-01T11:00:00Z", "Free cancel 24 hrs before arrival"],
]

# ---- Held-out evaluation set: 8 records with known correct canonical mappings ----
# Order of record ids follows parse order (A: R01-R10, B: R11-R20).
M = lambda category, bed, view, occ, meal, cancel, prepaid: dict(
    category=category, bed=bed, view=view, max_occupancy=occ, meal_plan=meal, cancellation=cancel, prepaid=prepaid)
HELDOUT = {
    "R03": dict(truth=M("deluxe", "king", "ocean", 2, "half_board", "free_48h", False), expected_anomalies=["rate-plan-on-wrong-room"]),
    "R04": dict(truth=M("deluxe", "twin", "city", 2, "breakfast", "free_48h", False), expected_anomalies=["schema-drift"]),
    "R06": dict(truth=M("suite", "king", "ocean", 4, "room_only", "non_refundable", True), expected_anomalies=["rate-outlier"]),
    "R09": dict(truth=M("standard", "queen", "city", 2, "room_only", "unspecified", False), expected_anomalies=["missing-cancellation-policy"]),
    "R12": dict(truth=M("deluxe", "king", "ocean", 2, "room_only", "non_refundable", True), expected_anomalies=[]),
    "R14": dict(truth=M("family", "two_queens", "none", 5, "half_board", "free_48h", False), expected_anomalies=[]),
    "R17": dict(truth=M("superior", "twin", "lake", 2, "room_only", "non_refundable", False), expected_anomalies=[]),
    "R18": dict(truth=M("family", "unspecified", "lake", 5, "half_board", "free_48h", False), expected_anomalies=[]),
}


def main():
    payload = {
        "property": {"id": "HG1", "name": "Harbor Grand", "currency": "USD", "city": "Valmora Bay"},
        "rooms": [{"code": c, "max_occ": occ, "ratePlans": plans} for c, occ, plans in A_ROOMS],
    }
    (OUT / "format_a.json").write_text(json.dumps(payload, indent=1))
    with open(OUT / "format_b.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(B_COLUMNS)
        w.writerows(B_ROWS)
    (OUT / "heldout_labels.json").write_text(json.dumps(HELDOUT, indent=1))
    n_a = sum(len(p) for _, _, p in A_ROOMS)
    print(f"wrote {n_a} format A + {len(B_ROWS)} format B records, {len(HELDOUT)} held out")


if __name__ == "__main__":
    main()
