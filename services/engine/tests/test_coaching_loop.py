from __future__ import annotations

import asyncio
import json
from typing import Any

import numpy as np
import pytest
from gamesense.capture import Frame, FrameRingBuffer
from gamesense.coaching import CoachingConfig, CoachingLoop
from gamesense.coaching.trigger import TriggerPolicy
from gamesense.games import game_by_id
from gamesense.providers import AnalysisRequest, AnalysisResult, ProviderError, Usage
from gamesense.providers.mock import MockProvider
from gamesense_contracts import StatusEvent, TipEvent
from gamesense_contracts.events import ControlMessage, FeedbackMessage


class Clock:
    def __init__(self) -> None:
        self.buffer = FrameRingBuffer(capacity=20)
        self.i = 0

    def push(self, value: int) -> None:
        img = np.full((90, 160, 3), value, np.uint8)
        self.buffer.append(Frame(id=f"f{self.i}", index=self.i, timestamp=float(self.i), image=img))
        self.i += 1


def _loop(
    provider: Any, game: str = "minecraft", **cfg: Any
) -> tuple[CoachingLoop, list[Any], Clock]:
    clock = Clock()
    events: list[Any] = []
    config = CoachingConfig(
        trigger=TriggerPolicy(scene_change_threshold=0.05, min_interval_s=3, heartbeat_s=20),
        **cfg,
    )
    loop = CoachingLoop(
        clock.buffer,
        provider,
        events.append,
        config=config,
        fixed_game=game_by_id(game),
        detect_foreground=lambda: None,
    )
    return loop, events, clock


async def _settle(loop: CoachingLoop, now: float) -> None:
    """Let the in-flight request finish, then run the tick that collects it."""
    await asyncio.sleep(0.01)
    await loop.tick(now)


async def _drive(loop: CoachingLoop, clock: Clock, values: list[int], start: float = 0.0) -> float:
    now = start
    for v in values:
        clock.push(v)
        await loop.tick(now)
        await _settle(loop, now + 0.1)
        now += 1.0
    return now


async def test_busy_scene_produces_a_tip() -> None:
    loop, events, clock = _loop(MockProvider(latency_s=0))
    await _drive(loop, clock, [0, 200, 0, 200])
    tips = [e for e in events if isinstance(e, TipEvent)]
    assert len(tips) == 1
    assert tips[0].decision.message
    status = loop.status()
    assert status.calls >= 1 and status.tips_delivered == 1 and status.spend_usd == 0.0


async def test_blocked_game_never_calls_model() -> None:
    loop, events, clock = _loop(MockProvider(latency_s=0), game="valorant")
    await _drive(loop, clock, [0, 200, 0, 200, 0, 200])
    assert loop.status().calls == 0 and not events
    assert loop.status().live_allowed is False


async def test_pause_and_feedback() -> None:
    loop, _events, clock = _loop(MockProvider(latency_s=0))
    loop.handle_client_message(ControlMessage(action="pause"))
    await _drive(loop, clock, [0, 200, 0, 200])
    assert loop.status().calls == 0
    loop.handle_client_message(ControlMessage(action="resume"))
    loop.handle_client_message(FeedbackMessage(tip_id="t", rating="useful"))
    assert not loop.paused and loop.feedback[0].rating == "useful"


class FailingProvider:
    name = "fail"
    model = "fail-1"

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        raise ProviderError("boom")

    async def aclose(self) -> None:
        return None


async def test_provider_error_degrades_and_backs_off() -> None:
    loop, events, clock = _loop(FailingProvider(), error_backoff_s=100)
    await _drive(loop, clock, [0, 200, 0, 200, 0, 200, 0, 200])
    statuses = [e for e in events if isinstance(e, StatusEvent)]
    assert len(statuses) == 1 and statuses[0].level == "degraded"


async def test_stale_tip_is_dropped() -> None:
    loop, events, clock = _loop(MockProvider(latency_s=0))
    clock.push(0)
    await loop.tick(0)
    clock.push(200)
    await loop.tick(1)  # starts a request
    await asyncio.sleep(0.01)
    await loop.tick(30)  # collected 29 s later: mock tips expire after 8 s
    assert not [e for e in events if isinstance(e, TipEvent)]
    assert loop.suppressed.get("expired") == 1


async def test_budget_cap_blocks_calls() -> None:
    class Pricey(MockProvider):
        async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
            r = await super().analyze(request)
            return AnalysisResult(r.analysis, Usage(1, 1), r.latency_ms, cost_usd=1.0)

    loop, _, clock = _loop(Pricey(latency_s=0), hourly_budget_usd=0.5)
    await _drive(loop, clock, [0, 200, 0, 200, 0, 200, 0, 200, 0, 200])
    assert loop.status().calls == 1
    assert loop.suppressed.get("budget", 0) >= 1


@pytest.mark.parametrize("value", [0])
async def test_static_screen_is_silent(value: int) -> None:
    loop, events, clock = _loop(MockProvider(latency_s=0))
    await _drive(loop, clock, [value] * 30)
    assert loop.status().calls == 0 and not events


async def test_ratings_are_saved_with_tip_text(tmp_path: Any) -> None:
    from gamesense.coaching.feedback import FeedbackLog

    log_path = tmp_path / "feedback.jsonl"
    loop, events, clock = _loop(MockProvider(latency_s=0))
    loop.feedback_log = FeedbackLog(log_path)
    await _drive(loop, clock, [0, 200, 0, 200])
    tip = next(e for e in events if isinstance(e, TipEvent)).decision
    loop.handle_client_message(FeedbackMessage(tip_id=tip.id, rating="useful"))
    loop.handle_client_message(FeedbackMessage(tip_id="tip_unknown", rating="not_useful"))
    rows = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["rating"] == "useful" and rows[0]["message"] == tip.message
    assert rows[0]["game_id"] == "minecraft" and rows[0]["provider"] == "mock"
    assert "image" not in json.dumps(rows[0])
