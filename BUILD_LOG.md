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

## 6. record.py rejected a valid key (my own regression)
- **What was wrong:** `make record` printed "Set ANTHROPIC_API_KEY first" although the key was in `.env`.
- **How detected:** the first real run of `make record`, right after adding `.env` support.
- **Cause:** scripts/record.py checked os.environ before importing config.py, which is what loads `.env`.
- **Correction:** import config first. Nothing was deleted: the check runs before the fixtures are removed.

## 7. Six tests were coupled to the simulated fixtures (tests passing for the wrong reason)
- **What was wrong:** after recording real model output, 6 Screen 2 and API tests failed. They asserted a specific
  search ranking (R18, R14, R07) and that certain records were auto-confirmed. Those facts came from the heuristic's
  confidence scores, not from anything the code guarantees.
- **How detected:** running pytest right after `make record` swapped the fixtures.
- **Correction:** the simulated outputs now live in tests/data/simulated_calls.json and a conftest autouse fixture
  points all tests at them. The app uses fixtures/calls.json (real). `make fixtures` only rebuilds the simulated set.

## 8. Approving a fix released a suspect record into search (design bug)
- **What was wrong:** after the demo shortcut approved every queue item, R20 ("Standard Double" claiming to sleep 6)
  appeared as a bookable offer for the family of five at $243.40. I had treated "resolved" as "safe to sell" for
  every class except duplicates and wrong-room plans.
- **How detected:** I ran the full approve-all flow against the real recorded fixtures and read the offer list.
  The simulated run had hidden it, because R20 had been excluded for a different reason there.
- **Cause:** approving a proposed fix records a decision. It does not correct the data at the hotel.
- **Correction:** records with a blocking anomaly stay out of search after approval ("held pending hotel fix")
  until the data is re-ingested. A regression test covers it.

## 9. `make run` with a key set made 28 live calls on every database rebuild
- **What was wrong:** in auto mode a present API key meant "go live", so the first `make run` after recording sat
  for 30+ seconds re-calling the model and would have produced outputs that differ from the recorded fixtures.
- **How detected:** the server was not answering /health 25 seconds after start.
- **Correction:** auto mode now uses a recorded fixture when one exists and calls the API only on a fixture miss.
  Use `CONNECT_LLM=live` to force live calls.

## 10. Page load could return a 500 and leave a panel blank (shared SQLite connection)
- **What was wrong:** `GET /api/eval` intermittently returned 500 (`sqlite3.InterfaceError: bad parameter or other
  API misuse`). The page fires queue, records, eval and audit requests at once, and the API shared one SQLite
  connection across FastAPI's worker threads.
- **How detected:** a Node smoke check of the UI after moving the evaluation to its own tab hit the 500, and the
  server log showed the traceback. It had been happening since the first version; the earlier Node checks were
  sequential and the 52 pytest cases never sent concurrent requests, so neither could see it. Whether it
  affected your browser earlier is likely but unconfirmed.
- **Correction:** wrote a concurrency test first (it failed 3 of 3 runs), then serialized API requests with a lock.
  The test now passes 5 of 5 runs. Single-user demo only; a multi-user version needs a connection per request.
