"""Deterministic CS2 tips computed from Game State Integration data.

These need no model call, so they cost nothing and arrive within about a second
of the game reporting the situation. Each tip is delivered at most once per round
(a tip the cooldown holds back is offered again on the next update), and
only for the local player (never for a spectated teammate). Rules only advise;
they never act for the player.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from gamesense_contracts import CoachingDecision, Condition

from .state import Cs2State

Priority = Literal["info", "important", "urgent"]

ARMOR_COST = 650
KIT_COST = 400
LOW_HP = 25
# Seconds left in freeze time when "did you forget to buy X" checks run, so the
# player gets a chance to buy on their own first.
FREEZE_END_S = 6.0
UNSPENT_MONEY = 4500


@dataclass(frozen=True, slots=True)
class RuleTip:
    """A rule's proposal; ``key`` limits it to once per round."""

    decision: CoachingDecision
    key: tuple[int, str]


def _tip(
    action: str,
    category: str,
    message: str,
    *,
    detail: str | None = None,
    priority: Priority = "info",
    expires: float = 8,
    valid_while: tuple[Condition, ...] = (),
    evidence: tuple[str, ...] = (),
) -> CoachingDecision:
    return CoachingDecision(
        id=f"rule_{uuid.uuid4().hex[:10]}",
        category=category,
        action=action,
        message=message,
        detail=detail,
        priority=priority,
        confidence=0.95,
        delivery="immediate",
        expires_in_seconds=max(3, min(120, round(expires))),
        valid_while=list(valid_while),
        evidence=[f"gsi:{e}" for e in evidence],
    )


def _cond(observation_type: str, op: str, value: object = None) -> Condition:
    return Condition(observation_type=observation_type, op=op, value=value)  # type: ignore[arg-type]


def _freeze_ending(s: Cs2State) -> bool:
    return (
        s.round_phase == "freezetime"
        and s.phase_ends_in is not None
        and s.phase_ends_in <= FREEZE_END_S
    )


def _buy_window(s: Cs2State) -> float:
    """Seconds a buy tip stays relevant: rest of freeze time plus a little buy time."""
    return (s.phase_ends_in or 0) + 8


# A rule sees the new state and the previous one (None on the first update).
Rule = Callable[[Cs2State, Cs2State | None], CoachingDecision | None]


def last_round_of_half(s: Cs2State, prev: Cs2State | None) -> CoachingDecision | None:
    if s.round_phase != "freezetime" or not s.is_last_round_of_half or (s.money or 0) < 1000:
        return None
    return _tip(
        "spend_last_round_of_half",
        "economy",
        "Last round of the half: spend it all",
        detail="Money resets at the half, so saving gains nothing.",
        priority="important",
        expires=_buy_window(s) if s.phase_ends_in is not None else 15,
        valid_while=(_cond("round_phase", "eq", "freezetime"),),
        evidence=("map_round", "money"),
    )


def missing_armor(s: Cs2State, prev: Cs2State | None) -> CoachingDecision | None:
    if not _freeze_ending(s) or s.is_pistol_round or s.is_last_round_of_half:
        return None
    if (s.armor or 0) >= 30 or (s.money or 0) < ARMOR_COST:
        return None
    return _tip(
        "buy_armor",
        "economy",
        "Buy armor before the round starts",
        detail="Without armor, most guns kill you in fewer shots.",
        priority="important",
        expires=_buy_window(s),
        valid_while=(_cond("armor", "lt", 30), _cond("money", "ge", ARMOR_COST)),
        evidence=("armor", "money", "round_phase"),
    )


def missing_kit(s: Cs2State, prev: Cs2State | None) -> CoachingDecision | None:
    if not _freeze_ending(s) or s.team != "CT" or s.defusekit or s.is_pistol_round:
        return None
    if not s.has_primary or (s.money or 0) < KIT_COST:
        return None
    return _tip(
        "buy_defuse_kit",
        "economy",
        "Grab a defuse kit",
        detail="A kit cuts the defuse from 10 to 5 seconds.",
        expires=_buy_window(s),
        valid_while=(_cond("defusekit", "ne", True), _cond("money", "ge", KIT_COST)),
        evidence=("team", "defusekit", "money"),
    )


def unspent_money(s: Cs2State, prev: Cs2State | None) -> CoachingDecision | None:
    if not _freeze_ending(s) or s.has_primary or (s.money or 0) < UNSPENT_MONEY:
        return None
    return _tip(
        "buy_primary_weapon",
        "economy",
        f"Buy a weapon: ${s.money} unspent",
        detail="You can afford a full buy and have no primary weapon.",
        expires=_buy_window(s),
        valid_while=(_cond("has_primary", "eq", False), _cond("money", "ge", UNSPENT_MONEY)),
        evidence=("money", "has_primary"),
    )


def low_health(s: Cs2State, prev: Cs2State | None) -> CoachingDecision | None:
    if s.round_phase != "live" or not s.alive or (s.health or 0) > LOW_HP:
        return None
    return _tip(
        "play_for_trades_low_hp",
        "survivability",
        "Low HP: play for trades, don't peek",
        detail=f"{s.health} HP. Let a teammate take first contact.",
        priority="important",
        expires=10,
        valid_while=(_cond("health", "le", LOW_HP), _cond("alive", "eq", True)),
        evidence=("health",),
    )


def planted_without_kit(s: Cs2State, prev: Cs2State | None) -> CoachingDecision | None:
    if s.bomb != "planted" or not s.alive or s.team != "CT" or s.defusekit:
        return None
    return _tip(
        "clear_site_before_defuse",
        "objective",
        "No kit: clear the site before defusing",
        detail="A defuse without a kit takes 10 of the bomb's 40 seconds.",
        expires=12,
        valid_while=(_cond("bomb", "eq", "planted"), _cond("alive", "eq", True)),
        evidence=("bomb", "defusekit"),
    )


def planted_as_t(s: Cs2State, prev: Cs2State | None) -> CoachingDecision | None:
    if s.bomb != "planted" or not s.alive or s.team != "T":
        return None
    return _tip(
        "hold_post_plant",
        "objective",
        "Bomb down: hold angles, let them come",
        detail="The clock is on your side; avoid chasing.",
        expires=10,
        valid_while=(_cond("bomb", "eq", "planted"), _cond("alive", "eq", True)),
        evidence=("bomb",),
    )


RULES: tuple[Rule, ...] = (
    last_round_of_half,
    missing_armor,
    missing_kit,
    unspent_money,
    low_health,
    planted_without_kit,
    planted_as_t,
)


@dataclass(slots=True)
class Cs2Rules:
    """Runs every rule on each GSI update and remembers which fired this round."""

    rules: tuple[Rule, ...] = RULES
    _delivered: set[tuple[int, str]] = field(default_factory=set)
    _round: tuple[str | None, int | None] | None = None

    def evaluate(self, state: Cs2State, prev: Cs2State | None) -> list[RuleTip]:
        round_id = (state.map_name, state.map_round)
        if round_id != self._round:
            self._round = round_id
            self._delivered.clear()
        if not state.in_game or not state.has_economy:
            return []
        tips = []
        for rule in self.rules:
            decision = rule(state, prev)
            if decision is None:
                continue
            key = (state.map_round or 0, decision.action)
            if key not in self._delivered:
                tips.append(RuleTip(decision, key))
        return tips

    def mark_delivered(self, tip: RuleTip) -> None:
        self._delivered.add(tip.key)
