"""Rolling empirical quantiles, with a one-sided DKW confidence bound."""

from collections import deque
from math import ceil, log, sqrt
from typing import Iterable


class JevThresholdCalibrator:
    def __init__(
        self,
        window: int = 500,
        minimum: int = 50,
        fallback: float = 0.15,
        cap: float = 0.40,
        keep_rate: float = 0.10,
        enabled: bool = True,
        conservative: bool = False,
    ):
        if window < 1 or not 1 <= minimum <= window:
            raise ValueError("invalid calibration window")
        if not all(0 <= v <= 1 for v in (fallback, cap, keep_rate)):
            raise ValueError("probabilities must be in [0, 1]")
        self.samples: deque[float] = deque(maxlen=window)
        self.minimum, self.fallback, self.cap = minimum, fallback, cap
        self.keep_rate, self.enabled, self.conservative = (
            keep_rate,
            enabled,
            conservative,
        )
        self.current, self.calibrated = fallback, False

    def observe(self, values: Iterable[float]) -> float:
        samples = list(values)
        if not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1
            for v in samples
        ):
            raise ValueError("invalid probability")
        self.samples.extend(samples)
        self.calibrated = self.enabled and len(self.samples) >= self.minimum
        self.current = self.fallback
        if self.calibrated:
            data = sorted(self.samples)
            q = self.keep_rate
            if self.conservative:
                q -= sqrt(log(1 / 0.05) / (2 * len(data)))
            if q < 0:
                self.current = 0.0
            else:
                position = (len(data) - 1) * q
                lo = int(position)
                hi = min(lo + 1, len(data) - 1)
                self.current = min(
                    self.cap, data[lo] + (data[hi] - data[lo]) * (position - lo)
                )
        return self.current

    def retained_indices(self, values: list[float]) -> set[int]:
        retained = {i for i, value in enumerate(values) if value >= self.current}
        floor = ceil(len(values) * self.keep_rate)
        ranked = sorted(range(len(values)), key=lambda i: (-values[i], i))
        return retained | set(ranked[:floor])
