"""Session metrics, with null for unevaluated recall."""
import logging
from typing import Any


class Metrics(dict[str, Any]):
    def __init__(self) -> None:
        super().__init__({key: 0 for key in (
            "jev_candidates_total", "jev_keep_call_count", "jev_keep_result_count", "jev_anchor_count", "jev_unscored_count", "jev_calls", "jev_pruned_units", "jev_fallbacks", "lcm_summary_nodes_created", "lcm_nodes_created", "lcm_text_floor_tokens", "jev_provider_fallback_count")})
        self.update(jev_threshold_current=0.15, jev_threshold_calibrated=False, jev_provider_primary="", lcm_recall_at_budget=None, lcm_freed_per_compaction=0.0)
        self.low_cycles = 0

    def compaction(self, before: int, after: int, nodes: int, text_floor: int) -> None:
        freed = 100 * (before - after) / before if before else 0.0
        self.update(lcm_freed_per_compaction=freed, lcm_summary_nodes_created=nodes, lcm_nodes_created=nodes, lcm_text_floor_tokens=text_floor)
        self.low_cycles = self.low_cycles + 1 if freed < 20 else 0
        if self.low_cycles >= 3:
            logging.getLogger(__name__).warning("LCM freed less than 20 percent for three consecutive compactions; consider a higher lcm_context_threshold or deeper summaries, within the model window")
