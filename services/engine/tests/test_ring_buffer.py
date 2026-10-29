import time

import numpy as np
import pytest
from gamesense.capture import Frame, FrameRingBuffer


def _frame(i: int) -> Frame:
    return Frame(
        id=f"f{i}", index=i, timestamp=time.monotonic(), image=np.zeros((2, 2, 3), np.uint8)
    )


def test_capacity_is_bounded() -> None:
    buf = FrameRingBuffer(capacity=3)
    for i in range(5):
        buf.append(_frame(i))
    assert len(buf) == 3
    assert [f.index for f in buf.last(10)] == [2, 3, 4]
    assert buf.latest() is not None and buf.latest().index == 4  # type: ignore[union-attr]


def test_get_by_id_and_eviction() -> None:
    buf = FrameRingBuffer(capacity=2)
    for i in range(3):
        buf.append(_frame(i))
    assert buf.get("f0") is None
    assert buf.get("f2") is not None


def test_last_handles_edge_cases() -> None:
    buf = FrameRingBuffer(capacity=2)
    assert buf.latest() is None
    assert buf.last(0) == []


def test_invalid_capacity() -> None:
    with pytest.raises(ValueError):
        FrameRingBuffer(capacity=0)
