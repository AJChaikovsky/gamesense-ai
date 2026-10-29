"""Generate a synthetic gameplay-like clip so the pipeline runs without real footage.

uv run python -m gamesense.tools.make_sample_clip evals/clips/sample.mp4
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def make_clip(
    path: Path, seconds: float = 10.0, fps: int = 30, size: tuple[int, int] = (1280, 720)
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = size
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"cannot write video: {path}")
    total = int(seconds * fps)
    try:
        for i in range(total):
            frame = np.full((height, width, 3), (40, 32, 28), dtype=np.uint8)
            # Moving "enemy" square and a draining health bar give the frame-diff something to see.
            x = int((i / total) * (width - 120))
            cv2.rectangle(
                frame, (x, height // 2 - 60), (x + 120, height // 2 + 60), (60, 60, 220), -1
            )
            health = 1.0 - (i / total)
            cv2.rectangle(frame, (40, height - 60), (440, height - 30), (80, 80, 80), -1)
            cv2.rectangle(
                frame, (40, height - 60), (40 + int(400 * health), height - 30), (60, 200, 60), -1
            )
            cv2.putText(
                frame,
                f"HP {int(health * 100)}",
                (460, height - 36),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (230, 230, 230),
                2,
            )
            writer.write(frame)
    finally:
        writer.release()
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path, nargs="?", default=Path("evals/clips/sample.mp4"))
    parser.add_argument("--seconds", type=float, default=10.0)
    args = parser.parse_args()
    print(make_clip(args.out, seconds=args.seconds))


if __name__ == "__main__":
    main()
