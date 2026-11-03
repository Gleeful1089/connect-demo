# Connect demo: AI on messy supply data, code on money

Synthetic data. Demo only. No real company data, no real payments.

One claim: a model handles messy hotel supply data, and deterministic code handles money.

## Run it
```
make setup      # once: Python 3.12 venv, deps, synthetic data, offline fixtures
make run        # http://127.0.0.1:8000
make test       # 52 pytest cases
```
Offline by default: every model call has a cached fixture. With no ANTHROPIC_API_KEY the fixtures are SIMULATED
(a keyword heuristic, not a language model) and the UI says so. To use real model output:
`export ANTHROPIC_API_KEY=...; make record`, then `make run`.

## Layout
- `data/` synthetic inputs (format A nested JSON, format B flat CSV) and the 8 held-out labels (read by `evaluation/` only)
- `mapping/` model proposes canonical fields and a confidence; `detect/` statistical and rule-based anomaly detection, no LLM
- `triage/` model classifies anomalies, class playbook, queue, audit trail
- `evaluation/` precision and recall on the held-out set only
- `money/` pricing, FX, fee, ledger, virtual card: `Decimal` and integer cents, no LLM (a test enforces it)
- `search/`, `buyer/`, `api/screen2.py` Screen 2: deterministic Connect search, mock buyer agent
- `llm.py` the single model entry point with the fixture fallback

See BUILD_LOG.md for what went wrong and QUESTIONS.md for assumptions.
