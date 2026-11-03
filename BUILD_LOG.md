# BUILD_LOG

Entries are appended as they happen. Nothing here is cleaned up after the fact.
All data is synthetic. This log has two parts. Part 1 is how the product direction evolved, from the starting brief to the
current app, including every change of direction Chris made and, where he gave one, his reason. Part 2 is what went wrong
technically. Items 1, 2 and 5 in Part 2 describe the first build, which ran on a simulated stand-in for the model; real
model output was recorded later (see D4).

# Part 1: Product direction

## Starting point
Chris brought a Head of Product case study memo and a build brief. The brief asked for a small demo of one claim:
"AI handles messy supply data, and deterministic code handles money." It specified two screens (an onboarding workbench
and a booking and statement flow), a build order (Screen 1 fully working and tested before Screen 2), a plan to be
approved before any code, and process rules (keep this log, evaluate each model step against held-out data, label
everything synthetic).

## Decision log
Each entry says what Chris decided, what prompted it, and what changed. Quotes are his words. Where he did not give a
reason, the entry says so.

**D1. Reuse patterns from an earlier project.** Chris asked to reuse some primitives (the approach to model API access,
a git repo, possibly a Railway deployment). Changed: a single model entry point with model tiers named in one config
file, with a cached-fixture fallback added so the demo runs offline; the deployment config shape. Patterns were copied,
nothing was imported from the other project.

**D2. Approved the plan.** I proposed a file layout and design decisions (fixture fallback, held-out labels read by one
module only, no LLM in detection or money code) plus defaults for a fee floor and repo location. Chris replied "ok".
He also approved installing Python 3.12 because the spec asked for 3.11+ and the machine had 3.9.

**D3. Work unattended, record assumptions.** Chris stepped away and said: "make whatever assumptions you need to and
record the questions/issues. use a pre-coded workflow/example feature if theres anything you cant build without my input
or authorization." Changed: with no model access yet, I wrote a clearly labeled simulated stand-in and pre-coded
fixtures; every assumption went into QUESTIONS.md (18 items); and I built Screen 2 without waiting for a second OK,
because this instruction superseded the brief's "Screen 1 first, then wait".

**D4. Record real model output.** Chris provided access and asked for the real recording. Findings with the real model:
7 of 8 held-out records fully correct, with the same single miss as the simulated run (prepaid on a non-refundable
rate); the model's confidence on every held-out record was 0.60 to 0.80, so the default 0.85 threshold auto-confirmed
none of them. I left the default alone on purpose, since choosing it from 8 records would be fitting to the test set.

**D5. Asked what a queue tile actually means.** Chris, looking at the first tile: "what was the raw data, what was the
analysis (deterministic, rule-based, agentic), and how was the information in the tile populated? ... I don't know what
DLX-KG-OV vs FAM-HB means, or the mechanism of how a room plan gets attached to a room". Finding: the tile mixed four
kinds of content (a deterministic detector's evidence, a model's label and rationale, a fixed playbook lookup, and a
priority formula) with nothing telling the reader which was which, and used vendor codes with no explanation. I explained
it in conversation. No UI change was made at that point; the About tab guide (D14) is where this ended up.

**D6. The workbench diagnoses but never repairs, so add a fix.** Chris asked what choosing a class in the dropdown
accomplishes: "given the description of issue #1, we would want to attach the rate to the correct room. is it just meant
to categorize the issue?" The honest answer was yes: approving recorded a decision and changed no data. His decisions:
"yes, add that action" and "for fixes, write the data directly" (when I asked whether a fix should write the data or
produce a change request for the hotel). Changed: a deterministic "Approve and apply fix" for rate-plan-on-wrong-room that
moves the plan to its eligible room and sends the mapping back to the queue for confirmation, with before and after
recorded in the audit trail and no model involved.

**D7. Override should record disagreement, not demand a replacement.** Chris: "if the system detects an anomaly and I
choose to override it, I just need to record what the initial triage said and that it was overridden." Changed: Override
on an anomaly needs no class; the audit trail keeps the model's class and confidence plus the override. Mapping overrides
still require at least one corrected field, since otherwise they do nothing.

**D8. More fixes, and an undo.** Chris approved the first tile without seeing a fix option (I diagnosed a browser page
loaded before the fix button existed) and asked me to undo that action and to add the duplicate and schema-drift fixes. Changed: those two fixes (suppress the copy; register the
field alias); and an undo that appends a reversal row instead of deleting the original, because the audit trail is meant
to be append-only. Applied fixes cannot be undone this way, since they changed data. Not every class has a fix: outliers,
stale data and missing policies need the hotel.

**D9. Remove Screen 2.** Chris: "delete anything about 'screen 2' from the app. I don't want to see it in the header
navigation and don't need the functionality." His reason, given afterward and similar to his reason for removing the evaluation:
Screen 2 was a second functionality to demo, and lower-impact than the onboarding workbench the demo is meant to show.
Changed: the booking flow, the buyer-agent mock, the search, and the entire money module (fees, FX, ledger, virtual
card) and their tests were deleted (recoverable from git). Consequence I flagged later: the demo now makes only the AI
half of the original claim; "money stays deterministic" is stated in the memo but no longer demonstrated. Chris's
response was "OK, great."

**D10. Move the evaluation out of the main workflow.** Chris: "lets move the evaluation on the hold-out set to a second
tab. this is more backend/design focus, not the actual UI that a user would interact with while using the system."
Changed: Evaluation became its own tab, labeled as a design view, with a note that its slider changes no data.

**D11. Confidence color must follow the slider.** Chris, in the browser: the last two issues "have model confidence .85
and show up as green, but i set the auto-confirm threshold to .9 so they should be amber." This was the first time the
UI was seen in a real browser; my own checks had only looked for crashes. Fixed (Part 2, item 11).

**D12. Which part of the product is this a demo for?** Chris asked me to explain the scope. Answer: one module,
AI-assisted supply onboarding (memo Section 2 hard problem 1 and Section 5 "AI leverage"), with explicit gaps (money, the
compounding effect over many properties, buyers, activation). He accepted it, and the answer became the basis of the
About tab.

**D13. Host it with no logins and a personal sandbox for every visitor.** Chris: "I don't want to manage any logins or
permissions; ideally when a new user starts the app for the first time it will automatically create synthetic data so
they have a 'personal sandbox' that has all the functionality but won't alter any other user (or my) use of the app."
Design that followed: a random cookie names a private database built from the recorded model outputs on first visit;
no model calls and no API key on the server; "Reset my sandbox" resets only the caller; old sandboxes expire after 7 days
and the total is capped at 300. Tests prove two visitors cannot affect each other, and a deliberate break (everyone
sharing one id) made them fail. Chris's choices at the gates: a public GitHub repo (I had recommended private), a new
separate Railway project, and rewriting git history before the first push so the commits carry a noreply identity and
mention nothing private.

**D14. Add context on the page.** Chris: "I think I should add a readme to the page so users have context", and he
supplied the text, plus a quick guide to the actions. Changed: an About tab as the landing page with his text (adapted
to read to HT readers rather than to him), a table explaining each action, and a note that the model output was
recorded once and replayed.

**D15. Remove the evaluation entirely.** After asking me to explain it again (what it measures and what it is for),
Chris: "I think the evaluation concept in general is too complicated. lets' remove it from the app and from the about."
He asked for two sentences in the About tab on how precision and recall were assessed during development and that the
threshold can be raised or lowered. Changed: the Evaluation tab and its API route are gone; the two sentences were
added. I kept the scoring code as a development script (`make evaluate`) so the claim stays reproducible, and Chris
agreed to keep it.

**D16. Put the product decisions in this log.** Chris noticed the log held only technical bugs and asked for the product
direction too. That is this section.

## The pattern in the removals and moves
Chris's test was impact on what the demo is meant to show, and who it is for. The evaluation was first moved to a second
tab because it is "more backend/design focus, not the actual UI that a user would interact with" (D10), then removed
because it was "too complicated" (D15). Screen 2 was removed for a similar reason: a second functionality, lower-impact
than the onboarding workbench being shown (D9). In the other direction, the fix actions (D6, D8) and the simpler override
(D7) came from Chris trying the workbench as a reviewer and asking what each control actually did. Two of his
corrections (the confidence color in D11 and the missing fix button in D8) were things my automated checks could not see,
because they only looked for crashes and correct data, not for whether a control was correctly colored or visible.

## Brief versus current app
| In the brief | In the current app |
|---|---|
| Screen 1: synthetic data in two formats, adversarial rows, 8 held-out records | Kept as specified |
| Canonical ontology; model mapping with confidence; threshold auto-confirm and review queue | Kept as specified |
| Rule-based anomaly detection with no model; model classification into the taxonomy; new classes need approval | Kept as specified |
| Triage queue with playbook fixes, human approve or override, audit table | Kept; override changed to need no class (D7) |
| Evaluation panel with threshold slider | Built, moved to its own tab (D10), then removed from the app (D15); kept as a development script |
| Screen 2: buyer agent, deterministic search, itemized price, fees, statements | Built, then removed (D9) |
| Not in the brief | Deterministic apply-fix actions for three classes (D6, D8); undo (D8); per-visitor sandboxes and hosting (D13); About tab and guide (D14) |

# Part 2: What went wrong

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

## 11. Confidence badge ignored the threshold slider (hardcoded 0.85)
- **What was wrong:** the green/amber confidence badge on each queue tile compared against a literal 0.85, so tiles at
  0.85 stayed green with the slider at 0.90.
- **How detected:** you noticed it in the browser. My Node smoke checks only looked for crashes, not for color logic.
- **Correction:** the badge now compares against the slider's threshold. Verified under Node at 0.90: both 0.85 tiles
  render amber. There is still no automated test of UI color logic.

## 12. New sandbox tests hardcoded the real-fixture queue size (same mistake as item 7)
- **What was wrong:** four of the first sandbox tests asserted a queue of exactly 28 items. Tests run on the simulated
  fixtures, which give 12, so they failed. Item 7 was the same coupling and I repeated it.
- **How detected:** the first pytest run of the new file.
- **Correction:** counts are now relative to a fresh sandbox (`baseline()`). One more failure was a test-client quirk
  (a second cookie with the same name), fixed by sending the forged cookie as a raw header. I also changed
  `new_sid` to a constant to confirm the isolation tests fail when sandboxes are shared: 5 failed, then I restored it.

## 13. First Railway deploy failed: no start command detected
- **What was wrong:** the build stopped with "No start command detected". My railway.toml named the NIXPACKS builder and
  a start command (copied from another project), but Railway now builds with Railpack, which did not
  take the start command from railway.toml.
- **How detected:** `railway up` reported "Deploy failed"; the build log said so.
- **Correction:** added a Procfile with the uvicorn command and removed the stale builder line.
