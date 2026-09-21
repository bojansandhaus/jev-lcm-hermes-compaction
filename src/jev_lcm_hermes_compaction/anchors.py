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


def extract(text: str, patterns: tuple[str, ...]) -> list[tuple[int, int, str]]:
    spans: set[tuple[int, int]] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            if match.end() > match.start():
                spans.add(match.span())
    return [(a, b, text[a:b]) for a, b in sorted(spans)]
