"""M3 coaching engine: stale-result validator, next_lull delivery and fallback mode."""

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import pytest
from gamesense.capture import Frame, FrameRingBuffer
from gamesense.coaching import CoachingConfig, CoachingLoop
from gamesense.coaching.trigger import TriggerPolicy
from gamesense.coaching.validator import first_failed, holds
from gamesense.games import game_by_id
from gamesense.providers import (
    AnalysisRequest,
    AnalysisResult,
    LiveAnalysis,
    ProviderError,
    Usage,
)
from gamesense.providers.schema import LiveCondition, LiveObservation, LiveTip
from gamesense_contracts import CoachingDecision, Condition, StatusEvent, TipEvent


def C(t: str, op: str, value: Any = None) -> Condition:
    return Condition(observation_type=t, op=op, value=value)  # type: ignore[arg-type]


# -- validator ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("cond", "facts", "ok"),
    [
        (C("health", "le", 25), {"health": 18}, True),
        (C("health", "le", 25), {"health": 80}, False),
        (C("health", "lt", "30%"), {"health": "18%"}, True),
        (C("money", "ge", 650), {"money": "$2,300"}, True),
        (C("health_low", "eq", "true"), {"health_low": "True"}, True),
        (C("health_low", "eq", True), {"health_low": "false"}, False),
        (C("time_of_day", "eq", "night"), {"time_of_day": "Night"}, True),
        (C("time_of_day", "ne", "night"), {"time_of_day": "night"}, False),
        (C("zombies", "gt", 1), {"zombies": "2 zombies"}, True),
        (C("enemy_visible", "present"), {"enemy_visible": "true"}, True),
        (C("enemy_visible", "present"), {}, False),
        (C("enemy_visible", "absent"), {}, True),
        (C("enemy_visible", "absent"), {"enemy_visible": "yes"}, False),
        (C("health", "le", 25), {}, True),  # unknown: can't prove stale
        (C("biome", "lt", 3), {"biome": "desert"}, True),  # not numeric: can't compare
    ],
)
def test_condition_checks(cond: Condition, facts: dict[str, Any], ok: bool) -> None:
    assert holds(cond, facts) is ok


def test_first_failed_names_the_broken_condition() -> None:
    conds = [C("alive", "eq", True), C("health", "le", 25)]
    assert first_failed(conds, {"alive": True, "health": 10}) is None
    failed = first_failed(conds, {"alive": True, "health": 90})
    assert failed is not None and failed.observation_type == "health"


# -- test doubles -------------------------------------------------------------------
class FakeFeed:
    source = "fake"

    def __init__(self) -> None:
        self.combat: bool | None = None
        self.obs: dict[str, Any] = {}
        self.live = True

    def connected(self) -> bool:
        return self.live

    def facts(self) -> list[str]:
        return []

    def observations(self) -> dict[str, Any]:
        return self.obs

    def in_combat(self) -> bool | None:
        return self.combat

    def close(self) -> None:
        return None


def _tip(**kw: Any) -> LiveTip:
    base: dict[str, Any] = {
        "category": "positioning",
        "action": "use_cover",
        "message": "Fight from cover",
        "detail": None,
        "priority": "info",
        "confidence": 0.9,
        "expires_in_seconds": 10,
        "valid_while": [],
        "evidence": [],
    }
    return LiveTip(**(base | kw))


class Scripted:
    """Returns queued analyses (or raises queued errors) in order."""

    name = "scripted"
    model = "scripted-1"

    def __init__(self, *items: LiveAnalysis | Exception, cost: float = 0.0) -> None:
        self.items = list(items)
        self.cost = cost
        self.calls = 0

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        self.calls += 1
        item = self.items.pop(0) if self.items else LiveAnalysis(
            activity="idle", observations=[], unknowns=[], tip=None
        )  # fmt: skip
        if isinstance(item, Exception):
            raise item
        return AnalysisResult(item, Usage(10, 10), latency_ms=5, cost_usd=self.cost)

    async def aclose(self) -> None:
        return None


def _analysis(tip: LiveTip | None, activity: str = "exploration", **obs: str) -> LiveAnalysis:
    return LiveAnalysis(
        activity=activity,
        observations=[
            LiveObservation(type=k, value=v, confidence=0.9, kind="observed")
            for k, v in obs.items()
        ],
        unknowns=[],
        tip=tip,
    )


class Rig:
    def __init__(self, provider: Any, **cfg: Any) -> None:
        self.buffer = FrameRingBuffer(capacity=8)
        self.events: list[Any] = []
        self.i = 0
        self.loop = CoachingLoop(
            self.buffer,
            provider,
            self.events.append,
            config=CoachingConfig(
                trigger=TriggerPolicy(scene_change_threshold=0.05, min_interval_s=1, heartbeat_s=2),
                **cfg,
            ),
            fixed_game=game_by_id("minecraft"),
            detect_foreground=lambda: None,
        )

    async def step(self, now: float, value: int | None = None) -> None:
        """Push a frame (alternating bright/dark by default) and run a tick + collect."""
        v = (200 if self.i % 2 else 0) if value is None else value
        img = np.full((90, 160, 3), v, np.uint8)
        self.buffer.append(Frame(id=f"f{self.i}", index=self.i, timestamp=now, image=img))
        self.i += 1
        await self.loop.tick(now)
        await asyncio.sleep(0.005)
        await self.loop.tick(now + 0.05)

    def tips(self) -> list[str]:
        return [e.decision.action for e in self.events if isinstance(e, TipEvent)]

    def statuses(self) -> list[StatusEvent]:
        return [e for e in self.events if isinstance(e, StatusEvent)]


def _local(action: str = "rule_tip", **kw: Any) -> CoachingDecision:
    base: dict[str, Any] = {
        "id": f"rule_{action}",
        "category": "economy",
        "action": action,
        "message": f"Do {action}",
        "priority": "info",
        "confidence": 0.95,
        "delivery": "immediate",
        "expires_in_seconds": 8,
    }
    return CoachingDecision(**(base | kw))


# -- next_lull delivery -------------------------------------------------------------
async def test_info_tip_waits_for_a_lull_then_shows() -> None:
    rig = Rig(Scripted(_analysis(_tip())))
    feed = FakeFeed()
    feed.combat = True
    rig.loop.telemetry = feed
    await rig.step(0.0, 0)
    await rig.step(1.0, 200)  # model call -> info tip, but we're mid-fight
    assert rig.tips() == [] and rig.loop.status().held_tips == 1
    await rig.loop.tick(5.0)
    assert rig.tips() == []
    feed.combat = False  # round over / fight ended
    await rig.loop.tick(6.0)
    assert rig.tips() == ["use_cover"] and rig.loop.status().held_tips == 0


async def test_important_tip_is_not_held() -> None:
    rig = Rig(Scripted(_analysis(_tip(priority="important"))))
    feed = FakeFeed()
    feed.combat = True
    rig.loop.telemetry = feed
    await rig.step(0.0, 0)
    await rig.step(1.0, 200)
    assert rig.tips() == ["use_cover"]


async def test_model_combat_reading_counts_as_combat_without_telemetry() -> None:
    rig = Rig(Scripted(_analysis(_tip(), activity="boss_fight")), combat_memory_s=10)
    await rig.step(0.0, 0)
    await rig.step(1.0, 200)
    assert rig.tips() == [] and rig.loop.in_combat(2.0)
    await rig.loop.tick(12.0)  # combat reading is now 11 s old
    assert rig.tips() == ["use_cover"]


async def test_held_tip_expires_if_the_fight_never_ends() -> None:
    rig = Rig(Scripted(_analysis(_tip())), hold_max_s=20)
    feed = FakeFeed()
    feed.combat = True
    rig.loop.telemetry = feed
    await rig.step(0.0, 0)
    await rig.step(1.0, 200)
    await rig.loop.tick(25.0)
    feed.combat = False
    await rig.loop.tick(26.0)
    assert rig.tips() == [] and rig.loop.suppressed["expired"] == 1


async def test_held_tip_is_revalidated_before_it_shows() -> None:
    tip = _tip(valid_while=[LiveCondition(observation_type="health", op="le", value="25")])
    rig = Rig(Scripted(_analysis(tip)))
    feed = FakeFeed()
    feed.combat, feed.obs = True, {"health": 20}
    rig.loop.telemetry = feed
    await rig.step(0.0, 0)
    await rig.step(1.0, 200)
    assert rig.loop.status().held_tips == 1
    feed.combat, feed.obs = False, {"health": 100}  # healed during the fight
    await rig.loop.tick(3.0)
    assert rig.tips() == [] and rig.loop.suppressed["stale"] == 1


def test_local_rules_choose_their_own_timing() -> None:
    rig = Rig(Scripted())
    feed = FakeFeed()
    feed.combat = True
    rig.loop.telemetry = feed
    assert rig.loop.submit_local(_local("now"), 0.0)  # info, immediate: shows now
    assert rig.loop.submit_local(_local("later", delivery="next_lull"), 10.0)
    assert rig.tips() == ["now"] and rig.loop.status().held_tips == 1
    assert not rig.loop.submit_local(_local("later", delivery="next_lull"), 10.5)  # dup


async def test_hold_queue_keeps_the_most_important_tips() -> None:
    rig = Rig(Scripted(), max_held=2)
    feed = FakeFeed()
    feed.combat = True
    rig.loop.telemetry = feed
    for name, prio in [("a", "info"), ("b", "important"), ("c", "info")]:
        rig.loop.submit_local(_local(name, priority=prio, delivery="next_lull"), 0.0)
    assert [h.decision.action for h in rig.loop._held] == ["b", "a"]
    feed.combat = False
    await rig.loop.tick(1.0)
    await rig.loop.tick(20.0)  # cooldown passed
    assert rig.tips() == ["b", "a"]


# -- stale-result validator on arrival ----------------------------------------------
async def test_model_tip_contradicted_by_telemetry_is_dropped() -> None:
    tip = _tip(
        priority="urgent",
        valid_while=[LiveCondition(observation_type="health", op="le", value="25")],
    )
    rig = Rig(Scripted(_analysis(tip, health="20")))
    feed = FakeFeed()
    feed.obs = {"health": 95}  # the game says otherwise
    rig.loop.telemetry = feed
    await rig.step(0.0, 0)
    await rig.step(1.0, 200)
    assert rig.tips() == [] and rig.loop.suppressed["stale"] == 1


def test_stale_local_tip_is_refused() -> None:
    rig = Rig(Scripted())
    feed = FakeFeed()
    feed.obs = {"armor": 100}
    rig.loop.telemetry = feed
    assert not rig.loop.submit_local(_local(valid_while=[C("armor", "lt", 30)]), 0.0)


# -- fallback mode ------------------------------------------------------------------
async def test_provider_outage_backs_off_exponentially_and_recovers() -> None:
    errors = [ProviderError("503 overloaded") for _ in range(3)]
    provider = Scripted(*errors, _analysis(_tip(priority="important")))
    rig = Rig(provider, error_backoff_s=10, max_backoff_s=25)
    feed = FakeFeed()
    rig.loop.telemetry = feed
    await rig.step(0.0, 0)
    await rig.step(1.0)  # error 1 -> retry after 10 s
    assert rig.loop._backoff_until == pytest.approx(11.05)
    assert rig.loop.status().fallback_reason == "provider_error"
    # Local rules keep coaching while the model is down.
    assert rig.loop.submit_local(_local("from_game_data", priority="important"), 2.0)
    await rig.step(12.0)  # error 2 -> 20 s
    assert rig.loop._backoff_until == pytest.approx(32.05)
    await rig.step(33.0)  # error 3 -> capped at 25 s
    assert rig.loop._backoff_until == pytest.approx(58.05)
    await rig.step(59.0)  # success
    assert rig.loop.status().fallback_reason is None
    statuses = rig.statuses()
    assert [s.level for s in statuses] == ["degraded", "ok"]
    assert "live game data keep working" in statuses[0].message
    assert rig.tips() == ["from_game_data", "use_cover"]


async def test_budget_exhaustion_enters_and_leaves_fallback() -> None:
    provider = Scripted(_analysis(None), cost=1.0)
    rig = Rig(provider, hourly_budget_usd=0.5)
    await rig.step(0.0, 0)
    await rig.step(1.0)  # one call spends $1, over the cap
    await rig.step(3.0)
    await rig.step(5.0)
    assert provider.calls == 1 and rig.loop.status().fallback_reason == "budget"
    assert rig.loop.submit_local(_local("still_coaching", priority="important"), 6.0)
    await rig.loop.tick(1.0 + 3601)  # spend ages out of the rolling hour
    assert rig.loop.status().fallback_reason is None
    assert [s.level for s in rig.statuses()] == ["degraded", "ok"]
    assert "budget" in rig.statuses()[0].message.lower()
