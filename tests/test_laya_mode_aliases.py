"""The four canonical modes, and every alias that selects one of them.

This package now names four arrangements, each of which says which side leads
and whether the other side is a fallback:

| Mode | Leads | Fallback |
|---|---|---|
| ``api_with_local_fallback`` | hosted API | local |
| ``api_only`` | hosted API | none |
| ``local_only`` | local | none |
| ``local_with_api_fallback`` | local | hosted API |

Every name this package previously accepted still resolves, and each resolves
to the canonical mode that reproduces the routing decision it produced before
this vocabulary existed. That is the property these tests pin: not that an alias
is accepted, but that the chain it builds is the chain it used to build.

``auto`` keeps this repository's existing meaning rather than the generic one.
It resolves the hosted side by credential from ``jev_fallback_order`` and never
selects the local slot on its own initiative, so a default profile still gets
exactly the chain it got before. ``typesafe``, ``openrouter``, ``clef``, and
``clef_api`` name a hosted provider to pin, which is why they resolve to
``api_only`` *with a pin* rather than to an order read from the fallback list.
"""

import pytest

from jev_lcm_hermes_compaction.providers import ProviderChain
from jev_lcm_hermes_compaction.settings import Settings

BOTH_KEYS = {"TYPESAFE_API_KEY": "private-one", "OPENROUTER_API_KEY": "private-two"}
CLEF_CREDENTIALS = {
    "CLOUDFLARE_API_TOKEN": "private-token",
    "CLOUDFLARE_ACCOUNT_ID": "private-account",
}
# Every name this package accepted before the four-mode vocabulary that resolves
# to a mode on its own, and the canonical mode it now denotes.
ALIASES = [
    ("auto", "api_only"),
    ("jev_api", "api_only"),
    ("laya", "local_only"),
    ("laya_local", "local_only"),
    ("laya_then_hosted", "local_with_api_fallback"),
    ("laya_with_jev_fallback", "local_with_api_fallback"),
]
# Names that additionally pin which hosted provider leads. Each value is
# ``(name, canonical mode, pinned provider)``. They are compared against each
# other rather than against the bare canonical mode, because a pin is part of
# what the name means: ``typesafe`` is a TypeSafe route, not an order read from
# ``jev_fallback_order``.
PINS = [
    ("typesafe", "api_only", "typesafe"),
    ("openrouter", "api_only", "openrouter"),
    ("clef", "api_only", "clef"),
    ("clef_api", "api_only", "clef"),
]


@pytest.mark.parametrize("alias,canonical", ALIASES)
def test_an_alias_resolves_to_the_canonical_value(alias, canonical):
    """An alias is replaced by the canonical mode, never carried downstream."""
    assert Settings(jev_provider=alias).jev_provider == canonical


@pytest.mark.parametrize("alias,canonical", ALIASES)
def test_an_alias_builds_the_same_chain_as_the_canonical_value(alias, canonical):
    """The resolved mode and the resulting provider order are what matters."""
    aliased = ProviderChain(Settings(jev_provider=alias), BOTH_KEYS, lambda *a: {})
    exact = ProviderChain(Settings(jev_provider=canonical), BOTH_KEYS, lambda *a: {})
    assert aliased.order == exact.order
    assert aliased.diagnostics() == exact.diagnostics()


@pytest.mark.parametrize("name,canonical,pin", PINS)
def test_a_pinned_name_resolves_to_a_mode_and_keeps_its_pin(name, canonical, pin):
    settings = Settings(jev_provider=name)
    assert settings.jev_provider == canonical
    assert settings.jev_provider_pin == pin


def test_both_spellings_of_a_pin_build_one_identical_chain():
    """``clef`` and ``clef_api`` name one route, not two."""
    aliased = ProviderChain(
        Settings(jev_provider="clef_api"), CLEF_CREDENTIALS, lambda *a: {}
    )
    exact = ProviderChain(
        Settings(jev_provider="clef"), CLEF_CREDENTIALS, lambda *a: {}
    )
    assert aliased.order == exact.order == ["clef"]
    assert aliased.diagnostics() == exact.diagnostics()


@pytest.mark.parametrize(
    "value,expected_order",
    [
        # The four canonical modes.
        ("api_with_local_fallback", ["typesafe", "openrouter", "laya"]),
        ("api_only", ["typesafe", "openrouter"]),
        ("local_only", ["laya"]),
        ("local_with_api_fallback", ["laya", "typesafe", "openrouter"]),
        # Every previously accepted name, unchanged behaviour.
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


@pytest.mark.parametrize("value", ["clef", "clef_api"])
def test_a_clef_pin_keeps_its_own_chain(value):
    chain = ProviderChain(Settings(jev_provider=value), CLEF_CREDENTIALS, lambda *a: {})
    assert chain.order == ["clef"]


def test_an_unknown_value_is_rejected_and_names_the_accepted_values():
    with pytest.raises(ValueError) as error:
        Settings(jev_provider="laya_then_jev")
    message = str(error.value)
    assert "invalid jev_provider" in message
    # Every canonical mode, every alias, and every pin appears in the error, so
    # an operator with a rejected configuration can see what is accepted without
    # consulting the documentation.
    for name in (
        "api_with_local_fallback",
        "api_only",
        "local_only",
        "local_with_api_fallback",
        "auto",
        "typesafe",
        "openrouter",
        "laya",
        "laya_then_hosted",
        "jev_api",
        "laya_local",
        "laya_with_jev_fallback",
        "clef",
        "clef_api",
    ):
        assert name in message


def test_a_rejected_value_never_reaches_a_chain():
    with pytest.raises(ValueError):
        ProviderChain(
            Settings(jev_provider="laya_then_local"), BOTH_KEYS, lambda *a: {}
        )


def test_the_alias_and_pin_tables_cannot_drift_from_the_canonical_modes():
    from jev_lcm_hermes_compaction.settings import (
        PROVIDER_ALIASES,
        PROVIDER_MODES,
        PROVIDER_PINS,
    )

    assert len(PROVIDER_MODES) == 4
    assert set(PROVIDER_ALIASES.values()) <= set(PROVIDER_MODES)
    assert not set(PROVIDER_ALIASES) & set(PROVIDER_MODES)
    # A pinned alias resolves to a canonical mode too, and to no alias name, so
    # the two tables cannot disagree about what a value means.
    for mode, _provider in PROVIDER_PINS.values():
        assert mode in PROVIDER_MODES
    assert not set(PROVIDER_PINS) & set(PROVIDER_MODES)
    assert not set(PROVIDER_PINS) & set(PROVIDER_ALIASES)


def test_no_alias_string_reaches_an_observable_output():
    """Aliases resolve before a chain, a diagnostic, or a log line sees them.

    ``laya`` is checked as a *mode* here, not as a provider name: it is a
    provider in ``chain.order`` by design, because the local slot keeps that
    name. What must never survive is an alias used where a mode belongs, which
    is why the assertion is about the resolved field rather than about every
    occurrence of the substring.
    """
    canonical = {
        "api_with_local_fallback",
        "api_only",
        "local_only",
        "local_with_api_fallback",
    }
    for alias in ("auto", "jev_api", "laya_local", "laya_then_hosted"):
        settings = Settings(jev_provider=alias)
        assert settings.jev_provider in canonical
        chain = ProviderChain(settings, BOTH_KEYS, lambda *a: {})
        # The diagnostic reports provider names and keys, never a mode alias.
        assert alias not in repr(chain.diagnostics())
        assert chain.diagnostics()["last_provider"] in (
            "",
            "typesafe",
            "openrouter",
            "clef",
            "laya",
        )
