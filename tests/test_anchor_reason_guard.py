"""Regressions for the reason-sentence pre-test guard.

The guard is what keeps the anchor extractor affordable. It was also what
silently discarded the sentences the extractor exists to find: its vocabulary
was three of the shipped pattern's six trigger words, and it tested the
guard's case-insensitively while compiling the pattern's case-sensitively.

Both halves are pinned below, alongside the invariant that the guard's reach
cannot widen past the pattern it guards. The TypeScript sibling in
``jevs-lcm-dsh-compaction`` carried the identical defect and is fixed there
with the identical mechanism.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from jev_lcm_hermes_compaction.anchors import _reason_triggers, extract  # noqa: E402
from jev_lcm_hermes_compaction.settings import Settings  # noqa: E402

PATTERNS = Settings().jev_anchor_patterns
REASON = next(p for p in PATTERNS if "root cause" in p and "because" in p)

# Every trigger word the shipped pattern actually alternates over. Each was
# reachable from the raw regex before the fix and none of them produced a span.
TRIGGERS = ("root cause", "because", "constraint", "must", "never", "always")


def _sentence(trigger: str) -> str:
    if trigger == "root cause":
        return "The root cause of the failure is the misconfigured route."
    return f"We {trigger} pin the dependency before the release."


@pytest.mark.parametrize("trigger", TRIGGERS)
def test_every_trigger_the_pattern_names_reaches_extraction(trigger: str) -> None:
    """The guard knew three of these six words.

    ``must``, ``never`` and ``always`` were absent from the guard's vocabulary,
    so on text whose only trigger was one of them the guard skipped the pattern
    outright and the sentence never became a candidate. Those are precisely the
    constraint sentences the anchor extractor exists to protect.
    """
    spans = extract(_sentence(trigger), PATTERNS)
    assert len(spans) == 1, f"{trigger!r} produced no spans"


@pytest.mark.parametrize(
    "text",
    [
        "Because the cache is cold, the call is slow.",
        "Must pin the dependency before the release.",
        "Never bypass the approval gate.",
        "Always validate input at the boundary.",
        "The build failed. Must pin the dependency first.",
    ],
)
def test_a_trigger_is_honoured_wherever_its_capitalisation_falls(text: str) -> None:
    """The guard was ``re.IGNORECASE``; the pattern was not.

    A trigger word at the start of a sentence is capitalised in ordinary prose.
    That shape passed the guard and was then missed by the pattern, so it cost
    one scan and produced nothing.
    """
    assert len(extract(text, PATTERNS)) == 1, text


def test_the_guard_vocabulary_is_the_patterns_own_alternation() -> None:
    """The mechanism, pinned directly: the vocabulary is read out of the
    pattern, so a change to the pattern cannot leave the guard behind.

    The old detector asked for two specific substrings (``root cause`` AND
    ``because``) to decide a pattern was reason-shaped, so an operator-supplied
    pattern that shared the shape without both lost the guard entirely and paid
    the 49-second pathological cost from a documented setting.
    """
    assert set(_reason_triggers(REASON)) == set(TRIGGERS)


def test_a_homeomorphic_pattern_is_guarded() -> None:
    custom = tuple(p for p in PATTERNS if p is not REASON) + (
        r"[^.!?\n]{0,400}(?:must|should|shall)[^.!?\n]{0,400}[.!?]?",
    )
    assert extract("You should pin the dependency before the release.", custom)
    # ... and it is still guarded, so the pre-test still saves the scan.
    assert extract("Nothing of interest happens here.", custom) == []
    assert _reason_triggers(
        r"[^.!?\n]{0,400}(?:must|should|shall)[^.!?\n]{0,400}[.!?]?"
    )


def test_the_guard_still_short_circuits_on_trigger_free_text() -> None:
    """The guard exists for performance and that half was already right.

    Text with none of the trigger words must not run the pattern.
    """
    assert extract("x" * (64 * 1024), PATTERNS) == []


def test_the_case_policy_does_not_leak_to_other_patterns() -> None:
    """Only the reason-sentence pattern is compiled case-insensitively.

    Forcing every pattern to ``re.IGNORECASE`` would have widened what the
    identifier and credential patterns match -- the exact silent widening this
    fix exists to avoid. The TypeScript sibling hit that trap through the same
    detector, and the credential pattern below is the reason the detector
    requires lowercase words.
    """
    credential = next(p for p in PATTERNS if "KEY" in p)
    assert extract("THE SUPERSECRET_KEY is here", (credential,))
    assert extract("the superscret_key is here", (credential,)) == []

    identifier = next(p for p in PATTERNS if "[a-f0-9]" in p)
    assert extract("commit deadbeefcafe0123", (identifier,))
    assert extract("commit DEADBEEFCAFE0123", (identifier,)) == []
