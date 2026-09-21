# Contributing

[hermes-agent PR #116246](https://github.com/NousResearch/hermes-agent/pull/116246) is the problem statement behind this project: Jev-only compaction showed threshold, text-floor, state-ceiling, assistant-text, and cache failure modes in the attributed evaluation. Contributions must preserve the corrected contract: LCM owns storage and condensation; Jev supplies bounded hints.

## Before changing code

Read the current source, [`docs/reference.md`](docs/reference.md), [`docs/limitations.md`](docs/limitations.md), and [`docs/review.md`](docs/review.md). Do not turn an implementation-local test into a product claim. Do not change the active engine default.

## Development

```sh
python -m pip install -e '.[dev]'
pytest
mypy src/
black --check src tests
```

These commands describe the repository's declared tooling. A passing local suite does not prove live provider behavior, clean-profile installation, assembled-prompt retention, or benchmark superiority.

## Pull requests

Describe the user-visible problem, the invariant affected, and the evidence that verifies the change. Include tests for settings validation, provider failure, privacy, anchor boundaries, overflow, batching, and recovery when relevant. Keep secrets, provider responses containing sensitive text, SQLite archives, and private paths out of commits.

Provider changes need a documented wire contract and sanitized diagnostics. Integration changes need a host-level receipt or an explicit pending dependency. Documentation must attribute PR #116246 numbers rather than presenting them as reproduced results.

## Review checklist

- [ ] Raw evidence remains immutable and recoverable.
- [ ] Jev never becomes the storage owner or primary text compressor.
- [ ] Key values cannot enter logs, metrics, errors, or fixtures.
- [ ] Existing LCM tools and profile opt-in behavior remain intact.
- [ ] Tests cover the failure path, not only the happy path.
- [ ] README and docs state what is verified and what remains pending.
- [ ] Release language remains Unreleased until acceptance gates pass.

MIT applies to this repository. Preserve upstream notices and attribution when modifying derived work.