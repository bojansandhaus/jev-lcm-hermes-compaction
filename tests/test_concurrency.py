from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from jev_lcm_hermes_compaction.compressor import JevLCMContextCompressor
from jev_lcm_hermes_compaction._vendor.lcm.config import LCMConfig


def test_concurrent_ingest_is_idempotent(tmp_path):
    engine=JevLCMContextCompressor(LCMConfig(database_path=str(tmp_path/'raw.db')),str(tmp_path))
    engine.on_session_start('parallel')
    messages=[{'role':'user','content':'message '+str(i)} for i in range(40)]
    barrier=Barrier(8)
    def ingest(_):
        barrier.wait()
        engine._ingest_messages(messages)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(ingest,range(8)))
    assert engine._store.get_session_count('parallel')==len(messages)
    assert engine.clone_for_agent()._jev_lock is not engine._jev_lock
