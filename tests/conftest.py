import json
import os

import pytest


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    for key in list(os.environ):
        if key.endswith("API_KEY") or key.startswith("LCM_"):
            monkeypatch.delenv(key, raising=False)


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
