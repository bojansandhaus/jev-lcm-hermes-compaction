import importlib.util
from jev_lcm_hermes_compaction.settings import Settings
from jev_lcm_hermes_compaction.providers import ProviderChain


def test_batched_anchors_are_exact_and_oversized_batch_is_explicit():
    assert importlib.util.find_spec(
        "jev_lcm_hermes_compaction.prepass"
    ), "prepass missing"
    from jev_lcm_hermes_compaction.prepass import Prepass

    requests = []

    def transport(url, key, payload, timeout):
        requests.append(payload)
        return {"answers": {q: {"noul": 0.19} for q in payload["questions"]}}

    settings = Settings(min_result_chars=0)
    chain = ProviderChain(settings, {"OPENROUTER_API_KEY": "private"}, transport)
    p = Prepass(settings, chain)
    messages = [
        {"role": "user", "content": "protected"},
        {
            "role": "assistant",
            "content": "The delegation id is `abc123def456`. We must retain it.",
        },
    ]
    for i in range(541):
        messages += [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": str(i),
                        "type": "function",
                        "function": {"name": "read", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": str(i), "content": "x" * 100},
        ]
    messages.append({"role": "user", "content": "fresh"})
    p.collect(messages, len(messages) - 1)
    p.tick()
    p.flush()
    p.tick()
    p.flush()
    assert not requests
    p.tick()
    p.flush()
    assert len(requests) == 1
    assert p.metrics["jev_unscored_count"] > 0
    assert any(c.text == "`abc123def456`" for c in p.protected())
    assert messages[-1]["content"] == "fresh"
    assert all(c.message_index != 0 for c in p.candidates.values())
