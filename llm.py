"""Single entry point for model calls, with a cached-fixture fallback so the demo runs offline.

Modes (env CONNECT_LLM): auto (default) | offline | live | record
  auto    : recorded fixture if one exists, otherwise live if ANTHROPIC_API_KEY is set. Reproducible and free
            once recorded. A live failure falls back to fixtures.
  offline : fixtures only.
  live    : live only.
  record  : live, and write each response to fixtures/calls.json.
A fixture miss raises FixtureMissing. It never invents an answer.
Only this module may import the anthropic SDK.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass

import config


class FixtureMissing(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    model: str          # model id, or the fixture's declared model_version
    source: str         # "live" | "fixture"
    provenance: str     # "live-model" | "simulated" (hand-authored stand-in, NOT a model measurement)
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


def fixture_key(task: str, prompt: str) -> str:
    return hashlib.sha256(f"{task}\n{prompt}".encode()).hexdigest()[:20]


def _load() -> dict:
    if config.FIXTURE_PATH.exists():
        return json.loads(config.FIXTURE_PATH.read_text())
    return {}


def save_fixture(task: str, prompt: str, text: str, model: str, provenance: str) -> None:
    data = _load()
    data[fixture_key(task, prompt)] = {"task": task, "model": model, "provenance": provenance, "text": text}
    config.FIXTURE_PATH.parent.mkdir(exist_ok=True)
    config.FIXTURE_PATH.write_text(json.dumps(data, indent=1, sort_keys=True))


def _mode() -> str:
    return os.environ.get("CONNECT_LLM", "auto")


def _live(task: str, prompt: str, system: str | None, tier: str, max_tokens: int) -> LLMResult:
    import anthropic  # lazy: offline runs need no SDK

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=2)
    model = config.MODEL_TIERS[tier]
    start = time.time()
    kwargs = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return LLMResult(text, model, "live", "live-model", int((time.time() - start) * 1000),
                     resp.usage.input_tokens, resp.usage.output_tokens)


def _fixture(task: str, prompt: str) -> LLMResult:
    hit = _load().get(fixture_key(task, prompt))
    if hit is None:
        raise FixtureMissing(
            f"No cached fixture for task '{task}'. Run `python scripts/author_fixtures.py` (simulated) "
            "or set ANTHROPIC_API_KEY with CONNECT_LLM=record to record real outputs."
        )
    return LLMResult(hit["text"], hit["model"], "fixture", hit["provenance"])


def complete(task: str, prompt: str, system: str | None = None, tier: str = "fast",
             max_tokens: int = 1024) -> LLMResult:
    mode = _mode()
    if mode == "offline":
        return _fixture(task, prompt)
    if mode == "auto":
        try:
            return _fixture(task, prompt)
        except FixtureMissing:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise
    try:
        res = _live(task, prompt, system, tier, max_tokens)
    except Exception:
        if mode == "live" or mode == "record":
            raise
        return _fixture(task, prompt)  # auto mode: network or API failure falls back
    if mode == "record":
        save_fixture(task, prompt, res.text, res.model, "live-model")
    return res
