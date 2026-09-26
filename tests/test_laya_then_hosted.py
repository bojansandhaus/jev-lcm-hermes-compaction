"""Laya leading with the hosted Jev providers as an explicit fallback hop.

``jev_provider: laya_then_hosted`` is opt-in. Laya answers first, and a
transport, timeout, authentication, rate-limit, or server failure from the
local server moves the same request to the hosted providers named by
``jev_fallback_order`` that have a key. The privacy consequence is deliberate
and documented: a failed local attempt leaves the machine.
"""

import pytest

from jev_lcm_hermes_compaction.jev_client import ProviderError
from jev_lcm_hermes_compaction.providers import ProviderChain
from jev_lcm_hermes_compaction.settings import Settings

QUESTIONS = {"x:keep_result": {"type": "noul", "instructions": "keep?"}}
LOCAL = "http://127.0.0.1:8000/v1/systemone"
TYPESAFE = "https://api.typesafe.ai/v1/systemone"
OPENROUTER = "https://openrouter.ai/api/alpha/decisions"
BOTH_KEYS = {"TYPESAFE_API_KEY": "private-one", "OPENROUTER_API_KEY": "private-two"}


def test_the_mode_puts_laya_first_then_every_keyed_hosted_provider():
    chain = ProviderChain(
        Settings(jev_provider="laya_then_hosted"), BOTH_KEYS, lambda *a: {}
    )
    assert chain.order == ["laya", "typesafe", "openrouter"]
    assert chain.diagnostics()["order"] == ["laya", "typesafe", "openrouter"]


@pytest.mark.parametrize(
    "env,expected",
    [
        ({"TYPESAFE_API_KEY": "private"}, ["laya", "typesafe"]),
        ({"OPENROUTER_API_KEY": "private"}, ["laya", "openrouter"]),
        (
            {"TYPESAFE_API_KEY": "private", "LAYA_API_KEY": "private"},
            ["laya", "typesafe"],
        ),
    ],
)
def test_one_hosted_key_narrows_the_chain_to_that_provider(env, expected):
    chain = ProviderChain(Settings(jev_provider="laya_then_hosted"), env, lambda *a: {})
    assert chain.order == expected


def test_the_configured_fallback_order_decides_the_hosted_hop_order():
    chain = ProviderChain(
        Settings(
            jev_provider="laya_then_hosted",
            jev_fallback_order=("openrouter", "typesafe"),
        ),
        BOTH_KEYS,
        lambda *a: {},
    )
    assert chain.order == ["laya", "openrouter", "typesafe"]


def test_no_hosted_key_at_all_fails_fast_and_names_the_variables():
    with pytest.raises(ValueError) as error:
        ProviderChain(Settings(jev_provider="laya_then_hosted"), {})
    message = str(error.value)
    assert "TYPESAFE_API_KEY" in message
    assert "OPENROUTER_API_KEY" in message
    assert "private" not in message


def test_a_narrowed_fallback_order_names_only_the_variables_it_can_use():
    with pytest.raises(ValueError) as error:
        ProviderChain(
            Settings(
                jev_provider="laya_then_hosted", jev_fallback_order=("openrouter",)
            ),
            {},
        )
    message = str(error.value)
    assert "OPENROUTER_API_KEY" in message
    assert "TYPESAFE_API_KEY" not in message


def test_the_local_hop_answers_first_and_no_hosted_request_is_made():
    seen = []

    def transport(url, key, payload, timeout):
        seen.append(url)
        return {"answers": {q: {"noul": 0.42} for q in payload["questions"]}}

    chain = ProviderChain(
        Settings(jev_provider="laya_then_hosted"), BOTH_KEYS, transport
    )
    assert chain.score({}, QUESTIONS) == {"x:keep_result": 0.42}
    assert seen == [LOCAL]
    assert chain.last_provider == "laya"
    assert chain.fallback_count == 0


def test_a_local_failure_falls_through_and_records_the_hosted_hop():
    seen = []

    def transport(url, key, payload, timeout):
        seen.append((url, key))
        if url == LOCAL:
            raise ProviderError("transport_error")
        return {"answers": {q: {"noul": 0.77} for q in payload["questions"]}}

    chain = ProviderChain(
        Settings(jev_provider="laya_then_hosted"), BOTH_KEYS, transport
    )
    assert chain.score({}, QUESTIONS) == {"x:keep_result": 0.77}
    assert [url for url, _ in seen] == [LOCAL, TYPESAFE]
    assert seen[1][1] == "private-one"
    assert chain.fallback_count == 1
    assert chain.last_provider == "typesafe"
    assert chain.diagnostics()["last_provider"] == "typesafe"
    assert chain.diagnostics()["last_errors"] == {"laya": "transport_error"}
    assert "private-" not in repr(chain.diagnostics())


@pytest.mark.parametrize("reason", ["timeout", "401", "403", "429", "5xx"])
def test_every_configured_trigger_moves_a_local_failure_to_the_hosted_hop(reason):
    def transport(url, key, payload, timeout):
        if url == LOCAL:
            raise ProviderError(reason)
        return {"answers": {q: {"noul": 0.5} for q in payload["questions"]}}

    chain = ProviderChain(
        Settings(jev_provider="laya_then_hosted"), BOTH_KEYS, transport
    )
    assert chain.score({}, QUESTIONS) == {"x:keep_result": 0.5}
    assert chain.last_provider == "typesafe"


def test_a_non_triggering_local_status_still_fails_loudly_without_the_hosted_hop():
    seen = []

    def transport(url, key, payload, timeout):
        seen.append(url)
        raise ProviderError("http_error")

    chain = ProviderChain(
        Settings(jev_provider="laya_then_hosted"), BOTH_KEYS, transport
    )
    with pytest.raises(ProviderError, match="http_error"):
        chain.score({}, QUESTIONS)
    assert seen == [LOCAL]
    assert chain.fallback_count == 0


def test_hosted_providers_cool_down_and_the_chain_recovers_after_expiry():
    now = [1.0]
    seen = []

    def transport(url, key, payload, timeout):
        seen.append(url)
        raise ProviderError("429")

    chain = ProviderChain(
        Settings(jev_provider="laya_then_hosted"),
        BOTH_KEYS,
        transport,
        lambda: now[0],
    )
    with pytest.raises(ProviderError, match="429"):
        chain.score({}, QUESTIONS)
    # The last available provider is retried once, so the final hop appears twice.
    assert seen == [LOCAL, TYPESAFE, OPENROUTER, OPENROUTER]
    assert chain.fallback_count == 2
    with pytest.raises(ProviderError, match="cooldown"):
        chain.score({}, QUESTIONS)
    now[0] = 100
    chain.transport = lambda *a: {"answers": {"x:keep_result": {"noul": 0.2}}}
    assert chain.score({}, QUESTIONS) == {"x:keep_result": 0.2}
    assert chain.last_provider == "laya"


def test_the_mode_never_prints_a_key_value():
    chain = ProviderChain(
        Settings(jev_provider="laya_then_hosted"),
        {"TYPESAFE_API_KEY": "SECRET_A", "OPENROUTER_API_KEY": "SECRET_B"},
        lambda *a: {},
    )
    diagnostics = repr(chain.diagnostics())
    assert "SECRET_" not in diagnostics
    assert "TYPESAFE_API_KEY" in diagnostics and "OPENROUTER_API_KEY" in diagnostics


def test_the_three_provider_modes_keep_their_own_chain_shapes():
    local_only = ProviderChain(Settings(jev_provider="laya"), BOTH_KEYS, lambda *a: {})
    assert local_only.order == ["laya"]
    auto = ProviderChain(Settings(), BOTH_KEYS, lambda *a: {})
    assert auto.order == ["typesafe", "openrouter"]
    assert "laya" not in auto.order
    keyless_auto = ProviderChain(Settings(), {}, lambda *a: {})
    assert keyless_auto.order == []
    with pytest.raises(ValueError, match="invalid jev_fallback_order"):
        Settings(jev_fallback_order=("laya",))
    with pytest.raises(ValueError, match="invalid jev_fallback_order"):
        Settings(jev_fallback_order=("typesafe", "laya"))
    assert Settings(jev_provider="laya_then_hosted").jev_provider == "laya_then_hosted"
    with pytest.raises(ValueError, match="invalid jev_provider"):
        Settings(jev_provider="laya_then_local")


def test_a_weak_local_answer_never_triggers_the_hosted_fallback():
    """Only a local exception falls through, never a low or wrong local score.

    The retained-state decision belongs to the threshold and the calibrator, so
    a local answer of zero is still a local answer and stays on the machine.
    """
    seen = []

    def transport(url, key, payload, timeout):
        seen.append(url)
        return {"answers": {q: {"noul": 0.0} for q in payload["questions"]}}

    chain = ProviderChain(
        Settings(jev_provider="laya_then_hosted"), BOTH_KEYS, transport
    )
    assert chain.score({}, QUESTIONS) == {"x:keep_result": 0.0}
    assert seen == [LOCAL]
    assert chain.last_provider == "laya"
    assert chain.fallback_count == 0
    assert chain.diagnostics()["last_errors"] == {}

    weak = ProviderChain(
        Settings(jev_provider="laya_then_hosted", keep_threshold=0.99),
        BOTH_KEYS,
        transport,
    )
    assert weak.score({"note": "weak span"}, QUESTIONS) == {"x:keep_result": 0.0}
    assert [url for url in seen if url != LOCAL] == []
    assert weak.diagnostics()["last_errors"] == {}
