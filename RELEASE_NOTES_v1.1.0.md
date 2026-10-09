# jev-lcm-hermes-compaction v1.1.0

## The reason-sentence guard silently discarded every `must` / `never` / `always` anchor

`anchors.extract()` runs over every assistant message on every turn, and the
reason-sentence pattern is the one that carries constraints and decisions — the
class of evidence this plugin exists to protect. A cheap literal pre-test guards
it, so a message with no trigger word never runs the pattern at all. The guard's
vocabulary was:

```python
_REASON_TRIGGER = re.compile(r"root cause|because|constraint", re.IGNORECASE)
```

Three words. The shipped pattern alternates over six:

```
[^.!?\n]{0,400}(?:root cause|because|constraint|must|never|always)[^.!?\n]{0,400}[.!?]?
```

`must`, `never` and `always` were absent from the guard, so on a message whose
only trigger was one of them the guard skipped the pattern outright and the
sentence never became a candidate. Measured directly, against the raw regex:

| Input | Raw regex | `extract()` |
| --- | --- | --- |
| `We must pin the dependency before the release.` | 1 span | **0 spans** |
| `You never bypass the approval gate.` | 1 span | **0 spans** |
| `The service always validates input.` | 1 span | **0 spans** |

Nothing logged it and nothing counted it. The evidence was dropped before
candidate generation, so it never reached the model's prompt and no metric
recorded a loss.

### Two compounding defects, fixed together

**Case.** The guard was `re.IGNORECASE`; the pattern was compiled without it. A
trigger word at the start of a sentence is capitalised in ordinary prose, so
`Because the cache is cold, the call is slow.` passed the guard and was then
missed by the pattern — one scan spent, nothing extracted.

**Applicability.** `_needs_reason_trigger()` decided a pattern was reason-shaped
by asking for two specific substrings:

```python
return "root cause" in pattern and "because" in pattern
```

`jev_anchor_patterns` is a documented operator setting, so a hand-written pattern
sharing the shape without both those words lost the guard entirely and paid the
49-second pathological cost that v1.0.1's fix was written to remove. No test
covered a custom pattern list.

### What changed

The guard's vocabulary is now read out of the pattern's own alternation, so the
guard, its applicability, and the pattern it guards are one thing rather than
three that must agree:

```python
_TRIGGER_GROUP = re.compile(r"\(\?:(?:(([a-z][a-z ]*\|)+[a-z][a-z ]*))\)")

def _reason_triggers(pattern: str) -> tuple[str, ...]:
    group = _TRIGGER_GROUP.search(pattern)
    if not group:
        return ()
    return tuple(t.strip().lower() for t in group.group(1).split("|") if t.strip())
```

And the reason-sentence pattern is the one pattern compiled case-insensitively,
because reason text is prose and its trigger's case depends on where the word
falls in the sentence.

The detector is deliberately **case-sensitive**, and that is load-bearing. This
module also ships
`\b[A-Z_]{2,}_(?:KEY|TOKEN|SECRET|URL|PATH|ID)\b`, whose alternation is just as
well formed. An ignorecase detector classified that credential pattern as
reason-shaped too and recompiled it case-insensitively, which began matching
`superscret_key` — the exact silent widening this fix exists to avoid. The
TypeScript sibling hit the same trap through the same detector, independently.
A pattern whose author writes its triggers in capitals now simply is not treated
as a reason pattern: it loses the guard, which costs performance, and never
changes what it matches.

### What is pinned

`tests/test_anchor_reason_guard.py`, 15 tests:

- each of the six trigger words yields a span under the full shipped pattern list;
- a trigger is honoured at sentence start, sentence middle, and after a period;
- the guard's vocabulary equals the pattern's alternation, asserted directly;
- a homeomorphic custom pattern is guarded *and* still matches;
- the guard still short-circuits on 64 KB of trigger-free text;
- the credential and identifier patterns match exactly what they matched before.

`tests/test_anchor_scan_performance.py` continues to pass unchanged, including
its monkeypatched proof that the pre-test short-circuits and its comparison
against the old unbounded pattern.

### Cross-language

The identical defect existed in `jevs-lcm-dsh-compaction`, the TypeScript
sibling that shares the parity fixtures. It was diagnosed independently in both
repositories and is fixed in both with the same mechanism. Python and TypeScript
now agree on all six triggers and on all three capitalisation shapes, which is
the property the cross-language parity tests were written to hold and did not
hold here.

### Verification

```
267 passed, 1 deselected        (was 252; +15, of which all 15 are new)
mypy:      Success: no issues found in 14 source files
black:     43 files would be left unchanged
coverage:  93.95% (--cov-fail-under=90)
```
