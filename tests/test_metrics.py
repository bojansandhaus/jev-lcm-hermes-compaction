"""Counters and the freed-per-compaction warning."""

import json

from jev_lcm_hermes_compaction.metrics import Metrics


def test_metrics_warning(caplog):
    m = Metrics()
    for _ in range(3):
        m.compaction(100, 90, 1, 30)
    assert "three consecutive" in caplog.text
    assert m["lcm_recall_at_budget"] is None
    m.compaction(0, 0, 0, 0)


def test_freed_space_is_clamped_to_a_usable_range():
    """A compaction that grows the context is not negative freed space.

    `100 * (before - after) / before` goes below zero whenever `after` exceeds
    `before`, and a negative value silently fails the `freed < 20` test that
    drives the low-cycle warning. The cycles that most need the signal are the
    ones that reported a number below zero, so the value is clamped to
    [0, 100] and the warning fires on them like any other.
    """
    m = Metrics()
    m.compaction(100, 130, 1, 30)
    assert m["lcm_freed_per_compaction"] == 0.0
    m.compaction(100, 100, 1, 30)
    assert m["lcm_freed_per_compaction"] == 0.0
    m.compaction(100, 0, 1, 30)
    assert m["lcm_freed_per_compaction"] == 100.0
    m.compaction(100, 50, 1, 30)
    assert m["lcm_freed_per_compaction"] == 50.0


def test_a_negative_cycle_still_charges_the_low_cycle_counter(caplog):
    m = Metrics()
    for _ in range(3):
        m.compaction(100, 200, 1, 30)
    assert "three consecutive" in caplog.text
    assert m.low_cycles == 3


def test_low_cycles_round_trips_through_the_mapping():
    """`low_cycles` was an attribute only, so `dict(m)` and JSON dropped it.

    Every other counter survives a `dict(m)` or a JSON round-trip, which is how
    the metrics reach an operator and a log. The one counter that gates a
    warning was the one that vanished.
    """
    m = Metrics()
    assert m.low_cycles == 0
    assert m["low_cycles"] == 0
    # 90% freed, which is above the 20% floor: a healthy cycle does not charge it.
    m.compaction(100, 10, 1, 30)
    assert m.low_cycles == 0
    assert m["low_cycles"] == 0
    # 10% freed: below the floor, so it charges.
    m.compaction(100, 90, 1, 30)
    assert m.low_cycles == 1
    assert m["low_cycles"] == 1
    assert json.loads(json.dumps(dict(m)))["low_cycles"] == 1
    # A healthy cycle resets it, in both places.
    m.compaction(100, 90, 1, 30)
    m.compaction(100, 50, 1, 30)
    assert m.low_cycles == 0
    assert m["low_cycles"] == 0


def test_the_hint_and_starvation_counters_start_at_zero():
    m = Metrics()
    assert m["jev_hint_dropped"] == 0
    assert m["jev_anchor_block_dropped"] == 0
    assert m["jev_starved_count"] == 0
    assert json.loads(json.dumps(dict(m)))["jev_hint_dropped"] == 0
