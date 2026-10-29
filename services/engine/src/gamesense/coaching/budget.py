"""Tracks estimated model spend and enforces an hourly cap."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass(slots=True)
class SpendMeter:
    hourly_budget_usd: float
    total_usd: float = 0.0
    calls: int = 0
    _window: deque[tuple[float, float]] = field(default_factory=deque)

    def record(self, cost_usd: float, now: float) -> None:
        self.calls += 1
        self.total_usd += cost_usd
        self._window.append((now, cost_usd))
        self._trim(now)

    def last_hour(self, now: float) -> float:
        self._trim(now)
        return sum(c for _, c in self._window)

    def allows_call(self, now: float) -> bool:
        if self.hourly_budget_usd <= 0:
            return True  # 0 disables the cap
        return self.last_hour(now) < self.hourly_budget_usd

    def _trim(self, now: float) -> None:
        while self._window and now - self._window[0][0] > 3600:
            self._window.popleft()
