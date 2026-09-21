"""LCM subclass using the pinned ingest and assembly extension points."""

import json
import logging
from functools import wraps
from threading import RLock
from typing import Any
from ._vendor.lcm.engine import LCMEngine
from ._vendor.lcm.config import LCMConfig
from ._vendor.lcm.tokens import count_messages_tokens
from .prepass import Prepass
from .settings import Settings


def serialized(method: Any) -> Any:
    @wraps(method)
    def guarded(self: Any, *args: Any, **kwargs: Any) -> Any:
        with self._jev_lock:
            return method(self, *args, **kwargs)

    return guarded


class JevLCMContextCompressor(LCMEngine):
    def __init__(
        self,
        config: LCMConfig | None = None,
        hermes_home: str = "",
        settings: Settings | None = None,
    ):
        self._jev_lock = RLock()
        self.jev_settings = settings or Settings()
        self.jev = Prepass(self.jev_settings)
        self._jev_compacting = False
        self._jev_assembling = False
        super().__init__(config=config, hermes_home=hermes_home)

    @property
    def name(self) -> str:
        return "jev-lcm"

    @serialized
    def clone_for_agent(self) -> Any:
        clone = super().clone_for_agent()
        clone._jev_lock = RLock()
        clone.jev_settings = self.jev_settings
        clone.jev = Prepass(self.jev_settings)
        return clone

    @serialized
    def _ingest_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        working = super()._ingest_messages(messages)
        if not self._session_id or self._session_ignored or self._session_stateless:
            return working
        try:
            tail_start = self._fresh_tail_start(working)
            self.jev.bind_storage(self._store, self._session_id)
            self.jev.collect(
                working, tail_start, self._get_store_id_map_for_messages(working)
            )
            # Condensation is a hard boundary: pending ranking must precede it.
            self.jev.flush(force=self._jev_compacting)
        except Exception:
            self.jev.metrics["jev_fallbacks"] += 1
            logging.getLogger(__name__).warning(
                "Jev prepass failed; LCM default condensation"
            )
        return working

    @staticmethod
    def _leading_anchor_count(messages: list[dict[str, Any]]) -> int:
        return min(len(messages), max(1, LCMEngine._leading_anchor_count(messages)))

    def _latest_user_context_anchor(self, source: Any, tail: Any) -> Any:
        original = super()._latest_user_context_anchor(source, tail)
        hint = (
            self.jev.active_context_block()
            if self._jev_assembling
            else self.jev.hint_block()
        )
        return "\n\n".join(p for p in (original, hint) if p) or None

    def _assemble_context(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        """Make the persisted Jev index part of the real LCM prompt."""
        self.jev.bind_storage(self._store, self._session_id)
        self._jev_assembling = True
        try:
            return super()._assemble_context(*args, **kwargs)
        finally:
            self._jev_assembling = False

    def _summarize_leaf_chunk_with_rescue(
        self,
        initial_chunk: Any,
        focus_topic: str | None = None,
        deadline: float | None = None,
    ) -> Any:
        hint = self.jev.hint_block()
        focus = "\n".join(p for p in (focus_topic, hint) if p) if hint else focus_topic
        return super()._summarize_leaf_chunk_with_rescue(
            initial_chunk, focus_topic=focus, deadline=deadline
        )

    @serialized
    def compress(
        self,
        messages: list[dict[str, Any]],
        current_tokens: int = 0,
        focus_topic: str | None = None,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        before = count_messages_tokens(messages)
        node_count = len(self._dag.get_session_nodes(self._session_id))
        self._jev_compacting = True
        try:
            result = super().compress(
                messages,
                current_tokens=current_tokens,
                focus_topic=focus_topic,
                force=force,
            )
        finally:
            self._jev_compacting = False
        self.jev.metrics.compaction(
            before,
            count_messages_tokens(result),
            max(0, len(self._dag.get_session_nodes(self._session_id)) - node_count),
            count_messages_tokens(
                [m for m in result if m.get("role") in ("user", "assistant")]
            ),
        )
        return result

    @serialized
    def on_turn_complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> None:
        self.jev.tick()
        self._ingest_messages(messages)
        usage = kwargs.get("prompt_tokens", self.last_prompt_tokens) or 0
        urgent = (
            self.threshold_tokens > 0
            and usage
            >= self.jev_settings.jev_urgent_context_ratio * self.threshold_tokens
        )
        self.jev.flush(force=urgent)

    @serialized
    def on_session_end(self, session_id: str, messages: list[dict[str, Any]]) -> None:
        self._ingest_messages(messages)
        self.jev.flush(force=True)
        super().on_session_end(session_id, messages)

    @serialized
    def on_session_reset(self) -> None:
        self.jev.flush(force=True)
        super().on_session_reset()
        self.jev = Prepass(self.jev_settings)

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        schemas = super().get_tool_schemas()
        for name in ("jev_stats", "jev_scores", "jev_anchors", "jev_providers"):
            schemas.append(
                {
                    "name": name,
                    "description": "Inspect session-local Jev ranking diagnostics without credential values.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                }
            )
        return schemas

    @serialized
    def handle_tool_call(self, name: str, args: dict[str, Any], **kwargs: Any) -> str:
        if name == "jev_stats":
            return json.dumps(dict(self.jev.metrics))
        if name == "jev_providers":
            return json.dumps(self.jev.chain.diagnostics())
        if name in ("jev_scores", "jev_anchors"):
            return json.dumps(
                [
                    {
                        "id": c.id,
                        "store_id": c.store_id,
                        "kind": c.kind,
                        "scores": c.scores,
                        "action": c.action,
                        "jev_unscored": c.jev_unscored,
                    }
                    for c in self.jev.candidates.values()
                    if name != "jev_anchors" or c.kind == "anchor"
                ]
            )
        return super().handle_tool_call(name, args, **kwargs)
