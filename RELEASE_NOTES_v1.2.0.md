# jev-lcm-hermes-compaction v1.2.0

## Five ways the evidence Jev decided to keep never reached the prompt

This release is about decisions that were made correctly and then lost. Jev
scores a candidate, decides to keep it, and the decision has to survive three
more steps — a token budget, a batch cap, a breaker — before a model reads it.
Each of the five high findings below was a place where it did not survive, and
in four of the five nothing recorded the loss.

The common shape is a loop that silently gives up. A budget test that `break`s,
a `break` instead of a `continue`, a cap that never re-scopes, a counter that is
only written on a path that rarely runs. None of them raised. Each one turns a
ranking decision into a no-op, which is the exact failure this plugin was built
to remove: LCM's default condensation is what happens when Jev's ranking is
discarded.

## 1. `hint_block()` dropped every kept tool result

`hint_block()` admits a candidate only if the whole block still fits
`hint_budget_tokens` (default 4000):

```python
if tokens("\n".join(lines + [entry])) <= self.settings.hint_budget_tokens:
    lines.append(entry)
```

A kept tool result at the default `min_result_chars` of 8000 is roughly 8000
bytes. It never fits. Because `protected()` sorts by score descending and the
loop `continue`s past the first non-fitting entry, the tool evidence Jev had just
spent a request deciding to keep was precisely what never reached the prompt.
The block returned `""`.

A kept row now leaves a one-line receipt — `store_id`, the byte length, and the
recovery tool:

```
[store_id=7; candidate=c1; bytes=3800; withheld by hint budget; recover with lcm_expand(store_id=7)]
```

The receipt is small enough to fit any budget that admits the header line. The
suppressed count is `jev_hint_dropped`.

## 2. `active_context_block()` discarded the whole anchor index on one row

The same budget test, with a `break`:

```python
if tokens("\n".join(lines + [entry])) > self.settings.hint_budget_tokens:
    break
```

Rows come back ordered by keep score, descending, so the highest-scoring row is
the most likely to be large. One oversized anchor therefore dropped every later
one — the opposite of what the ordering promises. Now a `continue`, plus a scan
cap of 64 rows so one session cannot make the render walk an unbounded index
subtoken by subtoken. The suppressed count is `jev_anchor_block_dropped`.

`tests/test_compressor.py::test_protected_evidence_is_budgeted_by_real_assembly`
asserted `prompt.count("cafebabedeadbeef") == 1`. That assertion pinned the old
early exit: the anchor is legitimately carried by two protected rows, so it now
appears twice. The test still asserts the real property it was written for — the
assembly stays within `max_assembly_tokens`, and no candidate row is emitted
twice — which is now explicit rather than inferred from a count of one.

## 3. A local outage suppressed the hosted fallback for the process lifetime

`_laya_failure_count` is a module global, cleared only by a successful local
call. Past three consecutive failures every later flush re-raised the local
error. But a suppressed fallback never runs the hosted hop that would have
succeeded, so nothing could clear the counter — and `cooldowns` is rebuilt with
every chain while the count is not, so the breaker outlived both the outage and
the chain that recorded it. A local server that recovered a minute later was
never tried again.

The count is now bounded by silence as well as by success: 60 seconds without a
new local failure (`_LAYA_FALLBACK_WINDOW_S`), after which the next failure is
counted as a first failure. The window is measured from the most recent
failure, so an outage that is still happening does not rearm the breaker on a
clock. Both fields are reset by `conftest.py`'s existing isolation fixture,
and `diagnostics()` reports `laya_failure_window_s` beside
`laya_consecutive_failures`.

## 4. Candidates behind the batch cap starved permanently

`shape()` took `candidates[: jev_max_candidates_per_batch]` in insertion order.
A candidate that arrived after the last slot never reached the head of the list,
so it was deferred by every batch, forever, and nothing recorded the drop.

`Candidate.jev_dropped_batches` counts the batches a candidate has waited
through, and `candidate_priority()` sorts by that count first, so a candidate
that has already waited is considered before one that has not and the queue
drains. Anchors then outrank tool results, and message position breaks the
remainder deterministically. The aggregate is `jev_starved_count`.

## 5. `jev_unscored_count` only existed after a flush

`_counts()` is called from `flush()`. With the default three-turn batch window,
two of every three turns never flush, so `jev_stats` reported zero unscored
candidates while they sat in the window. `collect()` now writes it too, alongside
`jev_starved_count`, both of which are derivable from candidate state.

## Three smaller fixes

**`metrics.compaction()` could report negative freed space.**
`100 * (before - after) / before` goes below zero whenever `after` exceeds
`before`, and a negative value fails the `freed < 20` test that drives the
low-cycle warning. The cycles that most needed the signal were the ones
reporting a number below zero. The value is clamped to `[0, 100]`, and
`low_cycles` is stored in the mapping rather than only as an attribute, so it
round-trips through `dict(m)` and JSON like every other counter.

**`endpoint()` accepted percent-encoded traversal in the base path.**
The `..` check ran against `unquote(path)` only, so
`https://example.test-/%2e%2e/secrets` was accepted: `urlsplit` puts the encoded
segment in the netloc, the check never sees it, and the joined URL decodes into
a traversal at the server. The base is now checked the same way.

**`jev_calibrate --dry-run` sent a live request.** It called `chain.score()`
with a synthetic state, billing the operator a request for a run the name calls a
dry run, and `ProviderChain(settings)` was constructed before the check, so a
mode that fails at load produced an uncaught traceback before the flag was ever
read. `--dry-run` now sends nothing and reports the resolved order, key presence,
and cooldown state; `--live` is the sending path and its help text says so
outright. Both the settings and the chain construction are guarded, and a load
failure prints the operator-facing message as JSON with exit code 2 instead of a
traceback.

## Docs corrected against the code

`README.md` and `docs/reference.md` both claimed `api_only` and `local_only` are
single-provider routes. `api_only` is a multi-provider chain filtered by
credential: with both keys present a `429` from TypeSafe cools it and tries
OpenRouter. Only a pinned `api_only` is single-provider, because a pin names its
provider outright and takes the fallback order out of the decision. Both files
now say that, and the mode tables' fallback column matches.

The two framings of Clef are unified as one provider with two checkpoints: the
chain member is always `clef`, and `clef_model` selects which checkpoint
answers, so `clef` appears in `jev_provider_pin` and `jev_fallback_order` while
`clef-flash` appears only in `clef_model`. `docs/reference.md` previously implied
the checkpoint "is never a chain member", which read as though `clef` itself
were not one either.

## Verification

```
293 passed, 1 deselected  (267 before, 26 new)
Success: no issues found in 14 source files      (mypy)
43 files would be left unchanged                  (black --check --target-version py311)
Required test coverage of 90% reached. Total coverage: 94.05%
```

Run with `--ignore=tests/test_plugin.py`, which needs a Hermes checkout on the
path and is excluded from the documented local command.
`tests/test_anchor_scan_performance.py` is unchanged and still passes.
