import importlib.util
import json
from jev_lcm_hermes_compaction.settings import Settings


def test_real_lcm_stores_before_scoring_and_preserves_anchor(tmp_path):
    assert importlib.util.find_spec(
        "jev_lcm_hermes_compaction.compressor"
    ), "engine missing"
    from jev_lcm_hermes_compaction.compressor import JevLCMContextCompressor
    from jev_lcm_hermes_compaction._vendor.lcm.config import LCMConfig
    from jev_lcm_hermes_compaction.providers import ProviderChain
    from jev_lcm_hermes_compaction.prepass import Prepass

    cfg = LCMConfig(database_path=str(tmp_path / "lcm.db"), fresh_tail_count=2)
    engine = JevLCMContextCompressor(
        config=cfg, hermes_home=str(tmp_path), settings=Settings(min_result_chars=0)
    )
    engine.on_session_start("test-session")
    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "The delegation id is `abc123def456`."},
        {"role": "user", "content": "next"},
        {"role": "assistant", "content": "fresh"},
    ]

    def transport(url, key, payload, timeout):
        raw = engine._store.get_session_messages("test-session")
        assert any("abc123def456" in str(m) for m in raw)
        return {"answers": {q: {"noul": 0.19} for q in payload["questions"]}}

    engine.jev = Prepass(
        engine.jev_settings,
        ProviderChain(
            engine.jev_settings, {"TYPESAFE_API_KEY": "synthetic-key"}, transport
        ),
    )
    engine._jev_compacting = True
    engine._ingest_messages(messages)
    engine._jev_compacting = False
    assert engine.jev.metrics["jev_calls"] == 1
    assembled = engine._assemble_context(None, messages[-2:])
    assert "abc123def456" in json.dumps(assembled)
    assert len(engine._store.get_session_messages("test-session")) == 4


def test_protected_anchor_index_survives_restart_and_enters_assembled_prompt(tmp_path):
    from jev_lcm_hermes_compaction.compressor import JevLCMContextCompressor
    from jev_lcm_hermes_compaction._vendor.lcm.config import LCMConfig
    from jev_lcm_hermes_compaction.providers import ProviderChain
    from jev_lcm_hermes_compaction.prepass import Prepass

    db = tmp_path / "lcm.db"
    cfg = LCMConfig(database_path=str(db), fresh_tail_count=1)
    settings = Settings(min_result_chars=0)
    engine = JevLCMContextCompressor(cfg, str(tmp_path), settings)
    engine.on_session_start("restart-session")
    messages = [
        {"role": "user", "content": "start"},
        {
            "role": "assistant",
            "content": "The root cause is `deadbeef1234567` and this must remain exact.",
        },
        {"role": "user", "content": "fresh"},
    ]
    chain = ProviderChain(
        settings,
        {"OPENROUTER_API_KEY": "synthetic"},
        lambda u, k, p, t: {"answers": {q: {"noul": 0.99} for q in p["questions"]}},
    )
    engine.jev = Prepass(settings, chain)
    engine._jev_compacting = True
    engine._ingest_messages(messages)
    engine._jev_compacting = False
    indexed = engine._store.get_protected_anchor_index("restart-session")
    anchor = next(row for row in indexed if row["text"] == "`deadbeef1234567`")
    raw = engine._store.get(anchor["store_id"])
    assert raw["content"] == messages[1]["content"]

    restarted = JevLCMContextCompressor(cfg, str(tmp_path), settings)
    restarted.on_session_start("restart-session")
    assembled = restarted._assemble_context(None, [messages[-1]])
    prompt = "\n".join(str(message.get("content", "")) for message in assembled)
    assert "`deadbeef1234567`" in prompt
    assert f"lcm_expand(store_id={anchor['store_id']})" in prompt
    recovered = restarted._store.get(anchor["store_id"])
    assert recovered["content"] == raw["content"]


def test_protected_evidence_is_budgeted_by_real_assembly(tmp_path):
    from jev_lcm_hermes_compaction.compressor import JevLCMContextCompressor
    from jev_lcm_hermes_compaction._vendor.lcm.config import LCMConfig
    from jev_lcm_hermes_compaction.providers import ProviderChain
    from jev_lcm_hermes_compaction.prepass import Prepass
    from jev_lcm_hermes_compaction._vendor.lcm.tokens import count_messages_tokens

    settings = Settings(min_result_chars=0, hint_budget_tokens=300)
    cfg = LCMConfig(
        database_path=str(tmp_path / "lcm.db"),
        fresh_tail_count=1,
        max_assembly_tokens=200,
    )
    engine = JevLCMContextCompressor(cfg, str(tmp_path), settings)
    engine.on_session_start("budget-session")
    messages = [
        {"role": "user", "content": "start"},
        {
            "role": "assistant",
            "content": "The root cause is `cafebabedeadbeef` and this must remain exact.",
        },
        {"role": "user", "content": "fresh"},
    ]
    engine.jev = Prepass(
        settings,
        ProviderChain(
            settings,
            {"OPENROUTER_API_KEY": "synthetic"},
            lambda u, k, p, t: {"answers": {q: {"noul": 0.99} for q in p["questions"]}},
        ),
    )
    engine._jev_compacting = True
    engine._ingest_messages(messages)
    engine._jev_compacting = False

    assembled = engine._assemble_context(None, [messages[-1]])
    assert count_messages_tokens(assembled) <= cfg.max_assembly_tokens
    prompt = "\n".join(str(message.get("content", "")) for message in assembled)
    assert prompt.count("cafebabedeadbeef") == 1


def test_index_write_failure_keeps_volatile_evidence_in_real_assembly(
    tmp_path, monkeypatch
):
    from jev_lcm_hermes_compaction.compressor import JevLCMContextCompressor
    from jev_lcm_hermes_compaction._vendor.lcm.config import LCMConfig
    from jev_lcm_hermes_compaction.providers import ProviderChain
    from jev_lcm_hermes_compaction.prepass import Prepass

    settings = Settings(min_result_chars=0)
    engine = JevLCMContextCompressor(
        LCMConfig(database_path=str(tmp_path / "lcm.db"), fresh_tail_count=1),
        str(tmp_path),
        settings,
    )
    engine.on_session_start("failure-session")
    messages = [
        {"role": "user", "content": "start"},
        {"role": "assistant", "content": "The constraint is `fadedbadc0ffee`."},
        {"role": "user", "content": "fresh"},
    ]
    engine.jev = Prepass(
        settings,
        ProviderChain(
            settings,
            {"OPENROUTER_API_KEY": "synthetic"},
            lambda u, k, p, t: {"answers": {q: {"noul": 0.99} for q in p["questions"]}},
        ),
    )
    monkeypatch.setattr(
        engine._store,
        "write_protected_anchor_index",
        lambda *a: (_ for _ in ()).throw(OSError("read-only")),
    )
    engine._jev_compacting = True
    engine._ingest_messages(messages)
    engine._jev_compacting = False

    assembled = engine._assemble_context(None, [messages[-1]])
    prompt = "\n".join(str(message.get("content", "")) for message in assembled)
    assert "`fadedbadc0ffee`" in prompt


def test_protected_index_rejects_raw_pointer_from_another_session(tmp_path):
    from jev_lcm_hermes_compaction._vendor.lcm.store import MessageStore

    store = MessageStore(str(tmp_path / "lcm.db"), hermes_home=str(tmp_path))
    other_id = store.append(
        "other-session", {"role": "assistant", "content": "`crosssession`"}
    )
    try:
        store.write_protected_anchor_index(
            "target-session",
            [
                {
                    "candidate_id": "bad",
                    "store_id": other_id,
                    "start": 0,
                    "end": 13,
                    "text": "`crosssession`",
                    "score": 1.0,
                }
            ],
        )
    except ValueError:
        pass
    else:
        raise AssertionError("cross-session raw pointer was accepted")
    assert store.get_protected_anchor_index("target-session") == []
