# Jev-LCM Compaction Plugin for Hermes

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![Python](https://img.shields.io/badge/python-%3E%3D3.11-blue.svg)](pyproject.toml) [![Version: 1.0.0](https://img.shields.io/badge/version-1.0.0-blue.svg)](CHANGELOG.md)

**Jev-LCM Compaction Plugin for Hermes** is the proposed fix for the Jev-only failure modes reported in [hermes-agent PR #116246](https://github.com/NousResearch/hermes-agent/pull/116246). Lossless Context Management for Hermes keeps raw evidence, while Jev compaction for Hermes ranks stale tool calls and recoverable assistant-text anchors before the Hermes context engine condenses history. The current checkout is experimental. Installation, live provider quality, and performance superiority remain unverified.

## What is a System One decision model?

Every provider this plugin can reach is a [System One decision model](https://systemonemodels.org/guides/what-is-a-system-one-model/), also written a typed decision model: a model that answers typed questions about the text you give it and returns typed answers with a probability for each, instead of generating prose. The three question types are `choice`, `score`, and `noul`. The term is TypeSafe's own, coined on 15 September 2026 alongside Jev, the first member of the category.

Naming the category rather than the product matters here, because this plugin reaches several of its members and Jev is only one of them. Jev is a vendor's member of the category, not the name of the category, so nothing in this documentation calls a decision model "Jev-like" as a type.

| Member | Where it runs | Weights | How this plugin reaches it |
|---|---|---|---|
| Jev | TypeSafe AI or OpenRouter, hosted | closed | `TYPESAFE_API_KEY` or `OPENROUTER_API_KEY` |
| Clef, Clef Flash | Cloudflare Workers AI, hosted | open (Apache 2.0) | `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`, the `clef` provider |
| Laya | local, on your own hardware | open (Apache 2.0) | the local slot, `local_model: laya`, which is the default |
| Kev | local, or OpenRouter | open (Apache 2.0) | the local slot, `local_model: kev` |
| Tev1 | local, or Together AI | open | the local slot, `local_model: tev1` |

**Membership of the category and the shared `/v1/systemone` wire contract are documented claims from those projects and the cited index, not measurements made by this repository.** No model named above was benchmarked here, and no live call was made to any of them.

### Repository topics

This repository carries the topics `clef`, `cloudflare`, `compaction`, `context-management`, `decision-model`, `hermes-agent`, `jev`, `kev`, `laya`, `lcm`, `plugin`, `system-one`, and `tev1`. The tags `system-one` and `decision-model` name the category, and `clef`, `kev`, `laya`, and `tev1` name its members, so the tags and this page describe the same thing.

## What problem does PR #116246 identify?

The PR reported that a fixed `keep_threshold: 0.5` dropped 100% of 851 scored candidates, Jev-only retention tied a recency baseline at one matched budget, freed-per-cycle decayed across long runs, a 25K state ceiling forced blind scoring, assistant-text identifiers escaped tool-call ranking, and per-turn requests disturbed the prompt cache. Those figures are attributed to hermes-agent PR 116246. They are not reproduced measurements from this repository.

| Reported finding | Corrective design in this checkout | Verification status |
|---|---|---|
| Fixed threshold dropped all candidates | Rolling calibration, `0.15` fallback, `0.40` cap, `0.10` minimum keep rate | Deterministic tests exist; deployment distribution pending |
| Tool-only ranking missed assistant text | Regex anchor extraction and protected hint index | Unit coverage exists; host assembly acceptance pending |
| Jev-only text floor grew | LCM remains the primary compressor and storage owner | Host-level proof pending |
| 25K ceiling caused blind decisions | T0 to T4 shrink ladder and explicit `jev_unscored` | Overflow fixture exists; fresh-host proof pending |
| Per-turn calls churned cache | Three-turn batch window and urgent flush | Unit coverage exists; live cache measurement pending |
| Metrics hid the cost | Threshold, unscored, provider, freed-per-compaction, and recall fields | Synthetic integration harness; production comparison unproven |

## What does it do?

- Ingests raw messages into LCM before scoring.
- Scores tool calls, result pairs, and selected assistant-text anchors.
- Leaves raw evidence unchanged. LCM owns SQLite, summaries, active assembly, and recall.
- Uses calibrated Jev thresholding instead of the rejected fixed `0.5` default.
- Batches candidates and marks overflow `jev_unscored` instead of inventing a decision.
- Accepts TypeSafe, OpenRouter, or both with automatic fallback.
- Runs the same payload through a local decision model instead, alone, with the hosted APIs as a fallback hop behind it, or as the fallback hop behind them, bounded by a three-failure breaker so repeated local errors stop becoming hosted requests.
- Optionally scores through Cloudflare Clef instead, as its own provider or as a member of the fallback order, with `clef-flash` as a checkpoint setting rather than a second provider.
- Keeps `lcm_grep` and `lcm_expand` recovery surfaces available.

## How does the pipeline work?

```text
new turn
   |
   v
LCM ingest: complete raw batch
   |
   v
anchor extraction: identifiers, decisions, constraints
   |
   v
batched Jev scoring: calls, results, anchors
   |       shrink ladder T0..T4, provider fallback
   v
LCM condensation: summaries + fresh tail + bounded protected hints
   |
   v
active prompt and recall tools
```

Jev is a ranking layer. It does not rewrite text. The current decision surface includes keep, truncate, defer/drop, and unscored. A keep score at or above the live threshold is eligible for protected inclusion, but the LCM assembler still enforces its prompt budget. A truncate action keeps a head and a raw-store pointer. A deferred item remains in LCM storage.

The shrink ladder starts with full state, then trims tool inputs and result bodies, and ends at a hard cap. Candidates that do not fit are marked `jev_unscored`. Anchors use the same state budget and have their own keep and recovery questions. The batcher flushes at three turns, urgent context pressure, shutdown, and `/reset`.

## Can I bring a TypeSafe key, an OpenRouter key, or both?

Yes, subject to the adapter contract documented in [`docs/reference.md`](docs/reference.md). A TypeSafe-only setup pins `jev_provider: typesafe`. An OpenRouter-only setup pins `jev_provider: openrouter`. With the default mode, both keys follow `jev_fallback_order`, defaulting to TypeSafe then OpenRouter. A fallback emits a sanitized line such as `jev_provider_fallback from=typesafe to=openrouter reason=429`. Key values are never printed.

### Which four modes can I choose from?

Configuration exposes exactly four selectable modes. Each one names which side leads and whether the other side is a fallback, so the mode alone tells you what leaves the machine.

| Mode | Leads | Fallback | Provider order with both hosted keys |
|---|---|---|---|
| `api_with_local_fallback` | hosted API | local | `typesafe`, `openrouter`, `laya` |
| `api_only` | hosted API | none | `typesafe`, `openrouter` |
| `local_only` | local | none | `laya` |
| `local_with_api_fallback` | local | hosted API | `laya`, `typesafe`, `openrouter` |

`api_only` is the default and it is the mode a profile that sets nothing gets. It never selects the local route on its own initiative, so default behaviour is unchanged from earlier releases. `api_only` and `local_only` are single-provider routes: a failure is reported, never rerouted. The two fallback modes are two-provider chains and use the existing cooldown, trigger, and breaker machinery unchanged. A mode that promises a fallback but has no usable provider for the other side fails at load, naming the missing environment variable.

Every name this plugin accepted before still works, resolving to the canonical mode it denotes:

| Existing name | Resolves to | Also pins |
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

The same engine therefore runs Jev for Hermes over a TypeSafe key, over an OpenRouter key, over a Cloudflare Clef model, or over a local decision model on your own machine, with fallback inside the hosted providers, from the local route into them, or from them into the local route. Jev threshold calibration is automatic from observed scores. LCM with Jev scoring changes which stale evidence stays visible; LCM continues to own storage and recall.

### Can the local slot run something other than Laya?

Yes, and that is the point of the new setting. The provider name stays `laya`, but it is a **generic local slot for a System One decision model** rather than a binding to one model. `local_model` selects which local engine answers, and it defaults to `laya`:

```yaml
context:
  engine: jev-lcm
jev_lcm:
  jev_provider: local_only
  local_model: kev-0.8b          # or tev1, jeff-gemma4-e2b, anything your server serves
  laya_base_url: http://127.0.0.1:8000
```

**There is no allowlist.** A new local model has to work by configuration alone, with no code change and no new provider name, so this package deliberately does not validate `local_model` against a list of known engines. Only an empty or whitespace-only value is rejected, and one containing a character that would corrupt the JSON `model` field or a URL path segment (`"`, `\`, `?`, `#`, or a control character). `local_model` is never a mode, an alias, or a member of `jev_fallback_order`.

Which System One decision models are known to fit the slot, all speaking the same `/v1/systemone` contract:

| System One decision model | Names that select it |
|---|---|
| Laya (Convai Innovations, open weights, local) | `laya`, `laya-multilingual`, `laya-typed-decisions` |
| Kev (open weights, 0.8B to 27B on Qwen3.5 and Qwen3.8 bases) | `kev`, `kev-0.8b` |
| Tev1 (Together AI, Qwen3.5-based, open weights) | `tev1`, `Tev1-4B`, `Tev1-0.8B` |
| Jeff family | `jeff-qwen3.5-0.8b`, `jeff-gemma4-e2b` |

The interchangeable-engine claim is sourced from [chaitin/Decis](https://github.com/chaitin/Decis), which serves Laya, Kev, and a Jeff family behind one endpoint speaking TypeSafe's `/v1/systemone` shape, with one Docker image per engine, where swapping `base_url` is the whole migration. Tev1 is [togethercomputer/tev1](https://github.com/togethercomputer/tev1), whose own repository describes `tev1-4B-experimental` as a Qwen3.5-4B fine-tune with open weights. Neither source claims this package measured any of them.

**No local model other than the shipped default has been called live by this plugin.** The claim is that these engines fit the wire contract, not that this release measured any of them. See [`docs/verification.md`](docs/verification.md) for what was and was not executed.

The older `laya_model` setting still works and is read when `local_model` is left alone; `local_model` wins when you set it on purpose. `laya_model` is then rewritten to the resolved name, so a pre-existing reader of that setting sees the engine actually sent.

### What does each mode do with my data?

Naming the model category changes no data flow. Every mode below moves the same bytes it moved before, and the mode still tells you what leaves the machine.

`local_only` scores through a System One decision model server on your own machine, configured with `laya_base_url` and `laya_endpoint_path` in place of a credential, and it is the only route that never leaves the machine. `local_with_api_fallback` puts that same local server first and then falls through to every hosted provider in `jev_fallback_order` that has a key. `api_with_local_fallback` reverses it: the hosted API leads and the local server is the last resort. Clef is described in its own section below.

**`local_with_api_fallback` is the one local-first route that can leave your machine.** In that mode, a local attempt that fails a transport, timeout, `401`, `403`, `429`, or `5xx` response sends the scored state to the hosted API as the next hop. That is the point of the mode, so it has to be named explicitly: `local_only` alone sends nothing, `api_only` never selects the local route, and `jev_fallback_order` still rejects `laya`. Selecting either fallback mode with no hosted key at all is a load-time error that names the missing variables, because the mode promises a fallback that could not otherwise exist.

Which vendor's System One decision model answers does not change that answer. A locally hosted Laya, Kev, or Tev1 keeps the state on the machine in every mode; a hosted Jev or Clef call does not, and that is a property of where the model runs, not of which member of the category it is.

See the [local FAQ](#can-i-run-it-locally-with-laya-instead-of-a-hosted-provider) for the measured limits of the base checkpoint.

### Can I use Cloudflare Clef instead of a Jev provider?

Yes, and it needs neither a TypeSafe nor an OpenRouter account. Clef is another member of the System One category, hosted on Cloudflare Workers AI, and it answers the same typed questions as the hosted Jev providers, so this package sends it the same `model`, `state`, and `questions` body and reads the same `answers` mapping back.

```yaml
context:
  engine: jev-lcm
jev_lcm:
  jev_provider: clef        # or the alias clef_api
  clef_model: clef          # or clef-flash
```

Set two environment variables through your secret manager: `CLOUDFLARE_API_TOKEN`, a Cloudflare API token with the Account > Workers AI > Read permission, and `CLOUDFLARE_ACCOUNT_ID`, the account id, which is configuration rather than a secret but is required because the endpoint is per account. Pinning `clef` with either missing fails at load and names the variable, never its value. `clef` can also be one member of `jev_fallback_order`, for example `[clef, typesafe, openrouter]`, and an uncredentialed `clef` is filtered out of a chain just as an uncredentialed TypeSafe is.

`clef-flash` is a **checkpoint of that one provider**, not a second provider: it changes the endpoint and the `model` field, and it is never a mode value, an alias, or a chain member.

**Selecting `clef` sends your conversation content to Cloudflare.** The scored state, the candidate text, and the protected anchors leave the machine on every request, and this package applies no redaction to them. A local System One decision model remains the only route that never leaves the machine. Review Cloudflare's retention terms for the account first.

**No live Clef call is part of this work.** No Cloudflare credential available on the machine that built it is authorized for Workers AI, so every Clef test runs against an injected transport and the wire contract is taken from Cloudflare's [clef](https://developers.cloudflare.com/workers-ai/models/clef/) and [clef-flash](https://developers.cloudflare.com/workers-ai/models/clef-flash/) documentation. Clef's retention quality, latency, and cost on this workload are unmeasured. What is verified and what is not is recorded in [`docs/verification.md`](docs/verification.md).

## Jev-LCM, Jev-alone, and LCM-alone

| Approach | Raw evidence | Assistant anchors | Primary text compression | Provider failure behavior |
|---|---|---|---|---|
| Jev-alone | Not owned by Jev | Not scored by the original tool-only design | Text floor remains | Host-dependent |
| LCM-alone | Lossless store and recall | No Jev ranking hint | LCM summaries | Host-dependent |
| Jev-LCM | LCM-owned and recoverable | Extracted and bounded | LCM remains primary | Continue without Jev |

This table describes design boundaries. It is not a benchmark claim.

## What changed after PR #116246?

The project follows the PR's conclusion that a summary path is still required. FIX-1 calibrates thresholds. FIX-2 scores assistant anchors. FIX-3 keeps LCM as primary text compressor. FIX-4 adds the hard-capped shrink ladder. FIX-5 batches requests. FIX-6 exposes honest metrics and low-freed warnings. Dual-provider authentication adds a TypeSafe/OpenRouter fallback chain. The complete mapping and edge cases live in [`docs/reference.md`](docs/reference.md).

## How do I install and enable it?

Use the Python environment that runs Hermes:

```sh
git clone https://github.com/bojansandhaus/jev-lcm-hermes-compaction.git
cd jev-lcm-hermes-compaction
python -m pip install .
```

Set one or both provider keys through a secret manager, enable the engine in one profile, then run `/reset`:

```yaml
context:
  engine: jev-lcm
jev_lcm:
  jev_provider: auto
```

`pip install .` registers the package in the host's `hermes_agent.plugins` entry-point group, so the host discovers the plugin. Discovery is not activation: the host loads a non-bundled plugin only when it is allow-listed.

```sh
hermes plugins enable jev-lcm
```

Leave `--allow-tool-override` off. The engine's `lcm_grep` and `lcm_expand` calls route through the host's context-engine dispatch, and the host refuses to let a plugin shadow its built-in tools by default.

A directory install works as well: place `plugin.yaml`, `plugin.py`, and `__init__.py` in `<HERMES_HOME>/plugins/jev-lcm/` with the package importable, then run the same command. `hermes plugins enable` resolves names from that directory, so it answers `No plugin named 'jev-lcm'` when neither the entry point nor the directory is present. Do not run two compaction engines in one profile. Details and executed receipts: [`docs/operator-guide.md`](docs/operator-guide.md).

## What configuration is available?

| Group | Important settings |
|---|---|
| Provider | `jev_provider`, `typesafe_base_url`, `openrouter_base_url`, `openrouter_endpoint_path`, `jev_endpoint_path`, `jev_model`, `openrouter_model`, `laya_base_url`, `laya_endpoint_path`, `local_model` |
| Credentials | `TYPESAFE_API_KEY`, `OPENROUTER_API_KEY`, `LAYA_API_KEY` (the local provider needs none) |
| Fallback | `jev_fallback_enabled`, `jev_fallback_order`, `jev_fallback_on`, `jev_fallback_cooldown_s`, `jev_fallback_max_retries` |
| Calibration | `keep_threshold`, `keep_threshold_max`, `min_keep_rate`, `jev_calibration_enabled`, `jev_calibration_window`, `jev_calibration_min_samples`, `conservative` |
| Anchors | `jev_anchor_patterns`, `jev_anchor_protection_enabled`, `hint_budget_tokens` |
| Batching | `jev_batch_window_turns`, `jev_max_candidates_per_batch`, `jev_urgent_context_ratio` |
| Shaping | `max_state_tokens`, `max_request_tokens`, `truncate_head_chars`, `min_result_chars`, `request_timeout_s` |

The complete defaults table is in [`docs/reference.md`](docs/reference.md). `jev_provider` takes the four canonical modes `api_with_local_fallback`, `api_only`, `local_only`, and `local_with_api_fallback`, plus every name earlier releases accepted (`auto`, `typesafe`, `openrouter`, `laya`, `laya_then_hosted`, `clef`) and the aliases `jev_api`, `laya_local`, `laya_with_jev_fallback`, `clef_api`, and `clef_with_local_fallback`; the alias table above is the full mapping and any other value is rejected at load with the accepted names in the error. `local_model` selects which local engine answers and defaults to `laya`, and `laya_model` remains accepted for configurations written before it existed. The settings validator rejects unsafe endpoint paths and non-local plain HTTP.

## Which commands and tools are available?

The active engine exposes `jev_stats`, `jev_scores`, `jev_anchors`, `jev_providers`, and the LCM recovery tools `lcm_grep` and `lcm_expand`. `jev_stats` reports counters, threshold state, provider identity, freed-per-compaction, and the currently unevaluated recall field. The command-line entry point is `jev-lcm`; provider diagnostics and calibration dry-run behavior remain host/version dependent, so verify `jev-lcm --help` in the installed environment.

## What does observability show?

Counters include `jev_candidates_total`, `jev_keep_call_count`, `jev_keep_result_count`, `jev_anchor_count`, `jev_unscored_count`, `jev_calls`, `jev_pruned_units`, `jev_fallbacks`, `jev_provider_fallback_count`, `jev_threshold_current`, `jev_threshold_calibrated`, `jev_provider_primary`, `lcm_summary_nodes_created`, `lcm_nodes_created`, `lcm_text_floor_tokens`, `lcm_freed_per_compaction`, and `lcm_recall_at_budget`. Three consecutive compactions below 20% freed space produce a warning. The evaluation field stays unevaluated until a real harness supplies a result.

## Why use this design?

The design keeps three boundaries visible: LCM owns evidence, LCM compresses text, and Jev ranks candidates. No summary model is allowed to overwrite the raw store. Those are architectural properties, not a claim that this release beats the PR's baselines. The evaluator and fresh-profile acceptance work remain open.

## Is it compatible with my host?

Supported: Hermes 0.21.x or later, hermes-lcm 0.20 or later, any endpoint speaking the System One decision model wire contract, and OpenRouter models that return Decisions shaped answers. The package declares Python >=3.11 and vendors its LCM integration, so it assembles context without a separate hermes-lcm install. The CI workflow pins host revision `52d203d0` and the vendored LCM snapshot `8d1b1e6d` so the tests are reproducible.

Executed on 2026-09-21 on a clean profile: the built wheel installed, the host discovered the plugin, and the engine ran three times, with `TYPESAFE_API_KEY` alone, with `OPENROUTER_API_KEY` alone, and with both keys. Each run loaded the engine, stored raw rows, and answered a marker query. The assembled-prompt proof is a test rather than a claim: `tests/test_compressor.py` asserts that a delegation id lifted from assistant text appears verbatim in the assembled context and survives a restart. `docs/verification.md` carries the commands and the observed output.

## Who created the ideas behind it?

- Tamara Tran, [`fast-jev-compaction`](https://github.com/tamaratran/fast-jev-compaction), MIT: state shaping and keep/truncate/drop lineage.
- TheEpTic, [`hermes-jev-compact`](https://github.com/TheEpTic/hermes-plugins/tree/main/hermes-jev-compact), MIT: Hermes integration lineage.
- Stephen Schoettler, [`hermes-lcm`](https://github.com/stephenschoettler/hermes-lcm), MIT: SQLite, DAG, and recall lineage.
- Bojan Sandhaus, [`jev-decisions`](https://github.com/bojansandhaus/jev-decisions), MIT: documentation and Decisions-shaped context.
- [System One Models](https://systemonemodels.org/guides/what-is-a-system-one-model/): the decision model category this plugin's providers belong to, and the independent index it is cited from.

Other members catalogued in the same index: **CLM** and **GLiNER2.5-Decide** (open weights), plus hosted **d1** (Liquid AI), **Mercury Decide** (Inception, free on OpenRouter), **Solar Decide** (Upstage), **pplx-decider** (Perplexity), **Span-01** (Respan), **Decider 1** (meraGPT), and the **OpenAI Decisions API**.
- TypeSafe: Jev model and Decisions API.
- OpenRouter: alternate provider surface used by the adapter.
- Ehrlich and Blackman, Voltropy PBC: LCM paper lineage.
- Hermes maintainers and the authors of [PR #116246](https://github.com/NousResearch/hermes-agent/pull/116246): evaluation and problem framing.

## Frequently asked questions

### What happens if Jev is down?
LCM proceeds without Jev scoring. Raw evidence remains in the LCM store.

### Does the plugin store more data?
It maintains raw evidence and metadata needed for recall. Storage growth and retention must be monitored by the operator.

### Can I use OpenRouter?
Yes. Configure `OPENROUTER_API_KEY` and pin `jev_provider: openrouter`, or leave the default mode, which is the same thing.

### Can I use both keys at once?
Yes. The default mode selects the first available provider and can fall back on configured failures.

### Can I run it locally with Laya instead of a hosted provider?
Yes. The local slot holds a System One decision model you run yourself, and the `laya-serve` server it ships speaks the same `/v1/systemone` wire protocol as TypeSafe, so the plugin scores through a process on your own machine with no key and no outbound request. This is unchanged by the category name: a local member keeps the state on the machine, a hosted one sends it off.

```sh
python -m pip install laya
laya-serve                       # LAYA_HOST, LAYA_PORT, LAYA_DEVICE, LAYA_THREADS, LAYA_API_KEY
```

```yaml
context:
  engine: jev-lcm
jev_lcm:
  jev_provider: local_only        # or the alias laya
  local_model: laya
  laya_base_url: http://127.0.0.1:8000
  request_timeout_s: 120
```

`laya_base_url` defaults to `http://127.0.0.1:8000`, `laya_endpoint_path` to `/v1/systemone`, and `local_model` to `laya`, which asks the server to pick a checkpoint from the script and language of the state. Name a checkpoint directly instead with `local_model: laya-multilingual`, or point the slot at a different engine entirely, which is covered in [Can the local slot run something other than Laya?](#can-the-local-slot-run-something-other-than-laya). `LAYA_API_KEY` is forwarded only when the server was started with its own bearer check. The local route has no key to find, so `api_only` never selects it, and `jev_fallback_order` accepts only the hosted names. `local_only` gives that profile exactly one provider, and nothing it scores leaves the machine. The only local-first mode that can reach a hosted API is `local_with_api_fallback`, which has to be named explicitly.

**Quality evidence, strongest first.** The matched 100-question, three-mode benchmark published with the DOGA fork measured local Laya against the hosted Jev API on the same classification questions and the same `0.7` ambiguity threshold: goal agreement `56/100` against `88/100`, response mode `41/100` against `68/100`, stakes `37/100` against `67/100`, high-versus-low ambiguity `67/100` against `87/100`, and local Laya detected none of the 30 authored high-ambiguity labels at that threshold. Those labels are one authored, subjective set, so read the table as a direction rather than as population accuracy. It is why the hosted arrangement stays the default and the local route is described as an offline mechanism first.

The smaller probe this repository ran itself is still true. Against `laya-serve` on 2026-09-22, base English checkpoint, CPU:

- **Separation between keep and discard is not established.** Across four clearly-keep spans and four clearly-droppable spans, scored with the production retention questions, the keep group averaged `0.6516` and the drop group `0.6502`, a gap of `0.0014`. Calibration then set `0.40`, its `keep_threshold_max` cap, and all 16 answers were retained. The failure direction is safe: the local path keeps everything rather than dropping evidence, so compaction frees nothing until you recalibrate on your own data or use a checkpoint tuned for retention. Treat the local route as an offline mechanism first and a scoring improvement only after you have measured it.
- **Cost is per question row.** The same 16-question request took `25.6s`, about `1.6s` per row, which is past the default `request_timeout_s` of `30`. Raise `request_timeout_s` and lower `jev_max_candidates_per_batch` for a CPU-only server, or load the model once on a GPU.
- **The default port is shared ground.** `laya_base_url` points at `http://127.0.0.1:8000`, which many self-hosted services also claim. If something else already listens there, the plugin reaches that service and reports an error instead of a score; a `404` with the body `{"detail":"Not Found"}` is how that looks. Start the server with `LAYA_PORT=<port>` and set `laya_base_url` to that same port.

### Can the local model fall back to a hosted provider?

Yes, with `jev_provider: local_with_api_fallback`. The local model answers first, and a transport error, timeout, `401`, `403`, `429`, or `5xx` from the local server moves the request to the providers in `jev_fallback_order` that have a key, defaulting to TypeSafe then OpenRouter. The failure list is the same one the hosted pair already uses, and a failure that is not on it, such as the `404` from a shared default port, stops at the local route instead of escalating.

```yaml
context:
  engine: jev-lcm
jev_lcm:
  jev_provider: local_with_api_fallback   # or laya_then_hosted
  laya_base_url: http://127.0.0.1:8123
  local_model: laya
  request_timeout_s: 120
```

**This mode sends your state off the machine when the local server fails.** A local transport error, timeout, `401`, `403`, `429`, or `5xx` makes the hosted API the next hop, which is the reason the mode has to be named explicitly rather than inferred. Plain `local_only` never leaves the machine, `api_only` still never selects a local route, and `jev_fallback_order` still rejects `laya`, so a local hop can only lead a chain when this mode names it. Selecting it with no hosted key raises at load and names the missing variables, so a profile cannot silently degrade to local-only.

**Repeated local failures stop escalating.** The chain counts consecutive local failures. While the count is at or below three the hosted fallback is still attempted; past three the fallback is suppressed, a category-only warning is logged, and the local error is re-raised instead of being answered remotely. Any healthy local answer clears the count, which is held per process, shared by every chain in that process, and reset when the process restarts. It is reported as `laya_consecutive_failures` in `jev_providers`. The provider cooldown bounds egress too: after a local failure the local hop is skipped for `jev_fallback_cooldown_s`. What the breaker cannot do is notice a local answer that is valid and wrong: only a local exception moves a request to a hosted provider, never a weak score, and no threshold is changed by it.

This mode is also selectable as `laya_with_jev_fallback`, and plain local mode as `laya_local`; both spellings build the same chain and carry the same breaker.

### What happens if TypeSafe is rate-limited?
A matching `429` can trigger fallback, cooldown, and a sanitized diagnostic when OpenRouter is available.

### Does it work without hermes-lcm?
The package contains a vendored LCM integration. Host compatibility still requires verification; it is not a promise that an arbitrary external LCM version will work.

### How do I disable it?
Set the profile engine back to `compressor`, then run `/reset`.

### Does it slow down every turn?
Scoring is batched, but provider calls add work when a batch flushes. No live latency claim is made here.

### Can I tune the threshold?
Yes. `keep_threshold` is the low-sample fallback; calibration can replace it with a rolling quantile capped by `keep_threshold_max`.

### What is the reduction ratio?
No universal ratio is promised. Measure it with the pending evaluator and your own workload.

### How is the threshold calibrated?
After the minimum sample count, the live threshold follows the configured keep-rate quantile and cap. Before that it uses `keep_threshold`.

### Why score assistant text?
PR #116246 attributed a recall gap to identifiers and constraints in assistant messages, which tool-call-only scoring cannot see.

### How does this differ from fast-jev-compaction?
This package uses Jev as a pre-pass and leaves primary compression, storage, and recall to LCM. It does not claim the upstream project is defective outside the cited evaluation context.

### What did PR #116246 actually prove?
It reported the findings cited above for its tested workloads. This checkout has not reproduced those headline numbers.

### Are dropped results deleted?
No. A drop/defer decision changes active prominence; raw evidence remains recoverable if the store is healthy.

## License and release status

MIT. This is an independent, community-maintained integration. This is the first stable release of the package, and it says nothing about the open verification work: the production recall-at-budget comparison, fresh-profile installation qualification, provider parity review, and the final documentation review are all still open, and no live call to a local model other than the shipped default has been made. Release language stays **Unreleased** until those gates pass.