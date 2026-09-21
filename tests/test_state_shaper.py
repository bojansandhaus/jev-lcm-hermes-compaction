"""Shrink ladder: token budgets, tiers, and oversized candidates."""

from jev_lcm_hermes_compaction.anchors import Candidate
from jev_lcm_hermes_compaction.settings import Settings
from jev_lcm_hermes_compaction.state_shaper import shape, tokens


def test_spans_and_tiers():
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
