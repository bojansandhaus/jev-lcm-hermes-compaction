"""Finite state ladder with conservative UTF-8 token upper bounds."""
import copy
import json
from typing import Any
from .anchors import Candidate
from .decisions import questions
from .settings import Settings


def wire(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def tokens(value: Any) -> int:
    # UTF-8 bytes upper-bound byte-based BPE tokens, including CJK.
    return len(wire(value).encode("utf-8"))


def shape(messages: list[dict[str, Any]], candidates: list[Candidate], settings: Settings) -> tuple[dict[str, Any], dict[str, Any], list[Candidate], int]:
    state: dict[str, Any] = {}
    tier = 0
    for tier in range(5):
        history = copy.deepcopy(messages)
        for message in history:
            text = message.get("content", "")
            if tier and message.get("role") == "tool":
                head = (settings.truncate_head_chars, 50, 0, 0)[tier - 1]
                message["content"] = str(text)[:head] + " [result omitted; raw evidence retained]"
            elif tier >= 2:
                message["content"] = " ".join(str(text).split())[:200 if tier == 2 else 60]
            for call in message.get("tool_calls", []):
                fn = call.get("function", {})
                if tier:
                    fn["arguments"] = str(fn.get("arguments", ""))[:(1000, 200, 60, 30)[tier-1]]
        state = {"history": history, "candidates": []}
        if tokens(state) <= settings.max_state_tokens:
            break
    if tokens(state) > settings.max_state_tokens:
        state = {"history": [], "candidates": [], "folded": True}
        for msg in reversed(history):
            trial = {**state, "history": [msg] + state["history"]}
            if tokens(trial) > settings.max_state_tokens // 2:
                break
            state = trial
    selected: list[Candidate] = []
    qs: dict[str, Any] = {}
    for candidate in candidates[:settings.jev_max_candidates_per_batch]:
        entry = {"id": candidate.id, "kind": candidate.kind, "text": candidate.text, "call": candidate.call}
        # The scored candidate always retains its evidence, even when history folds.
        trial = {**state, "candidates": state["candidates"] + [entry]}
        trial_q = {**qs, **questions(candidate)}
        envelope = {"model": max((settings.jev_model, settings.openrouter_model), key=len), "state": trial, "questions": trial_q}
        if tokens(trial) > settings.max_state_tokens or tokens(envelope) > settings.max_request_tokens:
            continue
        state, qs = trial, trial_q
        selected.append(candidate)
    return state, qs, selected, tier
