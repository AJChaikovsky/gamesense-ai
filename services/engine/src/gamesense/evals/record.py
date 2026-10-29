"""Record your own gameplay to an eval clip, marking interesting moments as you play.

Capture uses the same source as the live coach (Windows Graphics Capture), so clips
look exactly like what the model sees. Press Enter in the terminal to drop a mark;
marks are saved next to the clip and make labeling quicker.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from pathlib import Path

import cv2

from ..capture import FrameRingBuffer
from ..capture.base import CaptureSource

log = logging.getLogger(__name__)


def record(
    source: CaptureSource,
    buffer: FrameRingBuffer,
    out: Path,
    *,
    seconds: float,
    fps: float = 10.0,
    marks_from_stdin: bool = True,
    stop: threading.Event | None = None,
) -> tuple[Path, list[float]]:
    """Write the latest captured frame ``fps`` times a second until time runs out.

    The video's timeline matches wall-clock time (frames repeat if capture stalls),
    so a mark at 42.0 s lines up with 42.0 s in the clip.
    """
    stop = stop or threading.Event()
    marks: list[float] = []
    started = time.monotonic()

    def read_marks() -> None:
        for _line in sys.stdin:
            if stop.is_set():
                return
            marks.append(round(time.monotonic() - started, 2))
            print(f"  mark at {marks[-1]:.1f}s", file=sys.stderr, flush=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    source.start()
    writer: cv2.VideoWriter | None = None
    size: tuple[int, int] | None = None
    written = 0
    try:
        if marks_from_stdin:
            threading.Thread(target=read_marks, name="marks", daemon=True).start()
        interval = 1.0 / fps
        while not stop.is_set():
            frame = buffer.latest()
            if frame is None:
                if time.monotonic() - started > 10.0:
                    break  # nothing captured; reported below
                time.sleep(interval / 4)  # waiting for the first frame
                continue
            if writer is None:
                size = (frame.width, frame.height)
                writer = cv2.VideoWriter(str(out), cv2.VideoWriter.fourcc(*"mp4v"), fps, size)
                if not writer.isOpened():
                    raise RuntimeError(f"cannot write video: {out}")
                started = time.monotonic()  # the clip (and marks) start at the first frame
            if written * interval >= seconds:
                break
            if (frame.width, frame.height) != size:
                writer.write(cv2.resize(frame.image, size, interpolation=cv2.INTER_AREA))
            else:
                writer.write(frame.image)
            written += 1
            time.sleep(max(0.0, started + written * interval - time.monotonic()))
    finally:
        stop.set()
        source.stop()
        if writer is not None:
            writer.release()
    if writer is None:
        raise RuntimeError("no frames were captured; is the game window visible?")
    if marks:
        out.with_suffix(".marks.json").write_text(json.dumps({"marks_s": marks}) + "\n")
    log.info("recorded %d frames (%.1fs) to %s", written, written / fps, out)
    return out, marks
