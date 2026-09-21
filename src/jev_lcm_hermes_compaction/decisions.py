"""Decisions classify prompt hints only, never raw messages."""

from typing import Any
from .anchors import Candidate


def questions(candidate: Candidate) -> dict[str, Any]:
    instructions = (
        {
            "anchor_keep": "Does this span contain an identifier, decision, or constraint a future turn is likely to need verbatim?",
            "recovery": "Would re-reading this span be necessary if replaced by a raw-store pointer?",
        }
        if candidate.kind == "anchor"
        else {
            "keep_call": "Does this tool call still matter for continuing the current task?",
            "keep_result": "Is the exact tool result likely to be needed verbatim to continue the task?",
        }
    )
    return {
        candidate.id
        + ":"
        + name: {
            "type": "noul",
            "instructions": instruction + " Candidate id: " + candidate.id,
        }
        for name, instruction in instructions.items()
    }


def decide(
    candidate: Candidate,
    scores: dict[str, float],
    threshold: float,
    floor_keep: bool = False,
) -> None:
    names = (
        ("anchor_keep", "recovery")
        if candidate.kind == "anchor"
        else ("keep_call", "keep_result")
    )
    candidate.scores = {name: scores[candidate.id + ":" + name] for name in names}
    candidate.jev_unscored = False
    if candidate.kind == "anchor":
        candidate.action = (
            "keep"
            if candidate.scores["anchor_keep"] >= threshold or floor_keep
            else "drop"
        )
    elif candidate.scores["keep_result"] >= threshold or floor_keep:
        candidate.action = "keep"
    elif candidate.scores["keep_call"] >= threshold:
        candidate.action = "truncate"
    else:
        candidate.action = "drop"
