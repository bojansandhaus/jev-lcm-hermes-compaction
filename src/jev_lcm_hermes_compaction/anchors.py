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
# The vocabulary of the reason-sentence pre-test, read out of the pattern it
# guards rather than hard-coded beside it.
#
# The previous form was `re.compile(r"root cause|because|constraint",
# re.IGNORECASE)` -- three of the shipped pattern's six terms. `must`, `never`
# and `always` were therefore absent from the guard, so the guard skipped the
# pattern on text whose only trigger was one of them, and every such sentence
# was silently dropped before candidate generation. Verified on the shipped
# pattern list, against the TypeScript sibling in
# `jevs-lcm-dsh-compaction` which had the identical defect:
#
#   'We must pin the dependency before the release.'  raw regex 1 span, extract() 0
#   'You never bypass the approval gate.'             raw regex 1 span, extract() 0
#   'The service always validates input.'             raw regex 1 span, extract() 0
#
# `_needs_reason_trigger` compounded it: it asked for two specific substrings
# (`root cause` AND `because`) to decide a pattern was reason-shaped, so a
# pattern that shared the shape without those two words lost the guard
# entirely, and paid the 49-second pathological cost from a documented operator
# setting. Reading the alternation out of the pattern makes both the guard and
# its applicability a property of the pattern, so neither can drift again.
#
# The third defect was case. The guard was `re.IGNORECASE`, the pattern was
# not, so 'Because the cache is cold, the call is slow.' passed the guard and
# was then missed by the pattern. Reason text is prose, so its trigger word's
# case depends on where it falls in the sentence; the reason-sentence pattern
# is now the one pattern compiled case-insensitively.
#
# The match is deliberately case-SENSITIVE, and that matters. This module's
# settings also ship `\b[A-Z_]{2,}_(?:KEY|TOKEN|SECRET|URL|PATH|ID)\b`, whose
# alternation is just as well formed. An ignorecase detector classified that as
# reason-shaped too and recompiled it case-insensitively, which began matching
# `superscret_key` -- the exact silent widening this fix exists to avoid. The
# TypeScript sibling hit the same trap. Requiring lowercase words keeps the
# credential pattern out; a pattern whose author writes its triggers in capitals
# simply is not treated as a reason pattern, which costs it the guard but never
# changes what it matches: the conservative direction.
_TRIGGER_GROUP = re.compile(r"\(\?:(?:(([a-z][a-z ]*\|)+[a-z][a-z ]*))\)")


def _reason_triggers(pattern: str) -> tuple[str, ...]:
    group = _TRIGGER_GROUP.search(pattern)
    if not group:
        return ()
    return tuple(
        term.strip().lower() for term in group.group(1).split("|") if term.strip()
    )


def _needs_reason_trigger(pattern: str) -> bool:
    """True when this is a reason-sentence pattern needing the pre-test.

    Identified by the trigger alternation it contains rather than by an index
    or a hand-maintained list, so a future pattern that shares the shape is
    guarded automatically.
    """
    return bool(_reason_triggers(pattern))


_COMPILED: dict[str, re.Pattern[str]] = {}
_TRIGGERS: dict[str, re.Pattern[str]] = {}


def _compiled(pattern: str) -> re.Pattern[str]:
    """Compile once, with the case policy the pattern's shape calls for.

    `re` caches internally, but only up to 512 patterns and the cache is
    global, so an explicit per-pattern dict avoids both the lookup and the
    eviction for a hot path that runs on every turn."""
    found = _COMPILED.get(pattern)
    if found is None:
        triggers = _reason_triggers(pattern)
        # Reason sentences are prose, so the trigger word's case depends on
        # where it falls in the sentence. Only the reason-sentence pattern is
        # compiled case-insensitively; forcing every pattern to `re.I` would
        # widen what the identifier and credential patterns match, which this
        # fix has no business doing.
        found = re.compile(pattern, re.IGNORECASE if triggers else 0)
        _COMPILED[pattern] = found
    return found


def _trigger_test(pattern: str) -> re.Pattern[str] | None:
    """A literal pre-test for a reason-sentence pattern, or None."""
    found = _TRIGGERS.get(pattern)
    if found is None and pattern not in _TRIGGERS:
        triggers = _reason_triggers(pattern)
        if not triggers:
            _TRIGGERS[pattern] = None  # type: ignore[assignment]
            return None
        found = re.compile("|".join(re.escape(t) for t in triggers), re.IGNORECASE)
        _TRIGGERS[pattern] = found
    return found


def extract(text: str, patterns: tuple[str, ...]) -> list[tuple[int, int, str]]:
    spans: set[tuple[int, int]] = set()
    for pattern in patterns:
        trigger = _trigger_test(pattern) if _needs_reason_trigger(pattern) else None
        # A literal scan that no trigger word is present is far cheaper than
        # running the pattern. It is now provably complete: the vocabulary is
        # the pattern's own alternation, so no trigger can be missing from it.
        if trigger is not None and not trigger.search(text):
            continue
        for match in _compiled(pattern).finditer(text):
            if match.end() > match.start():
                spans.add(match.span())
    return [(a, b, text[a:b]) for a, b in sorted(spans)]
