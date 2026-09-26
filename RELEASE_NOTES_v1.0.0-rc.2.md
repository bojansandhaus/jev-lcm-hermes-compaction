## [1.0.0-rc.2] - 2026-09-22 (published as a GitHub prerelease; registries pending)

Jev-LCM Compaction Plugin for Hermes: Jev ranks stale evidence before Lossless Context Management condenses conversation history.

This candidate adds a way to run without any hosted service. Jev runs over a TypeSafe or OpenRouter key, or over Laya on your own machine with no key at all, and the local route replaces the hosted one for the profile that selects it. Nothing about the existing default changes: an installation that sets `jev_provider: auto` and supplies a hosted key behaves exactly as it did in `1.0.0-rc.1`.

Publication state: published as a GitHub prerelease at the commit whose CI run passed, with the built artifact `jev_lcm_hermes_compaction-1.0.0rc2-py3-none-any.whl` attached. No registry publication has happened, so no PyPI availability is claimed, and the `v1.0.0` tag remains unused.

### Added

- `laya` provider. Point `jev_provider: laya` at a `laya-serve` process on loopback and every scoring request stays on the machine.
- `laya_base_url`, `laya_endpoint_path`, and `laya_model` settings, defaulting to `http://127.0.0.1:8000`, `/v1/systemone`, and `convaiinnovations/laya`.
- Keyless provider handling. The chain accepts `laya` without a credential and the wire client sends no `Authorization` header when there is no key. `LAYA_API_KEY` is forwarded only when the local server was started with its own bearer check, and diagnostics keep reporting variable names rather than values.
- A replacement mode rather than a chain member: `jev_fallback_order` accepts only `typesafe` and `openrouter`, `auto` never selects the local route on its own, and pinning `laya` gives the profile exactly one provider.
- `tests/test_laya_provider.py`: eight contracts across nine cases covering keyless selection, the Decisions wire shape, loopback endpoint validation, stopped-server failure, fallback ordering, credential forwarding, and the header rule.

### Why this works without an adapter

`laya-serve`, which Laya ships, publishes `POST /v1/systemone` in the TypeSafe Decisions contract and answers with the same `answers` mapping. The provider is therefore the TypeSafe request shape pointed at loopback, not a second protocol path, and the response validation is shared with the hosted route.

### Measured against a live `laya-serve`, 2026-09-22, base English checkpoint, CPU

- Keep and discard were not separated. Four obviously-keep spans and four obviously-droppable spans, scored with the production retention questions, averaged `0.6516` and `0.6502`, a gap of `0.0014`. Calibration then reported `0.40`, its `keep_threshold_max` ceiling, and all 16 answers were retained. The failure direction is safe: the local route keeps evidence instead of dropping it, and compaction frees nothing until thresholds are recalibrated on labelled data or a retention-tuned checkpoint is used.
- Latency scales with question rows. Those 16 rows took `25.6s`, roughly `1.6s` each, past the default `request_timeout_s` of `30`. Raise `request_timeout_s` and lower `jev_max_candidates_per_batch` for a CPU-only server, or serve from a GPU.

No quality claim is made for the local checkpoint on these questions. The numbers above are measurements from one synthetic fixture, not a benchmark against the production transcripts.

### Configuration

```yaml
context:
  engine: jev-lcm
jev_lcm:
  jev_provider: laya
  laya_base_url: http://127.0.0.1:8000
  laya_model: english
  request_timeout_s: 120
```

```sh
python -m pip install laya
laya-serve        # LAYA_HOST, LAYA_PORT, LAYA_DEVICE, LAYA_THREADS, LAYA_MODELS, LAYA_API_KEY
```

### Unchanged

- LCM remains the source of truth and the primary text compressor.
- Jev remains a ranking layer that never rewrites raw evidence.
- Provider selection stays configuration driven, and key values are never printed.

### Status

Implementation, tests, and documentation are complete and pushed. Registry publication still requires an authenticated session this machine does not have. Nothing in this release installs Laya, selects it by default, or enables it in any host profile. See [docs/compliance.md](docs/compliance.md) and [docs/verification.md](docs/verification.md).

Licensed under the MIT license. Laya is by Nandakishor M and Convai Innovations, Apache-2.0: https://github.com/NandhaKishorM/laya
