"""Decides when a frame is worth sending to the model. Most frames are not."""

from __future__ import annotations

from dataclasses import dataclass

from ..perception import Signals


@dataclass(slots=True)
class TriggerPolicy:
    scene_change_threshold: float = 0.06
    min_interval_s: float = 3.0
    heartbeat_s: float = 20.0
    activity_floor: float = 0.004  # below this the screen is static (menu, pause, AFK)
    _last_call: float | None = None

    def should_analyze(self, signals: Signals, now: float) -> str | None:
        """Return the trigger reason, or None to skip this frame."""
        if self._last_call is not None and now - self._last_call < self.min_interval_s:
            return None
        if self._last_call is None and signals.activity >= self.activity_floor:
            return "first_activity"
        if signals.scene_change >= self.scene_change_threshold:
            return "scene_change"
        if (
            signals.activity >= self.activity_floor
            and self._last_call is not None
            and now - self._last_call >= self.heartbeat_s
        ):
            return "heartbeat"
        return None

    def mark_called(self, now: float) -> None:
        self._last_call = now
