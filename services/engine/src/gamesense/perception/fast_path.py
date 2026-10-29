"""Cheap, local per-frame signals. Runs on every sampled frame, in milliseconds."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ..capture import Frame

_THUMB = (160, 90)


@dataclass(frozen=True, slots=True)
class Signals:
    frame_id: str
    timestamp: float
    scene_change: float  # 0 (identical) .. 1 (completely different), vs previous frame
    activity: float  # smoothed recent change, used to tell "something is happening"


class FastPath:
    def __init__(self, smoothing: float = 0.3) -> None:
        self._prev: np.ndarray | None = None
        self._activity = 0.0
        self._smoothing = smoothing

    def update(self, frame: Frame) -> Signals:
        thumb = cv2.cvtColor(
            cv2.resize(frame.image, _THUMB, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
        )
        thumb = cv2.GaussianBlur(thumb, (3, 3), 0)
        change = 0.0 if self._prev is None else float(cv2.absdiff(thumb, self._prev).mean()) / 255.0
        self._prev = thumb
        self._activity = (1 - self._smoothing) * self._activity + self._smoothing * change
        return Signals(
            frame_id=frame.id,
            timestamp=frame.timestamp,
            scene_change=round(change, 4),
            activity=round(self._activity, 4),
        )

    def reset(self) -> None:
        self._prev = None
        self._activity = 0.0
