# Operator guide

[NousResearch/hermes-agent PR #116246](https://github.com/NousResearch/hermes-agent/pull/116246) found that Jev-only compaction can drop every candidate at a fixed threshold and cannot recover identifiers held in assistant text. This guide covers the corrected Hermes path: calibration, assistant anchors, tiered shaping, batching, provider fallback, and LCM-owned recovery.

## Install

From a checkout, use the Python environment that runs Hermes:

```sh
python -m pip install .
```

```sh
python -m pip install .
hermes plugins enable jev-lcm
```

The repository declares Python >=3.11. `pip install .` declares the package in the `hermes_agent.plugins` entry-point group, which is how the host discovers it. Discovery alone does not activate a non-bundled plugin, so the enable step writes the `plugins.enabled` allow-list; `hermes plugins disable jev-lcm` reverses it. An installation into a shared environment can affect every profile that selects the engine, so a profile-scoped installation is safer for evaluation.

Two install routes were executed against the host loader: the entry-point route (wheel installed, no plugin directory) reported `source: entrypoint`, and a directory install at `<HERMES_HOME>/plugins/jev-lcm/` reported `source: user`. In this host revision the directory route requires `__init__.py` beside `plugin.yaml` and `plugin.py`, and answers `No __init__.py in <dir>` without it. `hermes plugins enable` resolves names from that directory, so it reports `No plugin named 'jev-lcm'` when the plugin is installed only as an entry point; write the allow-list in `config.yaml` for that route:

```yaml
plugins:
  enabled:
    - jev-lcm
```

Do not pass `--allow-tool-override`. The engine's `lcm_grep` and `lcm_expand` calls reach the host context-engine dispatch, and the host refuses to let a plugin shadow built-in tools by default.

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

Three routes are available: `auto` runs Jev over the hosted keys, `laya` runs Laya locally and nothing leaves the machine, and `laya_then_hosted` runs Laya first with the keyed hosted providers behind it. The combined mode needs at least one hosted key and raises at load, naming the variables it needs, without one. In that mode a local failure on a configured trigger sends the state to a hosted API, so enable it only where that consequence is acceptable.

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