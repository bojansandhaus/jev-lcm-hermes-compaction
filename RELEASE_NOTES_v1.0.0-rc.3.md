## [1.0.0-rc.3] - 2026-09-26 (prepared; the release and tag are cut by the maintainer after verification)

Jev-LCM Compaction Plugin for Hermes: Jev ranks stale evidence before Lossless Context Management condenses conversation history.

This candidate adds the third way to run Jev: Laya locally with the hosted APIs behind it as a fallback. The engine now runs Jev over a hosted API key, Laya locally, or Laya locally with the hosted APIs as fallback. The new route is an explicit opt-in, `jev_provider: laya_then_hosted`, so an installation that sets `auto`, `typesafe`, `openrouter`, or `laya` behaves exactly as it did in `1.0.0-rc.2`.

Publication state: prepared and pushed. No git tag, no GitHub release, and no registry publication exists for this candidate; the maintainer cuts the release after verifying. The previous candidate is still the published GitHub prerelease.

### Added

- `laya_then_hosted` provider mode. The chain is Laya first, then every provider in `jev_fallback_order` that has a key, so the default order is `laya`, `typesafe`, `openrouter`. With only one hosted key the chain is `laya` plus that provider.
- Fail-fast validation. Naming the mode with no hosted key at all raises `ValueError` at load and names the missing environment variables, because the mode promises a fallback that would not otherwise exist. `LAYA_API_KEY` alone does not satisfy it.
- `tests/test_laya_then_hosted.py`: order construction with both keys, one key, and none; honouring of a narrowed or reordered `jev_fallback_order`; the local-first hop with no hosted request; fallback after a local failure with the hosted attempt recorded; fallback on transport error, timeout, `401`, `403`, `429`, and `5xx`; the non-triggering `http_error` that stays local; cooldown and recovery across the three-hop chain; secret-safe diagnostics; and the invariants that `laya` stays a single provider, `auto` never includes a Laya route, and `jev_fallback_order` still rejects `laya`.
- `evaluation/live_laya_then_hosted.py`, the live probe used for this candidate.

### Why the fallback triggers are unchanged

The mode reuses `jev_fallback_on`, `jev_fallback_cooldown_s`, and `jev_fallback_max_retries` unchanged, so a local transport error, timeout, `401`, `403`, `429`, or `5xx` moves the same request to the hosted hop, and a local failure that is not on that list, such as the `404` from a shared default port, stops at the local route. No trigger was added for this mode.

### Privacy

In `laya_then_hosted` a failed local attempt sends the scored state to a hosted API. That is the point of the mode, and it is the reason the mode is explicit rather than selected automatically. Plain `laya` never leaves the machine, `auto` still never selects a Laya route, and a local hop leads a chain only when this mode names it.

### Live verification, 2026-09-26

- Local hop, live. `evaluation/live_laya_then_hosted.py` ran the mode against the `laya-serve` on `http://127.0.0.1:8123`, sent one question over real HTTP, and printed the chain it built: `order` `["laya", "typesafe", "openrouter"]`, `last_provider` `laya`, `fallback_count` `0`, `calls` `1`, score `0.2966`, and no hosted URL reached. Nothing on the local leg was mocked.
- Hosted transition, recorded. The same probe then pointed the local hop at a closed port, took a real connection refusal, and recorded the hosted URLs the chain moved to in order: `https://api.typesafe.ai/v1/systemone` then `https://openrouter.ai/api/alpha/decisions`, with `fallback_count` `2` and `last_errors` `{"laya": "transport_error", "typesafe": "transport_error", "openrouter": "transport_error"}`. The hosted requests themselves were recorded, not sent.
- Bound on this claim. The hosted leg is covered by unit tests with an injected transport and by no live hosted call, because no hosted API key exists on the machine that built this candidate. No live hosted verification is claimed.

### Configuration

```yaml
context:
  engine: jev-lcm
jev_lcm:
  jev_provider: laya_then_hosted
  laya_base_url: http://127.0.0.1:8123
  laya_model: english
  request_timeout_s: 120
```

```sh
python -m pip install laya
laya-serve        # LAYA_HOST, LAYA_PORT, LAYA_DEVICE, LAYA_THREADS, LAYA_MODELS, LAYA_API_KEY
```

Set `TYPESAFE_API_KEY`, `OPENROUTER_API_KEY`, or both through the secret manager. At least one is required by this mode, and the variable names it needs are reported when it is missing.

### Unchanged

- LCM remains the source of truth and the primary text compressor.
- Jev remains a ranking layer that never rewrites raw evidence.
- Provider selection stays configuration driven, and key values are never printed.
- `auto` never selects a Laya route, `laya` still builds a chain of exactly one provider, and `jev_fallback_order` still accepts only `typesafe` and `openrouter`.

### Status

Implementation, tests, and documentation are complete and pushed. The maintainer cuts the tag and release after verification. See [docs/compliance.md](docs/compliance.md) and [docs/verification.md](docs/verification.md).

Licensed under the MIT license. Laya is by Nandakishor M and Convai Innovations, Apache-2.0: https://github.com/NandhaKishorM/laya
