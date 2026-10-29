"""Aggregate case results per model and write the comparison report."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .runner import CaseResult

# docs/model-selection.md assumes one live call every 6 seconds of play.
CALLS_PER_HOUR = 600


@dataclass(slots=True)
class ModelSummary:
    provider: str
    model: str
    calls: int
    errors: int
    schema_valid_rate: float
    silence_accuracy: float | None
    tip_recall: float | None  # spoke when it should
    false_alarm_rate: float | None  # spoke when it should have stayed silent
    perception_recall: float | None
    evidence_linked_rate: float | None
    usefulness: float | None
    grounded_rate: float | None
    latency_p50_ms: int | None
    latency_p95_ms: int | None
    cost_per_call_usd: float
    cost_per_hour_usd: float
    total_cost_usd: float
    judge_cost_usd: float


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _rate(flags: Sequence[bool]) -> float | None:
    return _mean([1.0 if f else 0.0 for f in flags])


def percentile(values: Sequence[int], pct: float) -> int | None:
    """Nearest-rank percentile."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def summarize(results: Sequence[CaseResult]) -> list[ModelSummary]:
    groups: dict[tuple[str, str], list[CaseResult]] = {}
    for r in results:
        groups.setdefault((r.provider, r.model), []).append(r)
    summaries = []
    for (provider, model), rs in groups.items():
        ok = [r for r in rs if r.ok]
        latencies = [r.latency_ms for r in ok if r.latency_ms is not None]
        cost = sum(r.cost_usd for r in rs)
        per_call = cost / len(ok) if ok else 0.0
        summaries.append(
            ModelSummary(
                provider=provider,
                model=model,
                calls=len(rs),
                errors=len(rs) - len(ok),
                schema_valid_rate=len(ok) / len(rs),
                silence_accuracy=_rate([bool(r.silence_correct) for r in ok]),
                tip_recall=_rate([r.tip_shown for r in ok if r.expect_tip]),
                false_alarm_rate=_rate([r.tip_shown for r in ok if not r.expect_tip]),
                perception_recall=_mean(
                    [r.perception_recall for r in rs if r.perception_recall is not None]
                ),
                evidence_linked_rate=_rate(
                    [r.evidence_linked for r in ok if r.evidence_linked is not None]
                ),
                usefulness=_mean([float(r.usefulness) for r in ok if r.usefulness is not None]),
                grounded_rate=_rate([r.grounded for r in ok if r.grounded is not None]),
                latency_p50_ms=percentile(latencies, 50),
                latency_p95_ms=percentile(latencies, 95),
                cost_per_call_usd=per_call,
                cost_per_hour_usd=per_call * CALLS_PER_HOUR,
                total_cost_usd=cost,
                judge_cost_usd=sum(r.judge_cost_usd for r in rs),
            )
        )
    return summaries


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def _num(value: float | None, fmt: str = "{:.2f}") -> str:
    return "n/a" if value is None else fmt.format(value)


def render_markdown(
    summaries: Sequence[ModelSummary], results: Sequence[CaseResult], meta: dict[str, Any]
) -> str:
    lines = [
        "# GameSense eval report",
        "",
        f"- Run: {meta.get('started', '')}",
        f"- Dataset: {meta.get('dataset', '')} ({meta.get('cases', 0)} cases, "
        f"{meta.get('repeats', 1)} repeat(s))",
        f"- Judge: {meta.get('judge', 'none')}",
    ]
    if meta.get("stopped"):
        lines.append(f"- **{meta['stopped']}**")
    lines += [
        "",
        "## Summary",
        "",
        "| Model | Valid | Silence acc. | Tip recall | False alarms | Perception | "
        "Useful (1-5) | Grounded | p50 / p95 ms | $/call | $/hour |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in summaries:
        lines.append(
            f"| {s.provider}:{s.model} | {_pct(s.schema_valid_rate)} | {_pct(s.silence_accuracy)} "
            f"| {_pct(s.tip_recall)} | {_pct(s.false_alarm_rate)} | {_pct(s.perception_recall)} "
            f"| {_num(s.usefulness)} | {_pct(s.grounded_rate)} "
            f"| {_num(s.latency_p50_ms, '{:.0f}')} / {_num(s.latency_p95_ms, '{:.0f}')} "
            f"| {s.cost_per_call_usd:.5f} | {s.cost_per_hour_usd:.2f} |"
        )
    lines += [
        "",
        f"$/hour assumes {CALLS_PER_HOUR} calls per hour (one every 6 s). Silence accuracy is "
        "how often the model spoke exactly when the label says a coach should. Perception is the "
        "share of labeled observations the model listed.",
        "",
        "## Cases",
        "",
        "| Model | Case | Expect tip | Shown | Tip | Perception | Useful | Latency | Note |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        note = r.error or r.judge_reason or ""
        lines.append(
            f"| {r.provider}:{r.model} | {r.case_id} | {'yes' if r.expect_tip else 'no'} "
            f"| {'yes' if r.tip_shown else 'no'} | {(r.tip_message or '').replace('|', '/')} "
            f"| {_pct(r.perception_recall)} | {r.usefulness or ''} | {r.latency_ms or ''} "
            f"| {note.replace('|', '/')[:120]} |"
        )
    return "\n".join(lines) + "\n"


def write_report(
    out_dir: Path,
    results: Sequence[CaseResult],
    meta: dict[str, Any],
) -> list[ModelSummary]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries = summarize(results)
    with (out_dir / "results.jsonl").open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r.to_json()) + "\n")
    (out_dir / "summary.json").write_text(
        json.dumps({"meta": meta, "models": [asdict(s) for s in summaries]}, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "report.md").write_text(render_markdown(summaries, results, meta), encoding="utf-8")
    return summaries
