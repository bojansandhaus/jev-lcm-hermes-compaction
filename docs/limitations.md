# Experimental release boundaries

[Hermes PR #116246](https://github.com/NousResearch/hermes-agent/pull/116246) motivates this project: ranking alone cannot replace text condensation. This page records limits or review evidence for the scoring, retention, storage, and compaction fixes.

This is the first stable release, not a production-certified replacement. The version number and the removal of release-candidate framing say nothing about the open verification gates recorded below and in [`verification.md`](verification.md).

Tests use synthetic text and scores. HTTP tests use loopback servers. They do not measure provider quality, real billing, or comparative performance against private transcripts.

Selected conversation text is sent to the configured provider. This is not an automatic secret-redaction system. The local raw archive is not encrypted by this package. Use a private data directory. In `local_with_api_fallback`, a local attempt that fails a configured trigger sends the state to a hosted provider as well; `local_only` alone is the only route that stays on the machine, whichever System One decision model serves it. Naming the category softens nothing on this page. Selecting `clef` sends the state, the candidate text, and the protected anchors to `api.cloudflare.com` on every request, with no redaction step, and naming `clef` in `jev_fallback_order` gives it the same trigger-driven escalation to the next member.

## What the local slot is not

Every provider named in this page is a [System One decision model](https://systemonemodels.org/guides/what-is-a-system-one-model/), also written a typed decision model, and naming the category adds no capability and removes no risk. It is a name, not a quality judgement or a privacy property.

The local slot accepts any engine name, which is the point: a new local model must work by configuration alone. The cost of that choice is that this package cannot tell you whether a given engine is any good. **No local model other than the shipped default has been called live by this code**, so the claim that Laya or other pre-deterministic routing models fit the slot is sourced from [chaitin/Decis](https://github.com/chaitin/Decis) as a statement about the wire contract, not from a measurement. Membership of the category is likewise that project's claim, not a measurement here. If you select a `local_model` other than the shipped default, nothing here has verified that it scores well on your retention questions; measure it on your own workload before trusting its retention decisions.

## What the local route is not

The strongest quality evidence for local Laya is the matched 100-question, three-mode benchmark published with the DOGA fork, which used the same questions and the same `0.7` ambiguity threshold: goal agreement `56/100` for local Laya against `88/100` for the hosted Jev API, response mode `41/100` against `68/100`, stakes `37/100` against `67/100`, high-versus-low ambiguity `67/100` against `87/100`, and local Laya detected none of the 30 authored high-ambiguity labels at that threshold. Those labels are one authored, subjective set and not an adjudicated ground truth, so treat the table as a direction. The consequence is unchanged: keep the hosted arrangement as the default and do not present the local route as a quality improvement.

The three-consecutive-failure breaker bounds repeated remote egress after local errors. It cannot detect a local answer that is valid and wrong. Nothing in this package scores a local answer for correctness before accepting it, and no threshold is tuned by the breaker. The count is per process, so a restart clears it, and a cooldown that is longer than the interval between failures means the breaker counts fewer failures than a naive reading of the traffic would suggest.

Logging is category-only by construction. A `ProviderError` reason is drawn from a fixed set and clamped to `transport_error` for anything else, provider names and counters are the only other values formatted into a scoring-path log line, and the state, candidate text, and answers are not. That is a property of this package's own modules; the vendored LCM snapshot is unchanged upstream code whose own logging this release did not audit or modify.

Cloudflare Clef is a new hosted route for a System One decision model, and no live Clef request has been made. No Cloudflare credential available on the machine that built the Clef provider is authorized for Workers AI: every candidate token returns HTTP 401 `Authentication error`, so its wire contract is taken from Cloudflare's model documentation and exercised only against an injected transport. Clef's retention quality, latency, and Workers AI billing on this workload are unmeasured, no Clef score has ever been produced here, and the behaviour of a 64-question request against the 65536-token context window is untested. Whether renaming a question id to Clef's alphabet changes a judgment is also untested. `docs/verification.md` records each of these under "Not established".

Hermes uses bundled upstream LCM. DSH uses its native BasicCompactionEngine with a separate SQLite archive and summary links, not a full TypeScript port of Hermes LCM.

The byte-based request cap is conservative, not an exact provider tokenizer. Oversized candidates remain unscored. Provider failure leaves host condensation available without fabricated scores.

Further qualification is required for live providers, sustained DSH sessions, cancellation, restart restoration of calibration, independently measured recall, and randomized cross-language parity.

DSH summary nodes currently record generated summaries, including attempts the host may reject. They do not prove a surface replacement committed. Their predecessor chain is not a complete source DAG. Raw evidence is stored separately.

Publication does not activate this engine in a running agent. Package registry publication is separate from GitHub publication.
