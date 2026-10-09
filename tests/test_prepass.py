import importlib.util
from jev_lcm_hermes_compaction.anchors import Candidate
from jev_lcm_hermes_compaction.prepass import ANCHOR_BLOCK_MAX_ROWS, Prepass
from jev_lcm_hermes_compaction.providers import ProviderChain
from jev_lcm_hermes_compaction.settings import Settings
from conftest import synthetic_transport


def test_batched_anchors_are_exact_and_oversized_batch_is_explicit():
    assert importlib.util.find_spec(
        "jev_lcm_hermes_compaction.prepass"
    ), "prepass missing"
    from jev_lcm_hermes_compaction.prepass import Prepass

    requests = []

    def transport(url, key, payload, timeout):
        requests.append(payload)
        return synthetic_transport(0.19)(url, key, payload, timeout)

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


def _render_prepass(**settings_kwargs):
    """A Prepass with no key, so rendering never reaches a provider."""
    settings = Settings(**settings_kwargs)
    return Prepass(settings, ProviderChain(settings, {}))


def _kept(candidate_id, text, store_id=None, kind="tool"):
    candidate = Candidate(
        candidate_id, kind, 3, text, start=0, end=len(text), store_id=store_id
    )
    candidate.action = "keep"
    return candidate


def test_hint_block_receipts_evidence_the_budget_cannot_carry():
    """A kept tool result must not vanish because it is too large.

    A kept result at the default `min_result_chars` of 8000 is about 8000 bytes
    against a 4000-token default hint budget, so it never fits and the block
    used to return "". Jev had spent a request deciding to keep exactly that
    evidence, and the decision never reached the prompt. Every withheld row now
    leaves a one-line receipt naming the store id, the byte length, and the tool
    that recovers it, and the drop is counted.
    """
    p = _render_prepass(hint_budget_tokens=200)
    p.candidates["c1"] = _kept("c1", "SENSITIVE-EVIDENCE " * 200, store_id=7)
    block = p.hint_block()
    assert "SENSITIVE-EVIDENCE" not in block
    assert "store_id=7" in block
    assert "bytes=3800" in block
    assert "lcm_expand(store_id=7)" in block
    assert block.splitlines()[-1].count("\n") == 0
    assert len(block.splitlines()) == 2
    assert p.metrics["jev_hint_dropped"] == 1


def test_hint_block_still_quotes_what_fits():
    """The receipt is for what is withheld; what fits is still quoted verbatim."""
    p = _render_prepass(hint_budget_tokens=4000)
    p.candidates["c1"] = _kept("c1", "small evidence", store_id=7)
    block = p.hint_block()
    assert "small evidence" in block
    assert p.metrics["jev_hint_dropped"] == 0


def test_hint_block_keeps_scanning_past_an_oversized_row():
    """One oversized row says nothing about the rows behind it."""
    p = _render_prepass(hint_budget_tokens=1000)
    p.candidates["big"] = _kept("big", "BIG-EVIDENCE " * 200, store_id=8)
    p.candidates["small"] = _kept("small", "tiny evidence", store_id=9)
    block = p.hint_block()
    assert "BIG-EVIDENCE" not in block
    # The receipt for the big row, and the verbatim quote of the small one.
    assert "lcm_expand(store_id=8)" in block
    assert "tiny evidence" in block
    assert p.metrics["jev_hint_dropped"] == 1


def test_hint_block_receipts_a_candidate_with_no_store_id():
    p = _render_prepass(hint_budget_tokens=200)
    p.candidates["c1"] = _kept("c1", "SENSITIVE-EVIDENCE " * 200, store_id=None)
    block = p.hint_block()
    assert "lcm_grep" in block
    assert p.metrics["jev_hint_dropped"] == 1


class _Store:
    """The two anchor-index methods Prepass actually calls."""

    def __init__(self, rows):
        self.rows = rows

    def write_protected_anchor_index(self, session_id, anchors):
        pass

    def get_protected_anchor_index(self, session_id):
        return self.rows


def test_anchor_block_skips_an_oversized_row_instead_of_dropping_the_tail():
    """The first oversized row must not discard every later anchor.

    Rows arrive ordered by keep score, descending, so the highest-scoring row is
    the most likely to be large. Breaking on it discarded the whole tail of the
    index, which is the opposite of what the ordering promises.
    """
    p = _render_prepass(hint_budget_tokens=200)
    p.bind_storage(
        _Store(
            [
                {
                    "candidate_id": "big",
                    "store_id": 1,
                    "text": "BIG-ANCHOR " * 100,
                    "score": 0.99,
                    "action": "keep",
                },
                {
                    "candidate_id": "small",
                    "store_id": 2,
                    "text": "tiny anchor",
                    "score": 0.5,
                    "action": "keep",
                },
            ]
        ),
        "session-1",
    )
    block = p.active_context_block()
    assert "BIG-ANCHOR" not in block
    assert "tiny anchor" in block
    assert "store_id=2" in block or "candidate=small" in block
    assert p.metrics["jev_anchor_block_dropped"] == 1


def test_anchor_block_caps_the_scan():
    """The scan cap bounds render cost without emptying the block."""
    p = _render_prepass(hint_budget_tokens=10**9)
    p.bind_storage(
        _Store(
            [
                {
                    "candidate_id": "row-%03d" % i,
                    "store_id": i,
                    "text": "anchor %d" % i,
                    "score": 0.9,
                    "action": "keep",
                }
                for i in range(ANCHOR_BLOCK_MAX_ROWS + 25)
            ]
        ),
        "session-1",
    )
    block = p.active_context_block()
    rows = [line for line in block.splitlines() if line.startswith("[candidate=")]
    assert len(rows) == ANCHOR_BLOCK_MAX_ROWS
    assert p.metrics["jev_anchor_block_dropped"] == 25
    # The cap takes the highest-scoring rows, not the first ones by insertion.
    assert "anchor 0" in block
    assert "anchor %d" % (ANCHOR_BLOCK_MAX_ROWS + 24) not in block


def test_unscored_count_is_reported_before_any_flush():
    """`jev_unscored_count` must not be a flush-only counter.

    It was written only inside `_counts()`, which runs from `flush()`. With the
    default three-turn batch window two of every three turns never flush, so
    `jev_stats` reported zero unscored candidates while they waited.
    """
    settings = Settings()
    p = Prepass(
        settings,
        ProviderChain(
            settings, {"OPENROUTER_API_KEY": "synthetic"}, synthetic_transport(0.99)
        ),
    )
    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "The delegation id is `abc123def456`."},
        {"role": "tool", "tool_call_id": "t", "content": ""},
        {"role": "user", "content": "fresh"},
    ]
    p.collect(messages, 3)
    assert p.metrics["jev_unscored_count"] > 0
    assert p.metrics["jev_unscored_count"] == len(p.candidates)
    # And it is still right after a flush, which is what it always meant.
    p.tick()
    p.tick()
    p.tick()
    p.flush()
    assert p.metrics["jev_unscored_count"] == 0


def test_starved_count_is_reported_and_charges_the_candidates():
    """Candidates past the per-batch cap are counted, not silently omitted."""
    p = _render_prepass(jev_max_candidates_per_batch=2, min_result_chars=0)
    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "The delegation id is `abc123def456`."},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "t1",
                    "type": "function",
                    "function": {"name": "read", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "t1", "content": "x" * 50},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "t2",
                    "type": "function",
                    "function": {"name": "read", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "t2", "content": "y" * 50},
        {"role": "user", "content": "fresh"},
    ]
    p.collect(messages, len(messages) - 1)
    assert p.metrics["jev_starved_count"] == 0
    p.tick()
    p.tick()
    p.tick()
    p.flush(force=True)
    assert p.metrics["jev_starved_count"] > 0
    assert any(c.jev_dropped_batches for c in p.candidates.values())
    # The count is visible again after a later collect, without another flush.
    p.collect(messages, len(messages) - 1)
    assert p.metrics["jev_starved_count"] > 0
