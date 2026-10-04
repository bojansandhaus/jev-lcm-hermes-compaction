"""The autouse credential isolation, asserted rather than assumed.

``tests/conftest.py`` strips provider credentials from the environment before
every test. That rule is easy to break by adding a test that reads a credential
whose name the existing rules do not match, and the failure is silent: the suite
still passes while the machine's real secret reaches a test asserting an empty
or a synthetic provider set.

It already happened once here. The original rule removed variables ending in
``API_KEY`` or starting with ``LCM_``, and ``CLOUDFLARE_API_TOKEN`` matches
neither, so a developer's real Cloudflare token survived isolation. These tests
keep that fix from being undone, and they cover the local slot's own variables,
which are the ones this work touches.
"""

import pytest

from jev_lcm_hermes_compaction.providers import ProviderChain
from jev_lcm_hermes_compaction.settings import Settings
from tests.conftest import CREDENTIAL_VARIABLES, is_credential


def test_the_isolation_covers_every_credential_the_chain_reads():
    """The strip list must match the provider credential map exactly.

    ``ENV`` and ``ACCOUNT_ENV`` in ``providers`` are the variables the chain
    actually reads. A credential added there and not stripped by name would
    reintroduce the leak silently, so the two sets are asserted equal.
    """
    from jev_lcm_hermes_compaction.providers import ACCOUNT_ENV, ENV

    read = set(ENV.values()) | set(ACCOUNT_ENV.values())
    stripped = set(CREDENTIAL_VARIABLES)
    assert (
        read == stripped
    ), "providers.py reads a credential the isolation does not strip: " + repr(
        sorted(read - stripped)
    )


@pytest.mark.parametrize("name", CREDENTIAL_VARIABLES)
def test_every_credential_name_is_stripped_by_the_rule(name):
    assert is_credential(name)


def test_the_rule_covers_names_that_do_not_end_in_api_key():
    """The gap that leaked a real token: ``_API_TOKEN`` matches no suffix rule."""
    assert not "CLOUDFLARE_API_TOKEN".endswith("API_KEY")
    assert is_credential("CLOUDFLARE_API_TOKEN")
    assert is_credential("CLOUDFLARE_ACCOUNT_ID")


def test_an_unrelated_variable_is_not_stripped():
    """The rule stays narrow: stripping everything would hide real bugs."""
    assert not is_credential("PATH")
    assert not is_credential("HOME")


def test_a_credential_is_absent_from_the_environment_inside_a_test():
    """Set the sentinel in the session, and the fixture must have removed it.

    The autouse fixture strips before the test body, so anything a
    ``setenv`` at collection time left behind is gone by now.
    """
    import os

    for name in CREDENTIAL_VARIABLES:
        assert name not in os.environ, name + " survived test isolation"


def test_a_pinned_provider_with_no_key_fails_rather_than_reading_the_environment():
    """Isolation makes the pin's own missing-credential path observable."""
    with pytest.raises(ValueError, match="TYPESAFE_API_KEY"):
        ProviderChain(Settings(jev_provider="typesafe"), {}, lambda *a: {})
    with pytest.raises(ValueError, match="CLOUDFLARE_API_TOKEN"):
        ProviderChain(Settings(jev_provider="clef"), {}, lambda *a: {})


def test_the_local_slot_is_reachable_without_any_credential_present():
    """The local route stays keyless, which is its privacy guarantee."""
    seen = []

    def transport(url, key, payload, timeout):
        seen.append((url, key))
        return {"answers": {q: {"noul": 0.4} for q in payload["questions"]}}

    chain = ProviderChain(Settings(jev_provider="local_only"), {}, transport)
    chain.score({}, {"x:keep_result": {}})
    assert seen == [("http://127.0.0.1:8000/v1/systemone", "")]
