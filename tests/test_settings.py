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
        # The traversal check ran against the decoded path only, so an encoded
        # segment in the BASE was accepted whole: `urlsplit` puts it in the
        # netloc, the `..` check never saw it, and the joined URL re-decoded into
        # a traversal at the server.
        ("https://example.test-/%2e%2e/secrets", "/x"),
        ("https://example.test/%2e%2e", "/x"),
        ("https://example.test/%2E%2E/", "/x"),
    ],
)
def test_bad_endpoint(base, path):
    with pytest.raises(ValueError):
        endpoint(base, path)


def test_endpoint_accepts_a_normal_pinned_base():
    assert (
        endpoint("https://api.typesafe.ai/v1", "/systemone")
        == "https://api.typesafe.ai/v1/systemone"
    )
    assert (
        endpoint("http://127.0.0.1:8000", "/v1/systemone")
        == "http://127.0.0.1:8000/v1/systemone"
    )
