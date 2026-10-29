"""OpenAI-compatible vision providers: OpenAI (GPT-5.6 Luna) and Meta Muse Spark.

Both speak the Chat Completions format, so one class covers them. OpenAI supports
strict JSON Schema output. Muse Spark's structured-output support isn't documented
yet, so by default it gets the schema in the prompt and we parse the JSON it returns.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from typing import Any, Literal

import openai
from pydantic import ValidationError

from .base import AnalysisRequest, AnalysisResult, ProviderError, Usage
from .jsonschema import inline_schema
from .pricing import PRICES_PER_MTOK, estimate_cost
from .schema import LiveAnalysis

_SCHEMA = inline_schema(LiveAnalysis)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")

StructuredMode = Literal["json_schema", "prompt"]

MUSE_BASE_URL = "https://api.meta.ai/v1"


class OpenAICompatibleProvider:
    def __init__(
        self,
        model: str,
        *,
        name: str = "openai",
        client: Any | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        structured: StructuredMode = "json_schema",
        reasoning_effort: str | None = "low",
        cached_input_discount: float | None = 0.1,
        timeout_s: float = 15.0,
    ) -> None:
        self.name = name
        self.model = model
        self._structured = structured
        self._effort = reasoning_effort
        # Fraction of the input price charged for cached prompt tokens (None = no discount).
        self._cached_discount = cached_input_discount
        self._client = client or openai.AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout_s, max_retries=1
        )

    def build_request(self, request: AnalysisRequest) -> dict[str, Any]:
        system = request.system_prompt
        if self._structured == "prompt":
            system += (
                "\n\nReply with one JSON object that matches this JSON Schema exactly, "
                f"with no prose or code fences:\n{json.dumps(_SCHEMA, separators=(',', ':'))}"
            )
        content: list[dict[str, Any]] = [
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/jpeg;base64,"
                    + base64.standard_b64encode(jpeg).decode("ascii")
                },
            }
            for jpeg in request.frames_jpeg
        ]
        content.append({"type": "text", "text": request.context})
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            "max_completion_tokens": 2048,
        }
        if self._effort:
            body["reasoning_effort"] = self._effort
        if self._structured == "json_schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "live_analysis", "strict": True, "schema": _SCHEMA},
            }
        return body

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        started = time.monotonic()
        label = self.name.capitalize()
        try:
            response = await self._client.chat.completions.create(**self.build_request(request))
        except openai.APIStatusError as exc:
            raise ProviderError(f"{label} API error {exc.status_code}: {exc.message}") from exc
        except openai.APIConnectionError as exc:
            raise ProviderError(f"{label} connection error: {exc}") from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        if not response.choices:
            raise ProviderError(f"{label} returned no choices")
        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise ProviderError(f"{label} response was cut off (length)")
        refusal = getattr(choice.message, "refusal", None)
        if refusal:
            raise ProviderError(f"{label} declined this request: {refusal[:120]}")
        text = choice.message.content
        if not text:
            raise ProviderError(f"{label} returned no text")
        try:
            analysis = LiveAnalysis.model_validate_json(_FENCE.sub("", text.strip()))
        except ValidationError as exc:
            raise ProviderError(f"{label} returned invalid JSON: {exc}") from exc

        usage = response.usage
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        details = getattr(usage, "prompt_tokens_details", None)
        cached = int(getattr(details, "cached_tokens", 0) or 0)
        cost = estimate_cost(self.model, input_tokens, output_tokens)
        if cached and self._cached_discount is not None:
            price_in, _ = PRICES_PER_MTOK.get(self.model, (0.0, 0.0))
            cost -= cached * price_in * (1 - self._cached_discount) / 1_000_000
        return AnalysisResult(
            analysis=analysis,
            usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
            latency_ms=latency_ms,
            cost_usd=max(cost, 0.0),
        )

    async def aclose(self) -> None:
        close = getattr(self._client, "close", None)
        if close is not None:
            await close()


def openai_provider(model: str = "gpt-5.6-luna", **kwargs: Any) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(model, name="openai", **kwargs)


def muse_provider(model: str = "muse-spark-1.1", **kwargs: Any) -> OpenAICompatibleProvider:
    """Meta Muse Spark through its OpenAI-compatible endpoint.

    Meta's docs name the key MODEL_API_KEY; MUSE_API_KEY is accepted as a clearer alias.
    Set GAMESENSE_MUSE_STRUCTURED=json_schema to try strict structured output.
    """
    if "client" not in kwargs:
        kwargs.setdefault(
            "api_key", os.environ.get("MUSE_API_KEY") or os.environ.get("MODEL_API_KEY")
        )
        kwargs.setdefault("base_url", os.environ.get("MUSE_BASE_URL", MUSE_BASE_URL))
    mode = os.environ.get("GAMESENSE_MUSE_STRUCTURED", "prompt")
    kwargs.setdefault("structured", "json_schema" if mode == "json_schema" else "prompt")
    kwargs.setdefault("cached_input_discount", None)
    return OpenAICompatibleProvider(model, name="muse", **kwargs)
