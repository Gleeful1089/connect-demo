"""Canonical ontology, anomaly taxonomy and class-level playbook. Synthetic data. Demo only."""

ROOM_CATEGORIES = ["standard", "superior", "deluxe", "suite", "family"]
BEDS = ["king", "queen", "twin", "two_queens", "double", "unspecified"]
VIEWS = ["city", "ocean", "garden", "lake", "none"]
MEALS = ["room_only", "breakfast", "half_board"]
CANCELLATIONS = ["free_48h", "free_24h", "non_refundable", "unspecified"]

FIELDS = ["category", "bed", "view", "max_occupancy", "meal_plan", "cancellation", "prepaid"]
ALLOWED = {
    "category": ROOM_CATEGORIES, "bed": BEDS, "view": VIEWS,
    "meal_plan": MEALS, "cancellation": CANCELLATIONS,
}

# Cross-vendor taxonomy. Vendor and chain are metadata tags on an anomaly, never part of the class.
TAXONOMY = {
    "rate-outlier": "Rate is far outside its peer group.",
    "stale-availability": "Availability or rate has not been updated within the freshness window.",
    "room-mismatch": "Room text and room attributes disagree.",
    "rate-plan-on-wrong-room": "A rate plan is attached to a room it does not apply to.",
    "duplicate-availability": "The same room and rate plan is listed more than once.",
    "missing-cancellation-policy": "A rate plan has no cancellation policy.",
    "schema-drift": "The payload shape differs from the connector's expected schema.",
    "connector-quirk": "Behavior specific to a connector that fits no other class.",
}

# Class-level playbook: proposed fix, severity (1-5), whether it blocks the record from sale.
PLAYBOOK = {
    "rate-outlier": ("Confirm the rate with the hotel. Hold the record from sale until confirmed.", 4, True),
    "stale-availability": ("Request a fresh availability push. Hold from sale until updated.", 3, True),
    "room-mismatch": ("Ask the hotel to confirm room attributes. Correct the mapping after confirmation.", 3, True),
    "rate-plan-on-wrong-room": ("Detach the rate plan from this room and attach it to its eligible room.", 5, True),
    "duplicate-availability": ("Keep the first listing, suppress the duplicate, and notify the hotel.", 2, True),
    "missing-cancellation-policy": ("Request the policy from the hotel. Treat as unspecified until supplied.", 4, True),
    "schema-drift": ("Update the connector field alias and re-validate the payload.", 3, False),
    "connector-quirk": ("Route to integrations for connector review.", 2, False),
}
DEFAULT_PLAYBOOK = ("Route to onboarding lead for review.", 3, False)

# After a human resolves an anomaly of these classes the record stays out of search (suppressed / detached).
SUPPRESS_ON_RESOLVE = {"duplicate-availability", "rate-plan-on-wrong-room"}
