from gamesense.coaching.budget import SpendMeter
from gamesense.coaching.cooldown import Cooldown
from gamesense.coaching.trigger import TriggerPolicy
from gamesense.perception import Signals


def _sig(change: float, activity: float) -> Signals:
    return Signals(frame_id="f", timestamp=0.0, scene_change=change, activity=activity)


def test_trigger_reasons_and_min_interval() -> None:
    t = TriggerPolicy(scene_change_threshold=0.1, min_interval_s=3, heartbeat_s=20)
    assert t.should_analyze(_sig(0.0, 0.0), now=0) is None  # static screen
    assert t.should_analyze(_sig(0.01, 0.01), now=0) == "first_activity"
    t.mark_called(0)
    assert t.should_analyze(_sig(0.5, 0.2), now=1) is None  # too soon
    assert t.should_analyze(_sig(0.5, 0.2), now=4) == "scene_change"
    t.mark_called(4)
    assert t.should_analyze(_sig(0.01, 0.01), now=10) is None
    assert t.should_analyze(_sig(0.01, 0.01), now=25) == "heartbeat"
    assert t.should_analyze(_sig(0.0, 0.0), now=25) is None  # static: no heartbeat


def test_cooldown_gap_repeat_and_urgent() -> None:
    c = Cooldown(min_gap_s=8, repeat_window_s=60, urgent_gap_s=3)
    assert c.allows("heal", "Heal now", "important", now=0) is None
    c.record("heal", "Heal now", now=0)
    assert c.allows("cover", "Move to cover", "important", now=5) == "too_soon"
    assert c.allows("cover", "Move to cover", "urgent", now=5) is None
    assert c.allows("heal", "Different words", "info", now=20) == "repeat"
    assert c.allows("x", "heal  NOW!", "info", now=20) == "repeat"
    assert c.allows("heal", "Heal now", "info", now=70) is None
    assert c.recent_messages(now=10) == ["heal now"]


def test_spend_meter_hourly_cap() -> None:
    m = SpendMeter(hourly_budget_usd=0.01)
    assert m.allows_call(0)
    m.record(0.006, now=0)
    m.record(0.006, now=10)
    assert not m.allows_call(20)
    assert m.allows_call(3700)  # first charges aged out
    assert m.calls == 2 and round(m.total_usd, 3) == 0.012
    assert SpendMeter(hourly_budget_usd=0).allows_call(0)
