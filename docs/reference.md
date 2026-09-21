# Technical reference

[NousResearch/hermes-agent PR #116246](https://github.com/NousResearch/hermes-agent/pull/116246) documented failure modes in Jev-only compaction: threshold collapse, a text floor, state-shaping saturation, assistant-text recall loss, and cache churn. This reference maps the current implementation to the corrected design: Jev scores candidates before LCM condensation, while LCM owns storage, summaries, assembly, and recall. The PR's reported measurements are cited as attributed findings, not reproduced results.

## Scope and invariants

The package is opt-in through `context.engine: jev-lcm`; installation does not change a profile. Raw messages enter the LCM-owned store before scoring. Jev returns scores and decisions. It never edits or deletes stored evidence. If scoring is disabled or fails, the host condensation path continues.

The Hermes package currently vendors an LCM implementation and exposes the integration through `plugin.py`, `compressor.py`, `jev_client.py`, `providers.py`, `state_shaper.py`, `anchors.py`, `calibration.py`, `batcher.py`, `metrics.py`, `decisions.py`, and `settings.py`. Read the source when a host-version detail matters; this document does not promise an installation or live-provider result.

## Configuration

Defaults below are read from `settings.py`.

| Setting | Default | Meaning |
|---|---:|---|
| `jev_provider` | `auto` | `auto`, `typesafe`, or `openrouter`. |
| `TYPESAFE_API_KEY` | unset | TypeSafe credential, supplied through the environment or secret manager. |
| `OPENROUTER_API_KEY` | unset | OpenRouter credential, supplied through the environment or secret manager. |
| `typesafe_base_url` | `https://api.typesafe.ai/v1` | TypeSafe base URL. |
| `openrouter_base_url` | `https://openrouter.ai/api` | OpenRouter base URL. |
| `openrouter_endpoint_path` | `/alpha/decisions` | OpenRouter path. Any other value selects the chat completions adapter. |
| `jev_endpoint_path` | `/systemone` | TypeSafe path appended to its base URL. |
| `jev_model` | `jev-latest` | TypeSafe model identifier. |
| `openrouter_model` | `~typesafe/jev-latest` | Model identifier sent by the current OpenRouter adapter. Verify model availability before use. |
| `jev_fallback_enabled` | `true` | Permit fallback to the next configured provider. |
| `jev_fallback_order` | `typesafe, openrouter` | Ordered provider preference. |
| `jev_fallback_on` | transport, timeout, 401, 403, 429, 5xx | Errors eligible for fallback. |
| `jev_fallback_cooldown_s` | `60` | Session-local cooldown after a failed provider. |
| `jev_fallback_max_retries` | `1` | Retries for the final available provider. |
| `request_timeout_s` | `30` | Per-request timeout. |
| `keep_threshold` | `0.15` | Fallback threshold before calibration has enough samples. This is deliberately not the rejected `0.5` default. |
| `keep_threshold_max` | `0.40` | Calibration ceiling. |
| `min_keep_rate` | `0.10` | Quantile target that prevents an empty pass. |
| `jev_calibration_enabled` | `true` | Enable rolling calibration. |
| `jev_calibration_window` | `500` | Maximum recent probability samples. |
| `jev_calibration_min_samples` | `50` | Minimum samples before calibration engages. |
| `conservative` | `false` | Enable conservative calibration mode where implemented. |
| `jev_anchor_protection_enabled` | `true` | Permit protected anchor hints. |
| `jev_anchor_patterns` | built-in list | Regexes for hashes, config keys, constraint sentences, file references, code spans, paths, and version pins. |
| `jev_batch_window_turns` | `3` | Turns accumulated before a normal flush. |
| `jev_max_candidates_per_batch` | `300` | Candidate cap per request. |
| `jev_urgent_context_ratio` | `0.90` | Early-flush ratio against the host compaction trigger. |
| `max_state_tokens` | `25000` | State budget for Jev. |
| `max_request_tokens` | `30000` | State plus question budget; must exceed state budget. |
| `truncate_head_chars` | `300` | Head retained for a truncate action. |
| `min_result_chars` | `8000` | Short results are not candidates. |
| `hint_budget_tokens` | `4000` | Bound for injected Jev hints. |
| `lcm_*` | host defaults | LCM settings remain available; do not assume vendor defaults match a host release. |

Provider keys are never included in diagnostics. An explicitly pinned provider fails at load when its key is absent. In `auto` mode, providers with absent keys are filtered out. With both absent, Jev is disabled and LCM continues without a Jev request.

## Decision model

Candidates can be tool calls, matched tool results, or assistant-text anchors. The provider response is parsed into score fields such as `keep_call`, `keep_result`, and `anchor_keep`, plus the `noul` answers and optional rationale. The current action is derived from the score and live threshold:

| Condition | Active-context treatment | Raw store |
|---|---|---|
| keep | Include the candidate within the protected hint budget. | Unchanged. |
| truncate | Include the configured head and a pointer to raw evidence. | Unchanged. |
| drop/defer | Let LCM summaries represent it. | Unchanged and searchable. |
| unscored | Do not invent a decision. | Retained for LCM and recall. |

A keep score at or above the live threshold is eligible for a keep action. LCM remains the deciding assembly layer. A protected anchor is never rewritten by Jev.

## Calibration

The calibrator records observed `keep_call`, `keep_result`, and `anchor_keep` probabilities in a rolling window. Once `jev_calibration_min_samples` is reached, the intended live threshold is the `min_keep_rate` quantile, capped by `keep_threshold_max`; otherwise `keep_threshold` is used. The resulting value is exposed as `jev_threshold_current` and whether it was calibrated as `jev_threshold_calibrated`.

These settings address the threshold failure attributed to PR #116246. They do not prove a target retention rate on a deployment. Recheck the distribution and the evaluator before claiming quality.

## State shaping and edge cases

The shrink ladder attempts full state first, then progressively shorter inputs and result bodies until `max_state_tokens` is respected. At the hard cap, candidates that do not fit are marked `jev_unscored`; they are not silently replaced by a host summary. A 541-call overflow fixture exists in tests, but installation and production behavior remain separate acceptance work.

Candidate pairing is defensive. An unpaired call or result stays raw and is not scored as a fabricated pair. Duplicate identities are rejected by the raw-store ownership check. Percent-encoded endpoint paths are decoded and rejected when they introduce unsafe path components, query strings, fragments, credentials, control characters, or non-local plain HTTP. CJK text is budgeted by the package tokenizer where available; do not treat character counts as token counts. Externalized payloads remain pointers until expanded, so a pointer is not evidence that its body was injected.

Anchor regexes may overlap. The extractor must deduplicate spans before scoring and preserve the original offsets. A broad constraint sentence can coexist with a narrower backtick or identifier anchor. The protected index is bounded by `hint_budget_tokens`; an over-budget item receives a pointer or is left to LCM.

The batcher flushes on the turn window, urgent context pressure, shutdown, and `/reset`. A failed flush leaves the raw batch available and increments fallback/error observability rather than deleting candidates.

## Providers and wire boundaries

The provider abstraction sends a Decisions-shaped payload containing `model`, `state`, and `questions`. TypeSafe uses the configured TypeSafe base plus `jev_endpoint_path`. OpenRouter uses `openrouter_base_url` plus `openrouter_endpoint_path`, with the configured OpenRouter model.

### OpenRouter surfaces

`openrouter_endpoint_path` selects the surface. Two are supported.

| Path | Request sent | Response accepted | When to use it |
|---|---|---|---|
| `/alpha/decisions` (default) | Decisions body: `model`, `state`, `questions` | Decisions body: `answers` mapping each question id to `noul` | OpenRouter's native scoring surface. This is the only surface that accepts the Jev decisions model. |
| any other path, for example `/chat/completions` | Chat body: `model`, `temperature`, `response_format`, one system instruction, and one user message holding `state` and `questions` | Chat body whose first choice content is JSON shaped as `answers` | Self-hosted or proxied gateways, and scoring-capable chat models. |

The chat adapter tolerates fenced JSON and wraps scalar answers, and it passes a body that already carries a non-empty `answers` mapping straight through. A missing, empty, or unparseable answer set raises `malformed`, which is not a fallback trigger, so the request fails loudly rather than scoring blind.

On 2026-09-21 OpenRouter answered a chat completions request for the configured model with `400 ~typesafe/jev-latest is a decisions model and cannot be used with the chat/completions endpoint. Use the /api/alpha/decisions endpoint instead.` The shipped default therefore points at the native surface, and the chat adapter is selectable rather than default. Response parity between the two surfaces is asserted in `tests/test_providers.py`.

Fallback is session-local. A matching transport, timeout, HTTP status, or provider parse failure can cool down the primary and try the next available provider. When both providers fail, LCM proceeds without Jev. Malformed Decisions output is an error, never a source of fabricated scores. Cooldown expiry makes the provider eligible again. `jev_provider_fallback_count` counts provider changes, not HTTP attempts.

## Metrics and diagnostics

`jev_stats` reports the counters below when the plugin is active:

`jev_candidates_total`, `jev_keep_call_count`, `jev_keep_result_count`, `jev_anchor_count`, `jev_unscored_count`, `jev_calls`, `jev_pruned_units`, `jev_fallbacks`, `lcm_summary_nodes_created`, `lcm_nodes_created`, `lcm_text_floor_tokens`, `jev_provider_fallback_count`, `jev_threshold_current`, `jev_threshold_calibrated`, `jev_provider_primary`, `lcm_recall_at_budget`, and `lcm_freed_per_compaction`.

After three consecutive compactions freeing less than 20 percent, the current metrics implementation emits a warning recommending review of the LCM context threshold or summary depth. This is an operator signal, not a performance claim. `jev_providers` reports provider order, environment-variable names present, cooldowns, last errors, and last provider. It must never print key values.

## Upstream lineage and sources

- [PR #116246](https://github.com/NousResearch/hermes-agent/pull/116246), the attributed evaluation and problem framing.
- [fast-jev-compaction](https://github.com/tamaratran/fast-jev-compaction), state shaping and keep/truncate/drop lineage.
- [hermes-jev-compact](https://github.com/TheEpTic/hermes-plugins/tree/main/hermes-jev-compact), Hermes seam and fallback lineage.
- [hermes-lcm](https://github.com/stephenschoettler/hermes-lcm), LCM storage, DAG, and recall lineage.
- [jev-decisions](https://github.com/bojansandhaus/jev-decisions), documentation and Decisions-shaped API context.
- [DeepSeek Harness CLI reference](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/reference/README.md), for the DSH port's related profile semantics.

All benchmark numbers from the brief belong to the cited PR unless an evaluation run in this repository records the fixture, command, environment, and output.