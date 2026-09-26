"""Laya as a local provider: keyless selection, wire shape, and fallback."""

import json
import urllib.request

import pytest

from jev_lcm_hermes_compaction.jev_client import ProviderError, post
from jev_lcm_hermes_compaction.providers import ProviderChain
from jev_lcm_hermes_compaction.settings import Settings

QUESTIONS = {"x:keep_result": {"type": "noul", "instructions": "keep?"}}
LOCAL = "http://127.0.0.1:8000/v1/systemone"


def answering(url, key, payload, timeout):
    return {"answers": {q: {"noul": 0.23} for q in payload["questions"]}}


def test_a_pinned_local_provider_needs_no_credential():
    chain = ProviderChain(Settings(jev_provider="laya"), {}, answering)
    assert chain.order == ["laya"]
    assert chain.score({}, QUESTIONS) == {"x:keep_result": 0.23}
    assert chain.last_provider == "laya"
    assert chain.diagnostics()["keys_present"] == []


def test_the_local_provider_sends_the_decisions_wire_shape_to_the_configured_endpoint():
    seen = {}

    def transport(url, key, payload, timeout):
        seen.update(url=url, key=key, payload=payload)
        return {"answers": {q: {"noul": 0.4} for q in payload["questions"]}}

    chain = ProviderChain(
        Settings(
            jev_provider="laya",
            laya_base_url="http://127.0.0.1:9111",
            laya_endpoint_path="/v1/systemone",
            laya_model="typed-decisions",
        ),
        {},
        transport,
    )
    chain.score({"history": []}, QUESTIONS)
    assert seen["url"] == "http://127.0.0.1:9111/v1/systemone"
    assert seen["key"] == ""
    assert seen["payload"]["model"] == "typed-decisions"
    assert set(seen["payload"]) == {"model", "state", "questions"}
    assert seen["payload"]["questions"] == QUESTIONS


def test_the_local_provider_is_skipped_when_its_server_is_not_running():
    def dead(url, key, payload, timeout):
        raise ProviderError("transport_error")

    chain = ProviderChain(Settings(jev_provider="laya"), {}, dead)
    with pytest.raises(ProviderError, match="transport_error"):
        chain.score({}, QUESTIONS)
    assert chain.calls == 1 + Settings().jev_fallback_max_retries


def test_the_local_mode_replaces_the_hosted_providers_rather_than_joining_them():
    seen = []

    def transport(url, key, payload, timeout):
        seen.append(url)
        return {"answers": {q: {"noul": 0.61} for q in payload["questions"]}}

    chain = ProviderChain(
        Settings(jev_provider="laya"),
        {"TYPESAFE_API_KEY": "private", "OPENROUTER_API_KEY": "private"},
        transport,
    )
    assert chain.order == ["laya"]
    assert chain.score({}, QUESTIONS) == {"x:keep_result": 0.61}
    assert seen == [LOCAL]
    assert chain.fallback_count == 0
    assert chain.last_provider == "laya"


def test_the_hosted_chain_never_selects_the_local_provider_on_its_own():
    hosted_keys = {"TYPESAFE_API_KEY": "private", "OPENROUTER_API_KEY": "private"}
    both = ProviderChain(Settings(), hosted_keys, answering)
    assert both.order == ["typesafe", "openrouter"]

    def unreachable(url, key, payload, timeout):
        raise AssertionError("no provider should be reachable without a key")

    keyless = ProviderChain(Settings(), {}, unreachable)
    assert keyless.order == []
    with pytest.raises(ProviderError, match="disabled"):
        keyless.score({}, QUESTIONS)


def test_a_local_chain_entry_is_rejected_because_it_is_not_a_fallback_member():
    with pytest.raises(ValueError, match="invalid jev_fallback_order"):
        Settings(jev_fallback_order=("typesafe", "laya"))
    with pytest.raises(ValueError, match="invalid jev_fallback_order"):
        Settings(jev_fallback_order=("laya",))


def test_a_configured_server_token_is_forwarded_and_reported_without_its_value():
    seen = {}

    def transport(url, key, payload, timeout):
        seen["key"] = key
        return {"answers": {q: {"noul": 0.5} for q in payload["questions"]}}

    chain = ProviderChain(
        Settings(jev_provider="laya"), {"LAYA_API_KEY": "private-local"}, transport
    )
    chain.score({}, QUESTIONS)
    assert seen["key"] == "private-local"
    assert chain.diagnostics()["keys_present"] == ["LAYA_API_KEY"]
    assert "private-local" not in str(chain.diagnostics())


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Type": "application/json"},
        {"Authorization": "Bearer local", "Content-Type": "application/json"},
    ],
)
def test_the_wire_client_only_sends_an_authorization_header_for_a_key(
    monkeypatch, headers
):
    captured = {}

    class Handler:
        def __init__(self, request, timeout):
            captured["headers"] = {
                key.title(): value for key, value in request.header_items()
            }
            captured["url"] = request.full_url

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, *args):
            return json.dumps({"answers": {}}).encode()

    class Opener:
        def open(self, request, timeout=None):
            return Handler(request, timeout)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *h: Opener())
    key = headers.get("Authorization", "").removeprefix("Bearer ")
    post(LOCAL, key, {"questions": {}}, 5.0)
    assert captured["headers"] == headers
    assert captured["url"] == LOCAL


def test_the_local_endpoint_is_validated_like_every_other_provider():
    default = Settings()
    assert default.laya_base_url == "http://127.0.0.1:8000"
    assert default.laya_endpoint_path == "/v1/systemone"
    assert default.laya_model == "convaiinnovations/laya"
    assert Settings().jev_provider == "auto"
    assert Settings(jev_provider="laya").jev_provider == "laya"
    assert Settings().jev_fallback_order == ("typesafe", "openrouter")
    with pytest.raises(ValueError, match="invalid jev_provider"):
        Settings(jev_provider="local")
    with pytest.raises(ValueError, match="invalid jev_fallback_order"):
        Settings(jev_fallback_order=("typesafe", "local"))
    with pytest.raises(ValueError, match="nonlocal provider requires HTTPS"):
        Settings(laya_base_url="http://192.168.1.10:8000")
    assert (
        Settings(laya_base_url="https://laya.example").laya_base_url
        == "https://laya.example"
    )
