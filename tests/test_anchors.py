"""Anchor extraction over the seven pattern classes the contract requires."""

from jev_lcm_hermes_compaction.anchors import extract
from jev_lcm_hermes_compaction.settings import Settings


def test_anchor_patterns_cover_every_required_class():
    text = (
        "Root cause: a03f5c9d1b must never be re-derived; "
        "OPENROUTER_API_KEY is unset; see line 412; "
        '`token_budget` and "docs/reference.md" pin v1.2.3.'
    )
    spans = {value for _, _, value in extract(text, Settings().jev_anchor_patterns)}
    assert "a03f5c9d1b" in spans, "hex identifier"
    assert "OPENROUTER_API_KEY" in spans, "config key"
    assert "`token_budget`" in spans, "backticked symbol"
    assert '"docs/reference.md"' in spans, "quoted path"
    assert "v1.2.3" in spans, "version pin"
    assert any("line 412" in s for s in spans), "file line reference"
    assert any("Root cause" in s for s in spans), "decision span"


def test_anchor_spans_are_exact_and_an_invalid_pattern_is_tolerated():
    text = 'We must keep `abc123def456` and "src/a.py" at v1.2.3.'
    spans = extract(text, Settings().jev_anchor_patterns)
    assert spans
    assert all(text[start:end] == value for start, end, value in spans)
    assert extract("abc", ("^",)) == []
