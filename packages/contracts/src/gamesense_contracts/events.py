"""Messages sent from the engine to the desktop app over the local WebSocket."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from .models import CoachingDecision, Contract


class CaptureStatus(Contract):
    source: Literal["none", "replay", "windows"]
    running: bool
    target: str | None = Field(default=None, description="Clip path or window title.")
    fps: float = Field(ge=0.0, description="Measured frames per second entering the buffer.")
    buffered_frames: int = Field(ge=0)
    frame_width: int | None = None
    frame_height: int | None = None


class CoachingStatus(Contract):
    provider: str
    model: str
    paused: bool
    game_id: str | None = None
    game_name: str | None = None
    live_allowed: bool = Field(description="False when the game's policy blocks live coaching.")
    policy_reason: str | None = None
    in_flight: bool = Field(description="A model request is currently running.")
    calls: int = Field(ge=0, description="Model calls this session.")
    tips_delivered: int = Field(ge=0)
    spend_usd: float = Field(ge=0.0, description="Estimated model spend this session.")
    spend_usd_last_hour: float = Field(ge=0.0)
    hourly_budget_usd: float = Field(ge=0.0)
    last_latency_ms: int | None = None


class HeartbeatEvent(Contract):
    type: Literal["heartbeat"] = "heartbeat"
    timestamp: datetime
    engine_version: str
    uptime_seconds: float
    capture: CaptureStatus
    coaching: CoachingStatus | None = None


class TipEvent(Contract):
    type: Literal["tip"] = "tip"
    timestamp: datetime
    decision: CoachingDecision


class StatusEvent(Contract):
    type: Literal["status"] = "status"
    timestamp: datetime
    level: Literal["ok", "degraded", "offline"]
    message: str


class FeedbackMessage(Contract):
    """Sent by the desktop app when the player rates or dismisses a tip."""

    type: Literal["feedback"] = "feedback"
    tip_id: str
    rating: Literal["useful", "not_useful", "dismissed"]


class ControlMessage(Contract):
    """Sent by the desktop app to pause or resume coaching."""

    type: Literal["control"] = "control"
    action: Literal["pause", "resume"]


EngineEvent = Annotated[HeartbeatEvent | TipEvent | StatusEvent, Field(discriminator="type")]

engine_event_adapter: TypeAdapter[HeartbeatEvent | TipEvent | StatusEvent] = TypeAdapter(
    EngineEvent
)

ClientMessage = Annotated[FeedbackMessage | ControlMessage, Field(discriminator="type")]

client_message_adapter: TypeAdapter[FeedbackMessage | ControlMessage] = TypeAdapter(ClientMessage)
