"""Shrink ladder: token budgets, tiers, and oversized candidates."""

from jev_lcm_hermes_compaction.anchors import Candidate
from jev_lcm_hermes_compaction.settings import Settings
from jev_lcm_hermes_compaction.state_shaper import (
    candidate_priority,
    ordered_candidates,
    shape,
    tokens,
)


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


def _candidate(name, **kwargs):
    """A small, real candidate; `name` only labels the assertion message."""
    base = {
        "id": name,
        "kind": "tool",
        "message_index": 10,
        "text": "evidence " + name,
        "start": 1,
    }
    base.update(kwargs)
    return Candidate(**base)


def test_the_batch_cap_admits_the_longest_starved_candidate_first():
    """The cap re-scopes by need, not by arrival order.

    Taking a prefix of the candidates in insertion order deferred everything
    after the cap, batch after batch, with nothing recording the drop: a
    candidate that arrived after the last slot never reached the head of the
    list, so it was never scored at all. The per-candidate drop count leads the
    ordering, so a candidate that already waited out a batch is considered
    before one that has not, and the queue drains.
    """
    first = _candidate("first")
    second = _candidate("second")
    second.jev_dropped_batches = 1
    assert ordered_candidates([first, second])[0] is second
    assert candidate_priority(second) < candidate_priority(first)


def test_anchors_outrank_tool_results_at_equal_starvation():
    anchor = _candidate("anchor", kind="anchor")
    tool = _candidate("tool", kind="tool")
    assert ordered_candidates([tool, anchor])[0] is anchor


def test_recent_messages_outrank_older_ones_at_equal_starvation():
    recent = _candidate("recent", message_index=40)
    older = _candidate("older", message_index=5)
    assert ordered_candidates([older, recent])[0] is recent


def test_ordering_does_not_mutate_the_callers_list():
    candidates = [_candidate("a"), _candidate("b")]
    before = list(candidates)
    ordered_candidates(candidates)
    assert candidates == before


def test_the_ordering_is_deterministic():
    candidates = [_candidate(str(i), message_index=i) for i in range(6)]
    assert ordered_candidates(candidates) == ordered_candidates(
        list(reversed(candidates))
    )
