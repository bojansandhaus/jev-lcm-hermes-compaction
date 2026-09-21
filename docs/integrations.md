# Integrations

[NousResearch/hermes-agent PR #116246](https://github.com/NousResearch/hermes-agent/pull/116246) showed why Jev-only compaction cannot replace a summary path: assistant text and the never-removed text floor remain outside its ranking scope. This guide applies the corrected fixes by keeping Hermes LCM as the storage and condensation owner while Jev supplies bounded ranking hints.

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

## Both providers with fallback

Use `jev_provider: auto`, keep `jev_fallback_enabled: true`, and configure both keys. The default order is TypeSafe, then OpenRouter. A configured error in `jev_fallback_on` cools the failed provider and tries the next provider. `jev_providers` exposes only environment-variable names, status, cooldowns, and sanitized errors. A log line has the form:

```text
jev_provider_fallback from=typesafe to=openrouter reason=429
```

## Self-hosted or proxied router

Use an HTTPS base URL and a path that implements the repository's Decisions-shaped contract. Plain HTTP is accepted only for localhost addresses by settings validation. The router must accept `model`, `state`, and `questions`, and return parseable score fields for each question. Test with synthetic, non-sensitive text first. A self-hosted endpoint is not automatically compatible because it resembles an OpenAI API.

## Privacy boundary

The selected state and candidates are sent to the active provider. There is no automatic secret redaction. Raw archives are local to the package and are not encrypted by it. Use a secret manager, exclude SQLite files from version control, and inspect provider retention terms.

## Verification checklist

- One profile has one active compaction engine.
- `/reset` was run after changing the engine.
- `jev_providers` shows environment-variable names only.
- `jev_stats` changes only after an actual compaction.
- `lcm_grep` and `lcm_expand` can recover a known synthetic marker.
- Provider compatibility and live quality remain separately verified work.