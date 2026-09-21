# Operator guide

[NousResearch/hermes-agent PR #116246](https://github.com/NousResearch/hermes-agent/pull/116246) found that Jev-only compaction can drop every candidate at a fixed threshold and cannot recover identifiers held in assistant text. This guide covers the corrected Hermes path: calibration, assistant anchors, tiered shaping, batching, provider fallback, and LCM-owned recovery.

## Install

From a checkout, use the Python environment that runs Hermes:

```sh
python -m pip install .
```

The repository declares Python >=3.11. A global installation depends on the host's plugin discovery and can affect every profile that selects the engine. A profile-scoped installation is safer for evaluation. The exact Hermes plugin-manager command is host-version dependent and is intentionally not invented here. Confirm discovery with the host's own plugin listing.

## Configure

Use a secret manager or environment export. Never place key values in YAML committed to a repository.

```yaml
context:
  engine: jev-lcm
jev_lcm:
  jev_provider: auto
  jev_calibration_enabled: true
  jev_batch_window_turns: 3
  hint_budget_tokens: 4000
```

Set one or both of `TYPESAFE_API_KEY` and `OPENROUTER_API_KEY`. Auto mode with both keys uses the configured order and can fall back. A pinned provider with a missing key is a load-time error. With neither key, Jev is disabled and LCM continues without provider traffic.

## Reset semantics

Run `/reset` after changing the engine, provider selection, endpoint, or scoring settings. The batcher flushes on reset, and the new turn begins with the new configuration. Reset does not erase the raw SQLite archive. Treat archive deletion as a separate, deliberate recovery operation.

## Observe

Use the package tools exposed by the active engine:

- `jev_stats`: counters, threshold, provider, freed-per-compaction, and recall field.
- `jev_scores`: candidate scores and actions.
- `jev_anchors`: extracted assistant-text anchors.
- `jev_providers`: sanitized provider order and cooldown diagnostics.
- `lcm_grep` and `lcm_expand`: raw evidence recovery.

A low-freed warning after three consecutive cycles means the current compaction is paying for less space. Inspect `lcm_text_floor_tokens`, summary depth, threshold calibration, and host context settings before raising limits blindly.

## Troubleshooting

| Symptom | Check | Safe response |
|---|---|---|
| Plugin does not load | Python environment, package discovery, YAML engine name | Reinstall in the Hermes environment and return to `compressor` while diagnosing. |
| Missing-key error | `jev_provider` is pinned but its environment variable is absent | Set the named variable through the secret manager or use `auto`. |
| Jev disabled | Neither key is present or all providers are cooling down | Confirm `jev_providers`; LCM should still condense. |
| Fallback repeats | `jev_fallback_on`, provider status, cooldown, endpoint compatibility | Run a synthetic check with no sensitive text, then fix the primary. |
| Malformed response | Provider adapter and model's Decisions-shaped output | Treat as provider failure; do not loosen parsing to accept guessed scores. |
| No anchor appears | Pattern, assistant role, threshold, or hint budget | Inspect `jev_anchors` and `jev_stats`; the raw message remains recoverable. |
| Large batch is unscored | State/request budgets or T4 hard cap | Use LCM recall. Do not claim the provider scored the unscored remainder. |
| Recovery query is empty | Exact session scope and query syntax | Try a distinctive synthetic marker and then expand its returned store id. |

## Bad configuration recovery

1. Stop the affected profile.
2. Copy the profile configuration and SQLite archive to a protected location.
3. Set `context.engine: compressor` or remove the opt-in engine.
4. Run `/reset` and confirm ordinary host operation.
5. Fix one setting at a time. Start with `jev_provider: auto`, one known-good key, and default endpoints.
6. Re-enable `jev-lcm`, run a synthetic marker through one session, and inspect `jev_providers`, `jev_stats`, `lcm_grep`, and `lcm_expand`.

Do not delete raw data as a first response. Key values should never appear in logs, metrics, or error messages. If they do, stop collection, rotate the exposed credential, preserve sanitized diagnostics, and file a security report.

## Operational limits

This guide does not claim a verified clean-profile installation, live provider availability, or benchmark superiority. Those are acceptance items still requiring host-level evidence.