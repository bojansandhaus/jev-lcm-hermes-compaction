"""Threshold calibration: quantile, floor, and parameter validation."""

import importlib.util

import pytest

from jev_lcm_hermes_compaction.calibration import JevThresholdCalibrator


def test_calibration_retains_low_probability_candidates():
    assert (
        importlib.util.find_spec("jev_lcm_hermes_compaction") is not None
    ), "package must exist"
    from jev_lcm_hermes_compaction.calibration import JevThresholdCalibrator

    c = JevThresholdCalibrator()
    values = [i / 5000 for i in range(500)]
    threshold = c.observe(values)
    assert threshold < 0.15
    assert sum(p >= threshold for p in values) >= 50
    assert c.calibrated


@pytest.mark.parametrize("values", [[], [0.1], [i / 2500 for i in range(500)]])
def test_quantile_and_floor(values):
    c = JevThresholdCalibrator()
    c.observe(values)
    assert len(c.retained_indices(values)) >= len(values) * 0.1
    if len(values) == 500:
        assert c.current == pytest.approx(0.01996)
    c = JevThresholdCalibrator(conservative=True)
    assert c.observe([0.1] * 50) == 0
    c = JevThresholdCalibrator(enabled=False)
    assert c.observe([0.1] * 500) == 0.15


@pytest.mark.parametrize("kw", [{"window": 0}, {"minimum": 501}, {"cap": 2}])
def test_bad_calibrator(kw):
    with pytest.raises(ValueError):
        JevThresholdCalibrator(**kw)


def test_bad_sample():
    with pytest.raises(ValueError):
        JevThresholdCalibrator().observe([float("nan")])
