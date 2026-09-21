import importlib.util


def test_calibration_retains_low_probability_candidates():
    assert importlib.util.find_spec('jev_lcm_hermes_compaction') is not None, 'package must exist'
    from jev_lcm_hermes_compaction.calibration import JevThresholdCalibrator
    c = JevThresholdCalibrator()
    values = [i / 5000 for i in range(500)]
    threshold = c.observe(values)
    assert threshold < 0.15
    assert sum(p >= threshold for p in values) >= 50
    assert c.calibrated
