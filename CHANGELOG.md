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

## [1.0.0] - 2026-10-04

First stable release. It names the four decision modes explicitly, adds the fourth one, and turns the local provider into a generic slot that any local [System One decision model](https://systemonemodels.org/guides/what-is-a-system-one-model/) can occupy by configuration. Every mode name this plugin has ever accepted still resolves, and every configuration that worked before produces the same routing decision.

### Documentation

- **The model category is now named as a category.** Every provider this plugin reaches is a System One decision model, also written a typed decision model: a model that answers typed questions and returns typed answers with a probability for each instead of prose. Jev (TypeSafe, hosted, closed weights), Clef and Clef Flash (Cloudflare Workers AI), Laya (Convai Innovations, open weights, local, the default), Kev (open weights, 0.8B to 27B on Qwen3.5 and Qwen3.8 bases, serving TypeSafe's `/v1/systemone` shape), and Tev1 (Together AI, Qwen3.5-based, open weights) are members of it. The term is TypeSafe's own, coined on 15 September 2026 alongside Jev. Jev is one vendor's member of the category, not the name of the category, so the documentation no longer uses "Jev-like" as a type name.
- **A taxonomy table and a topic list were added** to `README.md`, and the local-model lists in `README.md`, `docs/reference.md`, `docs/integrations.md`, `RELEASE_NOTES_v1.0.0-stable.md`, and `examples/hermes_config_snippet.yml` now name those members as System One decision models rather than as compatible-with-Jev engines. `README.md` lists the repository's own topic tags, `clef`, `cloudflare`, `compaction`, `context-management`, `decision-model`, `hermes-agent`, `jev`, `kev`, `laya`, `lcm`, `plugin`, `system-one`, `tev1`, so the tags and the prose agree.
- **Category membership and the shared wire contract stay documented claims.** They come from those projects and from [systemonemodels.org](https://systemonemodels.org/), not from any measurement made here. No privacy statement was softened by this change: `local_only` still never leaves the machine, `local_with_api_fallback` still escalates to a hosted API on a configured trigger, and `api_only` and `api_with_local_fallback` still send the scored state to the hosted API.

### Added

- **The fourth mode, `api_with_local_fallback`.** The hosted API leads and the local model is the last resort, the mirror of `local_with_api_fallback`. It uses the existing cooldown, trigger, and retry machinery unchanged, and it fails at load with no hosted key, naming the missing variable, because it promises a fallback that could not otherwise exist.
- **`local_model`**, default `laya`. The provider name stays `laya`; this setting selects which local engine answers, as the `model` field of the request. Any local server speaking the same `/v1/systemone` contract therefore fits the slot with no code change and no new provider name, whether it serves Laya, Kev, Tev1, or a member released after this version. Verified-fit engines include `laya` (also `laya-multilingual`, `laya-typed-decisions`), `kev` (also `kev-0.8b`), `tev1` (Together AI, Qwen3.5-based, open weights, `Tev1-4B` and `Tev1-0.8B`), and `jeff-qwen3.5-0.8b` and `jeff-gemma4-e2b`. The interchangeable-engine claim is sourced from [chaitin/Decis](https://github.com/chaitin/Decis), which serves those engines behind one Jev-compatible endpoint with one image per engine, and from [togethercomputer/tev1](https://github.com/togethercomputer/tev1).
- **`clef_with_local_fallback`**, resolving to `api_with_local_fallback` with the hosted side pinned to Clef.
- **`tests/test_local_model_slot.py`**, covering the four canonical modes and their provider orders, `local_model` changing what the local request asks for with the default unchanged, the empty, whitespace, and escaping rejections, the precedence rule against `laya_model`, and the privacy log assertions for every mode including the new one.
- **`tests/test_credential_isolation.py`**, asserting the test credential strip list matches the provider credential map exactly, so a credential added to `providers.py` and forgotten in `conftest.py` fails the suite instead of leaking silently.

### Changed

- **The mode vocabulary is now four canonical names**, each naming which side leads and whether the other side is a fallback: `api_with_local_fallback`, `api_only`, `local_only`, `local_with_api_fallback`. `api_only` is the default and is what the previous `auto` default resolves to, so the default profile is unchanged.
- **Every previously accepted name keeps working as an alias**, and each resolves to the canonical mode that reproduces the routing decision it produced before: `auto` and `jev_api` to `api_only`, `laya` and `laya_local` to `local_only`, `laya_then_hosted` and `laya_with_jev_fallback` to `local_with_api_fallback`, `clef_api` to `api_only` on Clef. `typesafe`, `openrouter`, and `clef` keep pinning their hosted provider: they resolve to `api_only` carrying a pin in `jev_provider_pin`, so the mode stays one of the four canonical names while the pin keeps the route specific. Aliases resolve before they reach a chain, a diagnostic, a log line, or a URL, so no alias string appears in observable output.
- **`laya_model` is superseded by `local_model` and is still accepted.** It is read when `local_model` was left alone, `local_model` wins when it is set on purpose, and `laya_model` is then rewritten to the resolved name so any pre-existing reader of it sees the engine actually sent. Its default is now `laya` rather than `convaiinnovations/laya`, which is the same default expressed through the generic slot.
- **`local_model` is deliberately not validated against an allowlist**, because the point of the slot is that a new local model works without a release. Only an empty or whitespace-only value, and one carrying a character that would corrupt the JSON `model` string or a URL path segment (`"`, `\`, `?`, `#`, or a control character), is rejected at load, and a rejected value is reported without being echoed back.
- **`tests/conftest.py` exposes its strip rule as `is_credential` and `CREDENTIAL_VARIABLES`.** The behaviour is unchanged, including the by-name stripping of `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` added in `1.0.0-rc.5`, and the rule is now testable rather than implicit.
- **Version is `1.0.0`** in `pyproject.toml`, `plugin.yaml`, and `__init__.py`, replacing `1.0.0rc5`. This is the first stable release and the release candidates are not continued.

### Privacy boundary

Unchanged in direction and strengthened in coverage. `local_only` still never leaves the machine; `local_with_api_fallback` still sends the scored state to a hosted API when the local server fails a configured trigger; `api_only` and `api_with_local_fallback` send it to the hosted API on the first hop. New tests assert that a log line, a diagnostic, and an error message in every mode carry the provider and the exception class only, never a credential value, a state, candidate text, a question, or an answer.

### Not established

No local model other than the shipped default has been called live, and no claim is made that any of them was measured: the interchangeable-engine list is a statement about the wire contract, sourced from the two projects named above. The production recall-at-budget comparison, fresh-profile installation qualification, provider parity review, and final documentation review remain open, exactly as they did for the candidates. `1.0.0` here is a version number, not a claim that those gates passed.

## [1.0.0-rc.5] - 2026-10-04 (unpublished)

Adds Cloudflare Clef as a fourth decision-model provider, selectable alone or inside the existing chain and fallback machinery. An installation that sets `auto`, `typesafe`, `openrouter`, `laya`, or `laya_then_hosted` behaves exactly as it did in `1.0.0-rc.4`. No live Clef call is part of this candidate and none is claimed: no Cloudflare credential available on the machine that built it is authorized for Workers AI, so every Clef test runs against an injected transport.

### Added

- The provider `clef`, hosted at Cloudflare Workers AI, reachable by `jev_provider: clef` and by the mode alias `clef_api`. It is a first class provider in the same sense as the hosted Jev pair: it is a `PROVIDER_MODES` value, it can be pinned on its own, it is accepted in `jev_fallback_order`, it participates in `auto` filtering by credential, and it uses the existing retry, cooldown, fallback-trigger, and diagnostics machinery with no change to any of them. A failure of `ClefError` keeps its `ProviderError.reason` inside the fixed vocabulary, so a Clef failure falls back, cools down, and reports exactly as a TypeSafe failure does.
- `clef_model`, default `clef`, selecting the checkpoint of that one provider. `clef-flash` routes to the `@cf/cloudflare/clef-flash` endpoint and sends `"model": "clef-flash"` in the body. It is a setting, not a second provider: it is never a mode value, never an alias, and never a chain member. An unknown checkpoint is rejected at load.
- `clef_base_url`, default `https://api.cloudflare.com/client/v4/accounts`, held to the same endpoint validation as every other provider, so plain HTTP for a non-local host is refused.
- Two environment variables. `CLOUDFLARE_API_TOKEN` is the credential and needs the Account > Workers AI > Read permission; `CLOUDFLARE_ACCOUNT_ID` is configuration, but the endpoint is per account so a request cannot be built without it. Both are validated before any request. Pinning `clef` with either missing raises `ValueError` at load naming the variable, and a member of `jev_fallback_order` without an account refuses each request with the same name. `diagnostics()` gained `configuration_present` so the account id is reported by variable name, separately from `keys_present`, and never by value.
- Question-id mapping. Cloudflare accepts letters, digits, `_`, `.`, and `-` in a question id, at most 100 characters, at most 64 per request. This package builds ids as `<sha256>:<name>`, so the colon it has always sent is illegal on this wire. An id Clef already accepts travels unchanged, anything else is renamed to `clefq<n>`, and the answer is mapped back before the caller sees it, so no caller ever observes a rename. Every caller id is reserved before any generated name is handed out, so a generated id cannot shadow a caller's own question. A batch over 64 questions fails before any request, naming `jev_max_candidates_per_batch`, rather than silently sending fewer.
- Per-type answer validation, reusing one helper rather than a copy per type. `index_scale` derives the bounds of an ordered scale from the `criteria` a question declared: a `noul` probability is bounded `0..1`, an ordered `score` is bounded `0..len(criteria)-1`, and a `choice` must name one of its `criteria` and is reported at that label's index. A score of `2` over three criteria is accepted and reported as `2.0`; the same value over two criteria is rejected. `parse_answers` takes the questions it is validating against as an optional third argument, so every existing provider keeps reading `noul` on `0..1` exactly as before.
- Both documented response shapes. The bare model output with top-level `answers` and Cloudflare's `{"success": true, "result": {...}}` envelope both parse, the top-level mapping winning. A `success: false` envelope is refused with Cloudflare's own error codes surfaced, for example `Cloudflare Workers AI refused the request (code 7003)`.
- `tests/test_clef_provider.py`, 36 tests over the wire shape, the chain, the envelopes, the credentials, the id mapping, the answer scales, and the logging boundary.
- `evaluation/live_clef.py`, a six-phase probe following `live_laya_then_hosted.py`: the recorded wire shape, the checkpoint selection, the alias and chain orders, the three missing-credential cases, a phase that attempts the real request when both variables are present and reports Cloudflare's answer, and both response envelopes offline. Its module docstring states the honesty boundary.
- A "Cloudflare Clef" section in `docs/reference.md` covering the per-account endpoint, the body, the id constraints, the answer table, both envelopes, the checkpoint rule, and the privacy consequence; a "Cloudflare Clef only" section in `docs/integrations.md` with the two variables and a profile snippet; a new "Executed locally for the Clef provider" section and four new entries under "Not established" in `docs/verification.md`; and the credential and privacy notes in `README.md` and `docs/limitations.md`.

### Changed

- `tests/conftest.py` now also strips `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` by name. The existing isolation rule only removed variables ending in `API_KEY`, so the new `_API_TOKEN` credential passed through it and a developer's real Cloudflare environment reached `tests/test_http_cli.py`, which asserts an empty `keys_present`. This was caught by running the suite, not by reading it.
- `docs/reference.md` now describes four arrangements rather than three and states that `jev_fallback_order` accepts `clef` as a member. No other arrangement changed.
- `examples/hermes_config_snippet.yml` documents the two Cloudflare variables, the optional Clef settings, and `LAYA_API_KEY`, which the file did not previously list.

### Verification

- 162 tests pass with `python -m pytest -q --ignore=tests/test_plugin.py`. `tests/test_plugin.py` is excluded for a pre-existing collection error at `HEAD`, unrelated to Clef: it imports `hermes_cli.plugins`, which needs `hermes_yaml` from the Hermes source tree on `sys.path`, and it passes on its own when that tree is on the path. The count before this candidate was 126. `mypy` passes over 14 source files and `black --check` reports 43 files unchanged.
- `evaluation/live_clef.py` was executed and reported the recorded wire shape, both checkpoint URLs, `clef_api` resolving to canonical `clef`, `auto` unchanged at `["typesafe", "openrouter"]`, an uncredentialed `clef` filtered out of a chain, and the missing-credential messages, with no credential value in its output.
- No live Clef request was made. `phase_5_refused_credential` reported `attempted: false` because no `CLOUDFLARE_ACCOUNT_ID` was present in the environment. The wire contract is taken from the Cloudflare model pages, [clef](https://developers.cloudflare.com/workers-ai/models/clef/) and [clef-flash](https://developers.cloudflare.com/workers-ai/models/clef-flash/), and is not a reproduced measurement.
- Not established: Clef's retention quality on this workload, its latency and Workers AI billing under a real batch, the behaviour of a 64-question request against the 65536-token context window, and whether a mapped question id changes a judgment relative to the caller's original id. Each is recorded in `docs/verification.md`.

### Privacy boundary

Selecting `clef` sends the scored state, the candidate text, and the protected anchors to `api.cloudflare.com` on every request. There is no redaction step. `clef` alone has no fallback member, so a Clef failure raises rather than becoming a request to another provider; naming `clef` in `jev_fallback_order` makes it inherit the existing trigger set, which is the same consequence `laya_then_hosted` already documents. `laya` remains the only route that never leaves the machine.

The new log line is `clef_provider_failed exception=<Type>` and it carries the exception class and nothing else. By the time a transport failure surfaces, the state has already left the machine, and a `urllib` message can quote the request object, so the URL, the account id, the token, the request body, and the exception message are all excluded from the log. The operator-facing message comes from `ClefError`, whose text is composed of provider names, variable names, counts, and Cloudflare error codes only.

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
