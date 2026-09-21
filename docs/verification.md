# Verification and release status

Hermes PR #116246 motivates the acceptance gates: compaction must retain useful evidence within a measured budget, not merely pass scoring helper tests. This report separates executed checks from outstanding product requirements. The clause-by-clause map is in [compliance.md](compliance.md).

## Executed locally

- 55 tests pass. `mypy` passes for 14 source files. `black --check` reports 28 files unchanged. Non-vendored coverage is 97.40%. `python -m build` produces a wheel and a source distribution.
- Calibration and provider parity: identical JSON scenarios with Python-generated golden results are checked by both languages, covering missing keys, single-provider operation, rate-limit fallback, cooldown expiry, pinned-provider failure, malformed payloads, low-score calibration, minimum samples, cap, and conservative mode.
- The evaluator runs actual engine compaction and raw retrieval with synthetic external transports. `evaluation/results.json` records `production_comparison: false` and `synthetic-transport-integration`. At a 2000-token budget the vendored-LCM arm retained no exact evidence marker (`exact_evidence_retention: 0`) while the Jev-LCM arm retained it (`1`); both arms recovered the marker from persisted raw storage.
- A disposable home install copied the built wheel into an isolated target directory, ran real plugin discovery, registered `jev-lcm` as the context engine, ingested evidence, recovered it with `lcm_grep`, and reset cleanly.
- Install discovery was re-executed against the host loader on 2026-09-21 through both routes. Entry-point route: the built wheel installed into an isolated target, the plugin discovered with `source: entrypoint`, `enabled: true` after the allow-list, engine `jev-lcm` registered. Directory route: `<HERMES_HOME>/plugins/jev-lcm/` with `plugin.yaml`, `plugin.py`, and `__init__.py`, discovered with `source: user`. `hermes plugins enable jev-lcm` was executed against a disposable home and wrote `plugins.enabled: [jev-lcm]`; `hermes plugins disable jev-lcm` wrote `plugins.disabled: [jev-lcm]`.
- Fresh-profile provider acceptance ran three times in disposable homes, one per key configuration, each through real discovery, ingest, `lcm_grep` recovery of a synthetic identifier, and reset: `OPENROUTER_API_KEY` only selected `['openrouter']`, `TYPESAFE_API_KEY` only selected `['typesafe']`, and both keys selected `['typesafe', 'openrouter']`. Each run stored two raw rows and recovered the marker.

## Not established

- The production recall-at-budget comparison. The upstream transcript, provider and model identities, and the upstream evaluation policy were never supplied, so no production number is asserted anywhere in this repository.
- Continuous integration on a later commit than the one under review. The `Tests` workflow was read back as `success` for every pushed head: `fd9d471` (run 35636485852), `37cf192` (35636650091), `fb08f11` (35637318780), and `0e15b2d` (35637532979). A head created after this document cannot carry a read-back run.
- Live provider qualification was performed on 2026-09-21 through this plugin's client with a synthetic sentence: TypeSafe at `https://api.typesafe.ai/v1/systemone` returned `{"q0": 0.83}` and OpenRouter at `https://openrouter.ai/api/alpha/decisions` returned `{"q0": 0.83}`, one request each, no fallback. Real conversation data was never sent.
- Live provider characterization on 2026-09-21 through `evaluation/live_qualification.py`, 12 scoring calls per provider over one synthetic payload of 2455 state tokens and 4 questions: TypeSafe answered 12 of 12 with p50 962 ms and p95 2286 ms, OpenRouter 12 of 12 with p50 1115 ms and p95 2446 ms, no errors and no fallback. Scores for the same question stayed inside 0.67 to 0.70 for both providers, so the providers agree to within 0.03 while neither is deterministic across repeats. That band sits far above the fixed `0.5` the upstream report criticises, which is the case for the calibrated threshold rather than a fixed cut. `LIVE_QUALIFICATION_CALLS` changes the call count; the harness sends no conversation data.
- npm publication: `npm whoami` reports no session, so registry publication is blocked. The GitHub remote and draft release are handled through the stored Git credential.

## Release content

The `1.0.0` changelog section and [RELEASE_NOTES_v1.0.0.md](../RELEASE_NOTES_v1.0.0.md) contain the requested release content and are marked prepared and unpublished. No stable release is asserted.

## Publication record

- Continuous integration, workflow `Tests`, passes on the default branch: the runs for the pushed rework commits, including `35637318780`, were read back green.
- Repository topics include `lcm`, `compaction`, `context-management`, and `jev`; the DSH repository also carries the required `dsh-plugin` discovery topic.
- The `v1.0.0` release exists as a draft and is marked prerelease, with content taken from `RELEASE_NOTES_v1.0.0.md`. A draft release is not a published release and the tag does not exist until it is published.
- npm publication is still blocked: `npm whoami` reports no session on this machine, so `npm publish` cannot run until an npm login exists. For this distribution the remaining command is `npm publish --access public`.
