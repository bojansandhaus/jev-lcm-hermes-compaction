# 1.0.0-rc.5

## [1.0.0-rc.5] - 2026-10-04 (unpublished)

Jev-LCM Compaction Plugin for Hermes: Jev ranks stale evidence before Lossless Context Management condenses conversation history.

This candidate adds Cloudflare Clef as a fourth decision-model provider. Clef is hosted at Cloudflare Workers AI, it answers the same System One shaped typed questions as the hosted Jev providers, and it plugs into the chain, the fallback order, the cooldown, and the diagnostics this package already had, with none of that machinery changed. An installation that sets `auto`, `typesafe`, `openrouter`, `laya`, or `laya_then_hosted` behaves exactly as it did in `1.0.0-rc.4`.

Publication state: **not published.** Nothing in this candidate was committed, tagged, or released, and no GitHub release, prerelease, or registry publication exists for it. The version is declared in `plugin.yaml`, `pyproject.toml`, and `__init__.py` so the candidate can be built and reviewed, which is not the same as being released.

### Added

- **The provider `clef`**, selectable as `jev_provider: clef` and as the mode alias `clef_api`. It is a first class provider rather than a special case: it is a `PROVIDER_MODES` value, pinning it builds a chain of exactly one provider, it is accepted as a member of `jev_fallback_order`, it is filtered out of a chain when it has no credential exactly as an uncredentialed TypeSafe is, and it uses the existing retry, cooldown, fallback-trigger, and diagnostics paths without modification.
- **`clef_model`**, default `clef`. `clef-flash` selects the checkpoint Cloudflare publishes for latency-bound paths: it routes to the `@cf/cloudflare/clef-flash` endpoint and sends `"model": "clef-flash"` in the request body. **Clef-flash is a checkpoint of one provider, not a second provider.** It is never a `PROVIDER_MODES` value, never an alias, and never a member of `jev_fallback_order`, and an unknown checkpoint is rejected at load.
- **`clef_base_url`**, default `https://api.cloudflare.com/client/v4/accounts`, the shared prefix of the per-account path. It is validated by the same endpoint rules as every other provider, so a non-local plain-HTTP base is refused.
- **Two environment variables.** `CLOUDFLARE_API_TOKEN` is the credential and needs the Account > Workers AI > Read permission; it is sent as `Authorization: Bearer`. `CLOUDFLARE_ACCOUNT_ID` is the account id, which is configuration rather than a secret, but the endpoint is per account, so the URL cannot be built without it. Both are checked before any request is attempted.
- **Question-id sanitization with a guaranteed restore.** Cloudflare accepts letters, digits, `_`, `.`, and `-` in a question id, at most 100 characters, at most 64 questions per request. This package builds ids as `<sha256>:<name>`, so the colon it has always sent is illegal on this wire. An id Clef already accepts travels unchanged; anything else is renamed to `clefq<n>` and the answer is mapped back before the caller sees it, so no caller ever observes a rename. Every caller id is reserved before any generated name is handed out, so a generated id can never shadow a caller's own question and two questions can never collapse onto one answer. The caller's own spelling still reaches the model inside the instruction text, which is where this package already put it.
- **Per-type answer validation from one shared helper.** `index_scale` derives the bounds of a scale from the `criteria` the question declared, and `answer_value` reduces one typed answer against those bounds. A `noul` answer is a probability on `0..1`; a `choice` must name one of its `criteria` and is reported at that label's index; an ordered `score` is an index on `0..len(criteria)-1` and is reported on that scale rather than divided into `0..1`. A score of `2` over three criteria is accepted and reported as `2.0`; the same value over two criteria is rejected, because the bound was derived from the question rather than copied from a constant. `parse_answers` takes the questions to validate against as an optional third argument, so every pre-existing provider keeps reading `noul` on `0..1` exactly as it did before this change.
- **Both documented Clef response shapes.** The bare model output with top-level `answers`, and Cloudflare's REST envelope `{"success": true, "result": {...}}`. Both parse, and the top-level `answers` mapping is preferred with `result.answers` as the fallback. A `success: false` envelope is refused with Cloudflare's own error codes surfaced verbatim, for example `Cloudflare Workers AI refused the request (code 7003)`, because those codes are more actionable than a parse failure.
- **`ClefError`**, a `ProviderError` subclass whose `reason` stays inside the existing fixed vocabulary while its message names the cause an operator can act on: a missing variable, an unusable account id, or a Cloudflare error code. Because the reason is unchanged, a Clef failure falls back, cools down, and appears in diagnostics exactly as a TypeSafe failure does. The message text is composed only of provider names, variable names, counts, and provider codes.
- **`configuration_present` in `chain.diagnostics()`**, so the Cloudflare account id is reported by variable name in its own field, separate from `keys_present`. Neither field ever reports a value.
- **`tests/test_clef_provider.py`**, 36 tests. Clef alone sends no request to TypeSafe, OpenRouter, or Laya; `clef_api` builds the same chain and diagnostics as `clef`; the token and account id are read from the environment and appear in no diagnostic; `clef` is accepted in `jev_fallback_order` and filtered out of it without a token; a `429` from Clef falls through to the next member on the existing trigger; `clef-flash` reaches the flash endpoint and model string; both envelopes parse; the top-level `answers` wins over `result.answers`; `success: false` raises with Cloudflare's codes and with reason `http_error`; a missing token or account id fails at load with no request and names the variable; an account id that could rewrite the path is refused before a request; a disallowed question id is mapped and restored; the caller's id still reaches the model in the instruction text; a generated id cannot shadow a caller's own question; 65 questions fail before any request naming `jev_max_candidates_per_batch` and 64 succeed; an unknown `choice` is rejected; an out-of-range index-scale `score` is rejected while an in-range one is accepted at its own scale; a probability outside `0..1` is rejected; and a failure whose exception message carries the token, the URL, and a sentinel from the state reaches neither `caplog` nor `diagnostics()`.
- **`evaluation/live_clef.py`**, a six-phase probe following `live_laya_then_hosted.py` as the precedent for provider qualification: the recorded wire shape, the checkpoint selection for both checkpoints, the alias and chain orders, the three missing-credential cases, a phase that attempts the real request when both variables are present and reports Cloudflare's answer, and both response envelopes offline. Its module docstring states the honesty boundary before the code runs.
- **Documentation.** A "Cloudflare Clef" section in `docs/reference.md` covering the per-account endpoint, the request body, the id constraints, the per-type answer table, both envelopes, the checkpoint rule, and the privacy consequence. A "Cloudflare Clef only" section in `docs/integrations.md` with the two variables, a profile snippet, and the chain form. A new "Executed locally for the Clef provider" section and four new entries under "Not established" in `docs/verification.md`. Provider and credential notes in `README.md` and `docs/limitations.md`. The Clef source pages are cited in `docs/reference.md`'s lineage list.

### Changed

- **`tests/conftest.py` strips the two Cloudflare variables by name.** The existing autouse fixture removed environment variables ending in `API_KEY` or starting with `LCM_`. `CLOUDFLARE_API_TOKEN` matches neither rule, so it survived isolation and the machine's real Cloudflare token reached `tests/test_http_cli.py`, which asserts an empty `keys_present`. This was found by running the suite, not by reading it, and the fix keeps a developer's real Cloudflare environment out of every test.
- **`docs/reference.md` describes four arrangements rather than three**, adding `clef` and `clef_api` to the arrangement table, and states that `jev_fallback_order` accepts `clef` as a member alongside `typesafe` and `openrouter`. No existing arrangement, alias, or default changed.
- **`examples/hermes_config_snippet.yml`** documents the two Cloudflare variables, the optional `clef_base_url` and `clef_model` settings with their privacy consequence, and `LAYA_API_KEY`, which the file did not previously list.
- **Version bumped to `1.0.0rc5`** in `plugin.yaml`, `pyproject.toml`, and `__init__.py`, matching the convention that the version moves in the same commit as its release notes.

### Privacy boundary

**Selecting `clef` sends conversation content to a third-party API.** The scored state, the candidate text, and the protected anchors all leave the machine on every request to `api.cloudflare.com`. This package applies no secret redaction to that state, and the raw archive it writes is not encrypted by this package. `clef` alone has no fallback member, so a Clef failure raises rather than becoming a request to some other provider; naming `clef` in `jev_fallback_order` makes it inherit the existing trigger set, which is the same consequence `laya_then_hosted` already documents and states plainly. `laya` remains the only route in this package that never leaves the machine.

**The new log line is `clef_provider_failed exception=<Type>`, and it carries the exception class and nothing else.** This is narrower than the existing lines on purpose. The content about to be compacted is the most sensitive thing this plugin touches, and by the time a transport failure surfaces, that content has already left the machine. A `urllib` exception message can quote the request object, which carries the URL and the header, so the message, the URL, the account id, the token, and the request body are all excluded from the log. The operator-facing detail comes from `ClefError` instead, whose text is built only from provider names, variable names, counts, and Cloudflare error codes. `diagnostics()` reports `CLOUDFLARE_API_TOKEN` under `keys_present` and `CLOUDFLARE_ACCOUNT_ID` under `configuration_present`, by name only, and a test drives a failure whose exception message contains both values plus a state sentinel and asserts none of the three reaches `caplog` or the diagnostics.

No credential is written to any file in this candidate. Secrets are read only from `CLOUDFLARE_API_TOKEN`, and the account id only from `CLOUDFLARE_ACCOUNT_ID`.

### Configuration

Two environment variables, both required for a Clef route, neither written to any config file:

| Variable | Role | Secret |
|---|---|---|
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token with Account > Workers AI > Read. Sent as `Authorization: Bearer`. | Yes, keep it in a secret manager. |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account id. Interpolated into the request path. | No, it is configuration, but treat it as internal rather than public. |

Two optional settings:

| Setting | Default | Meaning |
|---|---|---|
| `clef_base_url` | `https://api.cloudflare.com/client/v4/accounts` | Shared prefix of the per-account path. Must be HTTPS for a non-local host. |
| `clef_model` | `clef` | `clef` or `clef-flash`. A checkpoint of the one provider, never a chain member. |

Selecting the provider:

```yaml
context:
  engine: jev-lcm
jev_lcm:
  jev_provider: clef        # or the alias clef_api
  clef_model: clef          # or clef-flash
```

Or as one member of a chain, where an uncredentialed Clef is filtered out as any other provider with no key is:

```yaml
jev_lcm:
  jev_fallback_order: [clef, typesafe, openrouter]
```

Limits enforced by the implementation, from the Cloudflare model pages: question ids are letters, digits, `_`, `.`, `-`, at most 100 characters; at most 64 questions per request, beyond which the call fails before any request naming `jev_max_candidates_per_batch`; a 65536-token context window, which this package does not separately bound because `max_request_tokens` is already the request budget.

### Verification

Executed on this head, in the project virtual environment:

- **162 tests pass** with `python -m pytest -q --ignore=tests/test_plugin.py`. Before this candidate the same command reported **126 passed**, so the 36 new tests are the whole of the difference.
- `tests/test_plugin.py` is excluded from that count for a reason that predates this work and is unrelated to Clef: it imports `hermes_cli.plugins`, which imports `hermes_yaml` from the Hermes source tree, and that tree is not on the interpreter path under this venv, so collection fails with `ModuleNotFoundError: No module named 'hermes_yaml'`. With `PYTHONPATH=/home/beau/.hermes/hermes-agent` the file passes on its own, which confirms the error is an environment path issue and not a code defect.
- `mypy` passes over 14 source files. `black --check` reports 43 files unchanged.
- `evaluation/live_clef.py` was executed with `PYTHONPATH=src python evaluation/live_clef.py` and reported: `order ["clef"]` with the recorded URL `https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/cloudflare/clef` and a body of exactly `model`, `state`, `questions`; `clef-flash` reaching the `.../clef-flash` URL with `"model": "clef-flash"` and the chain still `["clef"]`; `clef_api` resolving to canonical `clef`; `auto` still `["typesafe", "openrouter"]` with both hosted keys present; an ordered chain `["clef", "typesafe", "openrouter"]`; an uncredentialed `clef` filtered to `["typesafe"]`; the three missing-credential cases naming `CLOUDFLARE_API_TOKEN` or `CLOUDFLARE_ACCOUNT_ID` with no request attempted; `placeholder_never_printed: true`; and both envelopes unwrapping with the `success: false` envelope reporting `code 7003` and reason `http_error`.

Not executed, and not claimed:

- **No live Clef request was made.** No Cloudflare credential available on the machine that built this candidate is authorized for Workers AI: every candidate token returns HTTP 401 `Authentication error`. `evaluation/live_clef.py` phase 5 is written to attempt the real request when both variables are present and to report Cloudflare's actual answer; on this machine it reported `attempted: false`, because no `CLOUDFLARE_ACCOUNT_ID` was present in the environment, so it attempted nothing. **No live Clef behaviour of any kind is verified here, and the wire contract above is a documented expectation, not a reproduced result.**
- **Clef's retention quality on this workload is unknown.** No Clef score was ever produced. There is no measurement, no comparison against TypeSafe or OpenRouter, and no calibrated threshold for this route. Selecting `clef` means feeding scores from an unmeasured model into the same decision table the measured providers feed.
- **Clef's latency and Workers AI billing under a real batch are unknown.** Nothing measured either.
- **The 65536-token context window is untested against a real request.** `max_request_tokens` is this package's own budget and is not a Clef-specific bound, so a state that fits the package budget can still exceed a Clef limit.
- **Whether a mapped question id changes a judgment is untested.** The caller's own id reaches the model in the instruction text, which is the intended mitigation, but no experiment here compares scores under the original and the mapped spelling.
- **No `python -m build` was run** for this candidate, so no wheel or source distribution is asserted.

The wire contract is taken from Cloudflare's own model documentation: [clef](https://developers.cloudflare.com/workers-ai/models/clef/) and [clef-flash](https://developers.cloudflare.com/workers-ai/models/clef-flash/).

### Release blockers

Publication of this candidate is not asserted. The repository's standing blockers are unchanged: the production recall-at-budget comparison, fresh-profile installation qualification, provider parity review, final documentation review, and publication remain open. Nothing here asserts a stable `1.0.0`.

### Credits and license

Clef is a Cloudflare Workers AI model; Cloudflare supplies the hosted decision model this provider calls. Bojan Sandhaus supplied the Jev Decisions conventions this provider follows and the DOGA fork's Clef integration, from which the endpoint, the envelope handling, and the checkpoint rule were adapted to this repository's provider architecture. The MIT license applies; see [third party notices](THIRD_PARTY_NOTICES.md).
