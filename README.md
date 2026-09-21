# Jev LCM for Hermes

Keep exact evidence recoverable when an agent condenses a long conversation. This plugin adds Jev relevance scoring before bundled Hermes LCM condensation.

**Experimental release candidate.** [Read the limitations](docs/limitations.md) before activation. [Attribution](THIRD_PARTY_NOTICES.md).

## Install from source

```sh
git clone https://github.com/bojansandhaus/jev-lcm-hermes-compaction.git
cd jev-lcm-hermes-compaction
python -m pip install .
```

Use the Python environment that runs Hermes. Install this checkout through the Hermes plugin manager after installing the package. Opt in through configuration:

```yaml
context:
  engine: jev-lcm
jev_lcm:
  jev_provider: auto
```

The package adds `jev_stats`, `jev_scores`, `jev_anchors`, and `jev_providers` to the bundled LCM tools. The `jev-lcm` CLI exposes provider diagnostics and calibration dry runs.

## Provider setup

Supply TYPESAFE_API_KEY or OPENROUTER_API_KEY through your normal secret manager. Auto mode prefers TypeSafe, then OpenRouter. Pinning a provider requires its own key. With no key, Jev scoring is disabled and ordinary host condensation remains available. Installation does not select the active engine automatically.

## What it does

Raw evidence is stored before scoring. Exact assistant spans and matched tool-result pairs become candidates. A rolling calibrator starts at 0.15, requires 50 samples, retains 500 samples, and enforces a 10 percent minimum keep rate. Batches normally span three turns with at most 300 candidates. Oversized and unscored evidence remains available through the raw archive.

## Verification

Deterministic tests cover calibration, fallback, exact spans, and a 541-call overflow fixture. Hermes additionally exercises upstream condensation with a synthetic summarizer. DSH additionally exercises real Cordis Loader composition. These tests do not establish live provider quality or production benchmark superiority.

## Privacy and licensing

Configured providers receive selected conversation content. This is not automatic secret redaction. Raw archives are local and not encrypted by this package. Do not commit archives or credentials.

MIT license. Original upstream authorship and license notices are preserved. This project does not claim authorship of Hermes LCM, DeepSeek Harness, or Cordis.
