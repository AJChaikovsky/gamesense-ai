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


class HeartbeatEvent(Contract):
    type: Literal["heartbeat"] = "heartbeat"
    timestamp: datetime
    engine_version: str
    uptime_seconds: float
    capture: CaptureStatus


class TipEvent(Contract):
    type: Literal["tip"] = "tip"
    timestamp: datetime
    decision: CoachingDecision


class StatusEvent(Contract):
    type: Literal["status"] = "status"
    timestamp: datetime
    level: Literal["ok", "degraded", "offline"]
    message: str


EngineEvent = Annotated[HeartbeatEvent | TipEvent | StatusEvent, Field(discriminator="type")]

engine_event_adapter: TypeAdapter[HeartbeatEvent | TipEvent | StatusEvent] = TypeAdapter(
    EngineEvent
)
