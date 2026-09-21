"""Decision table: keep, truncate, and drop for calls and anchors."""

import pytest

from jev_lcm_hermes_compaction.anchors import Candidate
from jev_lcm_hermes_compaction.decisions import decide, questions


@pytest.mark.parametrize(
    "kind,a,b,action",
    [
        ("tool", 0.1, 0.2, "keep"),
        ("tool", 0.2, 0.1, "truncate"),
        ("tool", 0.1, 0.1, "drop"),
        ("anchor", 0.2, 0.1, "keep"),
        ("anchor", 0.1, 0.1, "drop"),
    ],
)
def test_decisions(kind, a, b, action):
    c = Candidate("x", kind, 1, "exact")
    names = list(questions(c))
    decide(c, {names[0]: a, names[1]: b}, 0.15)
    assert c.action == action and not c.jev_unscored
