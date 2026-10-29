"""Core data contracts shared by the engine, the desktop app and model outputs.

These Pydantic models are the single source of truth. JSON Schema and TypeScript
types are generated from them (see ``scripts/export_schema.py``), and the same
schemas are handed to vision models as structured-output formats.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACTS_VERSION = "0.1.0"

Confidence = float


class Contract(BaseModel):
    """Base class: reject unknown fields so contract drift fails loudly."""

    model_config = ConfigDict(extra="forbid")


class Observation(Contract):
    """One fact or inference about the current game situation."""

    id: str
    type: str = Field(description='Observation kind, e.g. "health_low" or "enemy_visible".')
    value: Any = None
    confidence: Confidence = Field(
        ge=0.0, le=1.0, description="Estimated confidence; not a calibrated probability."
    )
    source: Literal["visual", "ocr", "telemetry", "model", "rule"]
    kind: Literal["observed", "inferred"] = Field(
        description="Observed facts are visible on screen or in telemetry; inferences are not."
    )


class GameState(Contract):
    """Standardized snapshot of the player's current situation."""

    game_id: str
    genre: str
    session_id: str
    timestamp: datetime
    activity: str | None = Field(
        default=None, description='High-level activity, e.g. "exploration" or "combat".'
    )
    observations: list[Observation] = Field(default_factory=list)
    unknowns: list[str] = Field(
        default_factory=list, description="Things that matter but cannot be determined."
    )
    game_specific: dict[str, Any] = Field(
        default_factory=dict, description="Adapter-defined extension fields."
    )
    frame_refs: list[str] = Field(
        default_factory=list, description="Ring-buffer frame ids used as evidence."
    )


class Condition(Contract):
    """A condition that must still hold for a tip to be shown (stale-result validator)."""

    observation_type: str
    op: Literal["eq", "ne", "lt", "le", "gt", "ge", "present", "absent"]
    value: Any = None


class CoachingDecision(Contract):
    """A proposed tip, its justification and its delivery conditions."""

    id: str
    category: str = Field(description='Skill area, e.g. "survivability" or "economy".')
    action: str = Field(description='Machine-readable action, e.g. "heal_before_engaging".')
    message: str = Field(max_length=80, description="Headline shown on the overlay (<= 8 words).")
    detail: str | None = Field(default=None, max_length=160)
    priority: Literal["info", "important", "urgent"]
    confidence: Confidence = Field(ge=0.0, le=1.0)
    delivery: Literal["immediate", "next_lull", "post_session"]
    expires_in_seconds: int = Field(ge=1, le=120)
    valid_while: list[Condition] = Field(default_factory=list)
    evidence: list[str] = Field(
        default_factory=list, description="Observation ids that justify this tip."
    )


class HabitObservation(Contract):
    """Evidence that may contribute to the player's long-term skill profile."""

    skill: str
    behavior: str
    session_id: str
    evidence: list[str] = Field(default_factory=list)
    evidence_count: int = Field(ge=0)
    confidence: Confidence = Field(ge=0.0, le=1.0)


class ModelAnalysis(Contract):
    """Structured output requested from the live vision model on each trigger."""

    state: GameState
    decision: CoachingDecision | None = Field(
        default=None, description="Null when the coach should stay silent."
    )
