"""Three arm recall-at-budget evaluation on the bundled synthetic fixture.

Arms:
  production-equivalent  the host's default condensation path, no Jev ranking
  jev-only               Jev ranking with every user and assistant turn left verbatim
  jev-lcm                Jev ranking before LCM condensation, the shipped design

The PR #116246 transcripts are real session data and are not published, so the
production arm here is a local stand-in for that path, not the PR's private run.
Everything this harness measures comes from executed plugin and host code.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from jev_lcm_hermes_compaction.compressor import JevLCMContextCompressor
from jev_lcm_hermes_compaction.prepass import Prepass
from jev_lcm_hermes_compaction.providers import ProviderChain
from jev_lcm_hermes_compaction.settings import Settings
from jev_lcm_hermes_compaction._vendor.lcm.config import LCMConfig
from jev_lcm_hermes_compaction._vendor.lcm.engine import LCMEngine
from jev_lcm_hermes_compaction._vendor.lcm.tokens import count_messages_tokens

FIXTURE_PATH = Path(__file__).with_name("fixture.json")
ARMS = ("production-equivalent", "jev-only", "jev-lcm")
SESSION = "synthetic-evaluation"
SUMMARY_PATCH = "jev_lcm_hermes_compaction._vendor.lcm.escalation._call_llm_for_summary"
REQUIRED_FIXTURE_KEYS = (
    "budget_tokens",
    "fresh_tail_count",
    "filler_turns",
    "filler_repeat",
    "markers",
    "summary",
    "tool_score",
    "anchor_score",
)


def load_fixture(path: Path = FIXTURE_PATH) -> dict:
    fixture = json.loads(Path(path).read_text())
    missing = [key for key in REQUIRED_FIXTURE_KEYS if key not in fixture]
    if missing:
        raise ValueError("fixture missing keys: " + ", ".join(missing))
    if not fixture["markers"]:
        raise ValueError("fixture needs at least one marker")
    return fixture


def build_transcript(fixture: dict) -> list[dict]:
    markers = fixture["markers"]
    filler = "Synthetic filler without evidence. " * fixture["filler_repeat"]
    messages = [{"role": "user", "content": "Investigate the synthetic archive."}]
    for turn in range(fixture["filler_turns"]):
        evidence = ""
        if turn < len(markers):
            evidence = f"The root cause is `{markers[turn]}` and it must stay exact. "
        messages.append({"role": "assistant", "content": evidence + filler})
        messages.append({"role": "user", "content": "Continue the investigation."})
    messages.extend(
        [
            {"role": "assistant", "content": "Ready."},
            {"role": "user", "content": "Report the retained evidence."},
        ]
    )
    return messages


def synthetic_chain(settings: Settings, fixture: dict) -> ProviderChain:
    """Score anchors high and tool results low, mirroring the PR's measured band."""

    def transport(url, key, payload, timeout):
        answers = {}
        for question in payload["questions"]:
            answers[question] = {
                "noul": (
                    fixture["anchor_score"]
                    if question.endswith((":anchor_keep", ":recovery"))
                    else fixture["tool_score"]
                )
            }
        return {"answers": answers}

    return ProviderChain(settings, {"TYPESAFE_API_KEY": "synthetic"}, transport)


def measure(
    arm: str,
    messages: list[dict],
    active: list[dict],
    fixture: dict,
    before: int,
    model_calls: int,
    raw_retrieval: int | None,
) -> dict:
    budget = fixture["budget_tokens"]
    after = count_messages_tokens(active)
    markers = fixture["markers"]
    retained = [marker for marker in markers if marker in json.dumps(active)]
    return {
        "mode": "synthetic-transport-integration",
        "arm": arm,
        "budget_tokens": budget,
        "token_accounting": "LCM count_messages_tokens",
        "input_tokens": before,
        "active_tokens": after,
        "budget_converged": after <= budget,
        "markers_total": len(markers),
        "markers_retained": len(retained),
        "recall_at_budget": len(retained) / len(markers),
        "raw_store": raw_retrieval is not None,
        "raw_retrieval_retention": raw_retrieval,
        "freed_ratio": (before - after) / before,
        "model_calls": model_calls,
    }


def _settings(fixture: dict) -> Settings:
    return Settings(hint_budget_tokens=400, min_result_chars=0)


def run_jev_lcm(fixture: dict, summary: str) -> dict:
    markers = fixture["markers"]
    messages = build_transcript(fixture)
    before = count_messages_tokens(messages)
    with tempfile.TemporaryDirectory(prefix="jev-eval-") as home:
        settings = _settings(fixture)
        cfg = LCMConfig(
            database_path=str(Path(home) / "lcm.db"),
            fresh_tail_count=fixture["fresh_tail_count"],
            max_assembly_tokens=fixture["budget_tokens"],
        )
        engine = JevLCMContextCompressor(cfg, home, settings)
        engine.jev = Prepass(settings, synthetic_chain(settings, fixture))
        engine.on_session_start(SESSION)
        with patch(SUMMARY_PATCH, return_value=summary) as transport:
            active = engine.compress(messages, current_tokens=before, force=True)
        if not transport.call_count:
            raise RuntimeError("summary transport was not exercised")
        search = engine.handle_tool_call(
            "lcm_grep", {"query": markers[0], "mode": "full_text"}
        )
        rows = engine._store.get_session_messages(SESSION)
        source = next(row for row in rows if markers[0] in str(row.get("content", "")))
        expanded = engine.handle_tool_call(
            "lcm_expand", {"store_id": source["store_id"]}
        )
    return measure(
        "jev-lcm",
        messages,
        active,
        fixture,
        before,
        transport.call_count,
        int(markers[0] in search and markers[0] in expanded),
    )


def run_production_equivalent(fixture: dict, summary: str) -> dict:
    markers = fixture["markers"]
    messages = build_transcript(fixture)
    before = count_messages_tokens(messages)
    with tempfile.TemporaryDirectory(prefix="jev-eval-") as home:
        cfg = LCMConfig(
            database_path=str(Path(home) / "lcm.db"),
            fresh_tail_count=fixture["fresh_tail_count"],
            max_assembly_tokens=fixture["budget_tokens"],
        )
        engine = LCMEngine(cfg, home)
        engine.on_session_start(SESSION)
        with patch(SUMMARY_PATCH, return_value=summary) as transport:
            active = engine.compress(messages, current_tokens=before, force=True)
        if not transport.call_count:
            raise RuntimeError("summary transport was not exercised")
        search = engine.handle_tool_call(
            "lcm_grep", {"query": markers[0], "mode": "full_text"}
        )
        rows = engine._store.get_session_messages(SESSION)
        source = next(row for row in rows if markers[0] in str(row.get("content", "")))
        expanded = engine.handle_tool_call(
            "lcm_expand", {"store_id": source["store_id"]}
        )
    return measure(
        "production-equivalent",
        messages,
        active,
        fixture,
        before,
        transport.call_count,
        int(markers[0] in search and markers[0] in expanded),
    )


def run_jev_only(fixture: dict) -> dict:
    """Jev ranking with no condensation path: the arm PR #116246 rejected.

    Tool results take the Jev verdict. Every user and assistant turn stays
    verbatim, which is why this arm reproduces the unbounded text floor.
    """
    messages = build_transcript(fixture)
    before = count_messages_tokens(messages)
    settings = _settings(fixture)
    prepass = Prepass(settings, synthetic_chain(settings, fixture))
    prepass.collect(messages, len(messages) - 1)
    prepass.flush(force=True)
    verdicts = {
        candidate.message_index: candidate
        for candidate in prepass.candidates.values()
        if candidate.kind == "tool"
    }
    active: list[dict] = []
    for index, message in enumerate(messages):
        verdict = verdicts.get(index - 1) if message["role"] == "tool" else None
        if verdict is not None and verdict.action == "drop":
            active.append(
                {"role": "tool", "content": "[dropped by Jev; no summary path]"}
            )
            continue
        if verdict is not None and verdict.action == "truncate":
            head = str(message.get("content", ""))[: settings.truncate_head_chars]
            active.append({"role": "tool", "content": head + " [result truncated]"})
            continue
        active.append(message)
    hint = prepass.hint_block()
    if hint:
        active.append({"role": "system", "content": hint})
    return measure(
        "jev-only",
        messages,
        active,
        fixture,
        before,
        prepass.metrics["jev_calls"],
        None,
    )


def compare(arms: dict, fixture: dict) -> dict:
    production = arms["production-equivalent"]
    jev_lcm = arms["jev-lcm"]
    return {
        "production_arm": production["arm"],
        "compared_against": "local production-equivalent condensation path",
        "upstream_transcripts_available": bool(
            fixture.get("upstream_transcripts_available", False)
        ),
        "upstream_production_run_reproduced": False,
        "production_recall_at_budget": production["recall_at_budget"],
        "jev_lcm_recall_at_budget": jev_lcm["recall_at_budget"],
        "jev_lcm_meets_or_beats_production": (
            jev_lcm["recall_at_budget"] >= production["recall_at_budget"]
            and jev_lcm["budget_converged"]
        ),
        "jev_only_budget_converged": arms["jev-only"]["budget_converged"],
        "jev_only_recall_at_budget": arms["jev-only"]["recall_at_budget"],
    }


def evaluate(
    arm: str = "jev-lcm", budget: int | None = None, summary: str | None = None
):
    if arm not in ARMS:
        raise ValueError("unknown arm: " + str(arm))
    fixture = load_fixture()
    if budget is not None:
        if not isinstance(budget, int) or budget < 1:
            raise ValueError("invalid budget")
        fixture["budget_tokens"] = budget
    text = summary if summary is not None else fixture["summary"]
    if arm == "jev-lcm":
        return run_jev_lcm(fixture, text)
    if arm == "production-equivalent":
        return run_production_equivalent(fixture, text)
    return run_jev_only(fixture)


def run_all() -> dict:
    fixture = load_fixture()
    arms = {
        "production-equivalent": run_production_equivalent(fixture, fixture["summary"]),
        "jev-only": run_jev_only(fixture),
        "jev-lcm": run_jev_lcm(fixture, fixture["summary"]),
    }
    return {
        "fixture": {
            "name": fixture["name"],
            "note": fixture["note"],
            "upstream_transcripts_available": bool(
                fixture.get("upstream_transcripts_available", False)
            ),
        },
        "arms": arms,
        "verdict": compare(arms, fixture),
    }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        raise SystemExit("No live mode or external fixture flags are implemented")
    print(json.dumps(run_all(), indent=2))
