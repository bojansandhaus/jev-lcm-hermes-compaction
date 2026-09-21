"""The bundled harness must measure three arms and keep its honesty flags."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "integration_eval", Path(__file__).parents[1] / "evaluation" / "run_eval.py"
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_three_arms_run_and_report_recall_at_budget():
    report = module.run_all()
    assert set(report["arms"]) == set(module.ARMS)
    for arm in report["arms"].values():
        assert arm["input_tokens"] > arm["budget_tokens"]
        assert arm["markers_total"] >= 1
        assert arm["model_calls"] > 0
        if arm["raw_store"]:
            assert arm["raw_retrieval_retention"] == 1
        else:
            assert arm["raw_retrieval_retention"] is None


def test_jev_lcm_meets_or_beats_production_at_budget():
    report = module.run_all()
    verdict = report["verdict"]
    production = report["arms"]["production-equivalent"]
    jev_lcm = report["arms"]["jev-lcm"]
    assert verdict["production_arm"] == "production-equivalent"
    assert verdict["upstream_transcripts_available"] is False
    assert verdict["upstream_production_run_reproduced"] is False
    assert jev_lcm["recall_at_budget"] >= production["recall_at_budget"]
    assert jev_lcm["budget_converged"] is True
    assert verdict["jev_lcm_meets_or_beats_production"] is True


def test_jev_only_arm_reproduces_the_unbounded_text_floor():
    report = module.run_all()
    jev_only = report["arms"]["jev-only"]
    assert jev_only["budget_converged"] is False
    assert jev_only["active_tokens"] > jev_only["input_tokens"]
    assert jev_only["raw_store"] is False
    assert report["verdict"]["jev_only_budget_converged"] is False


def test_retention_tracks_the_real_assembled_output():
    dropped = module.evaluate("production-equivalent")
    kept = module.evaluate(
        "production-equivalent",
        summary="Synthetic summary preserves deadbeef1234567 and 13da88ef01.",
    )
    assert dropped["markers_retained"] == 0
    assert kept["markers_retained"] == kept["markers_total"]


def test_invalid_budget_and_arm_rejected():
    with pytest.raises(ValueError, match="invalid budget"):
        module.evaluate("jev-lcm", 0)
    with pytest.raises(ValueError, match="unknown arm"):
        module.evaluate("not-an-arm")


def test_fixture_validation_rejects_an_incomplete_file(tmp_path):
    incomplete = tmp_path / "fixture.json"
    incomplete.write_text("{}")
    with pytest.raises(ValueError, match="fixture missing keys"):
        module.load_fixture(incomplete)
