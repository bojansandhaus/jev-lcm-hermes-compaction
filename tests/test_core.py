import json
import pytest
from jev_lcm_hermes_compaction.calibration import JevThresholdCalibrator
from jev_lcm_hermes_compaction.settings import Settings, endpoint
from jev_lcm_hermes_compaction.jev_client import (
    parse_answers,
    ProviderError,
    NoRedirect,
)
from jev_lcm_hermes_compaction.providers import ProviderChain
from jev_lcm_hermes_compaction.anchors import Candidate, extract
from jev_lcm_hermes_compaction.decisions import decide, questions
from jev_lcm_hermes_compaction.state_shaper import shape, tokens
from jev_lcm_hermes_compaction.metrics import Metrics
from jev_lcm_hermes_compaction.prepass import Prepass


@pytest.mark.parametrize("values", [[], [0.1], [i / 2500 for i in range(500)]])
def test_quantile_and_floor(values):
    c = JevThresholdCalibrator()
    c.observe(values)
    assert len(c.retained_indices(values)) >= len(values) * 0.1
    if len(values) == 500:
        assert c.current == pytest.approx(0.01996)
    c = JevThresholdCalibrator(conservative=True)
    assert c.observe([0.1] * 50) == 0
    c = JevThresholdCalibrator(enabled=False)
    assert c.observe([0.1] * 500) == 0.15


@pytest.mark.parametrize("kw", [{"window": 0}, {"minimum": 501}, {"cap": 2}])
def test_bad_calibrator(kw):
    with pytest.raises(ValueError):
        JevThresholdCalibrator(**kw)


def test_bad_sample():
    with pytest.raises(ValueError):
        JevThresholdCalibrator().observe([float("nan")])


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


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"answers": {}},
        {"answers": {"x": {"noul": True}}},
        {"answers": {"x": {"noul": 2}}},
    ],
)
def test_malformed(data):
    with pytest.raises(ProviderError):
        parse_answers(data, ["x"])


def test_parse_and_redirection():
    assert parse_answers({"answers": {"x": {"noul": 0}}}, ["x"]) == {"x": 0.0}
    assert str(ProviderError("private-key-value")) == "transport_error"
    assert (
        NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere")
        is None
    )


@pytest.mark.parametrize(
    "provider,key",
    [("typesafe", "TYPESAFE_API_KEY"), ("openrouter", "OPENROUTER_API_KEY")],
)
def test_single_provider(provider, key):
    chain = ProviderChain(
        Settings(jev_provider=provider),
        {key: "private"},
        lambda *a: {"answers": {"x": {"noul": 0.19}}},
    )
    assert chain.score({}, {"x": {}}) == {"x": 0.19}
    assert chain.last_provider == provider
    with pytest.raises(ValueError, match=key):
        ProviderChain(Settings(jev_provider=provider), {})


def test_failures_cooldown_recovery_and_secret_safety(caplog):
    now = [1.0]

    def fail(*a):
        raise ProviderError("429")

    chain = ProviderChain(
        Settings(),
        {"TYPESAFE_API_KEY": "SECRET_A", "OPENROUTER_API_KEY": "SECRET_B"},
        fail,
        lambda: now[0],
    )
    with pytest.raises(ProviderError):
        chain.score({}, {})
    assert chain.fallback_count == 1
    with pytest.raises(ProviderError, match="cooldown"):
        chain.score({}, {})
    now[0] = 100
    chain.transport = lambda *a: {"answers": {}}
    assert chain.score({}, {}) == {}
    assert chain.last_provider == "typesafe"
    assert "SECRET_" not in caplog.text + json.dumps(chain.diagnostics())
    with pytest.raises(ProviderError, match="disabled"):
        ProviderChain(Settings(), {}).score({}, {})
    assert (
        len(
            ProviderChain(
                Settings(jev_fallback_enabled=False),
                {"TYPESAFE_API_KEY": "a", "OPENROUTER_API_KEY": "b"},
            ).order
        )
        == 1
    )
    chain = ProviderChain(
        Settings(), {"TYPESAFE_API_KEY": "a"}, lambda *a: {"bogus": True}
    )
    with pytest.raises(ProviderError, match="malformed"):
        chain.score({}, {"x": {}})
    chain = ProviderChain(
        Settings(jev_fallback_max_retries=0),
        {"TYPESAFE_API_KEY": "a"},
        lambda *a: 1 / 0,
    )
    with pytest.raises(ProviderError, match="transport_error"):
        chain.score({}, {})


@pytest.mark.parametrize(
    "kind,a,b,action",
    [
        ("tool", 0.1, 0.2, "keep"),
        ("tool", 0.2, 0.1, "truncate"),
        ("tool", 0.1, 0.1, "drop"),
        ("anchor", 0.2, 0.1, "keep"),
        ("anchor", 0.1, 0.1, "drop"),
    ],
)
def test_decisions(kind, a, b, action):
    c = Candidate("x", kind, 1, "exact")
    names = list(questions(c))
    decide(c, {names[0]: a, names[1]: b}, 0.15)
    assert c.action == action and not c.jev_unscored


def test_spans_and_tiers():
    text = 'We must keep `abc123def456` and "src/a.py" at v1.2.3.'
    spans = extract(text, Settings().jev_anchor_patterns)
    assert all(text[a:b] == s for a, b, s in spans)
    assert any(s == "`abc123def456`" for _, _, s in spans)
    assert extract("abc", ("^",)) == []
    c = Candidate("x", "anchor", 1, "abc123def456")
    for count in (1, 100, 10000):
        messages = [
            {"role": "tool", "content": "中文字" * count},
            {
                "role": "assistant",
                "content": "x" * count,
                "tool_calls": [{"function": {"arguments": "x" * count}}],
            },
        ]
        settings = Settings(max_state_tokens=1500, max_request_tokens=3000)
        state, qs, selected, tier = shape(messages, [c], settings)
        assert tokens(state) <= settings.max_state_tokens
        assert (
            tokens(
                {"model": settings.openrouter_model, "state": state, "questions": qs}
            )
            <= settings.max_request_tokens
        )
    state, qs, selected, tier = shape(
        [], [Candidate("big", "anchor", 1, "x" * 10000)], settings
    )
    assert selected == []


def test_metrics_warning(caplog):
    m = Metrics()
    for _ in range(3):
        m.compaction(100, 90, 1, 30)
    assert "three consecutive" in caplog.text
    assert m["lcm_recall_at_budget"] is None
    m.compaction(0, 0, 0, 0)


def test_no_keys_and_no_budget():
    settings = Settings(min_result_chars=0)
    p = Prepass(settings, ProviderChain(settings, {}))
    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "`abc123def456`"},
        {"role": "user", "content": "tail"},
    ]
    p.collect(messages, 2)
    p.flush(force=True)
    assert p.metrics["jev_fallbacks"] == 1 and p.metrics["jev_unscored_count"] > 0
    p.flush(force=True)
    p = Prepass(
        Settings(max_state_tokens=10, max_request_tokens=20),
        ProviderChain(settings, {}),
    )
    p.collect(messages, 2)
    p.flush(force=True)
    assert p.metrics["jev_calls"] == 0
    p = Prepass(settings, ProviderChain(settings, {}))
    p.flush(force=True)
    assert p.hint_block() == ""
