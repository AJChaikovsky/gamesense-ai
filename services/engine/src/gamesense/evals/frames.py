"""Rebuild what the live coach would have seen at a case's decision moment."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2

from ..capture import Frame
from ..capture.replay import downscale
from ..coaching.loop import encode_jpeg
from ..perception import FastPath, Signals


@dataclass(frozen=True, slots=True)
class CaseFrames:
    jpegs: list[bytes]
    signals: Signals
    frame_times: list[float]


def extract(
    clip: Path,
    start_s: float,
    end_s: float,
    *,
    sample_fps: float = 4.0,
    frames_per_call: int = 2,
    max_width: int = 1280,
    model_frame_width: int = 1024,
    jpeg_quality: int = 80,
) -> CaseFrames:
    """Sample the clip from ``start_s`` to ``end_s`` like ``ReplaySource`` does.

    Every sampled frame goes through the fast path (so the signals match a live run),
    and the last ``frames_per_call`` frames are encoded exactly as the loop encodes them.
    """
    cap = cv2.VideoCapture(str(clip))
    if not cap.isOpened():
        raise FileNotFoundError(f"cannot open clip: {clip}")
    try:
        times: list[float] = []
        t = start_s
        step = 1.0 / sample_fps
        while t <= end_s + 1e-6:
            times.append(t)
            t += step
        fast = FastPath()
        frames: list[Frame] = []
        signals: Signals | None = None
        for i, ts in enumerate(times):
            cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000.0)
            ok, image = cap.read()
            if not ok:
                break
            frame = Frame(id=f"f{i}", index=i, timestamp=ts, image=downscale(image, max_width))
            signals = fast.update(frame)
            frames.append(frame)
        if signals is None:
            raise ValueError(f"no frames in {clip} between {start_s}s and {end_s}s")
        chosen = frames[-frames_per_call:]
        return CaseFrames(
            jpegs=[encode_jpeg(f, model_frame_width, jpeg_quality) for f in chosen],
            signals=signals,
            frame_times=[f.timestamp for f in chosen],
        )
    finally:
        cap.release()
