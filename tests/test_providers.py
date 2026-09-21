import importlib.util


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
