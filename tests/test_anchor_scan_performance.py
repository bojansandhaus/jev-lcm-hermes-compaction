"""The anchor scan runs on every assistant message on every turn.

These tests pin the guard added after an independent review measured the
reason-sentence pattern taking 49 seconds on a single 64 KB input: its greedy
`[^.!?\n]*` prefix was unbounded, so the engine retried it from every offset
when the text had no sentence terminator. Minified JSON, base64 blobs and long
paths all have that shape, and the scan walks the whole backlog every turn.

The bound is a deliberate behaviour change, so both halves are asserted: normal
sentences must extract exactly what they did before, and a pathological input
must be bounded in time.
"""

from __future__ import annotations

import re
import time

from jev_lcm_hermes_compaction.anchors import extract
from jev_lcm_hermes_compaction.settings import Settings

PATTERNS = Settings().jev_anchor_patterns
REASON_INDEX = 2


def _spans(text: str, patterns: tuple[str, ...] = PATTERNS) -> set[tuple[int, int]]:
    return {(a, b) for a, b, _ in extract(text, patterns)}


def _reason_patterns() -> tuple[str, ...]:
    """The pattern set as it was before the bound, for behavioural comparison."""
    old = list(PATTERNS)
    old[REASON_INDEX] = (
        r"[^.!?\n]*(?:root cause|because|constraint|must|never|always)[^.!?\n]*[.!?]?"
    )
    return tuple(old)


class TestReasonPatternIsBounded:
    def test_pattern_source_has_a_bounded_window(self):
        """Guard against someone widening the window back to unbounded."""
        assert "[^.!?\\n]{0," in PATTERNS[REASON_INDEX]
        assert "[^.!?\\n]*" not in PATTERNS[REASON_INDEX]

    def test_ordinary_sentences_extract_identically_to_the_unbounded_pattern(self):
        for text in [
            "The root cause is a timeout. Because of Y we must fix it.",
            "Must never always constraint root cause because.",
            "Deploy failed; the constraint is version pinning.",
            "There is no trigger word in this sentence at all.",
        ]:
            assert _spans(text) == _spans(text, _reason_patterns()), text

    def test_a_long_unterminated_run_is_truncated_not_swallowed_whole(self):
        """The old form captured all 6000 characters. The new one bounds the
        window either side of the trigger so a minified blob cannot become one
        enormous protected span."""
        text = "x" * 3000 + " because " + "y" * 3000
        spans = {s for s in _spans(text) if s[1] - s[0] > 1000}
        assert not spans, f"unbounded capture returned {spans}"
        assert _spans(text), "the trigger word must still be found"


class TestScanStaysFast:
    def test_degenerate_64k_input_is_not_pathological(self):
        text = "x" * 64_000
        start = time.perf_counter()
        extract(text, PATTERNS)
        elapsed = time.perf_counter() - start
        # The old form needed ~49 s here. A generous ceiling still fails loudly
        # if the unbounded form ever comes back.
        assert elapsed < 1.0, f"anchor scan took {elapsed:.3f}s on 64 KB"

    def test_realistic_64k_prose_is_not_pathological(self):
        text = ("The root cause is a timeout in the retry loop. " * 1200)[:64_000]
        start = time.perf_counter()
        assert extract(text, PATTERNS)
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"anchor scan took {elapsed:.3f}s on 64 KB of prose"

    def test_the_pretest_actually_skips_the_pattern(self, monkeypatch):
        """The guard is a cheap literal scan; assert it short-circuits rather
        than trusting that a fast total run implies it."""
        calls: list[str] = []
        real = re.compile

        def spy(pattern):
            calls.append(pattern)
            return real(pattern)

        monkeypatch.setattr("jev_lcm_hermes_compaction.anchors._compiled", spy)
        extract("nothing relevant in this text", PATTERNS)
        assert not any(
            "root cause" in p for p in calls
        ), "the reason pattern ran even though no trigger word was present"


class TestCompiledPatternCache:
    def test_compiled_patterns_are_reused(self, monkeypatch):
        import jev_lcm_hermes_compaction.anchors as anchors

        anchors._COMPILED.clear()
        extract("The root cause is a timeout.", PATTERNS)
        first = dict(anchors._COMPILED)
        extract("The root cause is another timeout.", PATTERNS)
        assert first  # something was cached
        assert set(anchors._COMPILED) == set(first), "cache keys should be stable"
