"""Runs eval cases through one or more providers and scores every output."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..games import game_by_id
from ..knowledge import KnowledgeBase
from ..providers import AnalysisRequest, ProviderError, VisionModelProvider
from ..providers.prompt import context_block, system_prompt
from .dataset import EvalCase
from .frames import CaseFrames, extract
from .judge import Judge
from .scoring import SHOW_THRESHOLD, perception_recall, tip_shown

log = logging.getLogger(__name__)


@dataclass(slots=True)
class CaseResult:
    provider: str
    model: str
    case_id: str
    game: str
    repeat: int
    ok: bool
    error: str | None = None
    latency_ms: int | None = None
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    expect_tip: bool = False
    tip_shown: bool = False
    silence_correct: bool | None = None
    perception_recall: float | None = None
    evidence_linked: bool | None = None
    usefulness: int | None = None
    grounded: bool | None = None
    judge_reason: str | None = None
    judge_cost_usd: float = 0.0
    tip_message: str | None = None
    activity: str | None = None
    analysis: dict[str, Any] | None = field(default=None, repr=False)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RunOptions:
    clips_dir: Path
    repeats: int = 1
    max_cost_usd: float = 1.0
    sample_fps: float = 4.0
    frames_per_call: int = 2
    model_frame_width: int = 1024
    show_threshold: float = SHOW_THRESHOLD


_KNOWLEDGE: KnowledgeBase | None = None


def _knowledge() -> KnowledgeBase:
    global _KNOWLEDGE
    if _KNOWLEDGE is None:
        _KNOWLEDGE = KnowledgeBase.load()
    return _KNOWLEDGE


def build_request(
    case: EvalCase, frames: CaseFrames, knowledge: KnowledgeBase | None = None
) -> AnalysisRequest:
    """The same prompt the live loop sends on its first call (no history, so only
    the game's core knowledge and no situational snippets)."""
    game = game_by_id(case.game)
    kb = knowledge or _knowledge()
    return AnalysisRequest(
        system_prompt=system_prompt(game, kb.core(game.game_id)),
        context=context_block(
            recent_tips=[], last_activity=None, last_observations=[], seconds_since_last_tip=None
        ),
        frames_jpeg=frames.jpegs,
        request_id=uuid.uuid4().hex,
        game_id=game.game_id,
        hints={"scene_change": frames.signals.scene_change, "activity": frames.signals.activity},
    )


async def run_case(
    provider: VisionModelProvider,
    case: EvalCase,
    frames: CaseFrames,
    judge: Judge | None,
    *,
    repeat: int = 0,
    show_threshold: float = SHOW_THRESHOLD,
) -> CaseResult:
    result = CaseResult(
        provider=provider.name,
        model=provider.model,
        case_id=case.id,
        game=case.game,
        repeat=repeat,
        ok=False,
        expect_tip=case.labels.expect_tip,
    )
    try:
        out = await provider.analyze(build_request(case, frames))
    except ProviderError as exc:
        result.error = str(exc)
        result.perception_recall = perception_recall(case.labels, None)
        return result

    analysis = out.analysis
    shown = tip_shown(analysis, show_threshold)
    result.ok = True
    result.latency_ms = out.latency_ms
    result.cost_usd = out.cost_usd
    result.input_tokens = out.usage.input_tokens
    result.output_tokens = out.usage.output_tokens
    result.tip_shown = shown
    result.silence_correct = shown == case.labels.expect_tip
    result.perception_recall = perception_recall(case.labels, analysis)
    result.activity = analysis.activity
    result.analysis = analysis.model_dump(mode="json")
    if shown and analysis.tip is not None:
        tip = analysis.tip
        result.tip_message = tip.message
        observed = {o.type for o in analysis.observations}
        result.evidence_linked = bool(tip.evidence) and all(e in observed for e in tip.evidence)
        if judge is not None:
            try:
                verdict = await judge.judge(case, analysis, frames.jpegs)
            except ProviderError as exc:
                result.judge_reason = f"judge failed: {exc}"
            else:
                result.usefulness = verdict.usefulness
                result.grounded = verdict.grounded
                result.judge_reason = verdict.reason
                result.judge_cost_usd = verdict.cost_usd
    return result


async def run_eval(
    cases: Sequence[EvalCase],
    providers: Sequence[VisionModelProvider],
    judge: Judge | None,
    options: RunOptions,
    *,
    on_result: Callable[[CaseResult], None] | None = None,
) -> tuple[list[CaseResult], str | None]:
    """Run every case on every provider. Returns the results and a stop reason, if any.

    Calls run one at a time so latency numbers aren't skewed by our own concurrency.
    The run stops early once estimated spend (models plus judge) passes ``max_cost_usd``.
    """
    frames_cache: dict[str, CaseFrames] = {}
    results: list[CaseResult] = []
    spent = 0.0
    for provider in providers:
        for repeat in range(options.repeats):
            for case in cases:
                if options.max_cost_usd > 0 and spent >= options.max_cost_usd:
                    return results, f"stopped early: spend reached ${spent:.4f}"
                frames = frames_cache.get(case.id)
                if frames is None:
                    frames = extract(
                        options.clips_dir / case.clip,
                        case.start_s,
                        case.end_s,
                        sample_fps=options.sample_fps,
                        frames_per_call=options.frames_per_call,
                        model_frame_width=options.model_frame_width,
                    )
                    frames_cache[case.id] = frames
                result = await run_case(
                    provider,
                    case,
                    frames,
                    judge,
                    repeat=repeat,
                    show_threshold=options.show_threshold,
                )
                spent += result.cost_usd + result.judge_cost_usd
                results.append(result)
                if on_result is not None:
                    on_result(result)
    return results, None
