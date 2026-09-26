# Changelog

This project addresses the Jev-only compaction failure modes described in [Hermes PR #116246](https://github.com/NousResearch/hermes-agent/pull/116246). The work below concerns calibrated scoring, protected evidence, text condensation, bounded requests, batching, and operational visibility.

## [Unreleased]

Jev-LCM Compaction Plugin for Hermes: Jev ranks stale evidence before LCM condenses conversation history.

### Added

- Rolling threshold calibration and a minimum retention floor, addressing the fixed-threshold failure.
- Assistant anchor extraction and verbatim evidence retention, addressing identifier loss during summarization.
- Raw SQLite evidence storage and retrieval, independent of active-prompt retention.
- Tiered state shaping and explicit unscored candidates for oversized batches.
- Batched scoring with forced lifecycle flushes and serialized concurrent requests.
- TypeSafe and OpenRouter provider resolution, retries, fallback, cooldown diagnostics, and secret-safe status output.
- Compaction counters and a warning after repeated low token savings.

### Changed

- Protected evidence and active-context assembly are being reworked against the original product contract.
- Host integration tests now supplement scoring and storage helper tests.

### Architecture

LCM remains responsible for evidence storage and context assembly. Jev supplies ranking hints; it never rewrites raw messages. Pinned source regions are excluded from scoring. Scoring failure falls back to the host condensation path.

### Release blockers

The production recall-at-budget comparison, fresh-profile installation qualification, provider parity review, final documentation review, and publication remain open. No stable 1.0.0 release is asserted here. The requested September 19 release heading must not imply a release occurred before acceptance.

### Credits and license

Tamara Tran contributed the upstream state-shaping and two-question scoring design. TheEpTic supplied the Hermes integration precedent. Stephen Schoettler authored Hermes-LCM's storage, summary DAG, and retrieval implementation. Bojan Sandhaus supplied Jev Decisions product and documentation conventions. TypeSafe supplies Jev; OpenRouter supplies an alternative provider surface. Ehrlich and Blackman authored the LCM research cited in the original brief. The Hermes maintainers supplied the evaluation motivating this project.

The project uses the MIT license. See [third party notices](THIRD_PARTY_NOTICES.md) for licenses and specific reuse.

## [1.0.0-rc.4] - 2026-09-26

Bounds repeated escalation from the local hop, adds the three-mode vocabulary, and replaces the small local quality probe with the strongest evidence available. An installation that sets `auto`, `typesafe`, `openrouter`, or `laya` behaves exactly as it did in `1.0.0-rc.3`.

### Added

- A consecutive-failure breaker on the local hop in `laya_then_hosted`. Three consecutive local failures may still fall through to the hosted provider; past three the fallback is suppressed, a category-only warning is logged, and the local error is re-raised instead of being answered remotely. Any successful local call clears the counter, on the fallback path and on the plain local path alike. The counter is held per process, shared by every chain in it, and reset by a restart. It is reported as `laya_consecutive_failures` in `chain.diagnostics()` and `jev_providers`.
- The mode aliases `laya_local` and `laya_with_jev_fallback` for `laya` and `laya_then_hosted`, plus `jev_api` for `auto`. `Settings` resolves an alias to its canonical value, so both spellings build one chain. Anything outside the accepted set raises `ValueError` at load with every accepted value and alias named in the message.
- `tests/test_laya_fallback_breaker.py`, eight tests named after the behaviour: three consecutive fallbacks then a suppressed fourth that re-raises the local error, no remote call on the suppressed attempt, the reset on a healthy local call on both paths, the per-process lifetime, the counter in diagnostics, a hosted failure that never charges the local breaker, and the category-only suppression warning.
- `tests/test_laya_mode_aliases.py`, six tests over seventeen cases: the alias-to-canonical resolution, the identical chain and diagnostics, every previously accepted value keeping its own chain, the rejection message, and the alias table not drifting from the canonical set.
- A weak local answer never escalates: `tests/test_laya_then_hosted.py` now pins that a local score of `0.0` with a `0.99` threshold is returned locally and makes no hosted request.
- `tests/test_fallback.py` drives a batch whose state and candidate text carry a sentinel and asserts the sentinel never reaches `caplog`, pinning the logging property rather than describing it.
- `evaluation/live_laya_then_hosted.py` grew two phases: four consecutive local failures against a dead port with the hosted hop answered by a recorder, and a build of both mode vocabularies.

### Changed

- `docs/reference.md`, `README.md`, `docs/limitations.md`, and `docs/verification.md` now lead with the matched 100-question, three-mode benchmark published with the DOGA fork instead of this repository's eight-span probe: goal agreement 56/100 for local Laya against 88/100 for the hosted Jev API, response mode 41 against 68, stakes 37 against 67, high-versus-low ambiguity 67 against 87, and none of the 30 authored high-ambiguity labels detected locally at the 0.7 threshold. The measured local numbers from 2026-09-22 remain, labelled as the smaller probe they are.
- Documentation states the breaker's limit as plainly as its behaviour: it bounds repeated remote egress after local errors and cannot detect a valid yet incorrect local judgment.
- `docs/reference.md` gained a "Logging and privacy" section recording the audit rule: a scoring-path log line carries a category, a provider name, or a counter, never the state, candidate text, a question instruction, or an answer.

### Verification

- 127 tests pass, `mypy` is clean over 14 source files, `black --check` reports 38 files unchanged, non-vendored coverage is 97.45% (688 of 706 statements), and `python -m build` produced `jev_lcm_hermes_compaction-1.0.0rc4-py3-none-any.whl` and its source distribution.
- The breaker was exercised live against the `laya-serve` on `http://127.0.0.1:8123`: three hosted fallbacks answered over a recorded URL, the fourth attempt ended with the local `transport_error` and reached no hosted URL, and the process counter read `4`. The hosted leg remains unit-tested with an injected transport; no hosted API key exists on this machine.

## [1.0.0-rc.3] - 2026-09-26

Adds the third provider route: Laya first with the hosted Jev providers behind it. Jev runs over a hosted API key, Laya runs locally, or Laya runs locally with the hosted APIs as fallback. `jev_provider: laya_then_hosted` is an explicit opt-in, so an installation that sets `auto`, `typesafe`, `openrouter`, or `laya` behaves exactly as it did in `1.0.0-rc.2`.

### Added

- `laya_then_hosted` provider mode. The chain is Laya first, then every provider in `jev_fallback_order` that has a key, so the default order is `laya`, `typesafe`, `openrouter`. Existing fallback triggers, cooldown, and retry settings apply unchanged: a transport error, timeout, `401`, `403`, `429`, or `5xx` from the local server moves the request to the hosted hop.
- Fail-fast validation. Selecting the mode with no hosted key at all raises `ValueError` at load and names the missing environment variables, because the mode promises a fallback that would not otherwise exist. `LAYA_API_KEY` alone does not satisfy it.
- `tests/test_laya_then_hosted.py`: order construction with both keys, one key, and none; honouring of a narrowed or reordered `jev_fallback_order`; the local-first hop; fallback on each configured trigger; the non-triggering `http_error` that stays local; cooldown and recovery across the three-hop chain; secret-safe diagnostics; and the invariants that `laya` stays a single provider, `auto` never includes a Laya route, and `jev_fallback_order` still rejects `laya`.
- `evaluation/live_laya_then_hosted.py`, the live probe used for this release, which prints the built order and the hop that answered.

### Changed

- `jev_provider` accepts `laya_then_hosted` in settings validation. Nothing else about provider selection changes.
- `__version__` in the package now tracks the release candidate instead of staying at `1.0.0`.

### Privacy

In `laya_then_hosted` a failed local attempt sends the scored state to a hosted API. That is the point of the mode, so the README and `docs/reference.md` state it next to the plain `laya` mode, which never leaves the machine. `auto` still never selects a Laya route, and a local hop leads a chain only when this mode names it.

### Verification status

The local hop is verified live against the `laya-serve` running on `http://127.0.0.1:8123`. The hosted hop is covered by unit tests with an injected transport and by no live hosted call: no hosted API key exists on this machine. No live hosted verification is claimed.

## [1.0.0-rc.2] - 2026-09-22

Adds a local route for Jev scoring: instead of calling TypeSafe or OpenRouter with a key, point the engine at a Laya server on your own machine. The hosted pair remains the default and an existing configuration keeps behaving exactly as before.

### Added

- `laya` provider, scoring through a local `laya-serve` process over the Decisions `/v1/systemone` protocol, configured with `laya_base_url`, `laya_endpoint_path`, and `laya_model`.
- Keyless provider handling: `ProviderChain` accepts `laya` with no credential, and the wire client omits the `Authorization` header when no key is configured. `LAYA_API_KEY` is forwarded only when the local server was started with one.
- `laya` as a `jev_provider` value that replaces the hosted pair for that profile. It is not a fallback member: `jev_fallback_order` accepts only `typesafe` and `openrouter`, and `auto` never selects the local route on its own.
- `tests/test_laya_provider.py`, eight contracts across nine cases: keyless selection, wire shape, endpoint validation, stopped-server failure, fallback ordering, credential forwarding without leaking it, and the header rule.

### Measured against a live `laya-serve`, 2026-09-22, base English checkpoint, CPU

- The local checkpoint did not separate keep from discard on the production retention questions: `0.6516` against `0.6502` on average, a gap of `0.0014`. Calibration then reported `0.40`, its `keep_threshold_max` ceiling, and all 16 answers were retained. The route fails safe, it keeps evidence instead of dropping it, and frees nothing until thresholds are recalibrated on labelled data or a retention-tuned checkpoint is used.
- Those 16 question rows took `25.6s`, roughly `1.6s` each, which exceeds the default `request_timeout_s` of `30`. Raise `request_timeout_s` and lower `jev_max_candidates_per_batch` for a CPU-only server.

### Status

Implementation, tests, and documentation are complete and pushed. Registry publication is unchanged from `1.0.0-rc.1`. Nothing in this release installs Laya or selects it by default.

## [1.0.0] - 2026-09-19 (prepared, unpublished)

Jev-LCM Compaction Plugin for Hermes: Jev ranks stale evidence before Lossless Context Management condenses conversation history.

Fixes the Jev-only compaction failure modes identified in [NousResearch/hermes-agent#116246](https://github.com/NousResearch/hermes-agent/pull/116246).

### Added

- Jev scoring pass before LCM condensation, so ranking happens on evidence that is still verbatim.
- Assistant-text anchor extraction and protected retention, covering the recall gap the PR identified.
- Calibrated keep thresholds derived from observed score distributions, replacing the fixed `0.5` default.
- Tiered state shrink ladder with a hard token cap and explicit `jev_unscored` marking.
- Batched scoring across turns with forced flushes at lifecycle boundaries.
- LCM hint consumption so ranking decisions reach active-context assembly with raw evidence pointers.
- Recall-tool compatibility for `lcm_grep`, `lcm_expand`, and node inspection.
- Provider fallback contract and observability counters.
- Recall-at-budget evaluation harness in `evaluation/`.
- Dual-provider authentication across TypeSafe and OpenRouter with automatic fallback.

### Architecture

- LCM remains the source of truth and the primary text compressor.
- Jev is a ranking layer only; it never rewrites raw evidence.
- Pinned regions are excluded from scoring.
- Provider selection is configuration driven and never prints key values.

### Finding map

| PR #116246 finding | Shipped correction |
|---|---|
| Fixed `keep_threshold: 0.5` dropped every scored candidate | Rolling threshold calibration with a `0.15` low-sample fallback, a `0.40` cap, and a `0.10` minimum keep rate |
| Tool-call ranking missed assistant text | Regex anchor extraction and a protected verbatim index carried into assembled context |
| A Jev-only text floor grew across long runs | LCM remains the primary compressor and storage owner; Jev ranks |
| A 25K state ceiling forced blind decisions | T0 to T4 shrink ladder, hard request cap, and explicit `jev_unscored` candidates |
| Per-turn scoring disturbed the prompt cache | Three-turn batch window with pressure and lifecycle flushes |
| Metrics hid the cost of compaction | `lcm_recall_at_budget`, `lcm_freed_per_compaction`, `jev_unscored_count`, live threshold, provider counters, and a repeated low-freed warning |

### Credits

- Tamara Tran, [fast-jev-compaction](https://github.com/tamaratran/fast-jev-compaction) (MIT): state shaping, two-question scoring, keep/truncate/drop model.
- TheEpTic, [hermes-jev-compact](https://github.com/TheEpTic/hermes-plugins/tree/main/hermes-jev-compact) (MIT): Hermes integration seam, fallback contract, counters.
- Stephen Schoettler, [hermes-lcm](https://github.com/stephenschoettler/hermes-lcm) (MIT): SQLite store, summary DAG, recall tools, active-context assembly.
- Bojan Sandhaus, [jev-decisions](https://github.com/bojansandhaus/jev-decisions) (MIT): README structure, documentation depth, product framing.
- TypeSafe: the Jev model and Decisions API. OpenRouter: the alternative provider surface.
- Ehrlich and Blackman (Voltropy PBC): the LCM paper.
- The Hermes maintainers and the authors of [NousResearch/hermes-agent#116246](https://github.com/NousResearch/hermes-agent/pull/116246): the evaluation that established Jev-only compaction as insufficient.None

### Status

Release content is complete but unpublished. The production recall-at-budget comparison remains unproven because the upstream transcript and evaluation policy were not supplied. The GitHub remote, repository topic, and draft release use the stored Git credential. Registry publication still requires an authenticated npm session, which this machine does not have. See [docs/compliance.md](docs/compliance.md) and [docs/verification.md](docs/verification.md).

Licensed under the MIT license.
