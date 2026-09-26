# Technical reference

[NousResearch/hermes-agent PR #116246](https://github.com/NousResearch/hermes-agent/pull/116246) documented failure modes in Jev-only compaction: threshold collapse, a text floor, state-shaping saturation, assistant-text recall loss, and cache churn. This reference maps the current implementation to the corrected design: Jev scores candidates before LCM condensation, while LCM owns storage, summaries, assembly, and recall. The PR's reported measurements are cited as attributed findings, not reproduced results.

## Scope and invariants

The package is opt-in through `context.engine: jev-lcm`; installation does not change a profile. Raw messages enter the LCM-owned store before scoring. Jev returns scores and decisions. It never edits or deletes stored evidence. If scoring is disabled or fails, the host condensation path continues.

The Hermes package currently vendors an LCM implementation and exposes the integration through `plugin.py`, `compressor.py`, `jev_client.py`, `providers.py`, `state_shaper.py`, `anchors.py`, `calibration.py`, `batcher.py`, `metrics.py`, `decisions.py`, and `settings.py`. Read the source when a host-version detail matters; this document does not promise an installation or live-provider result.

## Configuration

Defaults below are read from `settings.py`.

| Setting | Default | Meaning |
|---|---:|---|
| `jev_provider` | `auto` | `auto`, `typesafe`, `openrouter`, `laya`, or `laya_then_hosted` (Laya first, then the keyed hosted providers). |
| `TYPESAFE_API_KEY` | unset | TypeSafe credential, supplied through the environment or secret manager. |
| `OPENROUTER_API_KEY` | unset | OpenRouter credential, supplied through the environment or secret manager. |
| `LAYA_API_KEY` | unset | Optional bearer for a local `laya-serve` started with `LAYA_API_KEY`. The local provider needs no credential. |
| `typesafe_base_url` | `https://api.typesafe.ai/v1` | TypeSafe base URL. |
| `openrouter_base_url` | `https://openrouter.ai/api` | OpenRouter base URL. |
| `openrouter_endpoint_path` | `/alpha/decisions` | OpenRouter path. Any other value selects the chat completions adapter. |
| `jev_endpoint_path` | `/systemone` | TypeSafe path appended to its base URL. |
| `jev_model` | `jev-latest` | TypeSafe model identifier. |
| `openrouter_model` | `~typesafe/jev-latest` | Model identifier sent by the current OpenRouter adapter. Verify model availability before use. |
| `laya_base_url` | `http://127.0.0.1:8000` | Local `laya-serve` base URL. Plain HTTP is accepted for loopback only. |
| `laya_endpoint_path` | `/v1/systemone` | Local server path, which is the Decisions protocol `laya-serve` publishes. |
| `laya_model` | `convaiinnovations/laya` | Laya checkpoint. `english`, `multilingual`, and `typed-decisions` name a checkpoint; any other value routes by script and language. |
| `jev_fallback_enabled` | `true` | Permit fallback to the next configured provider. |
| `jev_fallback_order` | `typesafe, openrouter` | Ordered preference inside the hosted pair. The local route is not a chain member; `laya_then_hosted` places it in front of this order. |
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

Provider keys are never included in diagnostics. An explicitly pinned provider fails at load when its key is absent. In `auto` mode, providers with absent keys are filtered out. With both absent, Jev is disabled and LCM continues without a Jev request. `laya_then_hosted` fails at load when no hosted key is present and names the missing variables, because that mode promises a hosted fallback that could not otherwise exist.

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

The provider abstraction sends a Decisions-shaped payload containing `model`, `state`, and `questions`. TypeSafe uses the configured TypeSafe base plus `jev_endpoint_path`. OpenRouter uses `openrouter_base_url` plus `openrouter_endpoint_path`, with the configured OpenRouter model. Laya uses `laya_base_url` plus `laya_endpoint_path`, with `laya_model`, and carries no credential unless `LAYA_API_KEY` is set.

### OpenRouter surfaces

`openrouter_endpoint_path` selects the surface. Two are supported.

| Path | Request sent | Response accepted | When to use it |
|---|---|---|---|
| `/alpha/decisions` (default) | Decisions body: `model`, `state`, `questions` | Decisions body: `answers` mapping each question id to `noul` | OpenRouter's native scoring surface. This is the only surface that accepts the Jev decisions model. |
| any other path, for example `/chat/completions` | Chat body: `model`, `temperature`, `response_format`, one system instruction, and one user message holding `state` and `questions` | Chat body whose first choice content is JSON shaped as `answers` | Self-hosted or proxied gateways, and scoring-capable chat models. |

The chat adapter tolerates fenced JSON and wraps scalar answers, and it passes a body that already carries a non-empty `answers` mapping straight through. A missing, empty, or unparseable answer set raises `malformed`, which is not a fallback trigger, so the request fails loudly rather than scoring blind.

On 2026-09-21 OpenRouter answered a chat completions request for the configured model with `400 ~typesafe/jev-latest is a decisions model and cannot be used with the chat/completions endpoint. Use the /api/alpha/decisions endpoint instead.` The shipped default therefore points at the native surface, and the chat adapter is selectable rather than default. Response parity between the two surfaces is asserted in `tests/test_providers.py`.

### Local Laya server

`jev_provider: laya` points the same payload at a `laya-serve` process on loopback. Laya ships that server itself, and it publishes `POST /v1/systemone` in the TypeSafe Decisions contract, so the request and response path are identical to the hosted route except for the host, the absence of a credential, and the model field, which names a Laya checkpoint instead of a Jev model.

| Setting | Role |
|---|---|
| `laya_base_url` | Where the server listens. Plain HTTP is accepted only for `localhost`, `127.0.0.1`, and `::1`, the same rule every other provider follows. |
| `laya_endpoint_path` | Fixed at `/v1/systemone` by default, which is the route `laya-serve` exposes. |
| `laya_model` | `convaiinnovations/laya` (route by script and language), `english`, `multilingual`, or `typed-decisions`. |
| `LAYA_API_KEY` | Sent only when the server was started with `LAYA_API_KEY`. Diagnostics report the variable name, never its value. |

The local route replaces the hosted pair instead of joining it. `jev_provider: laya` builds a chain of exactly one provider, `auto` never selects it, and `jev_fallback_order` accepts only `typesafe` and `openrouter`. `laya_then_hosted` is the separate explicit mode that joins the two, and it is described in the next subsection. The wire client omits the `Authorization` header entirely for an empty key, so a server started without `LAYA_API_KEY` accepts the request unchanged.

Two limits were measured against a real `laya-serve` on 2026-09-22 with the base English checkpoint on CPU, using this repository's own retention questions:

1. **Separation between keep and discard is not established.** Four obviously-keep spans and four obviously-droppable spans scored `0.6516` and `0.6502` on average, a gap of `0.0014`, and `JevThresholdCalibrator` then reported `0.40`, its `keep_threshold_max` ceiling, retaining all 16 answers. The local route therefore fails safe: it keeps evidence rather than dropping it, and frees nothing until thresholds are recalibrated on labelled data or a retention-tuned checkpoint is used.
2. **Latency scales with question rows.** Those 16 questions took `25.6s`, roughly `1.6s` per row, beyond the default `request_timeout_s` of `30`. Raise `request_timeout_s` and lower `jev_max_candidates_per_batch`, or serve from a GPU.
3. **The default port is shared ground.** `laya_base_url` defaults to `http://127.0.0.1:8000`, and any other service bound to 8000 answers the request instead of Laya. A `404` carrying `{"detail": "Not Found"}` is the symptom, and it surfaces as `http_error`, which is not a fallback trigger. Start the server with `LAYA_PORT` and point `laya_base_url` at the port you actually bound.

### Laya with the hosted providers as a fallback

`jev_provider: laya_then_hosted` is the explicit opt-in that puts both routes in one chain. Laya leads, and the hosted providers named by `jev_fallback_order` that have a usable key follow it, so the default order is `laya`, `typesafe`, `openrouter`. The chain is built from whichever keys are present: with only `OPENROUTER_API_KEY` the order is `laya`, `openrouter`, and a reversed `jev_fallback_order` reverses the hosted hop. The fallback triggers, cooldown, and retry settings are the same objects the hosted pair already uses, so nothing about the trigger set changes.

| Mode | Resulting chain | Leaves the machine |
|---|---|---|
| `laya` | `laya` | Never. |
| `laya_then_hosted` | `laya`, then the keyed `jev_fallback_order` members | On a trigger listed in `jev_fallback_on`: transport, timeout, `401`, `403`, `429`, or `5xx`. |
| `auto` | the keyed `jev_fallback_order` members | Yes, by design. It never selects a Laya route. |

**Privacy consequence, stated plainly.** In `laya_then_hosted`, a local attempt that fails a transport, timeout, `401`, `403`, `429`, or `5xx` response sends the scored state to a hosted API. That is the point of the mode, and it is why the mode is explicit rather than selected automatically. The plain `laya` mode never leaves the machine. A local failure that is not on the trigger list, such as the `404` from a shared default port or a malformed answer, stops at the local route instead of escalating. Selecting `laya_then_hosted` with no hosted key at all raises `ValueError` at load and names the missing environment variables, because the mode promises a fallback that would not otherwise exist; `LAYA_API_KEY` alone does not satisfy it.

Diagnostics report the mode's real chain through `chain.diagnostics()` and `jev_providers`: `order` carries the full `laya`, `typesafe`, `openrouter` sequence, `last_provider` names the hop that answered, `last_errors` names the hop that failed and its reason, and `keys_present` reports variable names only, never values.

The hosted leg of this mode is covered by `tests/test_laya_then_hosted.py` with an injected transport that fails on the local URL and records the hosted attempt. No live hosted call is part of this release: no hosted API key exists on the machine that built it. The local leg is exercised live by `evaluation/live_laya_then_hosted.py`, which prints the built order and the hop that answered.

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