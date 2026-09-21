"""Counters and the freed-per-compaction warning."""

from jev_lcm_hermes_compaction.metrics import Metrics


def test_metrics_warning(caplog):
    m = Metrics()
    for _ in range(3):
        m.compaction(100, 90, 1, 30)
    assert "three consecutive" in caplog.text
    assert m["lcm_recall_at_budget"] is None
    m.compaction(0, 0, 0, 0)
