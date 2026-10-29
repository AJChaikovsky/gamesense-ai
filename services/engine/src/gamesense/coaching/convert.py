"""Turns a model's LiveAnalysis into contract objects with engine-assigned ids."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from gamesense_contracts import CoachingDecision, Condition, GameState, Observation

from ..games import GameProfile
from ..providers import LiveAnalysis


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def to_contracts(
    analysis: LiveAnalysis,
    *,
    game: GameProfile,
    session_id: str,
    frame_ids: list[str],
) -> tuple[GameState, CoachingDecision | None]:
    obs_ids: dict[str, str] = {}
    observations: list[Observation] = []
    for i, o in enumerate(analysis.observations):
        oid = f"obs_{uuid.uuid4().hex[:8]}_{i}"
        obs_ids.setdefault(o.type, oid)
        observations.append(
            Observation(
                id=oid,
                type=o.type,
                value=o.value,
                confidence=_clamp(o.confidence),
                source="model",
                kind=o.kind,
            )
        )
    state = GameState(
        game_id=game.game_id,
        genre=game.genre,
        session_id=session_id,
        timestamp=datetime.now(UTC),
        activity=analysis.activity,
        observations=observations,
        unknowns=analysis.unknowns,
        frame_refs=frame_ids,
    )
    tip = analysis.tip
    if tip is None:
        return state, None
    decision = CoachingDecision(
        id=f"tip_{uuid.uuid4().hex[:10]}",
        category=tip.category[:40],
        action=tip.action[:60],
        message=" ".join(tip.message.split()[:10])[:80],
        detail=(tip.detail or None) and tip.detail[:160],
        priority=tip.priority,
        confidence=_clamp(tip.confidence),
        delivery="immediate",
        expires_in_seconds=int(_clamp(tip.expires_in_seconds, 3, 60)),
        valid_while=[
            Condition(observation_type=c.observation_type, op=c.op, value=c.value)
            for c in tip.valid_while
        ],
        evidence=[obs_ids[e] for e in tip.evidence if e in obs_ids],
    )
    return state, decision
