# 1.0.0-rc.4

## [1.0.0-rc.4] - 2026-09-26 (published)

Jev-LCM Compaction Plugin for Hermes: Jev ranks stale evidence before Lossless Context Management condenses conversation history.

This candidate bounds the one Laya route that can leave the machine, names the three arrangements in the vocabulary the DOGA fork uses, and replaces this repository's eight-span quality probe with the strongest evidence that exists for the local classifier. An installation that sets `auto`, `typesafe`, `openrouter`, or `laya` behaves exactly as it did in `1.0.0-rc.3`.

Publication state: published as the GitHub prerelease **v1.0.0-rc.4**, with the wheel attached to that release. No registry publication exists: this plugin is distributed from the GitHub release, not from PyPI.

### Added

- A consecutive-failure breaker on the local hop in `laya_then_hosted`. Each local failure that the chain could escalate past increments a per-process counter. While the counter is at or below three the hosted fallback is still attempted; past three the fallback is suppressed, a warning naming the failure category is logged, and the local error is re-raised so the failure is visible instead of being answered remotely. Any successful local call clears the counter, on the fallback path and on the plain local path alike. The counter is held per process, shared by every chain in it, and reset by a restart; it is not persisted. It is reported as `laya_consecutive_failures` in `chain.diagnostics()` and `jev_providers`.
- The mode aliases `laya_local` and `laya_with_jev_fallback` for `laya` and `laya_then_hosted`, plus `jev_api` for `auto`. An alias is resolved in `Settings.__post_init__` to its canonical value, so both spellings build one chain with one privacy boundary and one breaker, and `Settings(jev_provider="laya_local") == Settings(jev_provider="laya")`. A value outside the accepted set raises `ValueError` at load, and the message names every accepted value and the alias it could have meant.
- `tests/test_laya_fallback_breaker.py`, eight tests named after the behaviour: three consecutive fallbacks followed by a suppressed fourth that re-raises the local error, no remote call of any kind on the suppressed attempt, the reset on a healthy local call on the fallback path and on the plain local path, the per-process lifetime across a rebuilt chain, the counter in diagnostics, a hosted failure that never charges the local breaker, and the category-only suppression warning.
- `tests/test_laya_mode_aliases.py`, six tests over seventeen cases: alias-to-canonical equality, an identical chain and identical diagnostics, every previously accepted value keeping its own chain, the value list in the rejection message, and a guard that the alias table cannot drift from the canonical set.
- A weak local answer never escalates. `tests/test_laya_then_hosted.py` pins that a local score of `0.0`, with the keep threshold at `0.99`, is returned from the machine and makes no hosted request. Only a local exception moves a request to a hosted provider.
- `tests/test_fallback.py` pins logging hygiene instead of describing it: a batch whose state text and candidate text carry a sentinel is scored through a failing chain, and the sentinel never appears in `caplog` while the failure category does.
- `evaluation/live_laya_then_hosted.py` grew two phases: four consecutive local failures against a dead port with the hosted hop answered by a recorder, and a build of both mode vocabularies.

### Changed

- `docs/reference.md`, `README.md`, `docs/limitations.md`, and `docs/verification.md` now lead with the matched 100-question, three-mode benchmark published with the DOGA fork rather than this repository's eight-span probe. `docs/reference.md` gained a table of the three arrangements and the names that select them, a paragraph on what the breaker does not do, and a "Logging and privacy" section recording the audit rule. `docs/operator-guide.md` gained the same arrangement vocabulary, the breaker behaviour, and a troubleshooting entry for repeated fallback. The measured local numbers from 2026-09-22 remain, labelled as the smaller probe they are.
- The documentation states the breaker's limit as plainly as its behaviour: it bounds repeated remote egress after local errors, and it cannot detect a valid yet incorrect local judgment. No threshold was tuned on the benchmark set.

### Evaluation and limitations

- The strongest evidence for the local classifier is the matched 100-question, three-mode benchmark published with the DOGA fork, which used the same classification questions and the same `0.7` ambiguity threshold. Local Laya agreed with the authored label on goal 56/100 against 88/100 for the hosted Jev API, on response mode 41/100 against 68/100, on stakes 37/100 against 67/100, and on high-versus-low ambiguity 67/100 against 87/100; local Laya detected none of the 30 authored high-ambiguity labels at that threshold. The labels are one authored, subjective set that was not independently adjudicated, so read the table as a direction rather than as population accuracy. It is why the hosted arrangement stays the default and the local route is described as an offline mechanism first.
- This repository's own probe remains the smaller measurement: on 2026-09-22, four obviously-keep spans and four obviously-droppable spans averaged `0.6516` and `0.6502`, a gap of `0.0014`, after which calibration reported `0.40`, its cap, and retained all 16 answers, and those 16 question rows took `25.6s` on CPU. The local route fails safe, it keeps evidence rather than dropping it, and frees nothing until thresholds are recalibrated on labelled data or a retention-tuned checkpoint is used.
- The breaker bounds repeated remote egress after local errors and nothing else. It cannot detect a valid yet incorrect local judgment, it is per process so a restart clears it, and the provider cooldown means it counts failures spaced at least `jev_fallback_cooldown_s` apart rather than every call inside one cooldown window.
- No final-answer quality was scored anywhere. Hook injection and classifier agreement are not evidence that a host follows a contract or answers better.

### Verification

- Executed on this head: 127 tests pass, `mypy` is clean over 14 source files, `black --check` reports 38 files unchanged, non-vendored coverage is 97.45% (688 of 706 statements), and `python -m build` produced `jev_lcm_hermes_compaction-1.0.0rc4-py3-none-any.whl` and its source distribution.
- The breaker was exercised live against the trained `laya-serve` on `http://127.0.0.1:8123`, whose `/health` answered `{"status":"ok","loaded":["english"],"device":"cpu"}`. The probe's first phase answered from the machine with score `0.2966`, `order` `["laya", "typesafe", "openrouter"]`, `last_provider` `laya`, and no hosted URL reached. Its third phase kept the local hop on the closed port `http://127.0.0.1:8124` with `jev_fallback_cooldown_s: 0`: three hosted fallbacks answered over the recorded URL `https://api.typesafe.ai/v1/systemone`, the fourth attempt ended with the local `transport_error` and reached no hosted URL at all, and the process counter read `4`.
- The hosted leg is covered by unit tests with an injected transport and by no live hosted call, because no hosted API key exists on the machine that built this candidate. No live hosted verification is claimed. The alias table was also built live, through `ProviderChain` order, for all three arrangements in both vocabularies.

### Configuration

```yaml
context:
  engine: jev-lcm
jev_lcm:
  jev_provider: laya_with_jev_fallback   # or laya_then_hosted
  laya_base_url: http://127.0.0.1:8123
  laya_model: english
  request_timeout_s: 120
```

```sh
python -m pip install laya
laya-serve        # LAYA_HOST, LAYA_PORT, LAYA_DEVICE, LAYA_THREADS, LAYA_MODELS, LAYA_API_KEY
```

Set `TYPESAFE_API_KEY`, `OPENROUTER_API_KEY`, or both through the secret manager. At least one is required by the combined arrangement, and the variable names it needs are reported when it is missing.

### Unchanged

- LCM remains the source of truth and the primary text compressor.
- Jev remains a ranking layer that never rewrites raw evidence.
- Provider selection stays configuration driven, and key values are never printed.
- `auto`, `typesafe`, `openrouter`, and `laya` keep the behaviour they had in `1.0.0-rc.3`: `auto` never selects a Laya route, `laya` still builds a chain of exactly one provider that never leaves the machine, and `jev_fallback_order` still accepts only `typesafe` and `openrouter`.

### Status

Implementation, tests, and documentation are complete, verified, and published. See [docs/compliance.md](docs/compliance.md) and [docs/verification.md](docs/verification.md).

Licensed under the MIT license. Laya is by Nandakishor M and Convai Innovations, Apache-2.0: https://github.com/NandhaKishorM/laya
