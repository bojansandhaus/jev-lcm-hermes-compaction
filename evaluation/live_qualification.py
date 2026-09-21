"""Bounded live qualification of the provider chain against the real endpoints.

Synthetic conversation only; no user data. Set one or both provider keys in the
environment, then run from the repository root:

    PYTHONPATH=src python evaluation/live_qualification.py

``LIVE_QUALIFICATION_CALLS`` sets the number of scoring calls per provider
(default 12). The script prints JSON: latency percentiles, per-call scores, and
the distinct score band, so provider stability and cross-provider agreement can
be reported instead of a single anecdote.
"""

import json
import os
import statistics
import sys
import time

from jev_lcm_hermes_compaction.anchors import Candidate
from jev_lcm_hermes_compaction.jev_client import post
from jev_lcm_hermes_compaction.providers import ProviderChain
from jev_lcm_hermes_compaction.settings import Settings
from jev_lcm_hermes_compaction.state_shaper import shape

ENV_NAMES = {"typesafe": "TYPESAFE_API_KEY", "openrouter": "OPENROUTER_API_KEY"}
CALLS = int(os.environ.get("LIVE_QUALIFICATION_CALLS", "12"))


def build_payload():
    settings = Settings()
    messages = [
        {"role": "user", "content": "Summarise the release checklist."},
        {"role": "tool", "content": "make test: 55 passed in 4.14s " * 40},
        {
            "role": "assistant",
            "content": "The gate is `abc123def456` and src/a.py at v1.2.3.",
        },
        {"role": "tool", "content": "git log --oneline -1: 13da88e " * 30},
        {
            "role": "assistant",
            "content": "Keep the calibration threshold at 0.15 for now.",
        },
    ]
    candidates = [
        Candidate("a", "anchor", 2, "abc123def456"),
        Candidate("b", "anchor", 4, "13da88e"),
    ]
    state, questions, selected, tier = shape(messages, candidates, settings)
    return settings, state, questions, selected, tier


def qualify(provider: str, settings, state, questions) -> dict:
    if not os.environ.get(ENV_NAMES[provider], "").strip():
        return {"skipped": f"{ENV_NAMES[provider]} not set"}
    chain = ProviderChain(settings, transport=post, clock=time.monotonic)
    chain.order = [provider]
    latencies, scores, errors = [], [], []
    first_question = list(questions)[0]
    for _ in range(CALLS):
        started = time.perf_counter()
        try:
            answers = chain.score(state, questions)
            latencies.append(time.perf_counter() - started)
            scores.append(round(float(answers[first_question]), 4))
        except Exception as error:  # noqa: BLE001
            errors.append(f"{type(error).__name__}: {error}"[:120])
    ordered = sorted(latencies)
    return {
        "calls": CALLS,
        "ok": len(latencies),
        "errors": errors[:3],
        "p50_ms": round(statistics.median(latencies) * 1000) if latencies else None,
        "p95_ms": (
            round(ordered[max(0, int(len(ordered) * 0.95) - 1)] * 1000)
            if latencies
            else None
        ),
        "first_question": first_question,
        "scores": scores,
        "distinct_scores": sorted(set(scores)),
    }


def main() -> int:
    settings, state, questions, selected, tier = build_payload()
    report = {
        "payload": {
            "state_tokens": len(json.dumps(state, separators=(",", ":"))),
            "question_count": len(questions),
            "selected": len(selected),
            "tier": tier,
            "keys_present": sorted(
                name for name in ENV_NAMES.values() if os.environ.get(name)
            ),
        },
        "providers": {
            provider: qualify(provider, settings, state, questions)
            for provider in ("typesafe", "openrouter")
        },
    }
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
