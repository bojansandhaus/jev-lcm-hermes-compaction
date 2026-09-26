"""The local hop's consecutive-failure breaker.

``laya_then_hosted`` exists to answer from the machine and to move to a hosted
provider only when the local server fails a configured trigger. A local server
that keeps failing would otherwise turn every batch into a hosted request, so
the chain counts consecutive local failures and stops escalating past the
limit, re-raising the local error instead of answering it remotely. The count
is held by the process, survives a rebuilt chain, resets on restart, and any
healthy local answer clears it, on the fallback path and on the plain local
path alike. Past the limit the local error is re-raised, so the caller sees the
failure rather than a remote answer the operator did not ask for.

The provider cooldown bounds egress too: after a local failure the local hop is
skipped for ``jev_fallback_cooldown_s``. The test that walks four consecutive
local failures zeroes that cooldown, which is the only way to reach the local
hop on every call inside one second.
"""

import pytest

from jev_lcm_hermes_compaction import providers
from jev_lcm_hermes_compaction.jev_client import ProviderError
from jev_lcm_hermes_compaction.providers import ProviderChain
from jev_lcm_hermes_compaction.settings import Settings

QUESTIONS = {"x:keep_result": {"type": "noul", "instructions": "keep?"}}
LOCAL = "http://127.0.0.1:8000/v1/systemone"
HOSTED = "https://api.typesafe.ai/v1/systemone"
BOTH_KEYS = {"TYPESAFE_API_KEY": "private-one", "OPENROUTER_API_KEY": "private-two"}
STATES = [
    {"note": "keep identifier abc123def456"},
    {"note": "keep identifier fff999aaa111"},
    {"note": "keep identifier 0a0b0c0d0e0f"},
    {"note": "keep identifier deadbeefcafe"},
]


@pytest.fixture(autouse=True)
def reset_breaker(monkeypatch):
    monkeypatch.setattr(providers, "_laya_failure_count", 0)


def split_transport(seen, local_fails=True):
    """Fail the local URL and answer the hosted ones, recording every URL."""

    def transport(url, key, payload, timeout):
        seen.append(url)
        if url == LOCAL and local_fails:
            raise ProviderError("transport_error")
        return {"answers": {q: {"noul": 0.77} for q in payload["questions"]}}

    return transport


def test_three_consecutive_local_failures_fall_through_and_the_fourth_is_suppressed():
    seen = []
    chain = ProviderChain(
        Settings(jev_provider="laya_then_hosted", jev_fallback_cooldown_s=0),
        BOTH_KEYS,
        split_transport(seen),
    )
    for state in STATES[:3]:
        assert chain.score(state, QUESTIONS) == {"x:keep_result": 0.77}
        assert chain.last_provider == "typesafe"
        assert providers.laya_consecutive_failures() <= 3
    assert seen == [LOCAL, HOSTED] * 3
    assert chain.fallback_count == 3

    with pytest.raises(ProviderError, match="transport_error"):
        chain.score(STATES[3], QUESTIONS)
    assert seen == [LOCAL, HOSTED] * 3 + [LOCAL]
    assert chain.fallback_count == 3
    assert providers.laya_consecutive_failures() == 4

    with pytest.raises(ProviderError, match="transport_error"):
        chain.score(STATES[3], QUESTIONS)
    assert seen == [LOCAL, HOSTED] * 3 + [LOCAL, LOCAL]
    assert providers.laya_consecutive_failures() == 5


def test_a_suppressed_fallback_makes_no_remote_call_at_all():
    seen = []
    providers._laya_failure_count = 3
    chain = ProviderChain(
        Settings(jev_provider="laya_then_hosted"), BOTH_KEYS, split_transport(seen)
    )
    with pytest.raises(ProviderError, match="transport_error"):
        chain.score(STATES[0], QUESTIONS)
    assert seen == [LOCAL]
    assert chain.last_provider == ""
    assert chain.fallback_count == 0
    assert providers.laya_consecutive_failures() == 4
    assert [url for url in seen if url != LOCAL] == []


def test_the_suppression_warning_names_the_category_and_no_state(caplog):
    seen = []
    providers._laya_failure_count = 3
    chain = ProviderChain(
        Settings(jev_provider="laya_then_hosted"), BOTH_KEYS, split_transport(seen)
    )
    with pytest.raises(ProviderError):
        chain.score({"note": "SENTINEL-abc123de"}, {"x:keep_result": {}})
    assert "laya_fallback_suppressed" in caplog.text
    assert "SENTINEL-abc123de" not in caplog.text


def test_a_healthy_local_call_resets_a_tripped_breaker_on_the_fallback_path():
    seen = []
    providers._laya_failure_count = 3
    chain = ProviderChain(
        Settings(jev_provider="laya_then_hosted"),
        BOTH_KEYS,
        split_transport(seen, local_fails=False),
    )
    assert chain.score(STATES[0], QUESTIONS) == {"x:keep_result": 0.77}
    assert seen == [LOCAL]
    assert chain.last_provider == "laya"
    assert providers.laya_consecutive_failures() == 0


def test_a_healthy_local_call_resets_a_tripped_breaker_on_the_plain_local_path():
    providers._laya_failure_count = 3
    chain = ProviderChain(
        Settings(jev_provider="laya"),
        {},
        lambda *a: {"answers": {q: {"noul": 0.4} for q in a[2]["questions"]}},
    )
    assert chain.score(STATES[0], QUESTIONS) == {"x:keep_result": 0.4}
    assert providers.laya_consecutive_failures() == 0


def test_the_breaker_follows_the_process_not_the_chain():
    seen = []
    providers._laya_failure_count = 3
    first = ProviderChain(
        Settings(jev_provider="laya_then_hosted"), BOTH_KEYS, split_transport(seen)
    )
    with pytest.raises(ProviderError):
        first.score(STATES[0], QUESTIONS)
    rebuilt = ProviderChain(
        Settings(jev_provider="laya_then_hosted"), BOTH_KEYS, split_transport(seen)
    )
    with pytest.raises(ProviderError):
        rebuilt.score(STATES[1], QUESTIONS)
    assert seen == [LOCAL, LOCAL]


def test_the_breaker_is_reported_in_diagnostics():
    seen = []
    chain = ProviderChain(
        Settings(jev_provider="laya_then_hosted"), BOTH_KEYS, split_transport(seen)
    )
    assert chain.diagnostics()["laya_consecutive_failures"] == 0
    chain.score(STATES[0], QUESTIONS)
    assert chain.diagnostics()["laya_consecutive_failures"] == 1
    assert "private-" not in repr(chain.diagnostics())


def test_a_hosted_failure_does_not_charge_the_local_breaker():
    """The breaker guards the local hop only; hosted failures are not its business."""

    def fail(*a):
        raise ProviderError("429")

    chain = ProviderChain(Settings(jev_provider="auto"), BOTH_KEYS, fail)
    with pytest.raises(ProviderError, match="429"):
        chain.score(STATES[0], QUESTIONS)
    assert chain.fallback_count == 1
    assert providers.laya_consecutive_failures() == 0
