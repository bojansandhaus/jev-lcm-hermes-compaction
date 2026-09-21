"""Fallback chain: failures, cooldown, recovery, secret safety."""

import json

import pytest

from jev_lcm_hermes_compaction.jev_client import ProviderError
from jev_lcm_hermes_compaction.prepass import Prepass
from jev_lcm_hermes_compaction.providers import ProviderChain
from jev_lcm_hermes_compaction.settings import Settings


def test_failures_cooldown_recovery_and_secret_safety(caplog):
    now = [1.0]

    def fail(*a):
        raise ProviderError("429")

    chain = ProviderChain(
        Settings(),
        {"TYPESAFE_API_KEY": "SECRET_A", "OPENROUTER_API_KEY": "SECRET_B"},
        fail,
        lambda: now[0],
    )
    with pytest.raises(ProviderError):
        chain.score({}, {})
    assert chain.fallback_count == 1
    with pytest.raises(ProviderError, match="cooldown"):
        chain.score({}, {})
    now[0] = 100
    chain.transport = lambda *a: {"answers": {}}
    assert chain.score({}, {}) == {}
    assert chain.last_provider == "typesafe"
    assert "SECRET_" not in caplog.text + json.dumps(chain.diagnostics())
    with pytest.raises(ProviderError, match="disabled"):
        ProviderChain(Settings(), {}).score({}, {})
    assert (
        len(
            ProviderChain(
                Settings(jev_fallback_enabled=False),
                {"TYPESAFE_API_KEY": "a", "OPENROUTER_API_KEY": "b"},
            ).order
        )
        == 1
    )
    chain = ProviderChain(
        Settings(), {"TYPESAFE_API_KEY": "a"}, lambda *a: {"bogus": True}
    )
    with pytest.raises(ProviderError, match="malformed"):
        chain.score({}, {"x": {}})
    chain = ProviderChain(
        Settings(jev_fallback_max_retries=0),
        {"TYPESAFE_API_KEY": "a"},
        lambda *a: 1 / 0,
    )
    with pytest.raises(ProviderError, match="transport_error"):
        chain.score({}, {})


def test_no_keys_and_no_budget():
    settings = Settings(min_result_chars=0)
    p = Prepass(settings, ProviderChain(settings, {}))
    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "`abc123def456`"},
        {"role": "user", "content": "tail"},
    ]
    p.collect(messages, 2)
    p.flush(force=True)
    assert p.metrics["jev_fallbacks"] == 1 and p.metrics["jev_unscored_count"] > 0
    p.flush(force=True)
    p = Prepass(
        Settings(max_state_tokens=10, max_request_tokens=20),
        ProviderChain(settings, {}),
    )
    p.collect(messages, 2)
    p.flush(force=True)
    assert p.metrics["jev_calls"] == 0
    p = Prepass(settings, ProviderChain(settings, {}))
    p.flush(force=True)
    assert p.hint_block() == ""
