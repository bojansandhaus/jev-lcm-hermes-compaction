# Integrations

[NousResearch/hermes-agent PR #116246](https://github.com/NousResearch/hermes-agent/pull/116246) showed why Jev-only compaction cannot replace a summary path: assistant text and the never-removed text floor remain outside its ranking scope. This guide applies the corrected fixes by keeping Hermes LCM as the storage and condensation owner while Jev supplies bounded ranking hints.

Every provider in this guide is a [System One decision model](https://systemonemodels.org/guides/what-is-a-system-one-model/), also written a typed decision model: it answers typed questions about the state you give it and returns typed answers with a probability for each instead of prose. Jev is hosted by TypeSafe or OpenRouter, Clef is hosted on Cloudflare Workers AI, and Laya, Kev, and Tev1 are open-weights models you run locally. Jev is one member of that category, not the name of it.

## With bundled Hermes LCM

Enable this package per profile:

```yaml
context:
  engine: jev-lcm
jev_lcm:
  jev_provider: auto
```

Keep the ordinary `compressor` engine as the default for profiles that do not opt in. Do not run two context engines against the same profile. The plugin stores raw evidence before scoring and keeps LCM recall surfaces available. Confirm the installed host's LCM version and tool names before relying on a host-specific option.

## With `hermes-jev-compact`

Those projects share Jev lineage and must not both own the same compaction seam. Choose one engine. For migration, disable `hermes-jev-compact`, preserve the existing LCM/raw archive, install this package in the same Python environment, then enable `context.engine: jev-lcm`. Run `/reset` after changing the engine so queued candidates belong to one implementation. Do not delete an old archive until `lcm_grep` and `lcm_expand` have been checked.

## Migrating from LCM alone

Leave the LCM settings unchanged first. Add a provider key through the secret manager, enable the engine in one profile, and compare `jev_stats` with the host's ordinary diagnostics. With no key, the package disables Jev and permits ordinary condensation, which is a safe configuration check but not a Jev test.

## TypeSafe only

Set `jev_provider: typesafe` and `TYPESAFE_API_KEY`. Pinning fails fast if that variable is absent. Keep the base URL and endpoint path from the current settings unless the provider documents a compatible deployment.

## OpenRouter only

Set `jev_provider: openrouter` and `OPENROUTER_API_KEY`. The default surface is `https://openrouter.ai/api` plus `/alpha/decisions` with model `~typesafe/jev-latest`, which is the native scoring surface and the only one OpenRouter accepts for a decisions model. Set `openrouter_endpoint_path` to a chat path such as `/chat/completions` to use the adapter instead, which is what a self-hosted or proxied gateway needs; the request and response mapping is in `docs/reference.md`. Verify the endpoint, model, request shape, and response shape against current provider documentation before sending production data.

## Cloudflare Clef only

Clef is a System One decision model hosted on Cloudflare Workers AI, so a Clef
route needs no TypeSafe or OpenRouter account at all. Set `jev_provider: clef`, or the alias
`clef_api`, and supply both of these through your secret manager:

| Variable | Role |
|---|---|
| `CLOUDFLARE_API_TOKEN` | The credential. A Cloudflare API token with the Account > Workers AI > Read permission. It is sent as `Authorization: Bearer`. |
| `CLOUDFLARE_ACCOUNT_ID` | The account id. Configuration, not a secret, but the endpoint is per account, so the URL cannot be built without it. |

```yaml
context:
  engine: jev-lcm
jev_lcm:
  jev_provider: clef
  clef_model: clef        # or clef-flash for a latency-bound path
```

Pinning `clef` fails at load when either variable is missing, and the message
names the missing variable rather than its value. The request goes to
`https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/@cf/cloudflare/{clef_model}`
carrying `model`, `state`, and `questions`. Both the bare model output and
Cloudflare's `{"success": true, "result": {...}}` envelope are accepted; a
`success: false` envelope is reported with Cloudflare's own error codes.

To have Clef participate in a chain rather than stand alone, name it in
`jev_fallback_order`, for example `[clef, typesafe, openrouter]`. A Clef with no
token is filtered out of that chain exactly as a TypeSafe with no key is.
`clef-flash` is a checkpoint of the `clef` provider, not a second provider, so
it is selected with `clef_model` and is never a chain member.

Verify the endpoint, the model name, and the account's Workers AI entitlement
against current Cloudflare documentation before sending production data. The
request and response mapping, the question-id handling, and the per-type answer
validation are in `docs/reference.md`.

**This route sends your conversation content to a third-party API.** The scored
state, the candidate text, and the protected anchors all leave the machine on
every request. There is no redaction step, and the raw archive is not encrypted
by this package. Review Cloudflare's retention terms for the account before
enabling it, and use a local System One decision model such as Laya if the content
must not leave the machine.

## Both providers with fallback

Use the default mode (`api_only`, or the alias `auto`), keep `jev_fallback_enabled: true`, and configure both keys. The default order is TypeSafe, then OpenRouter. A configured error in `jev_fallback_on` cools the failed provider and tries the next provider. `jev_providers` exposes only environment-variable names, status, cooldowns, and sanitized errors. A log line has the form:

```text
jev_provider_fallback from=typesafe to=openrouter reason=429
```

To add the local decision model as the last resort instead, use
`api_with_local_fallback`. The hosted providers lead in the order above and the
local slot answers only after they fail a configured trigger, which is the one
chain in this package that ends at a machine-local call.

## Pointing the local slot at a different engine

The local slot is not bound to Laya. `local_model` names whichever System One
decision model the local server serves, and `laya_base_url` says where that
server listens, so swapping engines is a configuration change and never a code
change.

[chaitin/Decis](https://github.com/chaitin/Decis) is the clearest example: it
serves Laya, Kev, and a Jeff family behind one endpoint speaking TypeSafe's
`/v1/systemone` shape, with one Docker image per engine, so migrating between
them is a `base_url` change. Start the container for the engine you want, then:

```yaml
context:
  engine: jev-lcm
jev_lcm:
  jev_provider: local_only
  local_model: kev               # or tev1, jeff-gemma4-e2b, laya-multilingual
  laya_base_url: http://127.0.0.1:8000
  request_timeout_s: 120
```

There is no allowlist on `local_model`, and that is deliberate: a new engine has
to work without a code change or a release. What is refused is an empty or
whitespace-only name, and one containing a character that would corrupt the JSON
`model` field or a URL path segment, which is `"`, `\`, `?`, `#`, or any control
character. A rejected value is reported without echoing it back.

**No local model other than the shipped default has been called live by this
package.** System One decision models known to fit the contract are `laya` (also
`laya-multilingual`, `laya-typed-decisions`), `kev` (also `kev-0.8b`), `tev1`
(Together AI, Qwen3.5-based, `Tev1-4B`, `Tev1-0.8B`), and `jeff-qwen3.5-0.8b`
and `jeff-gemma4-e2b`. That list is sourced from the two projects above; it is a
statement about the wire contract and about those projects' own claims of category
membership, not a measurement made here.

## Self-hosted or proxied router

Use an HTTPS base URL and a path that implements the repository's Decisions-shaped contract. Plain HTTP is accepted only for localhost addresses by settings validation. The router must accept `model`, `state`, and `questions`, and return parseable score fields for each question. Test with synthetic, non-sensitive text first. A self-hosted endpoint is not automatically compatible because it resembles an OpenAI API.

## Privacy boundary

The selected state and candidates are sent to the active provider. There is no automatic secret redaction. Raw archives are local to the package and are not encrypted by it. Use a secret manager, exclude SQLite files from version control, and inspect provider retention terms.

Selecting `clef` sends that content to Cloudflare. `clef_base_url` may be pointed
at a different HTTPS host for a proxy or a gateway, but it may not be plain HTTP:
the settings validator rejects non-local plain HTTP for every provider, and a
hosted route carrying conversation text must not be downgraded.

## Verification checklist

- One profile has one active compaction engine.
- `/reset` was run after changing the engine.
- `jev_providers` shows environment-variable names only.
- `jev_stats` changes only after an actual compaction.
- `lcm_grep` and `lcm_expand` can recover a known synthetic marker.
- Provider compatibility and live quality remain separately verified work.
- If `clef` is selected, `jev_providers` lists `CLOUDFLARE_API_TOKEN` under `keys_present` and `CLOUDFLARE_ACCOUNT_ID` under `configuration_present`, and neither value is printed.