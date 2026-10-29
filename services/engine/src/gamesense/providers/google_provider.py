"""Gemini vision provider (default: Gemini 3.1 Flash-Lite)."""

from __future__ import annotations

import os
import time
from typing import Any

from pydantic import ValidationError

from .base import AnalysisRequest, AnalysisResult, ProviderError, Usage
from .jsonschema import inline_schema
from .pricing import estimate_cost
from .schema import LiveAnalysis

_SCHEMA = inline_schema(LiveAnalysis)


class GoogleProvider:
    name = "google"

    def __init__(self, model: str = "gemini-3.1-flash-lite", *, client: Any | None = None) -> None:
        self.model = model
        if client is None:
            from google import genai

            api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            client = genai.Client(api_key=api_key)
        self._client = client

    def build_request(self, request: AnalysisRequest) -> dict[str, Any]:
        from google.genai import types

        parts: list[Any] = [
            types.Part.from_bytes(data=jpeg, mime_type="image/jpeg") for jpeg in request.frames_jpeg
        ]
        parts.append(request.context)
        return {
            "model": self.model,
            "contents": parts,
            "config": types.GenerateContentConfig(
                system_instruction=request.system_prompt,
                response_mime_type="application/json",
                response_json_schema=_SCHEMA,
                max_output_tokens=2048,
            ),
        }

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        started = time.monotonic()
        try:
            response = await self._client.aio.models.generate_content(**self.build_request(request))
        except Exception as exc:  # google-genai raises several unrelated error types
            raise ProviderError(f"Gemini error: {exc}") from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        text = getattr(response, "text", None)
        if not text:
            raise ProviderError("Gemini returned no text")
        try:
            analysis = LiveAnalysis.model_validate_json(text)
        except ValidationError as exc:
            raise ProviderError(f"Gemini returned invalid JSON: {exc}") from exc

        meta = getattr(response, "usage_metadata", None)
        input_tokens = int(getattr(meta, "prompt_token_count", 0) or 0)
        output_tokens = int(getattr(meta, "candidates_token_count", 0) or 0) + int(
            getattr(meta, "thoughts_token_count", 0) or 0
        )
        return AnalysisResult(
            analysis=analysis,
            usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
            latency_ms=latency_ms,
            cost_usd=estimate_cost(self.model, input_tokens, output_tokens),
        )

    async def aclose(self) -> None:
        return None
