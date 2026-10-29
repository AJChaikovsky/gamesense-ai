from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .schema import LiveAnalysis


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    """Everything a provider needs for one live analysis."""

    system_prompt: str
    context: str
    frames_jpeg: list[bytes]
    request_id: str
    game_id: str = "generic"
    # Free-form hints for providers that need them (e.g. the mock).
    hints: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    analysis: LiveAnalysis
    usage: Usage
    latency_ms: int
    cost_usd: float


class ProviderError(RuntimeError):
    """A provider call failed (network, auth, refusal, invalid output)."""


class VisionModelProvider(Protocol):
    name: str
    model: str

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult: ...

    async def aclose(self) -> None: ...
