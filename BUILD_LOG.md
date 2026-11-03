# BUILD_LOG

Entries are appended as problems are found. Nothing here is cleaned up after the fact.
All data is synthetic. Model outputs in this log come from the SIMULATED stand-in (scripts/simulated_model.py)
unless an entry says otherwise, because no ANTHROPIC_API_KEY was available during the first build session.

## 1. Rate outlier classified as parity break (detector bug)
- **What was wrong:** R06 (a $1,150 non-refundable suite rate, 2.6x its public rate) was not flagged by the IQR rule.
  The parity rule caught it instead, and the classifier proposed a new class for it.
- **How detected:** the first held-out evaluation run. Classification accuracy on held-out anomalies was 3 of 4, and
  the missed one was R06 (expected rate-outlier, got parity-break).
- **Cause:** I grouped peers by (currency, refundability). The USD non-refundable group had 3 members, below
  MIN_PEERS=4, so the group was skipped. Small peer groups silently disable the rule.
- **Correction:** the ratio to public rate is unitless, so peers are now grouped by refundability only (4 members).
  Caveat: this was surfaced by the held-out set, so the held-out classification number is no longer a clean
  out-of-sample measure of the detector. The change is principled (unitless metric) but I am recording that it was
  made after seeing the label result.

## 2. Confident wrong mapping (miscalibrated confidence)
- **What was wrong:** R17 ("Room only non-refundable") was mapped prepaid=true. The label says false: non-refundable
  does not imply prepaid. Confidence was 0.91, above the 0.85 threshold, so it was auto-confirmed.
- **How detected:** held-out evaluation. Precision at threshold 0.85 is 5/6, not 100%.
- **Cause:** the heuristic marks an inferred field as a small confidence penalty (0.07), so one wrong inference
  barely moves the score. In the curve, precision does not reach 100% until threshold 0.95, where coverage is 3/8.
- **Correction:** none yet, deliberately. This is the trade-off the threshold slider is meant to show. Open question:
  should inferred-not-stated fields (prepaid especially, since it moves money) be capped below any auto-confirm
  threshold? Recorded in QUESTIONS.md.

## 3. Override form crashed the whole queue (UI bug)
- **What was wrong:** the first version of renderQueue threw `Cannot read properties of undefined (reading 'map')`,
  so the triage queue would have rendered empty.
- **How detected:** no browser was available (the Chrome extension was not connected), so I ran web/app.js under
  Node with a stub DOM against the live API. This was the first time the UI code ran at all. The 52 pytest cases
  did not cover it because they test the API, not the front end.
- **Cause:** the override dropdowns are built from a CHOICES table, and max_occupancy, one of the 7 canonical
  fields, had no entry.
- **Correction:** added the missing entry. The Node check now passes, but it is a smoke check of the render
  functions, not a visual review. Nobody has looked at this UI in a real browser yet.

## 4. Environment: system Python was 3.9
- **What was wrong:** the spec asks for Python 3.11+, and this Mac's default python3 is 3.9.6.
- **How detected:** version check before writing any code.
- **Correction:** installed python@3.12 with Homebrew and built the venv from it. The code uses `X | None`
  annotations, which would have failed at import on 3.9 without this.

## 5. Fixtures are simulated, so the evaluation panel is a mechanics demo
- **What was wrong (process, not code):** no ANTHROPIC_API_KEY was available, so no real model output exists yet.
  The only way to run offline was to author fixtures from a keyword heuristic (scripts/simulated_model.py).
  Every precision/recall figure currently shown scores that heuristic, not a language model.
- **How detected:** I knew going in. Recorded here so the numbers are never quoted as model performance.
- **Correction:** every fixture carries provenance="simulated"; the UI header and the evaluation panel say so.
  `make record` with a key replaces them with real output. After that, items 1 and 2 above should be re-checked,
  since a real model will fail differently from the heuristic.
