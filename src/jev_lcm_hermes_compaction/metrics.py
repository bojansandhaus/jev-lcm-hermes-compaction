"""Session metrics, with null for unevaluated recall."""

import logging
from typing import Any


class Metrics(dict[str, Any]):
    def __init__(self) -> None:
        super().__init__(
            {
                key: 0
                for key in (
                    "jev_candidates_total",
                    "jev_keep_call_count",
                    "jev_keep_result_count",
                    "jev_anchor_count",
                    "jev_unscored_count",
                    "jev_calls",
                    "jev_pruned_units",
                    "jev_fallbacks",
                    "lcm_summary_nodes_created",
                    "lcm_nodes_created",
                    "lcm_text_floor_tokens",
                    "jev_provider_fallback_count",
                    "jev_hint_dropped",
                    "jev_anchor_block_dropped",
                    "jev_starved_count",
                    "low_cycles",
                )
            }
        )
        self.update(
            jev_threshold_current=0.15,
            jev_threshold_calibrated=False,
            jev_provider_primary="",
            lcm_recall_at_budget=None,
            lcm_freed_per_compaction=0.0,
        )

    @property
    def low_cycles(self) -> int:
        """Consecutive compactions that freed less than 20 percent.

        A property over the mapping key rather than a plain attribute, so the
        counter an attribute reader and a `dict(m)` / JSON reader see are the
        same number. As an attribute it was invisible to the mapping, which is
        how the metrics leave this class.
        """
        return int(self.get("low_cycles", 0))

    @low_cycles.setter
    def low_cycles(self, value: int) -> None:
        self["low_cycles"] = int(value)

    def compaction(self, before: int, after: int, nodes: int, text_floor: int) -> None:
        # A compaction that grew the context is not "negative freed space"; it
        # is zero freed space. Left unclamped the value went below zero, the
        # `freed < 20` test was never reached for the cycles that mattered, and
        # the low-cycle warning never fired on the shape that most needs it.
        freed = 100 * (before - after) / before if before else 0.0
        freed = min(100.0, max(0.0, freed))
        self.update(
            lcm_freed_per_compaction=freed,
            lcm_summary_nodes_created=nodes,
            lcm_nodes_created=nodes,
            lcm_text_floor_tokens=text_floor,
        )
        # Stored in the mapping, not only as an attribute, so it survives
        # `dict(m)` and JSON round-trips the way every other counter does.
        self.low_cycles = self.low_cycles + 1 if freed < 20 else 0
        if self.low_cycles >= 3:
            logging.getLogger(__name__).warning(
                "LCM freed less than 20 percent for three consecutive compactions; consider a higher lcm_context_threshold or deeper summaries, within the model window"
            )
