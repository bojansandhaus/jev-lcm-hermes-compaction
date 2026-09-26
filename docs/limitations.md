# Experimental release boundaries

[Hermes PR #116246](https://github.com/NousResearch/hermes-agent/pull/116246) motivates this project: ranking alone cannot replace text condensation. This page records limits or review evidence for the scoring, retention, storage, and compaction fixes.

This is a release candidate, not a production-certified replacement.

Tests use synthetic text and scores. HTTP tests use loopback servers. They do not measure provider quality, real billing, or comparative performance against private transcripts.

Selected conversation text is sent to the configured provider. This is not an automatic secret-redaction system. The local raw archive is not encrypted by this package. Use a private data directory. In `laya_then_hosted`, a local attempt that fails a configured trigger sends the state to a hosted provider as well; `laya` alone is the only route that stays on the machine.

## What the local route is not

The strongest quality evidence for local Laya is the matched 100-question, three-mode benchmark published with the DOGA fork, which used the same questions and the same `0.7` ambiguity threshold: goal agreement `56/100` for local Laya against `88/100` for the hosted Jev API, response mode `41/100` against `68/100`, stakes `37/100` against `67/100`, high-versus-low ambiguity `67/100` against `87/100`, and local Laya detected none of the 30 authored high-ambiguity labels at that threshold. Those labels are one authored, subjective set and not an adjudicated ground truth, so treat the table as a direction. The consequence is unchanged: keep the hosted arrangement as the default and do not present the local route as a quality improvement.

The three-consecutive-failure breaker bounds repeated remote egress after local errors. It cannot detect a local answer that is valid and wrong. Nothing in this package scores a local answer for correctness before accepting it, and no threshold is tuned by the breaker. The count is per process, so a restart clears it, and a cooldown that is longer than the interval between failures means the breaker counts fewer failures than a naive reading of the traffic would suggest.

Logging is category-only by construction. A `ProviderError` reason is drawn from a fixed set and clamped to `transport_error` for anything else, provider names and counters are the only other values formatted into a scoring-path log line, and the state, candidate text, and answers are not. That is a property of this package's own modules; the vendored LCM snapshot is unchanged upstream code whose own logging this release did not audit or modify.

Hermes uses bundled upstream LCM. DSH uses its native BasicCompactionEngine with a separate SQLite archive and summary links, not a full TypeScript port of Hermes LCM.

The byte-based request cap is conservative, not an exact provider tokenizer. Oversized candidates remain unscored. Provider failure leaves host condensation available without fabricated scores.

Further qualification is required for live providers, sustained DSH sessions, cancellation, restart restoration of calibration, independently measured recall, and randomized cross-language parity.

DSH summary nodes currently record generated summaries, including attempts the host may reject. They do not prove a surface replacement committed. Their predecessor chain is not a complete source DAG. Raw evidence is stored separately.

Publication does not activate this engine in a running agent. Package registry publication is separate from GitHub publication.
