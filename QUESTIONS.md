# Open questions and assumptions (recorded while building unattended)

Nothing here was approved by anyone. Each assumption is the simplest default that let the build continue.

## Needs your input or authorization
1. **No ANTHROPIC_API_KEY was set.** All model output is a pre-coded simulated stand-in (see BUILD_LOG item 5).
   To replace it: `export ANTHROPIC_API_KEY=...` then `make record`. This also needs a decision on spend (about
   28 small calls per run). I did not search any other project for a key.
2. **Model ids.** `config.py` uses `claude-haiku-5-5` for both model steps. Confirm that is the tier you want, and
   whether classification should use the stronger tier. No cost tracking is wired, because I did not have
   verified per-token prices for these models.
3. **Repo and hosting.** The code is committed locally in ~/connect-demo only. I did not create a GitHub repo or a
   Railway project, because both publish outward. Say the word and I will create `Gleeful1089/connect-demo`.
4. **Python.** I ran `brew install python@3.12` (you approved it). That is the only system change.

## Product assumptions to confirm
5. **Fee floor.** $5.00 per booking in USD and EUR (placeholder, `config.FEE_FLOOR_CENTS`). The floor also applies to a
   retained cancellation charge, and the fee is capped at the amount it is charged on (a $3 retained charge pays a $3 fee).
6. **Zero-charge cancellation:** fee is zero and the floor does not apply.
7. **Rounding:** half up to the cent, not banker's rounding.
8. **Taxes:** rates are treated as pre-tax and tax is out of scope, shown as a note on the statement.
9. **FX:** synthetic fixed rate EUR/USD 1.0900. The 1.5% margin is charged to the buyer on the converted amount, and the
   hotel is paid in its own currency and pays its fee in that currency. On a cancelled booking with a retained charge,
   only the retained amount is converted and carries margin.
10. **Fee currency** is the hotel's currency (the floor is per currency).
11. **Muse request** is canned (the spec allows it). "Next weekend" resolves to 13 to 15 Nov 2026, from a fixed demo
    date of 2 Nov 2026. Budget is a $360 per night cap, which I took as "mid-range" for a family of five.
12. **Hotels are fictional** (Harbor Grand, Seaview Inn, Lakeside Boutique in "Valmora Bay"). One of them bills in EUR so
    the cross-currency scenario exists.
13. **Parity break** is not in your eight-class taxonomy. The simulated classifier proposes it as a new class, so the
    new-class approval flow has something real to show. After you approve it, it stays a playbook-less class
    (default routing) until someone writes it a fix.
14. **Held-out set:** R03, R04, R06, R09, R12, R14, R17, R18. Four contain planted anomalies, so anomaly classification
    can also be scored. The labels were written by me, not by a hotel expert. Some are judgment calls (R18 "Family Suite"
    labelled `family`; R12 meal plan labelled `room_only` because the plan name says nothing about meals).
15. **Confidence threshold default** is 0.85.
16. **Eval recall definition:** correct and auto-confirmed, over all correct proposals. Other definitions are defensible.
17. **Demo shortcut:** Screen 2 has a button that approves every pending item so the search has confirmed inventory.
    Its decisions are written to the audit table with actor `demo-shortcut`.
18. **R17 prepaid** (non-refundable but not stated as prepaid) is labelled false. A different reviewer might disagree.

## Added 2026-11-03: fix action and override semantics (per your instructions)
19. **Override on an anomaly needs no class.** It records the model's triage (class and confidence), the override, and any
    note, and marks the anomaly `overridden`. I assumed an overridden anomaly no longer blocks the record from search,
    because you rejected the triage. Say so if overridden anomalies should keep the record held.
20. **Override on a mapping still needs at least one corrected field**, since otherwise it would be a no-op. Approve covers
    "accept as is". The error message now says so.
21. **Fix action (rate-plan-on-wrong-room only).** Writes directly: moves the plan to the one room named in its
    `applies_to`, and copies room attributes (category, bed, view, occupancy) from another listing of that room. It
    refuses when the plan lists more than one eligible room or the target room has no other listing.
22. **After a fix, the mapping returns to the queue for human confirmation**, since its room attributes changed. The
    model's original proposal is not modified, so the held-out evaluation is unaffected.
23. **Other classes have no automatic fix yet.** Candidates: duplicate-availability (suppress, deterministic) and
    schema-drift (add the field alias). Rate outliers, stale data and missing cancellation policies need the hotel.
