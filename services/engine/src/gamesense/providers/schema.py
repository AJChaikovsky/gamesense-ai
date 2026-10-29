"""The JSON shape we ask vision models to return.

Deliberately simpler than the contracts: no ids, timestamps or session fields
(the engine fills those in, so a model can't invent them) and only plain types,
which every provider's structured-output mode supports.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LiveObservation(_Strict):
    type: str = Field(description='snake_case fact name, e.g. "health_low", "enemy_visible".')
    value: str = Field(description='Short value, e.g. "18%", "true", "2 zombies".')
    confidence: float = Field(description="0 to 1.")
    kind: Literal["observed", "inferred"] = Field(
        description="observed = clearly visible on screen; inferred = a guess from context."
    )


class LiveCondition(_Strict):
    observation_type: str
    op: Literal["eq", "ne", "lt", "le", "gt", "ge", "present", "absent"]
    value: str | None


class LiveTip(_Strict):
    category: str = Field(description='Skill area, e.g. "survivability", "economy".')
    action: str = Field(description='snake_case action, e.g. "heal_before_engaging".')
    message: str = Field(description="Imperative headline, 8 words or fewer.")
    detail: str | None = Field(description="Optional short reason, 20 words or fewer.")
    priority: Literal["info", "important", "urgent"]
    confidence: float = Field(description="0 to 1: how sure you are this advice helps now.")
    expires_in_seconds: int = Field(description="How long the tip stays relevant (3 to 60).")
    valid_while: list[LiveCondition] = Field(
        description="Conditions that must still hold when the tip is shown."
    )
    evidence: list[str] = Field(description="observation types that justify the tip.")


class LiveAnalysis(_Strict):
    activity: str | None = Field(description='e.g. "combat", "exploration", "menu", "buy_phase".')
    observations: list[LiveObservation]
    unknowns: list[str] = Field(description="Important things you cannot see or determine.")
    tip: LiveTip | None = Field(description="null when nothing is worth saying right now.")
