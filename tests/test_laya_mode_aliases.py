"""Three named arrangements, and the alias names that select the same ones.

This package already had the three behaviours: a hosted Jev chain (`auto`),
Laya alone (`laya`), and Laya with the hosted providers behind it
(`laya_then_hosted`). The alternative names ``jev_api``, ``laya_local``, and
``laya_with_jev_fallback`` resolve to those same three, so an operator can use
either vocabulary and get one chain, one privacy boundary, and one local-hop
breaker. Every previously accepted value keeps behaving as it did, and anything
else is rejected with the accepted names in the error.
"""

import pytest

from jev_lcm_hermes_compaction.providers import ProviderChain
from jev_lcm_hermes_compaction.settings import Settings

BOTH_KEYS = {"TYPESAFE_API_KEY": "private-one", "OPENROUTER_API_KEY": "private-two"}
ALIASES = [
    ("jev_api", "auto"),
    ("laya_local", "laya"),
    ("laya_with_jev_fallback", "laya_then_hosted"),
]


@pytest.mark.parametrize("alias,canonical", ALIASES)
def test_an_alias_resolves_to_the_canonical_value(alias, canonical):
    assert Settings(jev_provider=alias) == Settings(jev_provider=canonical)
    assert Settings(jev_provider=alias).jev_provider == canonical


@pytest.mark.parametrize("alias,canonical", ALIASES)
def test_an_alias_builds_the_same_chain_as_the_canonical_value(alias, canonical):
    aliased = ProviderChain(Settings(jev_provider=alias), BOTH_KEYS, lambda *a: {})
    exact = ProviderChain(Settings(jev_provider=canonical), BOTH_KEYS, lambda *a: {})
    assert aliased.order == exact.order
    assert aliased.diagnostics() == exact.diagnostics()


@pytest.mark.parametrize(
    "value,expected_order",
    [
        ("auto", ["typesafe", "openrouter"]),
        ("typesafe", ["typesafe"]),
        ("openrouter", ["openrouter"]),
        ("laya", ["laya"]),
        ("laya_then_hosted", ["laya", "typesafe", "openrouter"]),
        ("laya_local", ["laya"]),
        ("laya_with_jev_fallback", ["laya", "typesafe", "openrouter"]),
        ("jev_api", ["typesafe", "openrouter"]),
    ],
)
def test_every_accepted_value_keeps_its_own_chain(value, expected_order):
    chain = ProviderChain(Settings(jev_provider=value), BOTH_KEYS, lambda *a: {})
    assert chain.order == expected_order


def test_an_unknown_value_is_rejected_and_names_the_accepted_values():
    with pytest.raises(ValueError) as error:
        Settings(jev_provider="laya_then_jev")
    message = str(error.value)
    assert "invalid jev_provider" in message
    for name in (
        "auto",
        "typesafe",
        "openrouter",
        "laya",
        "laya_then_hosted",
        "jev_api",
        "laya_local",
        "laya_with_jev_fallback",
    ):
        assert name in message


def test_a_rejected_value_never_reaches_a_chain():
    with pytest.raises(ValueError):
        ProviderChain(
            Settings(jev_provider="laya_then_local"), BOTH_KEYS, lambda *a: {}
        )


def test_the_alias_table_and_the_canonical_modes_cannot_drift():
    from jev_lcm_hermes_compaction.settings import PROVIDER_ALIASES, PROVIDER_MODES

    assert set(PROVIDER_ALIASES.values()) <= set(PROVIDER_MODES)
    assert not set(PROVIDER_ALIASES) & set(PROVIDER_MODES)
