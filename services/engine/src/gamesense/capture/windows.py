"""Live Windows capture of a single game window.

Primary backend: Windows Graphics Capture via ``windows-capture`` (works with
borderless and windowed games). Fallback: DXGI Desktop Duplication of the primary
monitor from the same library, for systems where WGC fails.

Frames can arrive far faster than we need, so we ask WGC for at most one update
per sampling interval and drop any extras, downscale, and push into the shared ring
buffer. Work happens on the capture library's thread; nothing blocks the game.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from typing import Any, Literal

import numpy as np

from .base import Frame
from .replay import downscale
from .ring_buffer import FrameRingBuffer

log = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform == "win32"


class WindowsCaptureSource:
    kind: Literal["windows"] = "windows"

    def __init__(
        self,
        window_name: str | None,
        buffer: FrameRingBuffer,
        *,
        window_hwnd: int | None = None,
        sample_fps: float = 4.0,
        max_width: int = 1280,
        backend: Literal["auto", "wgc", "dxgi"] = "auto",
    ) -> None:
        if not _IS_WINDOWS:
            raise RuntimeError("Windows capture is only available on Windows")
        self.target = window_name or (
            f"window {window_hwnd}" if window_hwnd else "foreground window"
        )
        self._window_name = window_name
        self._window_hwnd = window_hwnd
        self._buffer = buffer
        self._interval = 1.0 / sample_fps if sample_fps > 0 else 0.0
        self._max_width = max_width
        self._backend = backend
        self._index = 0
        self._last_emit = 0.0
        self._lock = threading.Lock()
        self._control: Any = None
        self._dxgi_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._stop.clear()
        if self._backend in ("auto", "wgc"):
            try:
                self._start_wgc()
                self._running = True
                return
            except Exception:
                if self._backend == "wgc":
                    raise
                log.exception("Windows Graphics Capture failed; falling back to DXGI duplication")
        self._start_dxgi()
        self._running = True

    def stop(self) -> None:
        self._stop.set()
        if self._control is not None:
            try:
                self._control.stop()
            except Exception:
                log.debug("capture control stop failed", exc_info=True)
            self._control = None
        if self._dxgi_thread is not None:
            self._dxgi_thread.join(timeout=5)
            self._dxgi_thread = None
        self._running = False

    def _due(self) -> bool:
        return bool(time.monotonic() - self._last_emit >= self._interval)

    def _emit(self, image_bgr: np.ndarray) -> None:
        with self._lock:
            now = time.monotonic()
            if now - self._last_emit < self._interval:
                return
            self._last_emit = now
            index = self._index
            self._index += 1
        # The capture buffer is only valid during the callback, so always copy.
        image = np.array(downscale(image_bgr, self._max_width), dtype=np.uint8, copy=True)
        self._buffer.append(Frame(id=f"f{index}", index=index, timestamp=now, image=image))

    def _resolve_target(self) -> None:
        if self._window_name or self._window_hwnd:
            return
        from ..games.foreground import foreground_window

        info = foreground_window()
        if info is not None and info.hwnd:
            self._window_hwnd = info.hwnd
            self.target = info.title or f"window {info.hwnd}"

    # -- Windows Graphics Capture -------------------------------------------------
    def _start_wgc(self) -> None:
        from windows_capture import WindowsCapture

        self._resolve_target()
        interval_ms = int(self._interval * 1000) or None
        capture = WindowsCapture(
            cursor_capture=False,
            draw_border=False,
            minimum_update_interval=interval_ms,
            window_name=self._window_name,
            window_hwnd=self._window_hwnd,
        )

        def on_frame_arrived(frame: Any, capture_control: Any) -> None:
            if self._stop.is_set():
                capture_control.stop()
                return
            if self._due():
                self._emit(frame.frame_buffer[:, :, :3])  # BGRA -> BGR view

        def on_closed() -> None:
            log.info("capture target closed: %s", self.target)
            self._running = False

        capture.frame_handler = on_frame_arrived
        capture.closed_handler = on_closed
        self._control = capture.start_free_threaded()
        log.info("WGC capture started: %s", self.target)

    # -- DXGI duplication fallback ------------------------------------------------
    def _start_dxgi(self) -> None:
        from windows_capture import DxgiDuplicationSession

        session = DxgiDuplicationSession()

        def run() -> None:
            while not self._stop.is_set():
                try:
                    frame = session.acquire_frame(timeout_ms=100)
                except RuntimeError:
                    session.recreate()
                    continue
                if frame is not None and self._due():
                    self._emit(frame.to_bgr())
                self._stop.wait(max(0.0, self._interval - 0.1))

        self._dxgi_thread = threading.Thread(target=run, name="dxgi-capture", daemon=True)
        self._dxgi_thread.start()
        self.target = "primary monitor (DXGI)"
        log.info("DXGI duplication capture started")
