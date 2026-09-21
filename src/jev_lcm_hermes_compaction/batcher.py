"""Turn-count gating. Pressure and lifecycle boundaries flush immediately."""
from dataclasses import dataclass


@dataclass
class Batcher:
    window: int = 3
    turns: int = 0

    def tick(self) -> None:
        self.turns += 1

    def ready(self, force: bool = False) -> bool:
        return force or self.turns >= self.window

    def flushed(self) -> None:
        self.turns = 0
