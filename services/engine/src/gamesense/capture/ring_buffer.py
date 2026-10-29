from __future__ import annotations

import threading
import time
from collections import deque

from .base import Frame


class FrameRingBuffer:
    """Thread-safe, fixed-capacity buffer of the most recent frames.

    The capture thread appends; the asyncio side reads snapshots. Old frames fall
    off the end, so memory use is bounded by ``capacity``.
    """

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._frames: deque[Frame] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._arrivals: deque[float] = deque(maxlen=120)

    @property
    def capacity(self) -> int:
        return self._frames.maxlen or 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._frames)

    def append(self, frame: Frame) -> None:
        with self._lock:
            self._frames.append(frame)
            self._arrivals.append(frame.timestamp)

    def latest(self) -> Frame | None:
        with self._lock:
            return self._frames[-1] if self._frames else None

    def last(self, n: int) -> list[Frame]:
        """Return up to ``n`` most recent frames, oldest first."""
        with self._lock:
            if n <= 0:
                return []
            return list(self._frames)[-n:]

    def get(self, frame_id: str) -> Frame | None:
        with self._lock:
            return next((f for f in reversed(self._frames) if f.id == frame_id), None)

    def fps(self, window_seconds: float = 2.0) -> float:
        """Measured arrival rate over the recent window."""
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self._arrivals if now - t <= window_seconds]
        if len(recent) < 2:
            return 0.0
        span = recent[-1] - recent[0]
        return (len(recent) - 1) / span if span > 0 else 0.0

    def clear(self) -> None:
        with self._lock:
            self._frames.clear()
            self._arrivals.clear()
