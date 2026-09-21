# Third party notices

This package is MIT licensed and community maintained. It reuses design from four projects, code from one, and calls two external services. Each entry names the license as published in that repository and exactly what was reused. Licenses were read through the GitHub license API on 2026-09-21.

## hermes-lcm

- Repository: https://github.com/stephenschoettler/hermes-lcm
- License: MIT
- Reused: code. The SQLite message store, the summary DAG, the active-context assembler, the protected fresh tail, and the recall tools are vendored under `src/jev_lcm_hermes_compaction/_vendor/lcm` at snapshot `8d1b1e6d3d63f5fc7b209e8d7ec1dc9b814f2e54`, so the plugin can assemble context without a separate install. The Jev pre-pass, the anchor index, the calibrated threshold, the batch window, the hint block, and the provider chain are additions by Bojan Sandhaus. The MIT text is reproduced at the end of this file.

## fast-jev-compaction

- Repository: https://github.com/tamaratran/fast-jev-compaction
- License: MIT
- Reused: design only, no code. The state shaping approach, the two-question scoring model, and the keep, truncate, drop vocabulary come from this project. This implementation is independent and adds assistant-text anchors, per-deployment calibration, the tiered shrink ladder, and batched scoring.

## hermes-jev-compact

- Repository: https://github.com/TheEpTic/hermes-plugins/tree/main/hermes-jev-compact
- License: MIT
- Reused: design only, no code. The Hermes context engine registration seam, the fallback contract that keeps a session alive when scoring fails, and the counter vocabulary.

## jev-decisions

- Repository: https://github.com/bojansandhaus/jev-decisions
- License: MIT
- Reused: documentation only. README structure, section order, and documentation depth. No code.

## hermes-agent

- Repository: https://github.com/NousResearch/hermes-agent
- License: MIT
- Reused: nothing in the shipped package. The CI workflow checks out pinned revision `52d203d041f9e4baad4a78013abeccd8f13a86e3` to run the integration tests. PR #116246 in that repository is the evaluation this plugin answers.

## TypeSafe (Jev, System One, Decisions API)

- Service: https://api.typesafe.ai/v1
- No TypeSafe code is reused or redistributed. The plugin sends Decisions-shaped scoring requests over HTTPS with the operator's own key. Jev and System One are TypeSafe products; this project is independent and not affiliated with TypeSafe.

## OpenRouter

- Service: https://openrouter.ai
- No OpenRouter code is reused or redistributed. The plugin sends scoring requests either to the chat completions surface at `/api/v1/chat/completions` through a Decisions-shaped adapter, or to the native Decisions surface at `/api/alpha/decisions`, using the operator's own key.

## Lossless Context Management

- Ehrlich and Blackman, Voltropy PBC, February 2026.
- No code reused. The vocabulary and the priorities, a DAG of summary nodes, a protected fresh tail, and a lossless raw store, come from the paper.

## MIT license text, hermes-lcm

MIT License

Copyright (c) 2026 Stephen Schoettler

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
