"""Fallback chain: failures, cooldown, recovery, secret safety."""

import json
import logging

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


def test_no_scoring_log_line_carries_state_candidate_text_or_an_answer(caplog):
    """Logging hygiene on the scoring path: categories, never content.

    Every warning this package emits while it scores names a category, a
    provider, or a counter. The state, the candidate text, and any answer must
    stay out of the log stream, because the log is copied around far more
    casually than the evidence store.
    """
    sentinel = "SENTINEL-9f3c2a57"

    def fail(*a):
        raise ProviderError("transport_error")

    settings = Settings(jev_provider="laya_then_hosted", min_result_chars=0)
    prepass = Prepass(
        settings, ProviderChain(settings, {"TYPESAFE_API_KEY": "private"}, fail)
    )
    messages = [
        {"role": "user", "content": sentinel + " keep this verbatim"},
        {"role": "assistant", "content": "`" + sentinel + "`"},
        {"role": "tool", "content": "result body " + sentinel},
        {"role": "user", "content": "tail"},
    ]
    with caplog.at_level(logging.DEBUG):
        prepass.collect(messages, 3)
        prepass.flush(force=True)
    assert caplog.text
    assert sentinel not in caplog.text
    assert "transport_error" in caplog.text
