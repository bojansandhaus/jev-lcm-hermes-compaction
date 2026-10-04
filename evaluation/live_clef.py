"""Live probe for ``jev_provider: clef`` and the Clef checkpoint selection.

Honesty boundary: no Cloudflare credential on this machine is authorized for
Workers AI. Every candidate token returns HTTP 401 ``Authentication error``, so
no live Clef call is possible here and none is attempted. Every phase below
runs against a local recorder or a refused credential, which is what this file
can honestly show. A phase that would have sent the state to Cloudflare records
the URL instead of sending it.

The Cloudflare Clef documentation consulted for this provider is at
https://developers.cloudflare.com/workers-ai/models/clef/ and
https://developers.cloudflare.com/workers-ai/models/clef-flash/. The wire
contract asserted here comes from those pages and from the unit tests in
``tests/test_clef_provider.py``. It is not a reproduced live result.

Run:  PYTHONPATH=src python evaluation/live_clef.py
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

from jev_lcm_hermes_compaction.jev_client import (
    ClefError,
    ProviderError,
    clef_result,
    post,
)
from jev_lcm_hermes_compaction.providers import ProviderChain
from jev_lcm_hermes_compaction.settings import Settings

PLACEHOLDER = "synthetic-placeholder-not-a-key"
QUESTIONS = {
    "probe:keep_result": {
        "type": "noul",
        "instructions": "Is the identifier needed verbatim?",
    }
}
STATE = {"note": "Retain identifier abc123def456 for the next step."}
Transport = Callable[[str, str, dict[str, Any], float], Any]


def recording_transport() -> tuple[Transport, list[str]]:
    """Record the URL and return a synthetic Clef answer; send nothing."""
    recorded: list[str] = []

    def transport(url: str, key: str, payload: dict[str, Any], timeout: float) -> Any:
        recorded.append(url)
        return {"answers": {q: {"noul": 0.2966} for q in payload["questions"]}}

    return transport, recorded


def refusing_transport() -> tuple[Transport, list[str]]:
    """Attempt the real request and report exactly what Cloudflare answers.

    This is the only phase that touches the network, and it sends the synthetic
    ``STATE`` above rather than any conversation content. It is expected to be
    refused with a 401 on this machine. The account id is reported as present or
    absent, never printed.
    """
    recorded: list[str] = []

    def transport(url: str, key: str, payload: dict[str, Any], timeout: float) -> Any:
        recorded.append(url)
        return post(url, key, payload, timeout)

    return transport, recorded


def phase_1_recorder() -> dict[str, Any]:
    transport, recorded = recording_transport()
    chain = ProviderChain(
        Settings(jev_provider="clef"),
        {
            "CLOUDFLARE_API_TOKEN": PLACEHOLDER,
            "CLOUDFLARE_ACCOUNT_ID": "0" * 32,
        },
        transport,
    )
    scores = chain.score(STATE, QUESTIONS)
    return {
        "order": chain.order,
        "last_provider": chain.last_provider,
        "fallback_count": chain.fallback_count,
        "calls": chain.calls,
        "scores": scores,
        "urls_recorded_not_sent": recorded,
        "keys_present": chain.diagnostics()["keys_present"],
        "configuration_present": chain.diagnostics()["configuration_present"],
        "note": "no request was sent; the URL is recorded",
    }


def phase_2_checkpoint() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for model in ("clef", "clef-flash"):
        transport, recorded = recording_transport()
        chain = ProviderChain(
            Settings(jev_provider="clef", clef_model=model),
            {
                "CLOUDFLARE_API_TOKEN": PLACEHOLDER,
                "CLOUDFLARE_ACCOUNT_ID": "0" * 32,
            },
            transport,
        )
        chain.score(STATE, QUESTIONS)
        out[model] = {
            "urls_recorded_not_sent": recorded,
            "model_in_body": model,
            "chain_order": chain.order,
        }
    out["clef_flash_is_a_checkpoint_not_a_provider"] = (
        Settings(jev_provider="clef", clef_model="clef-flash").jev_provider
        == "api_only"
        and Settings(jev_provider="clef", clef_model="clef-flash").jev_provider_pin
        == "clef"
        and "clef-flash"
        not in Settings(jev_fallback_order=("clef",)).jev_fallback_order
    )
    try:
        Settings(clef_model="clef-large")
        out["unknown_checkpoint"] = "accepted"
    except ValueError as error:
        out["unknown_checkpoint"] = str(error)
    return out


def phase_3_alias_and_chain() -> dict[str, Any]:
    keys = {
        "CLOUDFLARE_API_TOKEN": PLACEHOLDER,
        "CLOUDFLARE_ACCOUNT_ID": "0" * 32,
        "TYPESAFE_API_KEY": PLACEHOLDER,
        "OPENROUTER_API_KEY": PLACEHOLDER,
    }
    ordered = ProviderChain(
        Settings(jev_fallback_order=("clef", "typesafe", "openrouter")),
        keys,
        lambda *a: {},
    )
    uncredentialed = ProviderChain(
        Settings(jev_fallback_order=("clef", "typesafe", "openrouter")),
        {"TYPESAFE_API_KEY": PLACEHOLDER},
        lambda *a: {},
    )
    return {
        "clef": ProviderChain(Settings(jev_provider="clef"), keys, lambda *a: {}).order,
        "clef_api": ProviderChain(
            Settings(jev_provider="clef_api"), keys, lambda *a: {}
        ).order,
        "alias_resolves_to_canonical": Settings(jev_provider="clef_api").jev_provider,
        "auto_unchanged": ProviderChain(Settings(), keys, lambda *a: {}).order,
        "ordered_chain": ordered.order,
        "uncredentialed_clef_is_filtered": uncredentialed.order,
    }


def phase_4_missing_credentials() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for label, env in (
        ("no_token", {"CLOUDFLARE_ACCOUNT_ID": "0" * 32}),
        ("no_account", {"CLOUDFLARE_API_TOKEN": PLACEHOLDER}),
        ("neither", {}),
    ):
        try:
            ProviderChain(Settings(jev_provider="clef"), env, lambda *a: {})
            out[label] = "chain built"
        except ValueError as error:
            out[label] = str(error)
    out["placeholder_never_printed"] = PLACEHOLDER not in json.dumps(out)
    return out


def phase_5_refused_credential() -> dict[str, Any]:
    """Report the real Cloudflare answer without printing a credential."""
    token = (os.environ.get("CLOUDFLARE_API_TOKEN") or "").strip()
    account = (os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()
    if not token or not account:
        return {
            "attempted": False,
            "reason": "no CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID in the "
            "environment; no request was attempted",
        }
    transport, recorded = refusing_transport()
    chain = ProviderChain(
        Settings(jev_provider="clef"),
        {"CLOUDFLARE_API_TOKEN": token, "CLOUDFLARE_ACCOUNT_ID": account},
        transport,
    )
    terminal = ""
    detail = ""
    try:
        chain.score(STATE, QUESTIONS)
        detail = "accepted"
    except ClefError as error:
        detail, terminal = str(error), error.reason
    except ProviderError as error:
        detail, terminal = type(error).__name__, error.reason
    return {
        "attempted": bool(recorded),
        "synthetic_state_only": True,
        "terminal_reason": terminal,
        "detail": detail,
        "last_errors": chain.diagnostics()["last_errors"],
        "credential_values_printed": False,
    }


def phase_6_envelopes() -> dict[str, Any]:
    """Both documented response shapes, checked offline."""
    bare = {
        "model": "clef",
        "answers": {"probe:keep_result": {"noul": 0.31}},
        "usage": {"input_tokens": 12},
    }
    enveloped = {
        "success": True,
        "result": {
            "model": "clef",
            "answers": {"probe:keep_result": {"noul": 0.62}},
            "usage": {"input_tokens": 12},
        },
        "errors": [],
        "messages": [],
    }
    refused = {
        "success": False,
        "errors": [{"code": 7003, "message": "Authentication error"}],
        "result": None,
    }
    out: dict[str, Any] = {}
    for label, body in (("bare", bare), ("envelope", enveloped)):
        try:
            out[label] = clef_result(body)
        except ClefError as error:
            out[label] = str(error)
    try:
        clef_result(refused)
        out["success_false"] = "accepted"
    except ClefError as error:
        out["success_false"] = {"message": str(error), "reason": error.reason}
    return out


def main() -> None:
    report: dict[str, Any] = {
        "provider": "clef",
        "live_clef_call": "not possible on this machine; every candidate token "
        "returns HTTP 401 Authentication error",
        "source_pages": [
            "https://developers.cloudflare.com/workers-ai/models/clef/",
            "https://developers.cloudflare.com/workers-ai/models/clef-flash/",
        ],
        "phase_1_wire_shape": phase_1_recorder(),
        "phase_2_checkpoint_selection": phase_2_checkpoint(),
        "phase_3_alias_and_chain": phase_3_alias_and_chain(),
        "phase_4_missing_credentials": phase_4_missing_credentials(),
        "phase_5_refused_credential": phase_5_refused_credential(),
        "phase_6_response_envelopes": phase_6_envelopes(),
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
