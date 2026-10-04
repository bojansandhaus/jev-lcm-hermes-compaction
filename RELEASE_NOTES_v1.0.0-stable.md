# 1.0.0

## [1.0.0] - 2026-10-04 (unpublished)

Jev-LCM Compaction Plugin for Hermes: Jev ranks stale evidence before Lossless Context Management condenses conversation history.

This is the first stable release. It does three things: it names the four decision modes explicitly and adds the fourth one, it turns the local provider into a generic slot that any local [System One decision model](https://systemonemodels.org/guides/what-is-a-system-one-model/) can occupy by configuration, and it removes the release-candidate framing this package carried through `1.0.0-rc.5`.

The providers it reaches are members of that category: Jev (TypeSafe AI or OpenRouter, hosted, closed weights), Clef and Clef Flash (Cloudflare Workers AI), and the open-weights local models Laya (the default), Kev (0.8B to 27B on Qwen3.5 and Qwen3.8 bases, serving TypeSafe's `/v1/systemone` shape), and Tev1 (Together AI, Qwen3.5-based). Jev is one vendor's member of the category rather than the category's name, so nothing here calls a decision model "Jev-like" as a type.

Publication state: **not published.** Nothing here was committed, tagged, or released, and no GitHub release, prerelease, or registry publication exists for it. The version is declared in `plugin.yaml`, `pyproject.toml`, and `__init__.py` so it can be built and reviewed, which is not the same as being released.

### What changed

**The mode vocabulary is now four canonical names.** Each one names which side leads and whether the other side is a fallback, so the mode alone tells an operator what leaves the machine.

| Mode | Leads | Fallback | Order with both hosted keys |
|---|---|---|---|
| `api_with_local_fallback` | hosted API | local | `typesafe`, `openrouter`, `laya` |
| `api_only` | hosted API | none | `typesafe`, `openrouter` |
| `local_only` | local | none | `laya` |
| `local_with_api_fallback` | local | hosted API | `laya`, `typesafe`, `openrouter` |

`api_with_local_fallback` is new: the mirror of the mode that already existed, with the hosted API leading and the local model as the last resort. It uses the existing cooldown, trigger, retry, and diagnostics machinery unchanged. `api_only` and `local_only` are single-provider routes, so a failure is reported and never rerouted.

**The local provider is now a generic slot.** The provider name stays `laya` because that is the vocabulary an operator already writes, but `local_model` (default `laya`) selects which engine answers. Any local server speaking the same `/v1/systemone` contract fits by configuration alone: point `laya_base_url` at it and name it in `local_model`. No new provider name, no code change, no new release needed for a new engine. This is deliberately not enforced against an allowlist, because an allowlist would defeat the point; only an empty or whitespace-only value, and one carrying a character that would corrupt the JSON `model` string or a URL path segment, is rejected.

System One decision models known to fit: `laya` (also `laya-multilingual`, `laya-typed-decisions`), `kev` (also `kev-0.8b`), `tev1` (Together AI, Qwen3.5-based, open weights, `Tev1-4B` and `Tev1-0.8B`), and `jeff-qwen3.5-0.8b` and `jeff-gemma4-e2b`. Sourced from [chaitin/Decis](https://github.com/chaitin/Decis), which serves these engines behind one endpoint speaking TypeSafe's `/v1/systemone` shape with one Docker image per engine so that swapping `base_url` is the whole migration, and from [togethercomputer/tev1](https://github.com/togethercomputer/tev1).

**`laya_model` still works.** It is read when `local_model` was left alone, `local_model` wins when set on purpose, and `laya_model` is then rewritten to the resolved name so any pre-existing reader of it sees the engine actually sent. Its default is now `laya` rather than `convaiinnovations/laya`: the same default expressed through the generic slot.

### What stayed compatible

Every mode name this plugin has ever accepted still resolves, and each resolves to the canonical mode that reproduces the routing decision it produced before this change. This is asserted per alias, against both the resolved mode and the resulting provider order, in `tests/test_laya_mode_aliases.py`.

| Existing name | Resolves to | Pin |
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

`auto` keeps this package's existing meaning rather than the generic one: it resolves the hosted side by credential from `jev_fallback_order` and never selects the local slot on its own initiative. **The default behaviour did not change.** The default mode is now spelled `api_only`, which is what `auto` resolves to, so a profile that sets nothing builds the same chain it built at `1.0.0-rc.5`.

`typesafe`, `openrouter`, and `clef` keep pinning their hosted provider. They resolve to `api_only` carrying a pin in `jev_provider_pin`, which is what keeps `typesafe` meaning a TypeSafe route rather than becoming an order read from `jev_fallback_order`. Aliases resolve in `Settings.__post_init__`, before they reach a chain, a diagnostic, a log line, or a URL, so no alias string appears in observable output.

The settings `clef_base_url`, `clef_model`, `typesafe_base_url`, `openrouter_base_url`, `openrouter_endpoint_path`, `jev_endpoint_path`, `jev_model`, and `openrouter_model`, the credential names, the `PROVIDER_MODES` validation of the Clef checkpoints, the endpoint rules, and the `jev_fallback_order` member set (`typesafe`, `openrouter`, `clef`) are all unchanged.

### Privacy boundary

The direction is unchanged and the coverage is stronger.

- `local_only` never leaves the machine, whichever System One decision model is configured there. Naming the category changed no data flow in any mode.
- `local_with_api_fallback` sends the scored state to a hosted API when the local server fails a trigger in `jev_fallback_on`. That is the point of the mode and it is why the mode is named explicitly.
- `api_only` and `api_with_local_fallback` send it to the hosted API on the first hop. The local fallback in the latter is a cost and availability decision, not a privacy setting.
- Selecting Clef sends it to `api.cloudflare.com` on every request.

Failure logs record the provider and the exception class only. New tests in `tests/test_local_model_slot.py` drive a failure whose exception message carries the URL, the credential, the state, the candidate text, and the question, and assert that none of them reaches `caplog` or `diagnostics()` in any of the four modes. A rejected `local_model` is reported without echoing the value back.

### Testing

- **246 tests pass** with `python -m pytest -q --ignore=tests/test_plugin.py`. Before this change the same command reported **162 passed**; the 84 new tests are the whole of the difference.
- `tests/test_plugin.py` is excluded for a reason that predates this work: it imports `hermes_cli.plugins`, which imports `hermes_yaml` from the Hermes source tree, and that tree is not on the interpreter path under this venv.
- Six existing assertions were **updated** rather than deleted, because they encoded the old canonical spellings this change intentionally replaces: the alias table in `tests/test_laya_mode_aliases.py`, the local default and mode assertions in `tests/test_laya_provider.py`, the mode-name and chain-shape assertions in `tests/test_laya_then_hosted.py`, and the Clef alias resolution in `tests/test_clef_provider.py`. Each was rewritten to assert the resolved canonical mode and the unchanged provider order, which is the property that matters.
- `tests/conftest.py` exposes its credential strip rule as `is_credential` and `CREDENTIAL_VARIABLES`, and `tests/test_credential_isolation.py` asserts that list equals the credential map the provider chain actually reads. The by-name stripping of `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` introduced in `1.0.0-rc.5` is preserved, so a credential added to `providers.py` and forgotten in the fixture now fails the suite instead of leaking a real token into it silently.

### Not established, and not claimed

- **No live call to any local model other than the shipped default has been made by this package.** No local model server is running on the machine that built this, and every local test in the suite runs against an injected transport. The interchangeable-engine list is a statement about the wire contract, sourced from the two projects named above, not a measurement. No score from `kev`, `tev1`, or any Jeff checkpoint was ever produced here.
- **`evaluation/live_laya_then_hosted.py` cannot run on this machine**, because it requires a live `laya-serve` on loopback. It fails with `ProviderError: transport_error` on the current head and fails identically on the pre-change commit `ee8ea34`, so this is an environment condition and not a regression.
- `evaluation/live_clef.py` was executed and reported the same offline wire shape as before, including `clef_flash_is_a_checkpoint_not_a_provider: true`. No live Clef request is part of this release; no Cloudflare credential available on this machine is authorized for Workers AI, every candidate returning HTTP 401.
- No score quality, latency, or cost figure is claimed for the new mode or for any engine that can occupy the slot. No `python -m build` was run, so no wheel or source distribution is asserted.

### Release blockers

The repository's standing blockers are unchanged: the production recall-at-budget comparison, fresh-profile installation qualification, provider parity review, final documentation review, and publication. `1.0.0` is a version number and a removal of release-candidate framing; it is not a claim that those gates passed.

### Credits and license

The interchangeable-engine reference is [chaitin/Decis](https://github.com/chaitin/Decis) and [togethercomputer/tev1](https://github.com/togethercomputer/tev1). The MIT license applies; see [third party notices](THIRD_PARTY_NOTICES.md).