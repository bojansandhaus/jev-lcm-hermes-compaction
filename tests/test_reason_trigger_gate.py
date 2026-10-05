"""The reason-sentence pre-test must not drop spans the pattern would match.

The pre-test that skips the bounded reason pattern when no trigger word is
present was added for speed: the pattern is quadratic on a long input with no
sentence terminator, and skipping it drops a 64 KB scan from 0.6 seconds to 3
milliseconds. It shipped with its own list of three trigger words while the
pattern matched on six, so every sentence carrying only `must`, `never` or
`always` returned no span. Nothing failed: the sentences simply stopped being
anchored, and the perf tests were green because a skipped pattern is fast.

These tests pin the invariant from both directions. Every word the pattern can
match on must produce a span, and the gate's word set must be the one read out
of the pattern rather than a second list written beside it.
"""

from __future__ import annotations

import re

from jev_lcm_hermes_compaction import anchors
from jev_lcm_hermes_compaction.anchors import extract
from jev_lcm_hermes_compaction.settings import Settings

PATTERNS = Settings().jev_anchor_patterns
REASON_INDEX = 2
REASON_PATTERN = PATTERNS[REASON_INDEX]


def _spans(text: str, patterns: tuple[str, ...] = PATTERNS) -> set[tuple[int, int]]:
    return {(a, b) for a, b, _ in extract(text, patterns)}


# Every alternative of the pattern's trigger alternation, spelled out. Each
# case below carries that word and nothing else from the alternation, so a gate
# that recognises only part of the pattern produces an empty result. The words
# are lower case because the pattern's own alternation is case-sensitive: a
# capitalised trigger is not a defect of the gate and is not asserted here.
TRIGGER_CASES = (
    ("root cause", "The root cause is a retry storm."),
    ("because", "The build failed because the lockfile moved."),
    ("constraint", "The constraint is a two thousand token budget."),
    ("must", "We must ship by Friday."),
    ("never", "You should never commit a credential to the repository."),
    ("always", "The runner always rebuilds the image before pushing."),
)


class TestEveryTriggerWordStillAnchors:
    def test_each_trigger_word_alone_produces_a_span(self):
        """Regression: all six cases return empty on the unfixed gate."""
        for word, text in TRIGGER_CASES:
            assert word in text.lower(), text
            spans = extract(text, PATTERNS)
            assert spans, f"a sentence whose only trigger is {word!r} produced no span"

    def test_the_reason_pattern_matches_the_text_being_dropped(self):
        """Guard against the test passing because the text matches nothing."""
        for _, text in TRIGGER_CASES:
            assert re.search(REASON_PATTERN, text), text

    def test_multi_trigger_sentences_still_anchor(self):
        for text in (
            "You must always pin versions.",
            "The team must fix it before Friday.",
            "Must never always constraint root cause because.",
        ):
            assert extract(text, PATTERNS), text


class TestGateIsDerivedFromThePattern:
    def test_gating_a_pattern_never_changes_what_it_matches(self):
        """The gate is a necessary-condition check, so it may only ever skip a
        pattern that could not have matched. Derived gates now cover more than
        one shipped pattern, which makes this worth asserting rather than
        assuming.
        """
        corpus = [
            "Nothing interesting here.",
            "OPENROUTER_API_KEY and JEV_ENDPOINT_PATH are set.",
            "The root cause is a timeout. Because of the retry loop we must fix it.",
            "You must always pin versions. The constraint is pinning, never relax it.",
            'See "docs/reference.md" and src/jev_lcm_hermes_compaction/anchors.py.',
            "line 412:9:1 mentions v1.2.3 and `token_budget` plus a03f5c9d1b.",
            "x" * 500,
            '"' + "a/" * 250,
        ]
        for pattern in PATTERNS:
            gated = {t: _spans(t, (pattern,)) for t in corpus}
            saved = anchors._GATES.get(pattern)
            anchors._GATES[pattern] = None  # disable the pre-test
            try:
                ungated = {t: _spans(t, (pattern,)) for t in corpus}
            finally:
                if saved is not None:
                    anchors._GATES[pattern] = saved
                else:
                    anchors._GATES.pop(pattern, None)
            assert gated == ungated, pattern

    def test_the_derived_trigger_set_is_the_six_pattern_words(self):
        """A pattern edit without a gate edit fails here, loudly."""
        assert set(anchors._triggers(REASON_PATTERN)) == {
            "root cause",
            "because",
            "constraint",
            "must",
            "never",
            "always",
        }

    def test_the_gate_cannot_be_narrower_than_the_pattern(self):
        """The property the regression broke, asserted directly.

        Every word the pattern can match on must be searched by the gate, or the
        pre-test rejects text the pattern would have matched.
        """
        gate = anchors._gate(REASON_PATTERN)
        assert gate is not None, "the bounded reason pattern must stay guarded"
        for word in anchors._triggers(REASON_PATTERN):
            assert gate.search(f"prefix {word} suffix"), word

    def test_a_pattern_with_no_literal_alternation_is_never_gated(self):
        """A gate derived from nothing would reject every text."""
        assert anchors._pre_test(r"\b[a-f0-9]{7,40}\b") is None
        assert anchors._pre_test(r"`[^`\n]+`") is None
        assert anchors._triggers(r"\b[a-f0-9]{7,40}\b") == ()

    def test_a_group_with_a_metacharacter_is_not_treated_as_literals(self):
        """A gate built from `a` alone would reject text matching `\\d+`.

        The derivation therefore refuses a group unless every alternative is a
        plain word. Refusing means no gate for that pattern, which costs speed
        and cannot cost a span.
        """
        mixed = r"x{0,400}(?:a|\d+){0,400}"
        assert anchors._triggers(mixed) == ()
        assert anchors._pre_test(mixed) is None

    def test_words_from_several_groups_are_unioned(self):
        """One pattern may carry more than one alternation."""
        pattern = r"x{0,400}(?:alpha|beta)y{0,9}(?:gamma|delta)"
        assert set(anchors._triggers(pattern)) == {"alpha", "beta", "gamma", "delta"}

    def test_the_gate_is_case_insensitive_like_the_original_guard(self):
        """The original pre-test ignored case, so a capitalised sentence was
        never rejected on the strength of a trigger word it did contain."""
        gate = anchors._gate(REASON_PATTERN)
        assert gate is not None
        assert gate.search("The Root Cause is a timeout.")
        assert gate.search("We MUST ship by Friday.")

    def test_the_gate_still_short_circuits_the_degenerate_case(self):
        """The perf property that motivated the gate has to survive the fix."""
        text = "x" * 64_000
        assert extract(text, PATTERNS) == []
        calls: list[str] = []
        real = re.compile
        original = anchors._compiled

        def spy(pattern: str) -> re.Pattern[str]:
            calls.append(pattern)
            return original(pattern)

        anchors._compiled = spy
        try:
            extract("nothing relevant in this text", PATTERNS)
        finally:
            anchors._compiled = original
        assert real is re.compile
        assert not any(
            "root cause" in p for p in calls
        ), "the reason pattern ran even though no trigger word was present"
