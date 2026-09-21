"""Settings schema and endpoint validation."""

import pytest

from jev_lcm_hermes_compaction.settings import Settings, endpoint


@pytest.mark.parametrize(
    "kw",
    [
        {"jev_provider": "unknown"},
        {"jev_fallback_order": ("x",)},
        {"min_keep_rate": 2},
        {"jev_batch_window_turns": 0},
        {"max_request_tokens": 2},
        {"request_timeout_s": 0},
        {"jev_calibration_min_samples": 0},
    ],
)
def test_bad_settings(kw):
    with pytest.raises(ValueError):
        Settings(**kw)


@pytest.mark.parametrize(
    "base,path",
    [
        ("https://api.typesafe.ai/v1" + chr(92), "/systemone"),
        ("https://example.test", "/%2e%2e/secrets"),
        ("http://example.test", "/x"),
        ("https://u:p@example.test", "/x"),
        ("https://example.test", "/x?q=y"),
    ],
)
def test_bad_endpoint(base, path):
    with pytest.raises(ValueError):
        endpoint(base, path)
