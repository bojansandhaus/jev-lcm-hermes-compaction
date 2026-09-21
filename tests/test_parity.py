import json
from pathlib import Path

from parity_reference import run

ROOT = Path(__file__).parent


def test_python_reference_matches_checked_in_parity_golden():
    actual = run(ROOT / "parity_scenarios.json")
    expected = json.loads((ROOT / "parity_goldens.json").read_text())
    assert actual == expected


def test_parity_fixture_covers_required_cases():
    fixture = json.loads((ROOT / "parity_scenarios.json").read_text())
    assert {c["name"] for c in fixture["calibration"]} == {
        "uniform_low",
        "empty",
        "minimum_samples",
        "capped",
        "conservative",
    }
    assert {c["name"] for c in fixture["providers"]} == {
        "missing_keys",
        "single_provider",
        "both_keys",
        "primary429_fallback_once",
        "pinned_missing_key",
        "cooldown_expiration",
        "both_failing",
    }
