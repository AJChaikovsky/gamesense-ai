from datetime import UTC, datetime

import pytest
from gamesense_contracts import (
    CaptureStatus,
    CoachingDecision,
    GameState,
    HeartbeatEvent,
    ModelAnalysis,
    Observation,
    engine_event_adapter,
)
from pydantic import ValidationError


def _state() -> GameState:
    return GameState(
        game_id="minecraft",
        genre="sandbox",
        session_id="session_123",
        timestamp=datetime(2026, 10, 28, 20, 14, tzinfo=UTC),
        activity="exploration",
        observations=[
            Observation(
                id="obs_1",
                type="health_low",
                value=True,
                confidence=0.95,
                source="visual",
                kind="observed",
            )
        ],
        unknowns=["nearby_hidden_enemies"],
    )


def test_model_analysis_round_trip() -> None:
    analysis = ModelAnalysis(
        state=_state(),
        decision=CoachingDecision(
            id="tip_1",
            category="survivability",
            action="heal_before_engaging",
            message="Heal before your next fight",
            priority="important",
            confidence=0.91,
            delivery="immediate",
            expires_in_seconds=10,
            evidence=["obs_1"],
        ),
    )
    restored = ModelAnalysis.model_validate_json(analysis.model_dump_json())
    assert restored == analysis


def test_silence_is_valid() -> None:
    assert ModelAnalysis(state=_state()).decision is None


def test_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        Observation.model_validate(
            {
                "id": "x",
                "type": "t",
                "confidence": 0.5,
                "source": "visual",
                "kind": "observed",
                "surprise": 1,
            }
        )


def test_confidence_bounds() -> None:
    with pytest.raises(ValidationError):
        Observation(id="x", type="t", confidence=1.5, source="visual", kind="observed")


def test_engine_event_discriminator() -> None:
    event = HeartbeatEvent(
        timestamp=datetime.now(UTC),
        engine_version="0.1.0",
        uptime_seconds=1.0,
        capture=CaptureStatus(source="none", running=False, fps=0.0, buffered_frames=0),
    )
    parsed = engine_event_adapter.validate_json(event.model_dump_json())
    assert isinstance(parsed, HeartbeatEvent)
