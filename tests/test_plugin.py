import json
from hermes_cli.plugins import PluginManager, PluginContext, PluginManifest
from jev_lcm_hermes_compaction.plugin import register


def test_opt_in_registration_and_clone(tmp_path):
    manager = PluginManager(scope_key=str(tmp_path))
    ctx = PluginContext(
        PluginManifest(name="jev-lcm", path=str(tmp_path), source="user"), manager
    )
    (tmp_path / "config.yaml").write_text("context:\n  engine: compressor\n")
    register(ctx)
    assert manager._context_engine is None
    (tmp_path / "config.yaml").write_text(
        "context:\n  engine: jev-lcm\njev_lcm:\n  keep_threshold: 0.19\n"
    )
    register(ctx)
    engine = manager._context_engine
    assert engine.name == "jev-lcm"
    assert engine.jev_settings.keep_threshold == 0.19
    engine.on_session_start("clean")
    engine.on_turn_complete([{"role": "user", "content": "first"}])
    assert engine._store.get_session_count("clean") == 1
