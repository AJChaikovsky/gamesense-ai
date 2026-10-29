"""Stops the coach repeating itself or talking too often."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


def _norm(text: str) -> str:
    return " ".join("".join(c for c in text.lower() if c.isalnum() or c.isspace()).split())


@dataclass(slots=True)
class Cooldown:
    min_gap_s: float = 8.0  # between any two tips
    repeat_window_s: float = 90.0  # before the same action/message may repeat
    urgent_gap_s: float = 3.0  # urgent tips may follow sooner
    _history: deque[tuple[float, str, str]] = field(default_factory=lambda: deque(maxlen=50))

    def allows(self, action: str, message: str, priority: str, now: float) -> str | None:
        """Return None if allowed, else the reason it was suppressed."""
        if self._history:
            last_time = self._history[-1][0]
            gap = self.urgent_gap_s if priority == "urgent" else self.min_gap_s
            if now - last_time < gap:
                return "too_soon"
        key = _norm(message)
        for when, past_action, past_message in self._history:
            if now - when < self.repeat_window_s and (past_action == action or past_message == key):
                return "repeat"
        return None

    def record(self, action: str, message: str, now: float) -> None:
        self._history.append((now, action, _norm(message)))

    def recent_messages(self, now: float, window_s: float = 120.0) -> list[str]:
        return [m for t, _, m in self._history if now - t < window_s]

    def last_tip_time(self) -> float | None:
        return self._history[-1][0] if self._history else None
