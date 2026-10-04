"""The interchangeable local slot, and the mode that leads with the API.

Two things are new here and both are about what the plugin sends:

1. ``local_model`` selects which local engine answers. The provider name stays
   ``laya`` because that is the vocabulary an operator already writes, so a
   different local model is selected by configuration alone, with no code change
   and no new provider name. The value is deliberately not checked against a
   list of known models: the slot exists to be interchangeable, and a new engine
   has to work without a release.
2. ``api_with_local_fallback`` is the fourth mode: the hosted API leads and the
   local slot is the last resort. It is the mirror of the mode that already
   existed, and it is the only mode where a hosted failure ends at a local call
   rather than at a report.

The privacy boundary runs through all of this, so the log tests below are the
point of several of them. A local call keeps the reviewed state on the machine
and a hosted call sends it off the machine; either way the reviewed state, the
candidate text, the answers, and the credentials must never appear in a log
line, a diagnostic, or an error message.
"""

import logging

import pytest

from jev_lcm_hermes_compaction.jev_client import ProviderError
from jev_lcm_hermes_compaction.providers import ProviderChain
from jev_lcm_hermes_compaction.settings import Settings

QUESTIONS = {"x:keep_result": {"type": "noul", "instructions": "keep?"}}
LOCAL = "http://127.0.0.1:8000/v1/systemone"
TYPESAFE = "https://api.typesafe.ai/v1/systemone"
OPENROUTER = "https://openrouter.ai/api/alpha/decisions"
BOTH_KEYS = {"TYPESAFE_API_KEY": "private-one", "OPENROUTER_API_KEY": "private-two"}


def recording(score: float = 0.5, fails_on=()):
    def transport(url, key, payload, timeout):
        if url in fails_on:
            raise ProviderError("transport_error")
        return {"answers": {q: {"noul": score} for q in payload["questions"]}}

    return transport


# The four canonical modes: correct provider order.


def test_api_with_local_fallback_puts_the_hosted_providers_first():
    chain = ProviderChain(
        Settings(jev_provider="api_with_local_fallback"), BOTH_KEYS, lambda *a: {}
    )
    assert chain.order == ["typesafe", "openrouter", "laya"]
    assert chain.diagnostics()["order"] == ["typesafe", "openrouter", "laya"]


def test_api_only_reports_a_failure_and_never_reaches_the_local_slot():
    """A single-provider route does not reroute, so nothing stays on the machine."""
    seen = []

    def transport(url, key, payload, timeout):
        seen.append(url)
        raise ProviderError("transport_error")

    chain = ProviderChain(Settings(jev_provider="api_only"), BOTH_KEYS, transport)
    with pytest.raises(ProviderError):
        chain.score({"note": "state"}, QUESTIONS)
    assert seen == [TYPESAFE, OPENROUTER, OPENROUTER]
    assert LOCAL not in seen


def test_local_only_never_contacts_a_hosted_provider():
    seen = []

    def transport(url, key, payload, timeout):
        seen.append(url)
        return {"answers": {"x:keep_result": {"noul": 0.5}}}

    chain = ProviderChain(Settings(jev_provider="local_only"), BOTH_KEYS, transport)
    assert chain.order == ["laya"]
    chain.score({}, QUESTIONS)
    assert seen == [LOCAL]


def test_local_with_api_fallback_puts_the_local_slot_first():
    chain = ProviderChain(
        Settings(jev_provider="local_with_api_fallback"), BOTH_KEYS, lambda *a: {}
    )
    assert chain.order == ["laya", "typesafe", "openrouter"]


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("api_with_local_fallback", ["typesafe", "openrouter", "laya"]),
        ("api_only", ["typesafe", "openrouter"]),
        ("local_only", ["laya"]),
        ("local_with_api_fallback", ["laya", "typesafe", "openrouter"]),
    ],
)
def test_every_canonical_mode_has_its_own_provider_order(mode, expected):
    chain = ProviderChain(Settings(jev_provider=mode), BOTH_KEYS, lambda *a: {})
    assert chain.order == expected


def test_the_hosted_failure_falls_through_to_the_local_slot():
    """The mode that leads with the API ends at a local call, not a report."""
    seen = []

    def transport(url, key, payload, timeout):
        seen.append(url)
        if url != LOCAL:
            raise ProviderError("429")
        return {"answers": {"x:keep_result": {"noul": 0.6}}}

    chain = ProviderChain(
        Settings(jev_provider="api_with_local_fallback"), BOTH_KEYS, transport
    )
    assert chain.score({}, QUESTIONS) == {"x:keep_result": 0.6}
    assert seen == [TYPESAFE, OPENROUTER, LOCAL]
    assert chain.last_provider == "laya"
    assert chain.fallback_count == 2
    assert chain.diagnostics()["last_errors"] == {
        "typesafe": "429",
        "openrouter": "429",
    }


def test_a_non_triggering_hosted_status_does_not_reach_the_local_slot():
    seen = []

    def transport(url, key, payload, timeout):
        seen.append(url)
        raise ProviderError("malformed")

    chain = ProviderChain(
        Settings(jev_provider="api_with_local_fallback"), BOTH_KEYS, transport
    )
    with pytest.raises(ProviderError, match="malformed"):
        chain.score({}, QUESTIONS)
    assert seen == [TYPESAFE]
    assert LOCAL not in seen


def test_the_mode_without_a_hosted_key_fails_at_load_and_names_the_variable():
    """A promised fallback that could not exist is a load-time error."""
    with pytest.raises(ValueError) as error:
        ProviderChain(Settings(jev_provider="api_with_local_fallback"), {})
    message = str(error.value)
    assert "TYPESAFE_API_KEY" in message
    assert "OPENROUTER_API_KEY" in message
    assert "private" not in message


def test_one_hosted_key_narrows_the_chain_and_still_keeps_the_local_hop():
    chain = ProviderChain(
        Settings(jev_provider="api_with_local_fallback"),
        {"OPENROUTER_API_KEY": "private"},
        lambda *a: {},
    )
    assert chain.order == ["openrouter", "laya"]


# local_model: what the local request asks for.


def test_the_local_slot_defaults_to_laya_and_the_default_is_unchanged():
    seen = {}

    def transport(url, key, payload, timeout):
        seen.update(url=url, payload=payload)
        return {"answers": {"x:keep_result": {"noul": 0.3}}}

    chain = ProviderChain(Settings(jev_provider="local_only"), {}, transport)
    chain.score({}, QUESTIONS)
    assert seen["payload"]["model"] == "laya"
    assert seen["url"] == LOCAL
    assert set(seen["payload"]) == {"model", "state", "questions"}


@pytest.mark.parametrize(
    "engine",
    [
        "laya",
        "kev",
        "tev1",
        "Tev1-4B",
        "jeff-qwen3.5-0.8b",
        "jeff-gemma4-e2b",
        "laya-multilingual",
        "laya-typed-decisions",
        "a-local-model-this-package-has-never-heard-of",
    ],
)
def test_any_local_engine_name_is_accepted_without_a_code_change(engine):
    """No allowlist: a new local model has to work by configuration alone."""
    settings = Settings(jev_provider="local_only", local_model=engine)
    assert settings.local_model == engine
    seen = {}

    def transport(url, key, payload, timeout):
        seen["model"] = payload["model"]
        return {"answers": {"x:keep_result": {"noul": 0.3}}}

    ProviderChain(settings, {}, transport).score({}, QUESTIONS)
    assert seen["model"] == engine


def test_local_model_changes_what_the_local_request_asks_for():
    seen = {}

    def transport(url, key, payload, timeout):
        seen["model"] = payload["model"]
        return {"answers": {"x:keep_result": {"noul": 0.3}}}

    ProviderChain(
        Settings(jev_provider="local_only", local_model="kev-0.8b"), {}, transport
    ).score({}, QUESTIONS)
    assert seen["model"] == "kev-0.8b"


def test_local_model_reaches_the_local_hop_of_a_fallback_mode_too():
    seen = []

    def transport(url, key, payload, timeout):
        seen.append(payload["model"])
        return {"answers": {"x:keep_result": {"noul": 0.3}}}

    ProviderChain(
        Settings(jev_provider="local_with_api_fallback", local_model="tev1"),
        BOTH_KEYS,
        transport,
    ).score({}, QUESTIONS)
    assert seen == ["tev1"]


def test_local_model_wins_over_the_older_laya_model_when_both_are_set():
    settings = Settings(local_model="kev", laya_model="english")
    assert settings.local_model == "kev"
    # The older setting mirrors the resolved name so an existing reader of it
    # still sees the engine that is actually sent.
    assert settings.laya_model == "kev"


def test_laya_model_still_decides_when_local_model_is_left_alone():
    assert Settings(laya_model="english").local_model == "english"
    assert Settings(laya_model="multilingual").local_model == "multilingual"


def test_a_configured_laya_model_is_what_the_local_provider_sends():
    seen = {}

    def transport(url, key, payload, timeout):
        seen["model"] = payload["model"]
        return {"answers": {"x:keep_result": {"noul": 0.3}}}

    ProviderChain(
        Settings(jev_provider="local_only", laya_model="typed-decisions"),
        {},
        transport,
    ).score({}, QUESTIONS)
    assert seen["model"] == "typed-decisions"


# local_model rejection: only what could not be carried safely.


@pytest.mark.parametrize("value", ["", " ", "\t", "\n", "   "])
def test_an_empty_or_whitespace_local_model_is_rejected(value):
    with pytest.raises(ValueError):
        Settings(local_model=value)


@pytest.mark.parametrize("value", ["kev 0.8b", "kev\t0.8b", "kev\n", "ke v"])
def test_a_local_model_carrying_whitespace_is_rejected(value):
    with pytest.raises(ValueError, match="whitespace"):
        Settings(local_model=value)


@pytest.mark.parametrize(
    "value,why",
    [
        ('ke"v', "a quote would end the JSON string"),
        ("ke\\v", "a backslash would escape the closing quote"),
        ("kev?", "a question mark would start a query string"),
        ("kev#1", "a hash would start a fragment"),
        ("kev\x00", "a control character is not printable"),
        ("kev\x1b[0m", "an escape sequence is not printable"),
    ],
)
def test_a_local_model_needing_escaping_is_rejected_deliberately(value, why):
    """These are refused rather than silently mangled or escaped."""
    with pytest.raises(ValueError):
        Settings(local_model=value)


@pytest.mark.parametrize(
    "value", ["kev", "Tev1-4B", "jeff-gemma4-e2b", "laya:typed-decisions", "a/b/c"]
)
def test_a_local_model_with_safe_punctuation_is_accepted(value):
    """A slash, a colon, and a hyphen are safe in both a JSON body and a path."""
    assert Settings(local_model=value).local_model == value


def test_a_rejected_local_model_is_not_echoed_in_the_error():
    """A rejected value is operator configuration, not content to be quoted."""
    secret_ish = 'kev"SECRET-abc123'
    with pytest.raises(ValueError) as error:
        Settings(local_model=secret_ish)
    assert "SECRET-abc123" not in str(error.value)


def test_local_model_is_never_a_mode_or_a_fallback_member():
    with pytest.raises(ValueError, match="invalid jev_provider"):
        Settings(jev_provider="kev")
    with pytest.raises(ValueError, match="invalid jev_fallback_order"):
        Settings(jev_fallback_order=("kev",))
    with pytest.raises(ValueError, match="invalid jev_fallback_order"):
        Settings(jev_fallback_order=("typesafe", "kev"))


def test_selecting_the_local_slot_needs_no_credential_whatever_the_engine():
    for engine in ("laya", "kev", "tev1"):
        chain = ProviderChain(
            Settings(jev_provider="local_only", local_model=engine),
            {},
            recording(),
        )
        assert chain.diagnostics()["keys_present"] == []


# Privacy: a log line carries the provider and the exception class, nothing else.


def test_a_local_failure_names_the_provider_and_the_category_and_no_state(caplog):
    """The local hop fails, so nothing was ever sent anywhere."""

    def transport(url, key, payload, timeout):
        raise ProviderError("transport_error")

    chain = ProviderChain(
        Settings(jev_provider="local_with_api_fallback"),
        BOTH_KEYS,
        transport,
    )
    with caplog.at_level(logging.WARNING):
        with pytest.raises(ProviderError):
            chain.score({"note": "SENTINEL-state"}, QUESTIONS)
    assert "SENTINEL-state" not in caplog.text
    # The fallback line names providers and a reason category only.
    assert "typesafe" in caplog.text
    assert "private-one" not in caplog.text


def test_a_hosted_failure_falling_through_to_local_names_no_content(caplog):
    """The state already left the machine here, so the log is deliberately narrow."""

    def transport(url, key, payload, timeout):
        raise RuntimeError(
            "failed POST to https://api.typesafe.ai/v1/systemone "
            "with header private-one and body SENTINEL-candidate-text"
        )

    chain = ProviderChain(
        Settings(jev_provider="api_with_local_fallback"), BOTH_KEYS, transport
    )
    with caplog.at_level(logging.WARNING):
        with pytest.raises(ProviderError):
            chain.score(
                {"note": "SENTINEL-state"},
                {"x:keep_result": {"type": "noul", "instructions": "SENTINEL-q"}},
            )
    assert "SENTINEL-state" not in caplog.text
    assert "SENTINEL-candidate-text" not in caplog.text
    assert "SENTINEL-q" not in caplog.text
    assert "private-one" not in caplog.text
    # A fallback is still recorded, naming the route and a fixed reason category.
    assert "jev_provider_fallback" in caplog.text


def test_the_fallback_log_line_carries_no_state_and_no_answer(caplog):
    chain = ProviderChain(
        Settings(jev_provider="api_with_local_fallback"),
        BOTH_KEYS,
        recording(fails_on=(TYPESAFE, OPENROUTER)),
    )
    with caplog.at_level(logging.WARNING):
        chain.score({"note": "SENTINEL-state"}, QUESTIONS)
    assert "SENTINEL-state" not in caplog.text
    assert "0.5" not in caplog.text
    assert "private-" not in caplog.text


def test_a_local_slot_failure_in_the_api_first_mode_leaves_no_trace_of_content(
    caplog,
):
    """The local hop is the last resort and it fails on the machine."""

    def transport(url, key, payload, timeout):
        raise ProviderError("transport_error")

    chain = ProviderChain(
        Settings(jev_provider="api_with_local_fallback"), BOTH_KEYS, transport
    )
    with caplog.at_level(logging.WARNING):
        with pytest.raises(ProviderError):
            chain.score({"note": "SENTINEL-state"}, QUESTIONS)
    assert "SENTINEL-state" not in caplog.text
    assert "private-" not in caplog.text


def test_no_diagnostic_reports_a_credential_a_state_or_an_answer():
    chain = ProviderChain(
        Settings(jev_provider="api_with_local_fallback", local_model="kev"),
        BOTH_KEYS,
        recording(),
    )
    chain.score({"note": "SENTINEL-state"}, QUESTIONS)
    reported = repr(chain.diagnostics())
    assert "private-" not in reported
    assert "SENTINEL-state" not in reported
    assert "TYPESAFE_API_KEY" in reported
