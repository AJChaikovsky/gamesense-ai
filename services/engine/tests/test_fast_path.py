import numpy as np
from gamesense.capture import Frame
from gamesense.perception import FastPath


def _frame(i: int, value: int) -> Frame:
    return Frame(
        id=f"f{i}", index=i, timestamp=float(i), image=np.full((90, 160, 3), value, np.uint8)
    )


def test_static_scene_has_no_change() -> None:
    fp = FastPath()
    fp.update(_frame(0, 50))
    s = fp.update(_frame(1, 50))
    assert s.scene_change == 0.0
    assert s.activity == 0.0


def test_scene_change_detected_and_activity_smoothed() -> None:
    fp = FastPath(smoothing=0.5)
    fp.update(_frame(0, 0))
    s = fp.update(_frame(1, 255))
    assert s.scene_change > 0.9
    assert 0.4 < s.activity < 0.6
    s2 = fp.update(_frame(2, 255))
    assert s2.scene_change == 0.0 and s2.activity < s.activity
