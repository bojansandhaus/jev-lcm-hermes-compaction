"""Run actual LCM compaction with explicitly synthetic external transports."""

from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from jev_lcm_hermes_compaction.compressor import JevLCMContextCompressor
from jev_lcm_hermes_compaction.settings import Settings
from jev_lcm_hermes_compaction.prepass import Prepass
from jev_lcm_hermes_compaction.providers import ProviderChain
from jev_lcm_hermes_compaction._vendor.lcm.engine import LCMEngine
from jev_lcm_hermes_compaction._vendor.lcm.config import LCMConfig
from jev_lcm_hermes_compaction._vendor.lcm.tokens import count_messages_tokens

MARKER = "deadbeef1234567"


def evaluate(
    protect=True,
    budget=2000,
    summary="Synthetic summary intentionally omits exact evidence.",
):
    if not isinstance(budget, int) or budget < 1:
        raise ValueError("invalid budget")
    messages = [{"role": "user", "content": "Investigate the synthetic archive."}]
    for turn in range(6):
        messages.extend(
            [
                {
                    "role": "assistant",
                    "content": (
                        "The root cause is `" + MARKER + "`. " if turn == 0 else ""
                    )
                    + "Synthetic filler without evidence. " * 1000,
                },
                {"role": "user", "content": "Continue the investigation."},
            ]
        )
    messages.extend(
        [
            {"role": "assistant", "content": "Ready."},
            {"role": "user", "content": "Report the retained evidence."},
        ]
    )
    with tempfile.TemporaryDirectory(prefix="jev-eval-") as home:
        cfg = LCMConfig(
            database_path=str(Path(home) / "lcm.db"),
            fresh_tail_count=2,
            max_assembly_tokens=budget,
        )
        if protect:
            settings = Settings(hint_budget_tokens=400)
            engine = JevLCMContextCompressor(cfg, home, settings)
            engine.jev = Prepass(
                settings,
                ProviderChain(
                    settings,
                    {"TYPESAFE_API_KEY": "synthetic"},
                    lambda u, k, p, t: {
                        "answers": {q: {"noul": 0.99} for q in p["questions"]}
                    },
                ),
            )
        else:
            engine = LCMEngine(cfg, home)
        engine.on_session_start("synthetic-evaluation")
        before = count_messages_tokens(messages)
        if before <= budget:
            raise ValueError("input must exceed target budget")
        with patch(
            "jev_lcm_hermes_compaction._vendor.lcm.escalation._call_llm_for_summary",
            return_value=summary,
        ) as transport:
            assembled = engine.compress(messages, current_tokens=before, force=True)
        after = count_messages_tokens(assembled)
        if not transport.call_count:
            raise RuntimeError("summary transport was not exercised")
        if after > budget:
            raise ValueError(f"nonconvergence: {after} > {budget}")
        search = engine.handle_tool_call(
            "lcm_grep", {"query": MARKER, "mode": "full_text"}
        )
        rows = engine._store.get_session_messages("synthetic-evaluation")
        source = next(row for row in rows if MARKER in str(row.get("content", "")))
        expanded = engine.handle_tool_call(
            "lcm_expand", {"store_id": source["store_id"]}
        )
        return {
            "mode": "synthetic-transport-integration",
            "arm": "jev-lcm" if protect else "lcm",
            "budget_tokens": budget,
            "token_accounting": "LCM count_messages_tokens",
            "input_tokens": before,
            "active_tokens": after,
            "exact_evidence_retention": int(MARKER in json.dumps(assembled)),
            "raw_retrieval_retention": int(MARKER in search and MARKER in expanded),
            "freed_ratio": (before - after) / before,
            "model_calls": transport.call_count,
            "production_comparison": False,
        }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        raise SystemExit("No live mode or external fixture flags are implemented")
    print(json.dumps([evaluate(False), evaluate(True)], indent=2))
