"""Live probe for ``jev_provider: laya_then_hosted``.

Phase 1 is a live end-to-end call through the new mode: the chain is built with
the mode and the local hop is a real HTTP request to a running ``laya-serve``.
Phase 2 exercises the transition to the hosted hop.

Honesty boundary: no hosted API key exists on this machine, so no hosted request
is sent. Phase 1 uses the real ``post`` transport for the local URL and records
(never sends) any hosted URL the chain would reach; phase 2 points the local hop
at a closed port so the local attempt fails over the network for real, then
shows the hosted URL the chain moved to. The hosted leg is covered by the unit
tests in ``tests/test_laya_then_hosted.py``, not by a live hosted call.

The mode fails fast without a hosted key, so a placeholder value satisfies the
constructor. It is never sent anywhere and never printed.

Run:  PYTHONPATH=src python evaluation/live_laya_then_hosted.py
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

from jev_lcm_hermes_compaction.jev_client import ProviderError, post
from jev_lcm_hermes_compaction.providers import ProviderChain
from jev_lcm_hermes_compaction.settings import Settings

BASE = os.environ.get("LAYA_LIVE_BASE_URL", "http://127.0.0.1:8123")
CLOSED = os.environ.get("LAYA_DEAD_PORT_URL", "http://127.0.0.1:8124")
PLACEHOLDER = "synthetic-placeholder-not-a-key"
PLACEHOLDERS = {"TYPESAFE_API_KEY": PLACEHOLDER, "OPENROUTER_API_KEY": PLACEHOLDER}
QUESTIONS = {
    "probe:keep_result": {
        "type": "noul",
        "instructions": "Is the identifier needed verbatim?",
    }
}
STATE = {"note": "Retain identifier abc123def456 for the next step."}
Transport = Callable[[str, str, dict[str, Any], float], Any]


def recording_transport(base: str) -> tuple[Transport, list[str]]:
    """Send the local request for real; record any hosted URL instead of sending it."""
    reached: list[str] = []

    def transport(url: str, key: str, payload: dict[str, Any], timeout: float) -> Any:
        if url.startswith(base):
            return post(url, key, payload, timeout)
        reached.append(url)
        raise ProviderError("transport_error")

    return transport, reached


def main() -> None:
    report: dict[str, Any] = {"mode": "laya_then_hosted"}

    settings = Settings(
        jev_provider="laya_then_hosted",
        laya_base_url=BASE,
        laya_model="english",
        request_timeout_s=120,
    )
    transport, reached = recording_transport(BASE)
    chain = ProviderChain(settings, PLACEHOLDERS, transport)
    scores = chain.score(STATE, QUESTIONS)
    report["phase_1_live_local_call"] = {
        "laya_base_url": BASE,
        "order": chain.order,
        "last_provider": chain.last_provider,
        "fallback_count": chain.fallback_count,
        "calls": chain.calls,
        "scores": scores,
        "hosted_urls_reached": reached,
        "keys_present": chain.diagnostics()["keys_present"],
    }

    dead, dead_reached = recording_transport(CLOSED)
    dead_chain = ProviderChain(
        Settings(
            jev_provider="laya_then_hosted",
            laya_base_url=CLOSED,
            laya_model="english",
            request_timeout_s=10,
        ),
        {"TYPESAFE_API_KEY": PLACEHOLDER, "OPENROUTER_API_KEY": PLACEHOLDER},
        dead,
    )
    terminal = ""
    try:
        dead_chain.score(STATE, QUESTIONS)
    except ProviderError as error:
        terminal = error.reason
    report["phase_2_hosted_transition"] = {
        "laya_base_url": CLOSED,
        "order": dead_chain.order,
        "last_errors": dead_chain.diagnostics()["last_errors"],
        "fallback_count": dead_chain.fallback_count,
        "hosted_urls_recorded": dead_reached,
        "terminal_reason": terminal,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
