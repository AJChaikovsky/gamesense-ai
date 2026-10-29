"""A free, offline provider for development, replay demos and tests.

It never looks at pixels. It turns the fast-path hints into plausible output so the
whole pipeline (triggers, validation, cooldowns, overlay) can be exercised without
an API key or any spend.
"""

from __future__ import annotations

import asyncio
import itertools
import time

from .base import AnalysisRequest, AnalysisResult, Usage
from .schema import LiveAnalysis, LiveCondition, LiveObservation, LiveTip

_TIPS: dict[str, list[tuple[str, str, str, str]]] = {
    # (category, action, message, detail)
    "cs2": [
        ("economy", "save_round", "Consider saving this round", "Team money looks low."),
        (
            "positioning",
            "hold_angle",
            "Hold the angle, don't peek",
            "You're trading at a disadvantage.",
        ),
        ("utility", "use_flash", "Flash before you swing", "They likely have the angle held."),
    ],
    "fromsoft_rpg": [
        (
            "survivability",
            "heal_now",
            "Back off and heal",
            "Health is low and the boss is recovering.",
        ),
        (
            "stamina",
            "stop_rolling",
            "Stop rolling, let stamina recover",
            "Stamina bar is nearly empty.",
        ),
        (
            "patterns",
            "punish_recovery",
            "Punish after the slam",
            "That attack has a long recovery.",
        ),
    ],
    "minecraft": [
        ("survival", "eat_food", "Eat before you explore further", "Hunger is dropping."),
        ("night_safety", "find_shelter", "Find shelter before nightfall", "The sun is setting."),
        ("inventory", "craft_shield", "Craft a shield soon", "You're fighting mobs without one."),
    ],
}
_GENERIC = [
    ("survivability", "heal_before_engaging", "Heal before the next fight", "Health looks low."),
    ("positioning", "use_cover", "Move to cover", "You're exposed in the open."),
]


class MockProvider:
    name = "mock"

    def __init__(self, model: str = "mock-coach", latency_s: float = 0.4) -> None:
        self.model = model
        self._latency_s = latency_s
        self._cycle: dict[str, itertools.cycle[tuple[str, str, str, str]]] = {}

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        started = time.monotonic()
        await asyncio.sleep(self._latency_s)
        activity_level = request.hints.get("activity", 0.0)
        busy = activity_level >= 0.01 or request.hints.get("scene_change", 0.0) >= 0.05
        observations = [
            LiveObservation(
                type="scene_activity",
                value=f"{activity_level:.3f}",
                confidence=0.9,
                kind="observed",
            )
        ]
        tip: LiveTip | None = None
        if busy:
            cycle = self._cycle.setdefault(
                request.game_id, itertools.cycle(_TIPS.get(request.game_id, _GENERIC))
            )
            category, action, message, detail = next(cycle)
            tip = LiveTip(
                category=category,
                action=action,
                message=message,
                detail=f"{detail} (mock tip)",
                priority="important",
                confidence=0.8,
                expires_in_seconds=8,
                valid_while=[
                    LiveCondition(observation_type="scene_activity", op="present", value=None)
                ],
                evidence=["scene_activity"],
            )
        analysis = LiveAnalysis(
            activity="action" if busy else "idle",
            observations=observations,
            unknowns=["mock provider does not read pixels"],
            tip=tip,
        )
        return AnalysisResult(
            analysis=analysis,
            usage=Usage(input_tokens=0, output_tokens=0),
            latency_ms=int((time.monotonic() - started) * 1000),
            cost_usd=0.0,
        )

    async def aclose(self) -> None:
        return None
