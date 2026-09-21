"""Turn count gating for batched scoring."""

from jev_lcm_hermes_compaction.batcher import Batcher
from jev_lcm_hermes_compaction.settings import Settings


def test_window_holds_turns_until_the_configured_count():
    window = Settings().jev_batch_window_turns
    assert window == 3
    b = Batcher(window)
    b.tick()
    b.tick()
    assert not b.ready()
    b.tick()
    assert b.ready()
    b.flushed()
    assert b.turns == 0 and not b.ready()
    assert b.ready(force=True)
