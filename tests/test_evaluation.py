import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location(
    "integration_eval", Path(__file__).parents[1] / "evaluation" / "run_eval.py"
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_real_compaction_and_raw_retrieval():
    for protect in [False, True]:
        result = module.evaluate(protect)
        assert result["input_tokens"] > result["budget_tokens"]
        assert result["active_tokens"] <= result["budget_tokens"]
        assert result["raw_retrieval_retention"] == 1
        assert result["model_calls"] > 0
        assert result["production_comparison"] is False


def test_retention_is_sensitive_to_real_assembled_output():
    dropped = module.evaluate(False)
    kept = module.evaluate(
        False, summary="Synthetic summary preserves deadbeef1234567."
    )
    assert dropped["exact_evidence_retention"] == 0
    assert kept["exact_evidence_retention"] == 1


def test_invalid_budget_rejected():
    with pytest.raises(ValueError, match="invalid budget"):
        module.evaluate(True, 0)
