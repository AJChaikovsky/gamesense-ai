"""Usefulness judges for shown tips.

``heuristic`` is free and offline: it compares the tip with the case's example good
and bad tips. ``anthropic:<model>`` asks a stronger model, which also sees the frames,
whether the tip is useful and grounded in what is on screen. Humans spot-check both.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..providers import LiveAnalysis, ProviderError
from ..providers.jsonschema import inline_schema
from ..providers.pricing import estimate_cost
from .dataset import EvalCase
from .scoring import Verdict, tip_similarity


class Judge(Protocol):
    name: str

    async def judge(self, case: EvalCase, analysis: LiveAnalysis, jpegs: list[bytes]) -> Verdict:
        """Judge the analysis's tip. Only called when a tip was shown."""
        ...


class HeuristicJudge:
    name = "heuristic"

    async def judge(self, case: EvalCase, analysis: LiveAnalysis, jpegs: list[bytes]) -> Verdict:
        tip = analysis.tip
        assert tip is not None
        labels = case.labels
        if not labels.expect_tip:
            return Verdict(1, None, "spoke when a good coach would stay silent")
        # Example tips are headlines, so compare headline to headline.
        good = tip_similarity(tip.message, labels.good_tips)
        bad = tip_similarity(tip.message, labels.bad_tips)
        if bad >= 0.3 and bad > good:
            return Verdict(1, None, f"close to a labeled bad tip ({bad:.2f})")
        if not labels.good_tips:
            return Verdict(3, None, "no example tips to compare with")
        score = 5 if good >= 0.5 else 4 if good >= 0.3 else 3 if good >= 0.15 else 2
        return Verdict(score, None, f"overlap with good tips {good:.2f}")


class _JudgeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usefulness: int = Field(description="1 = wrong or harmful, 3 = okay, 5 = exactly right.")
    grounded: bool = Field(description="Is every claim in the tip supported by the frames?")
    reason: str = Field(description="One sentence.")


_JUDGE_SYSTEM = """You grade a live video game coach. You get the frames the coach saw, a human
label describing the moment, and the tip the coach showed. Score usefulness from 1 to 5:
5 = exactly what an expert coach would say right now; 4 = helpful; 3 = okay but generic;
2 = not useful now; 1 = wrong, ungrounded, harmful or interrupts when silence was better.
"grounded" is false if the tip relies on anything not visible in the frames or the label.
Be strict and consistent."""


class AnthropicJudge:
    def __init__(self, model: str = "claude-sonnet-5-5", *, client: Any | None = None) -> None:
        self.model = model
        self.name = f"anthropic:{model}"
        if client is None:
            import anthropic

            client = anthropic.AsyncAnthropic(timeout=60.0, max_retries=2)
        self._client: Any = client

    async def judge(self, case: EvalCase, analysis: LiveAnalysis, jpegs: list[bytes]) -> Verdict:
        labels = case.labels
        brief = {
            "game": case.game,
            "what_is_happening": labels.notes,
            "should_coach_speak": labels.expect_tip,
            "key_observations": labels.observations,
            "example_good_tips": labels.good_tips,
            "example_bad_tips": labels.bad_tips,
            "coach_output": analysis.model_dump(mode="json"),
        }
        content: list[dict[str, Any]] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(j).decode("ascii"),
                },
            }
            for j in jpegs
        ]
        content.append({"type": "text", "text": json.dumps(brief, indent=1)})
        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=_JUDGE_SYSTEM,
                messages=[{"role": "user", "content": content}],
                output_config={
                    "effort": "low",
                    "format": {"type": "json_schema", "schema": inline_schema(_JudgeOutput)},
                },
            )
        except Exception as exc:
            raise ProviderError(f"judge call failed: {exc}") from exc
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            out = _JudgeOutput.model_validate_json(text)
        except ValidationError as exc:
            raise ProviderError(f"judge returned invalid JSON: {exc}") from exc
        usage = response.usage
        return Verdict(
            usefulness=max(1, min(5, out.usefulness)),
            grounded=out.grounded,
            reason=out.reason,
            cost_usd=estimate_cost(self.model, usage.input_tokens, usage.output_tokens),
        )


def create_judge(spec: str) -> Judge | None:
    if spec in ("", "none"):
        return None
    if spec == "heuristic":
        return HeuristicJudge()
    name, _, model = spec.partition(":")
    if name == "anthropic":
        return AnthropicJudge(model or "claude-sonnet-5-5")
    raise ValueError(f"unknown judge {spec!r} (use none, heuristic or anthropic[:model])")
