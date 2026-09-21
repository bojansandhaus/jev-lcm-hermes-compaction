"""Provider chain: selection, fail fast, and OpenRouter response parity."""

import importlib.util
import json

import pytest

from jev_lcm_hermes_compaction.jev_client import ProviderError
from jev_lcm_hermes_compaction.providers import ProviderChain
from jev_lcm_hermes_compaction.settings import Settings

CHAT_SURFACE = {
    "jev_provider": "openrouter",
    "openrouter_base_url": "https://openrouter.ai/api/v1",
    "openrouter_endpoint_path": "/chat/completions",
}


def test_primary_rate_limit_uses_fallback_without_exposing_secret():
    assert importlib.util.find_spec(
        "jev_lcm_hermes_compaction.providers"
    ), "provider chain missing"
    from jev_lcm_hermes_compaction.providers import ProviderChain, ProviderError
    from jev_lcm_hermes_compaction.settings import Settings

    seen = []

    def transport(url, key, payload, timeout):
        seen.append(url)
        if "typesafe" in url:
            raise ProviderError("429")
        return {"answers": {"x": {"noul": 0.19}}}

    chain = ProviderChain(
        Settings(),
        {"TYPESAFE_API_KEY": "private-one", "OPENROUTER_API_KEY": "private-two"},
        transport,
    )
    assert (
        chain.score({}, {"x": {"type": "noul", "instructions": "keep?"}})["x"] == 0.19
    )
    assert len(seen) == 2
    assert chain.fallback_count == 1
    assert chain.last_provider == "openrouter"
    assert "private-" not in str(chain.diagnostics())


@pytest.mark.parametrize(
    "provider,key",
    [("typesafe", "TYPESAFE_API_KEY"), ("openrouter", "OPENROUTER_API_KEY")],
)
def test_single_provider(provider, key):
    chain = ProviderChain(
        Settings(jev_provider=provider),
        {key: "private"},
        lambda *a: {"answers": {"x": {"noul": 0.19}}},
    )
    assert chain.score({}, {"x": {}}) == {"x": 0.19}
    assert chain.last_provider == provider
    with pytest.raises(ValueError, match=key):
        ProviderChain(Settings(jev_provider=provider), {})


def test_openrouter_chat_adapter_matches_the_native_decisions_surface():
    from jev_lcm_hermes_compaction.providers import ProviderChain
    from jev_lcm_hermes_compaction.settings import Settings

    answers = {"x:keep_result": {"noul": 0.42}, "y:keep_result": {"noul": 0.07}}
    questions = {
        "x:keep_result": {"type": "noul", "instructions": "keep?"},
        "y:keep_result": {"type": "noul", "instructions": "keep?"},
    }
    seen = {}

    def chat_transport(url, key, payload, timeout):
        seen["chat"] = (url, payload)
        body = {"answers": answers}
        return {
            "choices": [{"message": {"role": "assistant", "content": json.dumps(body)}}]
        }

    def decisions_transport(url, key, payload, timeout):
        seen["native"] = (url, payload)
        return {"answers": answers}

    chat = ProviderChain(
        Settings(**CHAT_SURFACE), {"OPENROUTER_API_KEY": "private"}, chat_transport
    )
    native = ProviderChain(
        Settings(
            jev_provider="openrouter",
            openrouter_base_url="https://openrouter.ai/api",
            openrouter_endpoint_path="/alpha/decisions",
        ),
        {"OPENROUTER_API_KEY": "private"},
        decisions_transport,
    )
    assert (
        chat.score({}, questions)
        == native.score({}, questions)
        == {
            "x:keep_result": 0.42,
            "y:keep_result": 0.07,
        }
    )
    assert seen["chat"][0] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["native"][0] == "https://openrouter.ai/api/alpha/decisions"
    body = seen["chat"][1]
    assert body["model"] == Settings().openrouter_model
    assert Settings().openrouter_base_url == "https://openrouter.ai/api"
    assert Settings().openrouter_endpoint_path == "/alpha/decisions"
    assert body["messages"][0]["role"] == "system"
    assert seen["native"][1]["questions"] == questions
    assert json.loads(body["messages"][1]["content"])["questions"] == questions


@pytest.mark.parametrize(
    "completion",
    [
        None,
        {},
        {"choices": []},
        {"choices": ["text"]},
        {"choices": [{"message": {"content": ""}}]},
        {"choices": [{"message": {"content": "not json"}}]},
        {"choices": [{"message": {"content": '{"answers": {}}'}}]},
        {"choices": [{"message": {"content": 17}}]},
    ],
)
def test_openrouter_chat_adapter_rejects_malformed_completions(completion):
    from jev_lcm_hermes_compaction.providers import ProviderChain
    from jev_lcm_hermes_compaction.settings import Settings

    chain = ProviderChain(
        Settings(**CHAT_SURFACE),
        {"OPENROUTER_API_KEY": "private"},
        lambda *a: completion,
    )
    with pytest.raises(ProviderError, match="malformed"):
        chain.score({}, {"x:keep_result": {}})


def test_openrouter_chat_adapter_unwraps_fences_and_scalar_answers():
    from jev_lcm_hermes_compaction.providers import ProviderChain
    from jev_lcm_hermes_compaction.settings import Settings

    fenced = "```json\n" + json.dumps({"answers": {"x:keep_result": 0.31}}) + "\n```"
    chain = ProviderChain(
        Settings(**CHAT_SURFACE),
        {"OPENROUTER_API_KEY": "private"},
        lambda *a: {"choices": [{"message": {"content": fenced}}]},
    )
    assert chain.score({}, {"x:keep_result": {}}) == {"x:keep_result": 0.31}


def test_openrouter_path_passes_a_decisions_shaped_gateway_response_through():
    from jev_lcm_hermes_compaction.providers import ProviderChain
    from jev_lcm_hermes_compaction.settings import Settings

    chain = ProviderChain(
        Settings(jev_provider="openrouter"),
        {"OPENROUTER_API_KEY": "private"},
        lambda *a: {"answers": {"x:keep_result": {"noul": 0.55}}},
    )
    assert chain.score({}, {"x:keep_result": {}}) == {"x:keep_result": 0.55}
