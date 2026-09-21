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

The same engine therefore runs as TypeSafe Jev for Hermes, as OpenRouter Jev for Hermes, or as a chain across both. Jev threshold calibration is automatic from observed scores. Jev provider fallback covers configured transport, timeout, authentication, rate-limit, and server failures. LCM with Jev scoring changes which stale evidence stays visible; LCM continues to own storage and recall.

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

The exact host plugin-manager command is version-dependent and is not claimed here. See [`docs/operator-guide.md`](docs/operator-guide.md). Do not run two compaction engines in one profile.

## What configuration is available?

| Group | Important settings |
|---|---|
| Provider | `jev_provider`, `typesafe_base_url`, `openrouter_base_url`, `jev_endpoint_path`, `jev_model`, `openrouter_model` |
| Fallback | `jev_fallback_enabled`, `jev_fallback_order`, `jev_fallback_on`, `jev_fallback_cooldown_s`, `jev_fallback_max_retries` |
| Calibration | `keep_threshold`, `keep_threshold_max`, `min_keep_rate`, `jev_calibration_enabled`, `jev_calibration_window`, `jev_calibration_min_samples`, `conservative` |
| Anchors | `jev_anchor_patterns`, `jev_anchor_protection_enabled`, `hint_budget_tokens` |
| Batching | `jev_batch_window_turns`, `jev_max_candidates_per_batch`, `jev_urgent_context_ratio` |
| Shaping | `max_state_tokens`, `max_request_tokens`, `truncate_head_chars`, `min_result_chars`, `request_timeout_s` |

The complete defaults table is in [`docs/reference.md`](docs/reference.md). The settings validator rejects unsafe endpoint paths and non-local plain HTTP.

## Which commands and tools are available?

The active engine exposes `jev_stats`, `jev_scores`, `jev_anchors`, `jev_providers`, and the LCM recovery tools `lcm_grep` and `lcm_expand`. `jev_stats` reports counters, threshold state, provider identity, freed-per-compaction, and the currently unevaluated recall field. The command-line entry point is `jev-lcm`; provider diagnostics and calibration dry-run behavior remain host/version dependent, so verify `jev-lcm --help` in the installed environment.

## What does observability show?

Counters include `jev_candidates_total`, `jev_keep_call_count`, `jev_keep_result_count`, `jev_anchor_count`, `jev_unscored_count`, `jev_calls`, `jev_pruned_units`, `jev_fallbacks`, `jev_provider_fallback_count`, `jev_threshold_current`, `jev_threshold_calibrated`, `jev_provider_primary`, `lcm_summary_nodes_created`, `lcm_nodes_created`, `lcm_text_floor_tokens`, `lcm_freed_per_compaction`, and `lcm_recall_at_budget`. Three consecutive compactions below 20% freed space produce a warning. The evaluation field stays unevaluated until a real harness supplies a result.

## Why use this design?

The design keeps three boundaries visible: LCM owns evidence, LCM compresses text, and Jev ranks candidates. No summary model is allowed to overwrite the raw store. Those are architectural properties, not a claim that this release beats the PR's baselines. The evaluator and fresh-profile acceptance work remain open.

## Is it compatible with my host?

The package declares Python >=3.11. Hermes and hermes-lcm compatibility depends on the host seam in use. The source includes a vendored LCM integration, but a clean-profile installation and assembled-prompt proof are still required. Verify the installed Hermes version before enabling it.

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