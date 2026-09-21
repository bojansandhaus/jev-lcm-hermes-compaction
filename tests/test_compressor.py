import importlib.util
import json
from jev_lcm_hermes_compaction.settings import Settings


def test_real_lcm_stores_before_scoring_and_preserves_anchor(tmp_path):
    assert importlib.util.find_spec('jev_lcm_hermes_compaction.compressor'), 'engine missing'
    from jev_lcm_hermes_compaction.compressor import JevLCMContextCompressor
    from jev_lcm_hermes_compaction._vendor.lcm.config import LCMConfig
    from jev_lcm_hermes_compaction.providers import ProviderChain
    from jev_lcm_hermes_compaction.prepass import Prepass
    cfg = LCMConfig(database_path=str(tmp_path/'lcm.db'), fresh_tail_count=2)
    engine = JevLCMContextCompressor(config=cfg, hermes_home=str(tmp_path), settings=Settings(min_result_chars=0))
    engine.on_session_start('test-session')
    messages = [{'role':'user','content':'first'}, {'role':'assistant','content':'The delegation id is `abc123def456`.'}, {'role':'user','content':'next'}, {'role':'assistant','content':'fresh'}]
    def transport(url,key,payload,timeout):
        raw = engine._store.get_session_messages('test-session')
        assert any('abc123def456' in str(m) for m in raw)
        return {'answers':{q:{'noul':0.19} for q in payload['questions']}}
    engine.jev = Prepass(engine.jev_settings, ProviderChain(engine.jev_settings, {'TYPESAFE_API_KEY':'synthetic-key'}, transport))
    engine._jev_compacting = True
    engine._ingest_messages(messages)
    engine._jev_compacting = False
    assert engine.jev.metrics['jev_calls'] == 1
    assembled = engine._assemble_context(None, messages[-2:])
    assert 'abc123def456' in json.dumps(assembled)
    assert len(engine._store.get_session_messages('test-session')) == 4
