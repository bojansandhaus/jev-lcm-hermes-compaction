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
#   - `_pre_test` rejects a pattern outright when none of its trigger words are
#     present, which is the case that was pathological. That drops the same
#     64 KB input to 3 milliseconds, and costs one cheap linear scan when the
#     pattern is relevant.
#
# The trigger list is read out of the pattern string rather than written beside
# it. The first version of this guard kept its own list of three words while the
# pattern matched on six, so every sentence carrying only `must`, `never` or
# `always` returned no span at all: a silent correctness regression hiding
# behind a performance fix. `_triggers` derives the list, and
# `tests/test_reason_trigger_gate.py` asserts the derived set.

# A literal alternation group: the shape whose members every match contains.
# A character class is excluded from the body so a `|` inside one is never read
# as a separator.
_LITERAL_GROUP = re.compile(r"\(\?:([^()\[\]]*)\)")
# One alternative of such a group: a plain word carrying no metacharacter.
_LITERAL_ALTERNATIVE = re.compile(r"[A-Za-z][A-Za-z0-9 _-]*\Z")
# A counted repeat of a character class. This is the bounded window that makes
# a pattern expensive on a long input, so it is also what marks a pattern as
# worth guarding.
_BOUNDED_WINDOW = re.compile(r"\[[^\]\n]*\]\{\d+,\d*\}")


def _triggers(pattern: str) -> tuple[str, ...]:
    """Every word a literal alternation inside ``pattern`` can match.

    Read out of the pattern, so editing an alternation edits this with it. Every
    group contributes rather than the first one, because a pattern may carry
    more than one and a union can only ever let more text through, never less.
    Empty when the pattern has no literal alternation to pre-test against.
    """
    words: list[str] = []
    for group in _LITERAL_GROUP.finditer(pattern):
        parts = [part.strip() for part in group.group(1).split("|")]
        if len(parts) > 1 and all(_LITERAL_ALTERNATIVE.match(p) for p in parts):
            words.extend(p for p in parts if p not in words)
    return tuple(words)


def _pre_test(pattern: str) -> re.Pattern[str] | None:
    """A cheap scan that proves ``pattern`` cannot match, or ``None``.

    A pattern that repeats a bounded window has to be retried from every offset
    of a long input, and it can only match text containing one of the words of
    the literal alternation inside it. Returning early when none of those words
    appears is a necessary condition, never a filter on the result: any text the
    pattern would match contains its own trigger word, so the pre-test cannot
    drop a span.
    """
    if not _BOUNDED_WINDOW.search(pattern):
        return None
    words = _triggers(pattern)
    return re.compile("|".join(words), re.IGNORECASE) if words else None


_COMPILED: dict[str, re.Pattern[str]] = {}
_GATES: dict[str, re.Pattern[str] | None] = {}


def _compiled(pattern: str) -> re.Pattern[str]:
    """Compile once. `re` caches internally, but only up to 512 patterns and the
    cache is global, so an explicit per-pattern dict avoids both the lookup and
    the eviction for a hot path that runs on every turn."""
    found = _COMPILED.get(pattern)
    if found is None:
        found = re.compile(pattern)
        _COMPILED[pattern] = found
    return found


def _gate(pattern: str) -> re.Pattern[str] | None:
    """The pre-test for ``pattern``, derived once per distinct pattern string."""
    if pattern not in _GATES:
        _GATES[pattern] = _pre_test(pattern)
    return _GATES[pattern]


def extract(text: str, patterns: tuple[str, ...]) -> list[tuple[int, int, str]]:
    spans: set[tuple[int, int]] = set()
    for pattern in patterns:
        pre_test = _gate(pattern)
        if pre_test is not None and not pre_test.search(text):
            continue
        for match in _compiled(pattern).finditer(text):
            if match.end() > match.start():
                spans.add(match.span())
    return [(a, b, text[a:b]) for a, b in sorted(spans)]
