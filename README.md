# Jev-LCM Compaction Plugin for Hermes

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![Python](https://img.shields.io/badge/python-%3E%3D3.11-blue.svg)](pyproject.toml) [![Status: RC](https://img.shields.io/badge/status-release--candidate-orange.svg)](CHANGELOG.md)

**Jev-LCM Compaction Plugin for Hermes** is the proposed fix for the Jev-only failure modes reported in [hermes-agent PR #116246](https://github.com/NousResearch/hermes-agent/pull/116246). Lossless Context Management for Hermes keeps raw evidence, while Jev compaction for Hermes ranks stale tool calls and recoverable assistant-text anchors before the Hermes context engine condenses history. The current checkout is experimental. Installation, live provider quality, and performance superiority remain unverified.

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
- Runs the same payload through a local Laya server instead, alone or with the hosted APIs as a fallback hop behind it.
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

Yes, subject to the adapter contract documented in [`docs/reference.md`](docs/reference.md). A TypeSafe-only setup pins `jev_provider: typesafe`. An OpenRouter-only setup pins `jev_provider: openrouter`. With `auto`, both keys follow `jev_fallback_order`, defaulting to TypeSafe then OpenRouter. A fallback emits a sanitized line such as `jev_provider_fallback from=typesafe to=openrouter reason=429`. Key values are never printed.

There are three routes, and each is a separate opt-in. Jev runs over a hosted API key, Laya runs locally with no key, or Laya runs locally with the hosted APIs behind it as a fallback. `jev_provider: laya` scores through a `laya-serve` process on your own machine, configured with `laya_base_url`, `laya_endpoint_path`, and `laya_model` in place of a credential, and it is the only route that never leaves the machine. `jev_provider: laya_then_hosted` puts that same local server first and then falls through to every hosted provider in `jev_fallback_order` that has a key. Laya is not a hosted Jev endpoint, it is a separate model that answers the same `/v1/systemone` contract. See the [Laya FAQ](#can-i-run-it-locally-with-laya-instead-of-a-hosted-provider) for the measured limits of the base checkpoint.

**The combined mode is the one Laya route that leaves your machine.** In `laya_then_hosted`, a local attempt that fails a transport, timeout, `401`, `403`, `429`, or `5xx` response sends the scored state to the hosted API as the next hop. That is the point of the mode, so it has to be named explicitly: `laya` alone sends nothing, `auto` still never selects the local route, and `jev_fallback_order` still rejects `laya`. Selecting `laya_then_hosted` with no hosted key at all is a load-time error that names the missing variables, because the mode promises a fallback that would not otherwise exist.

The same engine therefore runs Jev for Hermes over a TypeSafe key, over an OpenRouter key, or over a Laya server on your own machine, with fallback inside the hosted pair or from the local route into it. Jev threshold calibration is automatic from observed scores. Jev provider fallback covers configured transport, timeout, authentication, rate-limit, and server failures. LCM with Jev scoring changes which stale evidence stays visible; LCM continues to own storage and recall.

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
| Provider | `jev_provider`, `typesafe_base_url`, `openrouter_base_url`, `openrouter_endpoint_path`, `jev_endpoint_path`, `jev_model`, `openrouter_model`, `laya_base_url`, `laya_endpoint_path`, `laya_model` |
| Credentials | `TYPESAFE_API_KEY`, `OPENROUTER_API_KEY`, `LAYA_API_KEY` (the local provider needs none) |
| Fallback | `jev_fallback_enabled`, `jev_fallback_order`, `jev_fallback_on`, `jev_fallback_cooldown_s`, `jev_fallback_max_retries` |
| Calibration | `keep_threshold`, `keep_threshold_max`, `min_keep_rate`, `jev_calibration_enabled`, `jev_calibration_window`, `jev_calibration_min_samples`, `conservative` |
| Anchors | `jev_anchor_patterns`, `jev_anchor_protection_enabled`, `hint_budget_tokens` |
| Batching | `jev_batch_window_turns`, `jev_max_candidates_per_batch`, `jev_urgent_context_ratio` |
| Shaping | `max_state_tokens`, `max_request_tokens`, `truncate_head_chars`, `min_result_chars`, `request_timeout_s` |

The complete defaults table is in [`docs/reference.md`](docs/reference.md). `jev_provider` accepts `auto`, `typesafe`, `openrouter`, `laya`, and `laya_then_hosted`; the first four keep the behaviour described above and the last one is the explicit local-first route with the hosted APIs behind it. The settings validator rejects unsafe endpoint paths and non-local plain HTTP.

## Which commands and tools are available?

The active engine exposes `jev_stats`, `jev_scores`, `jev_anchors`, `jev_providers`, and the LCM recovery tools `lcm_grep` and `lcm_expand`. `jev_stats` reports counters, threshold state, provider identity, freed-per-compaction, and the currently unevaluated recall field. The command-line entry point is `jev-lcm`; provider diagnostics and calibration dry-run behavior remain host/version dependent, so verify `jev-lcm --help` in the installed environment.

## What does observability show?

Counters include `jev_candidates_total`, `jev_keep_call_count`, `jev_keep_result_count`, `jev_anchor_count`, `jev_unscored_count`, `jev_calls`, `jev_pruned_units`, `jev_fallbacks`, `jev_provider_fallback_count`, `jev_threshold_current`, `jev_threshold_calibrated`, `jev_provider_primary`, `lcm_summary_nodes_created`, `lcm_nodes_created`, `lcm_text_floor_tokens`, `lcm_freed_per_compaction`, and `lcm_recall_at_budget`. Three consecutive compactions below 20% freed space produce a warning. The evaluation field stays unevaluated until a real harness supplies a result.

## Why use this design?

The design keeps three boundaries visible: LCM owns evidence, LCM compresses text, and Jev ranks candidates. No summary model is allowed to overwrite the raw store. Those are architectural properties, not a claim that this release beats the PR's baselines. The evaluator and fresh-profile acceptance work remain open.

## Is it compatible with my host?

Supported: Hermes 0.21.x or later, hermes-lcm 0.20 or later, any System One compatible endpoint, and OpenRouter models that return Decisions shaped answers. The package declares Python >=3.11 and vendors its LCM integration, so it assembles context without a separate hermes-lcm install. The CI workflow pins host revision `52d203d0` and the vendored LCM snapshot `8d1b1e6d` so the tests are reproducible.

Executed on 2026-09-21 on a clean profile: the built wheel installed, the host discovered the plugin, and the engine ran three times, with `TYPESAFE_API_KEY` alone, with `OPENROUTER_API_KEY` alone, and with both keys. Each run loaded the engine, stored raw rows, and answered a marker query. The assembled-prompt proof is a test rather than a claim: `tests/test_compressor.py` asserts that a delegation id lifted from assistant text appears verbatim in the assembled context and survives a restart. `docs/verification.md` carries the commands and the observed output.

## Who created the ideas behind it?

- Tamara Tran, [`fast-jev-compaction`](https://github.com/tamaratran/fast-jev-compaction), MIT: state shaping and keep/truncate/drop lineage.
- TheEpTic, [`hermes-jev-compact`](https://github.com/TheEpTic/hermes-plugins/tree/main/hermes-jev-compact), MIT: Hermes integration lineage.
- Stephen Schoettler, [`hermes-lcm`](https://github.com/stephenschoettler/hermes-lcm), MIT: SQLite, DAG, and recall lineage.
- Bojan Sandhaus, [`jev-decisions`](https://github.com/bojansandhaus/jev-decisions), MIT: documentation and Decisions-shaped context.
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
Yes. Configure `OPENROUTER_API_KEY` and pin `jev_provider: openrouter`, or use `auto`.

### Can I use both keys at once?
Yes. `auto` selects the first available provider and can fall back on configured failures.

### Can I run it locally with Laya instead of a hosted provider?
Yes. Laya is a typed decision model you run yourself, and the `laya-serve` server it ships speaks the same `/v1/systemone` wire protocol as TypeSafe, so the plugin scores through a process on your own machine with no key and no outbound request:

```sh
python -m pip install laya
laya-serve                       # LAYA_HOST, LAYA_PORT, LAYA_DEVICE, LAYA_THREADS, LAYA_API_KEY
```

```yaml
context:
  engine: jev-lcm
jev_lcm:
  jev_provider: laya
  laya_base_url: http://127.0.0.1:8000
  laya_model: english
  request_timeout_s: 120
```

`laya_base_url` defaults to `http://127.0.0.1:8000`, `laya_endpoint_path` to `/v1/systemone`, and `laya_model` to `convaiinnovations/laya`, which asks the server to pick a checkpoint from the script and language of the state; `english`, `multilingual`, and `typed-decisions` name a checkpoint directly. `LAYA_API_KEY` is forwarded only when the server was started with its own bearer check. The local route has no key to find, so `auto` never selects it, and `jev_fallback_order` accepts only the hosted names. Pinning `laya` gives that profile exactly one provider, and nothing it scores leaves the machine. The only Laya route that can reach a hosted API is `laya_then_hosted`, which has to be named explicitly.

Two measured limits come from a live run against `laya-serve` on 2026-09-22, base English checkpoint, CPU:

- **Quality on these questions is not established.** Across four clearly-keep spans and four clearly-droppable spans, scored with the production retention questions, the keep group averaged `0.6516` and the drop group `0.6502`, a gap of `0.0014`. Calibration then set `0.40`, its `keep_threshold_max` cap, and all 16 answers were retained. The failure direction is safe: the local path keeps everything rather than dropping evidence, so compaction frees nothing until you recalibrate on your own data or use a checkpoint tuned for retention. Treat the local route as an offline mechanism first and a scoring improvement only after you have measured it.
- **Cost is per question row.** The same 16-question request took `25.6s`, about `1.6s` per row, which is past the default `request_timeout_s` of `30`. Raise `request_timeout_s` and lower `jev_max_candidates_per_batch` for a CPU-only server, or load the model once on a GPU.
- **The default port is shared ground.** `laya_base_url` points at `http://127.0.0.1:8000`, which many self-hosted services also claim. If something else already listens there, the plugin reaches that service and reports an error instead of a score; a `404` with the body `{"detail":"Not Found"}` is how that looks. Start the server with `LAYA_PORT=<port>` and set `laya_base_url` to that same port.

### Can Laya fall back to a hosted provider?

Yes, with `jev_provider: laya_then_hosted`. Laya answers first, and a transport error, timeout, `401`, `403`, `429`, or `5xx` from the local server moves the request to the providers in `jev_fallback_order` that have a key, defaulting to TypeSafe then OpenRouter. The failure list is the same one the hosted pair already uses, and a failure that is not on it, such as the `404` from a shared default port, stops at the local route instead of escalating.

```yaml
context:
  engine: jev-lcm
jev_lcm:
  jev_provider: laya_then_hosted
  laya_base_url: http://127.0.0.1:8123
  laya_model: english
  request_timeout_s: 120
```

**This mode sends your state off the machine when the local server fails.** A local transport error, timeout, `401`, `403`, `429`, or `5xx` makes the hosted API the next hop, which is the reason the mode has to be named explicitly rather than inferred. Plain `laya` never leaves the machine, `auto` still never selects a Laya route, and `jev_fallback_order` still rejects `laya`, so a local hop can only lead a chain when this mode names it. Selecting `laya_then_hosted` with no hosted key raises at load and names the missing variables, so a profile cannot silently degrade to local-only.

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

MIT. This is an independent, community-maintained integration. The repository remains an experimental release candidate. Any changelog or release claim must remain **Unreleased** until clean-profile installation, host assembly, provider scenarios, and the recall-at-budget harness are verified.