import json
import os

import pytest

from jev_lcm_hermes_compaction import providers

# Every environment variable that carries a provider credential, or the
# configuration a credential's endpoint cannot be built without. These are
# stripped by name rather than by suffix: the original rule removed names
# ending in ``API_KEY`` or starting with ``LCM_``, which matches neither
# ``CLOUDFLARE_API_TOKEN`` nor ``CLOUDFLARE_ACCOUNT_ID``. That gap let a
# developer's real Cloudflare environment reach a test asserting an empty
# ``keys_present``. A test that reads a credential must never see the machine's.
CREDENTIAL_VARIABLES: tuple[str, ...] = (
    "TYPESAFE_API_KEY",
    "OPENROUTER_API_KEY",
    "LAYA_API_KEY",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_ACCOUNT_ID",
)


def is_credential(name: str) -> bool:
    """Whether ``name`` is stripped from the environment before a test runs."""
    return (
        name.endswith("API_KEY")
        or name.startswith("LCM_")
        or name in CREDENTIAL_VARIABLES
    )


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    for key in list(os.environ):
        if is_credential(key):
            monkeypatch.delenv(key, raising=False)
    # The local-hop breaker counts failures per process, so a test that fails
    # the local provider must not charge the next test's counter. The timestamp
    # that bounds the count is reset beside it, so no test inherits the window
    # from the one before it.
    monkeypatch.setattr(providers, "_laya_failure_count", 0)
    monkeypatch.setattr(providers, "_laya_last_failure_at", None)


def synthetic_transport(score: float = 0.99):
    """Answer whichever surface the provider is configured for.

    The Decisions surface receives a ``questions`` mapping, the chat completions
    surface receives ``messages``. Tests stay indifferent to that choice.
    """

    def transport(url, key, payload, timeout):
        if "messages" in payload:
            body = json.loads(payload["messages"][1]["content"])
            answers = {"answers": {q: {"noul": score} for q in body["questions"]}}
            return {"choices": [{"message": {"content": json.dumps(answers)}}]}
        return {"answers": {q: {"noul": score} for q in payload["questions"]}}

    return transport
