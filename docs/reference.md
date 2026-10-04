# Technical reference

[NousResearch/hermes-agent PR #116246](https://github.com/NousResearch/hermes-agent/pull/116246) documented failure modes in Jev-only compaction: threshold collapse, a text floor, state-shaping saturation, assistant-text recall loss, and cache churn. This reference maps the current implementation to the corrected design: Jev scores candidates before LCM condensation, while LCM owns storage, summaries, assembly, and recall. The PR's reported measurements are cited as attributed findings, not reproduced results.

## Scope and invariants

The package is opt-in through `context.engine: jev-lcm`; installation does not change a profile. Raw messages enter the LCM-owned store before scoring. Jev returns scores and decisions. It never edits or deletes stored evidence. If scoring is disabled or fails, the host condensation path continues.

The Hermes package currently vendors an LCM implementation and exposes the integration through `plugin.py`, `compressor.py`, `jev_client.py`, `providers.py`, `state_shaper.py`, `anchors.py`, `calibration.py`, `batcher.py`, `metrics.py`, `decisions.py`, and `settings.py`. Read the source when a host-version detail matters; this document does not promise an installation or live-provider result.

Every provider this reference describes is a [System One decision model](https://systemonemodels.org/guides/what-is-a-system-one-model/), also written a typed decision model: a model that reads the state you give it, answers typed `choice`, `score`, and `noul` questions, and returns each answer with a probability rather than prose. The members reachable from this package are Jev (TypeSafe AI or OpenRouter, hosted, closed weights), Clef and Clef Flash (Cloudflare Workers AI), and the local engines Laya (open weights, the default), Kev (open weights, 0.8B to 27B on Qwen3.5 and Qwen3.8 bases), and Tev1 (Together AI, Qwen3.5-based, open weights). Category membership and the shared `/v1/systemone` wire contract are documented claims from those projects and the cited index, not measurements made here. Jev is one vendor's member of the category, not the category's name.

## Configuration

Defaults below are read from `settings.py`.

| Setting | Default | Meaning |
|---|---:|---|
| `jev_provider` | `api_only` | One of the four canonical modes: `api_with_local_fallback`, `api_only`, `local_only`, `local_with_api_fallback`. Every name this package accepted before is still accepted and resolves to the canonical mode it denotes; the alias table below is exhaustive. Anything else is rejected at load with every accepted name in the error. |
| `jev_provider_pin` | derived | The hosted provider a mode name pins. Not written by an operator: it is derived from the mode name in `__post_init__` so `typesafe` keeps meaning TypeSafe rather than becoming an order read from `jev_fallback_order`. |
| `TYPESAFE_API_KEY` | unset | TypeSafe credential, supplied through the environment or secret manager. |
| `OPENROUTER_API_KEY` | unset | OpenRouter credential, supplied through the environment or secret manager. |
| `LAYA_API_KEY` | unset | Optional bearer for a local `laya-serve` started with `LAYA_API_KEY`. The local provider needs no credential. |
| `CLOUDFLARE_API_TOKEN` | unset | Cloudflare Workers AI credential for Clef. Needs the Account > Workers AI > Read permission. |
| `CLOUDFLARE_ACCOUNT_ID` | unset | Cloudflare account id. This is configuration, not a secret, but the endpoint is per account so a Clef request cannot be built without it. |
| `typesafe_base_url` | `https://api.typesafe.ai/v1` | TypeSafe base URL. |
| `openrouter_base_url` | `https://openrouter.ai/api` | OpenRouter base URL. |
| `openrouter_endpoint_path` | `/alpha/decisions` | OpenRouter path. Any other value selects the chat completions adapter. |
| `jev_endpoint_path` | `/systemone` | TypeSafe path appended to its base URL. |
| `jev_model` | `jev-latest` | TypeSafe model identifier. |
| `openrouter_model` | `~typesafe/jev-latest` | Model identifier sent by the current OpenRouter adapter. Verify model availability before use. |
| `laya_base_url` | `http://127.0.0.1:8000` | Local System One decision model server base URL. Plain HTTP is accepted for loopback only. Point it at any engine speaking the same contract. |
| `laya_endpoint_path` | `/v1/systemone` | Local server path, which is the Decisions protocol these local System One servers publish. |
| `local_model` | `laya` | Which local System One decision model answers. This is the engine or checkpoint name sent as the request's `model` field, so a different local model is selected by configuration alone. **Not validated against an allowlist**: the slot is deliberately interchangeable, so a new engine works without a code change or a release. Only an empty or whitespace-only value, and one containing a character that would corrupt the JSON `model` string or a URL path segment (`"`, `\`, `?`, `#`, control characters), is rejected at load. Never a mode, an alias, or a member of `jev_fallback_order`. |
| `laya_model` | mirrors `local_model` | Kept for backwards compatibility and superseded by `local_model`. Read only when `local_model` was left alone; `__post_init__` rewrites it to the resolved name, so a pre-existing reader of this setting sees the engine actually sent. |
| `clef_base_url` | `https://api.cloudflare.com/client/v4/accounts` | Shared base of the per-account Clef path. The account id and the model complete it. Plain HTTP is rejected: a hosted route that carries conversation text must use HTTPS. |
| `clef_model` | `clef` | Clef checkpoint, either `clef` or `clef-flash`. This is a checkpoint of one provider, not a second provider, so it is never a chain member and never an alias. Any other value is rejected at load. |
| `jev_fallback_enabled` | `true` | Permit fallback to the next configured provider. |
| `jev_fallback_order` | `typesafe, openrouter` | Ordered preference inside the hosted providers. The local route is not a chain member under any spelling; `local_with_api_fallback` places it in front of this order and `api_with_local_fallback` places it behind. `clef` is accepted here as a member, and `clef-flash` and `local_model` are not members under any spelling. |
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

Provider keys are never included in diagnostics. An explicitly pinned provider fails at load when its key is absent. In `api_only` (the default), providers with absent keys are filtered out. With both absent, Jev is disabled and LCM continues without a Jev request. Both fallback modes fail at load when no hosted key is present and name the missing variables, because those modes promise a fallback that could not otherwise exist. Pinning `clef` fails at load on either missing variable, the token or the account id, and `diagnostics()` reports the two in separate fields: `keys_present` for credentials and `configuration_present` for the account id. Both report variable names only.

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

The provider abstraction sends a Decisions-shaped payload containing `model`, `state`, and `questions`. TypeSafe uses the configured TypeSafe base plus `jev_endpoint_path`. OpenRouter uses `openrouter_base_url` plus `openrouter_endpoint_path`, with the configured OpenRouter model. Laya uses `laya_base_url` plus `laya_endpoint_path`, with `laya_model`, and carries no credential unless `LAYA_API_KEY` is set. Clef uses `clef_base_url` plus the account id from `CLOUDFLARE_ACCOUNT_ID`, with `clef_model`, and sends the same three body fields.

### OpenRouter surfaces

`openrouter_endpoint_path` selects the surface. Two are supported.

| Path | Request sent | Response accepted | When to use it |
|---|---|---|---|
| `/alpha/decisions` (default) | Decisions body: `model`, `state`, `questions` | Decisions body: `answers` mapping each question id to `noul` | OpenRouter's native scoring surface. This is the only surface that accepts the Jev decisions model. |
| any other path, for example `/chat/completions` | Chat body: `model`, `temperature`, `response_format`, one system instruction, and one user message holding `state` and `questions` | Chat body whose first choice content is JSON shaped as `answers` | Self-hosted or proxied gateways, and scoring-capable chat models. |

The chat adapter tolerates fenced JSON and wraps scalar answers, and it passes a body that already carries a non-empty `answers` mapping straight through. A missing, empty, or unparseable answer set raises `malformed`, which is not a fallback trigger, so the request fails loudly rather than scoring blind.

On 2026-09-21 OpenRouter answered a chat completions request for the configured model with `400 ~typesafe/jev-latest is a decisions model and cannot be used with the chat/completions endpoint. Use the /api/alpha/decisions endpoint instead.` The shipped default therefore points at the native surface, and the chat adapter is selectable rather than default. Response parity between the two surfaces is asserted in `tests/test_providers.py`.

### The four modes and the names that select them

Configuration exposes exactly four selectable modes. Each names which side
leads and whether the other side is a fallback, so the mode alone says what
leaves the machine.

| Mode | Leads | Fallback | Provider order with both hosted keys |
|---|---|---|---|
| `api_with_local_fallback` | hosted API | local | `typesafe`, `openrouter`, `laya` |
| `api_only` | hosted API | none | `typesafe`, `openrouter` |
| `local_only` | local | none | `laya` |
| `local_with_api_fallback` | local | hosted API | `laya`, `typesafe`, `openrouter` |

`api_only` and `local_only` are single-provider routes: no fallback, no chain,
no cooldown list beyond the one provider. A failure is reported, never
rerouted. `api_with_local_fallback` and `local_with_api_fallback` are
two-provider chains and use the existing cooldown, trigger, and breaker
machinery unchanged. A mode that promises a fallback but has no usable provider
for the other side fails at load, naming the missing environment variable.

#### Aliases

Every name this package accepted before the four-mode vocabulary still resolves,
so a deployed configuration keeps the routing decision it had. The mapping is
exhaustive and is asserted in `tests/test_laya_mode_aliases.py`.

| Accepted name | Resolves to | Pin |
|---|---|---|
| `auto` | `api_only` | none |
| `jev_api` | `api_only` | none |
| `laya` | `local_only` | none |
| `laya_local` | `local_only` | none |
| `laya_then_hosted` | `local_with_api_fallback` | none |
| `laya_with_jev_fallback` | `local_with_api_fallback` | none |
| `typesafe` | `api_only` | `typesafe` |
| `openrouter` | `api_only` | `openrouter` |
| `clef` | `api_only` | `clef` |
| `clef_api` | `api_only` | `clef` |
| `clef_with_local_fallback` | `api_with_local_fallback` | `clef` |

`auto` keeps **this package's** existing meaning rather than the generic one: it
resolves the hosted side by credential from `jev_fallback_order` and never
selects the local slot on its own initiative. The default profile therefore
builds the same chain it built before, which is why the default behaviour did
not change.

A pin is stored beside the mode in `jev_provider_pin` rather than folded into
the mode string, so the mode stays one of the four canonical names while
`typesafe` keeps meaning a TypeSafe route. Resolution happens in
`Settings.__post_init__`, so no alias string reaches a chain, a diagnostic, a
log line, or a URL.

`local_model` is never a mode alias and never appears in a fallback order. A
value that is not in the tables above raises `ValueError` at load, and the
message lists the canonical modes, the aliases, and the pinned aliases it could
have meant.

#### The local slot is interchangeable

The provider name stays `laya`, but it is a generic local slot for a System One
decision model rather than a binding to one model. `local_model` selects the
engine, so any local server speaking the same `/v1/systemone` contract fits by
configuration alone: point `laya_base_url` at it and name it in `local_model`.
Known to fit: `laya` (also `laya-multilingual` and `laya-typed-decisions` as
engine names), `kev` (open weights, also `kev-0.8b`), `tev1` (Together AI,
Qwen3.5-based, open weights, `Tev1-4B` and `Tev1-0.8B`), and
`jeff-qwen3.5-0.8b` and `jeff-gemma4-e2b`.

The interchangeable-engine claim is sourced from
[chaitin/Decis](https://github.com/chaitin/Decis), which serves those engines
behind one endpoint speaking TypeSafe's `/v1/systemone` shape, one Docker image
per engine, where swapping `base_url` is the whole migration. Tev1 is
[togethercomputer/tev1](https://github.com/togethercomputer/tev1). **No local
model other than the shipped default has been called live by this package**; the
claim is that they fit the contract, not that this release measured any of them.

### Cloudflare Clef

`jev_provider: clef` scores through [Cloudflare Workers AI](https://developers.cloudflare.com/workers-ai/models/clef/),
which hosts Clef, a member of the same System One decision model category as the
hosted Jev providers. Clef answers the same typed questions in the same way, so
the request and the response path are identical to every other provider except
for three things that are its own.

**The endpoint is per account.** There is no shared Clef endpoint: the URL is
`https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/cloudflare/{model}`.
`CLOUDFLARE_ACCOUNT_ID` is therefore a required part of the path and not an
optional setting. It is configuration rather than a secret, but it is
interpolated into a URL, so it is held to a narrow shape: 1 to 64 characters of
`A-Z`, `a-z`, `0-9`, `_`, or `-`. Anything else is refused before a request is
built, and the error names the variable rather than the value.
`CLOUDFLARE_API_TOKEN` is the credential, needs the Account > Workers AI > Read
permission, and is sent as `Authorization: Bearer`. Both are checked before any
request; pinning `clef` with either missing raises `ValueError` at load naming
it.

**The body is the same three fields.** `model`, `state`, and `questions`, with
`model` set to the selected checkpoint. Nothing is added for Clef.

**Question ids are constrained.** Cloudflare accepts letters, digits, `_`, `.`,
and `-` in a question id, at most 100 characters, and at most 64 questions per
request. This package builds question ids as `<sha256>:<name>`, so the colon it
has always sent is illegal on this wire. An id Clef already accepts travels
unchanged; anything else is renamed to `clefq<n>` and mapped back before the
caller sees the answer, so no caller ever observes a rename. Every caller id is
reserved before any generated name is handed out, so a generated id cannot
shadow a caller's own question and two questions cannot collapse onto one
answer. The caller's own spelling still reaches the model inside the
instruction text. A batch over 64 questions fails before any request, naming
`jev_max_candidates_per_batch`, rather than silently sending fewer questions and
leaving candidates unscored without saying so.

| Question type | Answer read | Reported as | Validated against |
|---|---|---|---|
| `noul` | `noul` | the probability | `0..1` |
| `choice` | `choice` | the index of that label in `criteria` | the label must be one of `criteria` |
| `score` | `score` | the index, on the scale `criteria` defines | `0..len(criteria)-1` |

The bounds come from one helper, `index_scale`, rather than from a per-type
copy, and they are derived from the question that was sent. An ordinal answer
therefore keeps its own scale: a score of `2` over three criteria is accepted
and reported as `2.0`, and the same value over two criteria is rejected. An
answer type this package does not send is read as a `noul` probability, which is
what every other provider in this package returns.

**Both response shapes are accepted.** The bare model output carries `answers`,
`model`, and `usage` at the top level. Cloudflare's general REST surface wraps
the same object as `{"success": true, "result": {...}}`. Both parse and the
top-level `answers` mapping is preferred, falling back to `result.answers`. A
`success: false` envelope is refused with Cloudflare's own error codes surfaced,
for example `Cloudflare Workers AI refused the request (code 7003)`, because
those are more actionable than a parse failure. The reason that feeds fallback,
cooldown, and diagnostics stays inside `ProviderError`'s fixed vocabulary, so a
Clef failure behaves exactly as a TypeSafe failure does.

**Clef-flash is a checkpoint, not a provider.** `clef_model: clef-flash` selects
the 9B variant Cloudflare publishes for latency-bound paths and routes to the
`.../clef-flash` endpoint with `"model": "clef-flash"` in the body. It is a
setting of the one `clef` provider: it is never a `PROVIDER_MODES` value, never
an alias, and never a member of `jev_fallback_order`. An unknown checkpoint is
rejected at load.

**Privacy consequence, stated plainly.** Selecting `clef` sends the scored state,
the candidate text, and the anchors to `api.cloudflare.com`. That is the point
of the route. `clef` alone has no fallback, so a Clef failure does not become a
request to another provider; it raises. If `clef` is placed in
`jev_fallback_order`, it inherits the existing trigger set and a failure on a
trigger moves the same state to the next member, which is the same consequence
`local_with_api_fallback` already documents. `local_only` remains the only route
that never leaves the machine, whichever System One decision model serves it.

Nothing in this subsection was verified against a live Clef service. No
Cloudflare credential available on the machine that built this is authorized for
Workers AI: every candidate token returns HTTP 401 `Authentication error`. The
wire contract above is taken from the two Cloudflare model pages, cited at the
top of the section and again in `docs/verification.md`, and is exercised by
`tests/test_clef_provider.py` and `evaluation/live_clef.py` against an injected
transport. No test sends anything off the machine.

### The local System One slot

`local_only` (alias `laya`) points the same payload at a local server on loopback. `laya-serve` is the reference server and it publishes `POST /v1/systemone` in the TypeSafe Decisions contract, so the request and response path are identical to the hosted route except for the host, the absence of a credential, and the model field.

The slot is **not** bound to that one server. Anything speaking the same `/v1/systemone` contract fits, selected by `local_model` alone: [chaitin/Decis](https://github.com/chaitin/Decis) serves Laya, Kev, and a Jeff family behind one endpoint with one Docker image per engine, so migrating between them is a `base_url` change. See the alias section for the full list of engines known to fit and for the honesty boundary on what has actually been called.

| Setting | Role |
|---|---|
| `laya_base_url` | Where the server listens. Plain HTTP is accepted only for `localhost`, `127.0.0.1`, and `::1`, the same rule every other provider follows. |
| `laya_endpoint_path` | `/v1/systemone` by default, which is the route these servers expose. |
| `local_model` | Which engine answers. Defaults to `laya`. Not checked against an allowlist. |
| `laya_model` | Superseded by `local_model`, still accepted, read only when `local_model` was left alone. |
| `LAYA_API_KEY` | Sent only when the server was started with a bearer check. Diagnostics report the variable name, never its value. |

The local slot replaces the hosted pair rather than joining it. `local_only` builds a chain of exactly one provider, `api_only` never selects it, and `jev_fallback_order` accepts only `typesafe`, `openrouter`, and `clef`. `local_with_api_fallback` is the separate explicit mode that joins the local slot with the keyed hosted providers, and it is described in the next subsection. The wire client omits the `Authorization` header entirely for an empty key, so a server started without a bearer check accepts the request unchanged.

**Quality evidence for this route, in order of strength.** The strongest
available comparison is the matched 100-question, three-mode benchmark published
with the DOGA fork, which exercises the same local server, the same
classification questions, and the same 0.7 ambiguity threshold as this package's
ambiguity handling. It ran each question through local Laya with no fallback,
through the hosted Jev API, and through local Laya with the fallback enabled:

| Measure | Laya local | Hosted Jev API |
|---|---:|---:|
| Goal agreement with the authored label | 56/100 | 88/100 |
| Response-mode agreement | 41/100 | 68/100 |
| Stakes agreement | 37/100 | 67/100 |
| High-versus-low ambiguity agreement at score 0.7 | 67/100 | 87/100 |
| Authored high-ambiguity cases detected | 0/30 | 21/30 |

Read this as a signal about one authored, subjective label set, not as
population accuracy: the labels were written before the local comparison and
were not independently adjudicated. The decision it supports is the one this
package ships: keep the hosted arrangement as the default, describe the local
route as an offline mechanism rather than a quality improvement, and treat a
local failure as the only reason to escalate to a hosted provider.

The older, much smaller probe this repository ran itself is still true and still
secondary. Three limits were measured against a real `laya-serve` on 2026-09-22
with the base English checkpoint on CPU, using this repository's own retention
questions:

1. **Separation between keep and discard is not established.** Four obviously-keep spans and four obviously-droppable spans scored `0.6516` and `0.6502` on average, a gap of `0.0014`, and `JevThresholdCalibrator` then reported `0.40`, its `keep_threshold_max` ceiling, retaining all 16 answers. The local route therefore fails safe: it keeps evidence rather than dropping it, and frees nothing until thresholds are recalibrated on labelled data or a retention-tuned checkpoint is used.
2. **Latency scales with question rows.** Those 16 questions took `25.6s`, roughly `1.6s` per row, beyond the default `request_timeout_s` of `30`. Raise `request_timeout_s` and lower `jev_max_candidates_per_batch`, or serve from a GPU.
3. **The default port is shared ground.** `laya_base_url` defaults to `http://127.0.0.1:8000`, and any other service bound to 8000 answers the request instead of Laya. A `404` carrying `{"detail": "Not Found"}` is the symptom, and it surfaces as `http_error`, which is not a fallback trigger. Start the server with `LAYA_PORT` and point `laya_base_url` at the port you actually bound.

### The two fallback modes

`local_with_api_fallback` (alias `laya_then_hosted`, `laya_with_jev_fallback`) is the explicit opt-in that puts both sides in one chain with the local slot leading. `api_with_local_fallback` is its mirror: the hosted providers lead and the local slot is the last resort. Both use the existing cooldown, trigger, and breaker machinery unchanged.

| Mode | Resulting chain | Leaves the machine |
|---|---|---|
| `local_only` | `laya` | Never. |
| `local_with_api_fallback` | `laya`, then the keyed `jev_fallback_order` members | On a trigger listed in `jev_fallback_on`: transport, timeout, `401`, `403`, `429`, or `5xx`. |
| `api_only` | the keyed `jev_fallback_order` members | Yes, by design. It never selects the local slot on its own initiative and never selects `clef` unless `clef` is named in `jev_fallback_order`. |
| `api_with_local_fallback` | the keyed `jev_fallback_order` members, then `laya` | Yes, on the first hop, always. The local fallback is a last resort, not a privacy setting. |
| `clef` / `clef_api` | `clef` | Yes, to Cloudflare on every request. There is no fallback member, so a failure raises instead of calling another provider. |

With both hosted keys present and the default `jev_fallback_order`, `local_with_api_fallback` builds `laya`, `typesafe`, `openrouter` and `api_with_local_fallback` builds `typesafe`, `openrouter`, `laya`. Each is built from whichever keys are present: with only `OPENROUTER_API_KEY` the orders are `laya`, `openrouter` and `openrouter`, `laya` respectively, and a reversed `jev_fallback_order` reverses the hosted hop in both.

**Privacy consequence, stated plainly.** In `local_with_api_fallback`, a local attempt that fails a transport, timeout, `401`, `403`, `429`, or `5xx` response sends the scored state to a hosted API. That is the point of the mode, and it is why the mode is explicit rather than selected automatically. `local_only` never leaves the machine. A local failure that is not on the trigger list, such as the `404` from a shared default port or a malformed answer, stops at the local route instead of escalating. Selecting `local_with_api_fallback` with no hosted key at all raises `ValueError` at load and names the missing environment variables, because the mode promises a fallback that would not otherwise exist; `LAYA_API_KEY` alone does not satisfy it. `api_with_local_fallback` makes the same guarantee in reverse: it raises at load with no hosted key, and it never sends state anywhere the operator did not already expect to send it.

**The consecutive-failure breaker.** A local server that keeps failing would
otherwise turn every batch into a hosted request, so the chain bounds that.
Each local failure that the chain could escalate past increments a counter, and
while the counter is at or below three the hosted fallback is still attempted.
Past three the fallback is suppressed, a warning naming the category is logged,
and the local error is re-raised so the failure stays visible instead of being
answered remotely. Any successful local call clears the counter, on this mode
and on plain `local_only` alike, and so does any hosted-arrangement success. The count
is held per process, is shared by every chain in that process, and resets when
the process restarts; it is not persisted, so a restart begins at zero. The
provider cooldown bounds egress as well: after a local failure the local hop is
skipped for `jev_fallback_cooldown_s`, so the breaker counts failures across
those windows rather than every call inside one. The counter is reported as
`laya_consecutive_failures` in `chain.diagnostics()` and `jev_providers`.

**What the breaker does not do.** It bounds repeated remote egress after local
errors. It cannot detect a local answer that is valid and wrong, and it does not
change the threshold: a low-scoring local answer is still an answer, returned
locally, and never a reason to call a hosted provider. Only an exception is.

Diagnostics report the mode's real chain through `chain.diagnostics()` and `jev_providers`: `order` carries the full `laya`, `typesafe`, `openrouter` sequence, `last_provider` names the hop that answered, `last_errors` names the hop that failed and its reason, `laya_consecutive_failures` reports the breaker, and `keys_present` reports variable names only, never values.

The hosted leg of this mode is covered by `tests/test_laya_then_hosted.py` with an injected transport that fails on the local URL and records the hosted attempt, and the breaker is covered by `tests/test_laya_fallback_breaker.py`. No live hosted call is part of this release: no hosted API key exists on the machine that built it. The local leg and the breaker are exercised live by `evaluation/live_laya_then_hosted.py`, which prints the built order, the hop that answered, and how four consecutive local failures end.

Fallback is session-local. A matching transport, timeout, HTTP status, or provider parse failure can cool down the primary and try the next available provider. When both providers fail, LCM proceeds without Jev. Malformed Decisions output is an error, never a source of fabricated scores. Cooldown expiry makes the provider eligible again. `jev_provider_fallback_count` counts provider changes, not HTTP attempts.

## Logging and privacy

Every warning this package emits while it scores names a category, a provider, or
a counter. The state, the candidate text, a question instruction, and any answer
are never formatted into a log line: a provider failure is logged by its
`ProviderError.reason` value, which is drawn from a fixed set (`transport_error`,
`timeout`, `401`, `403`, `429`, `5xx`, `http_error`, `malformed`, `disabled`,
`cooldown`) and clamped to `transport_error` for anything else, so a provider
response body or an exception message cannot reach the log. The fallback line is
`jev_provider_fallback from=... to=... reason=...` with provider names, and the
suppression line is `laya_fallback_suppressed after 3 consecutive local failures`.
`tests/test_fallback.py` pins this by driving a batch whose state and candidate
text contain a sentinel and asserting the sentinel never appears in `caplog`.

Clef adds one line, `clef_provider_failed exception=<Type>`, and it is narrower
than the others on purpose. A Clef request carries the conversation text that is
about to be compacted, and by the time a transport failure surfaces that text has
already left the machine, so the only safe thing to report is the exception class
itself. The URL, the account id, the token, the request body, and the exception
message are all excluded; a `urllib` message can quote the request object. The
message an operator sees instead comes from `ClefError`, whose text is composed
of provider names, variable names, counts, and Cloudflare error codes only.
`tests/test_clef_provider.py` drives a Clef failure whose exception message
contains the token, the URL, and a sentinel from the state, and asserts that
none of the three reaches `caplog` or `diagnostics()`.

## Metrics and diagnostics

`jev_stats` reports the counters below when the plugin is active:

`jev_candidates_total`, `jev_keep_call_count`, `jev_keep_result_count`, `jev_anchor_count`, `jev_unscored_count`, `jev_calls`, `jev_pruned_units`, `jev_fallbacks`, `lcm_summary_nodes_created`, `lcm_nodes_created`, `lcm_text_floor_tokens`, `jev_provider_fallback_count`, `jev_threshold_current`, `jev_threshold_calibrated`, `jev_provider_primary`, `lcm_recall_at_budget`, and `lcm_freed_per_compaction`.

After three consecutive compactions freeing less than 20 percent, the current metrics implementation emits a warning recommending review of the LCM context threshold or summary depth. This is an operator signal, not a performance claim. `jev_providers` reports provider order, environment-variable names present, non-credential configuration variable names present, cooldowns, last errors, and last provider. It must never print key values, and it must never print the Cloudflare account id: `configuration_present` reports the variable name, as `keys_present` reports a credential's name without its value.

## Upstream lineage and sources

- [PR #116246](https://github.com/NousResearch/hermes-agent/pull/116246), the attributed evaluation and problem framing.
- [fast-jev-compaction](https://github.com/tamaratran/fast-jev-compaction), state shaping and keep/truncate/drop lineage.
- [hermes-jev-compact](https://github.com/TheEpTic/hermes-plugins/tree/main/hermes-jev-compact), Hermes seam and fallback lineage.
- [hermes-lcm](https://github.com/stephenschoettler/hermes-lcm), LCM storage, DAG, and recall lineage.
- [jev-decisions](https://github.com/bojansandhaus/jev-decisions), documentation and Decisions-shaped API context.
- [System One Models](https://systemonemodels.org/guides/what-is-a-system-one-model/), the category term for every provider this package reaches, and the independent index its member list is cited from.
- [Cloudflare Workers AI: clef](https://developers.cloudflare.com/workers-ai/models/clef/) and [clef-flash](https://developers.cloudflare.com/workers-ai/models/clef-flash/), the hosted Clef endpoint, body, answer types, and question-id constraints the Clef provider implements.
- [DeepSeek Harness CLI reference](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/reference/README.md), for the DSH port's related profile semantics.

All benchmark numbers from the brief belong to the cited PR unless an evaluation run in this repository records the fixture, command, environment, and output.