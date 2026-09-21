import copy
import json
from jev_lcm_hermes_compaction.compressor import JevLCMContextCompressor
from jev_lcm_hermes_compaction._vendor.lcm.config import LCMConfig
from jev_lcm_hermes_compaction._vendor.lcm import engine as upstream
from jev_lcm_hermes_compaction.settings import Settings


def test_real_compaction_and_recall_with_failed_jev(tmp_path, monkeypatch):
    engine = JevLCMContextCompressor(
        config=LCMConfig(
            database_path=str(tmp_path / "lcm.db"),
            fresh_tail_count=2,
            fresh_tail_max_tokens=500,
            leaf_chunk_tokens=500,
        ),
        hermes_home=str(tmp_path),
    )
    engine.on_session_start("integration")
    messages = [{"role": "user", "content": "first"}]
    for i in range(12):
        messages.extend(
            [
                {"role": "user", "content": ("User facts %s. " % i) * 100},
                {
                    "role": "assistant",
                    "content": ("Assistant facts %s. " % i) * 100
                    + " identifier `abc123def456`.",
                },
            ]
        )
    original = copy.deepcopy(messages)

    def summarize(**kwargs):
        assert engine._store.get_session_count("integration") == len(messages)
        assert engine.jev.metrics["jev_fallbacks"] > 0
        return ("Synthetic test summary; raw evidence remains recoverable.", 3)

    monkeypatch.setattr(upstream, "summarize_with_escalation", summarize)
    result = engine.compress(messages, current_tokens=20000, force=True)
    assert messages == original
    assert len(json.dumps(result)) < len(json.dumps(messages))
    assert engine._store.get_session_count("integration") == len(messages)
    assert engine._dag.get_session_nodes("integration")
    found = json.loads(engine.handle_tool_call("lcm_grep", {"query": "abc123def456"}))
    assert "abc123def456" in json.dumps(found)
    for name in ("jev_stats", "jev_scores", "jev_anchors", "jev_providers"):
        assert json.loads(engine.handle_tool_call(name, {})) is not None
    assert any(s["name"] == "jev_stats" for s in engine.get_tool_schemas())
    clone = engine.clone_for_agent()
    assert clone.jev is not engine.jev and clone.name == "jev-lcm"
    engine.on_turn_complete(result)
    engine.on_session_end("integration", result)
    engine.on_session_reset()
    assert engine.jev.metrics["jev_calls"] == 0


def test_541_unscored_raw_recovery(tmp_path):
    from jev_lcm_hermes_compaction.providers import ProviderChain
    from jev_lcm_hermes_compaction.prepass import Prepass

    settings = Settings(min_result_chars=0)
    engine = JevLCMContextCompressor(
        config=LCMConfig(
            database_path=str(tmp_path / "lcm.db"),
            fresh_tail_count=2,
            fresh_tail_max_tokens=500,
            leaf_chunk_tokens=500,
        ),
        hermes_home=str(tmp_path),
        settings=settings,
    )
    engine.on_session_start("bulk")
    messages = [{"role": "user", "content": "first"}]
    for i in range(541):
        messages.extend(
            [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": str(i),
                            "type": "function",
                            "function": {"name": "read", "arguments": "{}"},
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": str(i),
                    "content": "evidence%s " % i + "x" * 100,
                },
            ]
        )
    messages.extend(
        [
            {"role": "user", "content": "fresh"},
            {"role": "assistant", "content": "fresh answer"},
        ]
    )
    engine.jev = Prepass(
        settings,
        ProviderChain(
            settings,
            {"OPENROUTER_API_KEY": "synthetic"},
            lambda u, k, p, t: {"answers": {q: {"noul": 0.19} for q in p["questions"]}},
        ),
    )
    engine._jev_compacting = True
    engine._ingest_messages(messages)
    assert engine.jev.metrics["jev_unscored_count"] > 0
    for c in engine.jev.candidates.values():
        if c.jev_unscored:
            found = engine.handle_tool_call("lcm_grep", {"query": c.text.split()[0]})
            assert c.text.split()[0] in found
