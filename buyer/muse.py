"""Mock buyer agent "Muse". Parsing natural language into a structured request is the BUYER AGENT's job.

Connect never sees the sentence. It receives only the structured call below. This request is canned.
"""
REQUEST_TEXT = "Family of five, next weekend, mid-range budget."

STRUCTURED_REQUEST = {
    "destination": "Valmora Bay",
    "check_in": "2026-11-13",
    "check_out": "2026-11-15",
    "occupancy": {"adults": 2, "children": 3},
    "budget": {"currency": "USD", "max_per_night_cents": 36000},
    "preferences": {"meal_plan_min": "breakfast", "free_cancellation": True},
    "buyer_currency": "USD",
}


def muse_turn() -> dict:
    return {"agent": "Muse (mock buyer agent)", "parsing_done_by": "BUYER AGENT, not Connect", "parsing_source": "canned",
            "request_text": REQUEST_TEXT, "tool_call": {"name": "connect.search", "arguments": STRUCTURED_REQUEST}}
