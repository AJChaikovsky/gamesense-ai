from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

from .base import Frame
from .ring_buffer import FrameRingBuffer

log = logging.getLogger(__name__)


def downscale(image: np.ndarray, max_width: int) -> np.ndarray:
    height, width = image.shape[:2]
    if width <= max_width:
        return image
    scale = max_width / width
    return cv2.resize(image, (max_width, round(height * scale)), interpolation=cv2.INTER_AREA)


class ReplaySource:
    """Plays a recorded gameplay video into the ring buffer at real-time speed.

    Lets the whole engine run on macOS (or in CI and the eval harness) without a
    live game. ``sample_fps`` caps how many frames per second enter the buffer;
    frames in between are skipped, mirroring how live capture is sampled.
    """

    kind: Literal["replay"] = "replay"

    def __init__(
        self,
        path: str | Path,
        buffer: FrameRingBuffer,
        *,
        sample_fps: float = 4.0,
        max_width: int = 1280,
        loop: bool = True,
        realtime: bool = True,
    ) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        self.target = str(self.path)
        self._buffer = buffer
        self._sample_fps = sample_fps
        self._max_width = max_width
        self._loop = loop
        self._realtime = realtime
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._index = 0
        self.finished = threading.Event()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self.finished.clear()
        self._thread = threading.Thread(target=self._run, name="replay-capture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                self._play_once()
                if not self._loop:
                    break
        except Exception:
            log.exception("replay capture failed")
        finally:
            self.finished.set()

    def _play_once(self) -> None:
        cap = cv2.VideoCapture(str(self.path))
        if not cap.isOpened():
            raise RuntimeError(f"cannot open video: {self.path}")
        try:
            video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            step = max(1, round(video_fps / self._sample_fps)) if self._sample_fps > 0 else 1
            frame_interval = step / video_fps
            started = time.monotonic()
            source_index = 0
            emitted = 0
            while not self._stop.is_set():
                ok = cap.grab()
                if not ok:
                    return
                if source_index % step == 0:
                    ok, image = cap.retrieve()
                    if not ok:
                        return
                    if self._realtime:
                        due = started + emitted * frame_interval
                        delay = due - time.monotonic()
                        if delay > 0 and self._stop.wait(delay):
                            return
                    self._buffer.append(
                        Frame(
                            id=f"f{self._index}",
                            index=self._index,
                            timestamp=time.monotonic(),
                            image=downscale(image, self._max_width),
                        )
                    )
                    self._index += 1
                    emitted += 1
                source_index += 1
        finally:
            cap.release()
