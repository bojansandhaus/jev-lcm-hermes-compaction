# jev-lcm-hermes-compaction v1.0.1

## The anchor scan could take 49 seconds on a single message

`anchors.extract()` runs every configured pattern over every assistant message on
every turn, so a pattern's cost is multiplied by the whole backlog. The
reason-sentence pattern's leading `[^.!?\n]*` was unbounded, which reads like a
linear scan and is not one: on text with no sentence terminator, the engine
retried the greedy prefix from every offset.

Measured on this machine, a single 64 KB input, Python 3.11:

| input | before | after |
| --- | --- | --- |
| 64 KB, no terminator, no trigger word | 49,190 ms | 7.0 ms |
| 64 KB of ordinary prose | 8.6 ms | 8.6 ms |

Minified JSON, base64 blobs and long paths all have the terminator-free shape
that triggers it, so this was reachable from ordinary transcripts rather than a
contrived input.

## What changed

- The reason-sentence pattern is bounded to a 400-character window either side of
  its trigger word, so a minified blob cannot become one enormous protected span.
- A cheap literal pre-test rejects the pattern outright when none of its trigger
  words is present. That is the case that was pathological, and it is the common
  one.
- Patterns are compiled once into an explicit per-pattern dict instead of relying
  on `re`'s global 512-entry cache, which runs on every turn and is shared with
  the rest of the process.

## What deliberately did not change

The bound is a real behaviour change, so it is pinned on both sides.
`tests/test_anchor_scan_performance.py` (7 tests) asserts that ordinary sentences
extract **byte-identical spans** to the old unbounded pattern, that only a
terminator-free run is truncated, and that the pre-test genuinely short-circuits
rather than inferring that from a fast total runtime.

## Verification

```
253 passed          (246 before, 7 new)
Success: no issues found in 14 source files      (mypy)
42 files would be left unchanged                  (black --check --target-version py311)
Required test coverage of 90% reached. Total coverage: 96.25%
```

Run with `--ignore=tests/test_plugin.py`, which needs a Hermes checkout on the
path and is excluded from the documented local command.
