import os
import pytest


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    for key in list(os.environ):
        if key.endswith("API_KEY") or key.startswith("LCM_"):
            monkeypatch.delenv(key, raising=False)
