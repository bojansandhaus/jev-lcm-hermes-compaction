# Requirement compliance map

This page is part of the rework of the Jev-only compaction failure modes reported in [hermes-agent PR #116246](https://github.com/NousResearch/hermes-agent/pull/116246). It maps the six required corrections, the dual-provider contract, and the packaging requirements to implementation files, tests, and executed receipts.

## FIX-1 to FIX-6

| Clause | Implementation | Tests | Status |
|---|---|---|---|
| FIX-1 calibrated threshold, never a fixed `0.5` | `src/jev_lcm_hermes_compaction/calibration.py` | `tests/test_calibration.py::test_calibration_retains_low_probability_candidates`, `tests/test_core.py::test_quantile_and_floor`, `tests/test_parity.py::test_python_reference_matches_checked_in_parity_golden` | Passing |
| FIX-2 assistant-text anchors protected verbatim | `src/jev_lcm_hermes_compaction/anchors.py`, `prepass.py` (`_persist_protected_anchors`, `active_context_block`), `compressor.py` | `tests/test_compressor.py::test_protected_anchor_index_survives_restart_and_enters_assembled_prompt`, `::test_protected_evidence_is_budgeted_by_real_assembly`, `::test_real_lcm_stores_before_scoring_and_preserves_anchor`, `::test_index_write_failure_keeps_volatile_evidence_in_real_assembly`, `::test_protected_index_rejects_raw_pointer_from_another_session`, `tests/test_core.py::test_spans_and_tiers` | Passing |
| FIX-3 LCM is the primary text compressor | `src/jev_lcm_hermes_compaction/compressor.py` (ingests before scoring, supplies ranking hints, leaves condensation and storage to LCM) | `tests/test_integration.py::test_real_compaction_and_recall_with_failed_jev` | Passing |
| FIX-4 tiered shrink ladder, hard cap, explicit `jev_unscored` | `src/jev_lcm_hermes_compaction/state_shaper.py` | `tests/test_core.py::test_spans_and_tiers`, `tests/test_integration.py::test_541_unscored_raw_recovery` | Passing |
| FIX-5 batched scoring across turns | `src/jev_lcm_hermes_compaction/batcher.py`, `prepass.py` | `tests/test_prepass.py::test_batched_anchors_are_exact_and_oversized_batch_is_explicit`, `tests/test_concurrency.py::test_concurrent_ingest_is_idempotent` | Passing |
| FIX-6 honest metrics and low-freed warning | `src/jev_lcm_hermes_compaction/metrics.py` | `tests/test_core.py::test_metrics_warning` | Passing |
| Dual-provider authentication (TypeSafe, OpenRouter, fallback) | `src/jev_lcm_hermes_compaction/providers.py`, `jev_client.py`, `settings.py` | `tests/test_providers.py::test_primary_rate_limit_uses_fallback_without_exposing_secret`, `tests/test_core.py::test_single_provider`, `::test_failures_cooldown_recovery_and_secret_safety`, `::test_no_keys_and_no_budget`, `::test_malformed`, `::test_bad_endpoint`, `tests/test_http_cli.py::test_real_http_transport` | Passing |
| Recall tools remain usable | `compressor.py` tool handlers | `tests/test_integration.py::test_real_compaction_and_recall_with_failed_jev` | Passing |
| Recall-at-budget evaluator | `evaluation/run_eval.py` | `tests/test_evaluation.py::test_real_compaction_and_raw_retrieval`, `::test_retention_is_sensitive_to_real_assembled_output`, `::test_invalid_budget_rejected` | Passing |
| Hermes installation and engine registration | `plugin.py`, `plugin.yaml`, `pyproject.toml` (`hermes_agent.plugins` entry point) | `tests/test_plugin.py::test_opt_in_registration_and_clone`, plus fresh-home install receipts for both discovery routes and the `plugins.enabled` allow-list in `docs/verification.md` | Passing |

## Required regression assertions

| Required assertion | Covered by | Status |
|---|---|---|
| Uniform `[0, 0.2]` `keep_result` probabilities still keep at least 10% of candidates | `tests/test_calibration.py::test_calibration_retains_low_probability_candidates` uses `i/5000` over 500 samples, a stricter band, and asserts at least 50 retained | Passing |
| A delegation id in assistant text appears verbatim in the assembled prompt once its anchor score crosses the threshold | `tests/test_compressor.py::test_protected_anchor_index_survives_restart_and_enters_assembled_prompt` | Passing |
| A 541-call transcript yields `jev_unscored_count > 0` and every unscored candidate is retrievable with `lcm_grep` | `tests/test_integration.py::test_541_unscored_raw_recovery` | Passing |
| `lcm_freed_per_compaction < 20%` for three consecutive cycles emits a warning | `tests/test_core.py::test_metrics_warning` | Passing |
| Two consecutive turns inside the batch window do not produce two Jev requests | `tests/test_prepass.py::test_batched_anchors_are_exact_and_oversized_batch_is_explicit` asserts zero requests after two ticks and exactly one at the window boundary | Passing |
| `OPENROUTER_API_KEY` alone loads and scores without TypeSafe | `tests/test_core.py::test_single_provider` (OpenRouter parameter) | Passing |
| Both keys set, primary returns 429: one fallback retry, `jev_provider_fallback_count` increments by one | `tests/test_providers.py::test_primary_rate_limit_uses_fallback_without_exposing_secret` observes two calls and `fallback_count == 1` | Passing |
| `jev_provider: typesafe` pinned with only an OpenRouter key fails fast naming `TYPESAFE_API_KEY` | `tests/test_core.py::test_single_provider` asserts the raised `ValueError` message names the key | Passing |
| Both keys missing disables Jev scoring and LCM proceeds without raising | `tests/test_core.py::test_no_keys_and_no_budget` | Passing |

## Packaging and documentation

| Requirement | Receipt |
|---|---|
| `pytest` with at least 90% coverage on core modules | 55 tests pass; non-vendored coverage 97.40% |
| `mypy` on `src/` | Passes for 14 source files |
| `black --check` | 28 files unchanged |
| No secret, key, token, or private path in tracked content | A scan for key prefixes, private keys, and absolute home paths over tracked files returns no hit; the only match is the gitignored `.coverage` artifact |
| A test asserts no key value reaches a log, error, or metric | `tests/test_core.py::test_failures_cooldown_recovery_and_secret_safety` and `tests/test_providers.py::test_primary_rate_limit_uses_fallback_without_exposing_secret` |
| `THIRD_PARTY_NOTICES.md` lists upstream projects, licenses, and reuse | Present |
| README section order, provider section, comparison table, FAQ with at least 12 questions, credits, license | Present; 15 FAQ entries |
| Doc pages open with the PR #116246 reminder | `docs/*.md` all open with the reminder and the fixes they concern |
| Ready-to-publish wheel and source distribution | `python -m build` produces both |
| Fresh-profile install, configure, reset, retrieval | Disposable home install registered `jev-lcm` through real discovery, ingested, retrieved with `lcm_grep`, and reset; receipt in `docs/verification.md` |

## Deviations and open items

- The upstream production transcript, provider and model identities, and evaluation policy were never supplied. The evaluator reports synthetic transport integration only; it does not reproduce the PR #116246 production comparison. See `docs/evaluation.md`.
- Live provider qualification was performed once on 2026-09-21 with a synthetic sentence: TypeSafe returned `{"q0": 0.83}` and OpenRouter `{"q0": 0.83}`, one request each and no fallback. Continuous live qualification against real conversation data is not established.
- npm publication is blocked because `npm whoami` reports no session. The GitHub remote push and the draft release are handled through the stored Git credential.
- The requested `1.0.0` changelog heading is present as prepared release content marked unpublished; no stable release is asserted.
