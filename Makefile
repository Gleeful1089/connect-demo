.PHONY: setup run test fixtures record
PY=.venv/bin/python

setup:
	/opt/homebrew/bin/python3.12 -m venv .venv || python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt
	$(PY) data/synth.py
	$(PY) scripts/author_fixtures.py

run:
	$(PY) run.py

test:
	$(PY) -m pytest -q

fixtures:
	$(PY) scripts/author_fixtures.py

# Needs ANTHROPIC_API_KEY. Replaces simulated fixtures with real model output.
record:
	$(PY) scripts/record.py
