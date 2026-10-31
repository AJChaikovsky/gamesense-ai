"""Engine settings, read from CLI flags, environment variables and an optional .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

ProviderName = Literal["mock", "anthropic", "google", "openai", "muse"]
CaptureMode = Literal["auto", "replay", "window", "none"]

DEFAULT_MODELS: dict[str, str] = {
    "mock": "mock-coach",
    "anthropic": "claude-haiku-5-5",
    "google": "gemini-3.1-flash-lite",
    "openai": "gpt-5.6-luna",
    "muse": "muse-spark-1.1",
}


def load_env_file(start: Path | None = None) -> None:
    """Load the nearest .env (repo root in dev). Real environment variables win."""
    here = (start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        candidate = folder / ".env"
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            return


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


@dataclass(slots=True)
class Settings:
    provider: ProviderName = "mock"
    model: str = ""
    capture: CaptureMode = "auto"
    replay: str | None = None
    window: str | None = None
    game: str | None = None
    sample_fps: float = 4.0
    buffer_seconds: float = 60.0
    max_width: int = 1280
    model_frame_width: int = 1024
    frames_per_call: int = 2
    hourly_budget_usd: float = 0.50
    min_call_interval: float = 3.0
    heartbeat_trigger_seconds: float = 20.0
    scene_change_threshold: float = 0.06
    loop: bool = True
    save_feedback: bool = True
    gsi_port: int = 3727  # CS2 Game State Integration receiver; 0 turns it off
    gsi_record: str | None = None
    extra: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.model:
            self.model = DEFAULT_MODELS[self.provider]

    @classmethod
    def from_env(cls) -> Settings:
        provider = os.environ.get("GAMESENSE_PROVIDER", "mock")
        if provider not in DEFAULT_MODELS:
            raise ValueError(f"GAMESENSE_PROVIDER must be one of {sorted(DEFAULT_MODELS)}")
        capture = os.environ.get("GAMESENSE_CAPTURE", "auto")
        if capture not in ("auto", "replay", "window", "none"):
            raise ValueError("GAMESENSE_CAPTURE must be auto, replay, window or none")
        return cls(
            provider=provider,  # type: ignore[arg-type]
            model=os.environ.get("GAMESENSE_MODEL", ""),
            capture=capture,  # type: ignore[arg-type]
            replay=os.environ.get("GAMESENSE_REPLAY") or None,
            window=os.environ.get("GAMESENSE_WINDOW") or None,
            game=os.environ.get("GAMESENSE_GAME") or None,
            hourly_budget_usd=_float_env("GAMESENSE_HOURLY_BUDGET_USD", 0.50),
            save_feedback=os.environ.get("GAMESENSE_SAVE_FEEDBACK", "1") != "0",
            gsi_port=int(os.environ.get("GAMESENSE_GSI_PORT") or 3727),
            gsi_record=os.environ.get("GAMESENSE_GSI_RECORD") or None,
        )
