"""Claude vision provider (default: Claude Haiku 5.5, the cheapest fast tier)."""

from __future__ import annotations

import base64
import time
from typing import Any

import anthropic
from pydantic import ValidationError

from .base import AnalysisRequest, AnalysisResult, ProviderError, Usage
from .jsonschema import inline_schema
from .pricing import PRICES_PER_MTOK, estimate_cost
from .schema import LiveAnalysis

_SCHEMA = inline_schema(LiveAnalysis)


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        model: str = "claude-haiku-5-5",
        *,
        client: Any | None = None,
        timeout_s: float = 15.0,
        effort: str = "low",
    ) -> None:
        self.model = model
        self._effort = effort
        # One quick retry at most: a late tip is a useless tip.
        self._client = client or anthropic.AsyncAnthropic(timeout=timeout_s, max_retries=1)

    def build_request(self, request: AnalysisRequest) -> dict[str, Any]:
        content: list[dict[str, Any]] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(jpeg).decode("ascii"),
                },
            }
            for jpeg in request.frames_jpeg
        ]
        content.append({"type": "text", "text": request.context})
        return {
            "model": self.model,
            "max_tokens": 2048,
            # Stable per game, so it is cached across calls.
            "system": [
                {
                    "type": "text",
                    "text": request.system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [{"role": "user", "content": content}],
            "output_config": {
                "effort": self._effort,
                "format": {"type": "json_schema", "schema": _SCHEMA},
            },
        }

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        started = time.monotonic()
        try:
            response = await self._client.messages.create(**self.build_request(request))
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError(f"Anthropic connection error: {exc}") from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        if response.stop_reason == "refusal":
            raise ProviderError("Claude declined this request")
        if response.stop_reason == "max_tokens":
            raise ProviderError("Claude response was cut off (max_tokens)")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise ProviderError("Claude returned no text block")
        try:
            analysis = LiveAnalysis.model_validate_json(text)
        except ValidationError as exc:
            raise ProviderError(f"Claude returned invalid JSON: {exc}") from exc

        usage = response.usage
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        price_in, _ = PRICES_PER_MTOK.get(self.model, (0.0, 0.0))
        cache_cost = (cache_read * 0.1 + cache_write * 1.25) * price_in / 1_000_000
        cost = estimate_cost(self.model, usage.input_tokens, usage.output_tokens) + cache_cost
        return AnalysisResult(
            analysis=analysis,
            usage=Usage(
                input_tokens=usage.input_tokens + cache_read + cache_write,
                output_tokens=usage.output_tokens,
            ),
            latency_ms=latency_ms,
            cost_usd=cost,
        )

    async def aclose(self) -> None:
        close = getattr(self._client, "close", None)
        if close is not None:
            await close()
