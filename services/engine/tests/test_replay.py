from pathlib import Path

import pytest
from gamesense.capture import FrameRingBuffer, ReplaySource


def test_replay_samples_and_downscales(sample_clip: Path) -> None:
    buf = FrameRingBuffer(capacity=100)
    source = ReplaySource(
        sample_clip, buf, sample_fps=10, max_width=640, loop=False, realtime=False
    )
    source.start()
    assert source.finished.wait(timeout=20)
    source.stop()
    # 2 s clip at 30 fps sampled at 10 fps -> about 20 frames
    assert 18 <= len(buf) <= 22
    frame = buf.latest()
    assert frame is not None
    assert frame.width == 640 and frame.height == 360


def test_replay_runs_in_realtime(sample_clip: Path) -> None:
    buf = FrameRingBuffer(capacity=100)
    source = ReplaySource(sample_clip, buf, sample_fps=5, loop=True)
    source.start()
    try:
        assert source.running
        import time

        time.sleep(1.0)
        assert 3 <= len(buf) <= 8  # roughly 5 frames per second
    finally:
        source.stop()
    assert not source.running


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ReplaySource(tmp_path / "nope.mp4", FrameRingBuffer(capacity=1))
