"""Exact source spans; overlapping matches are retained without rewriting."""

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Candidate:
    id: str
    kind: str
    message_index: int
    text: str
    start: int = 0
    end: int = 0
    store_id: int | None = None
    call: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    action: str = "unscored"
    jev_unscored: bool = True


# `anchors.extract` runs over every assistant message on every turn, so the cost
# of a pattern is multiplied by the whole backlog. Two guards, both measured:
#
#   - The reason-sentence pattern below has a bounded 400-character window
#     either side of its trigger word. Its previous form was unbounded, so on a
#     long string with no sentence terminator and no trigger word (minified
#     JSON, base64, a path) the engine retried the greedy prefix from every
#     offset: 49 seconds on a 64 KB input, in linear-looking but quadratic
#     practice. Bounded, the same input costs 0.6 seconds.
#   - `_NEEDS_TRIGGER` rejects the pattern outright when the trigger words are
#     absent, which is the case that was pathological. That drops the same
#     64 KB input to 3 milliseconds, and costs one cheap linear scan when the
#     pattern is relevant.
_REASON_TRIGGER = re.compile(r"root cause|because|constraint", re.IGNORECASE)


def _needs_reason_trigger(pattern: str) -> bool:
    """True when this is a reason-sentence pattern needing the pre-test.

    Identified by the trigger alternation it contains rather than by an index or
    a hand-maintained list, so a future pattern that shares the shape is guarded
    automatically.
    """
    return "root cause" in pattern and "because" in pattern


_COMPILED: dict[str, re.Pattern[str]] = {}


def _compiled(pattern: str) -> re.Pattern[str]:
    """Compile once. `re` caches internally, but only up to 512 patterns and the
    cache is global, so an explicit per-pattern dict avoids both the lookup and
    the eviction for a hot path that runs on every turn."""
    found = _COMPILED.get(pattern)
    if found is None:
        found = re.compile(pattern)
        _COMPILED[pattern] = found
    return found


def extract(text: str, patterns: tuple[str, ...]) -> list[tuple[int, int, str]]:
    spans: set[tuple[int, int]] = set()
    for pattern in patterns:
        if _needs_reason_trigger(pattern) and not _REASON_TRIGGER.search(text):
            continue
        for match in _compiled(pattern).finditer(text):
            if match.end() > match.start():
                spans.add(match.span())
    return [(a, b, text[a:b]) for a, b in sorted(spans)]
