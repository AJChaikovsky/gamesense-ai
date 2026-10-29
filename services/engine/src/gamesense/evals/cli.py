"""GameSense eval harness.

    uv run gamesense-eval run                                   # every dataset, mock provider
    uv run gamesense-eval run --providers anthropic,google,openai,muse --judge anthropic --yes
    uv run gamesense-eval record --window "Minecraft" --seconds 120 --game minecraft
    uv run gamesense-eval add-case --dataset evals/datasets/minecraft.jsonl --clip mc_001.mp4 \\
        --game minecraft --end 42.5 --tip --obs night_falling --good "Find shelter before night"

Providers are written as name or name:model (e.g. anthropic:claude-haiku-5-5). Any paid
provider or judge needs --yes, and the run stops once estimated spend passes --max-cost.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from ..config import DEFAULT_MODELS, load_env_file
from ..providers import VisionModelProvider, create_provider
from ..providers.pricing import estimate_cost, is_priced
from .dataset import CaseLabels, EvalCase, append_case, clips_dir_for, load_cases
from .judge import create_judge
from .report import write_report
from .runner import CaseResult, RunOptions, run_eval

log = logging.getLogger("gamesense.evals")

# Rough per-call token use (see docs/model-selection.md), for the pre-run estimate.
_EST_IN, _EST_OUT = 3100, 250
_EST_JUDGE_IN, _EST_JUDGE_OUT = 3600, 150


def find_evals_dir(start: Path | None = None) -> Path:
    here = (start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        if (folder / "evals" / "datasets").is_dir():
            return folder / "evals"
    return here / "evals"


def parse_provider(spec: str) -> tuple[str, str]:
    name, _, model = spec.strip().partition(":")
    if name not in DEFAULT_MODELS:
        raise SystemExit(f"unknown provider {name!r}; choose from {', '.join(DEFAULT_MODELS)}")
    return name, model or DEFAULT_MODELS[name]


def estimate_run_cost(
    providers: list[tuple[str, str]], n_cases: int, repeats: int, judge_model: str | None
) -> float:
    calls = n_cases * repeats
    total = sum(estimate_cost(model, _EST_IN, _EST_OUT) * calls for _, model in providers)
    if judge_model:
        # Assume roughly half the calls produce a tip that needs judging.
        paid_calls = calls * len(providers) / 2
        total += estimate_cost(judge_model, _EST_JUDGE_IN, _EST_JUDGE_OUT) * paid_calls
    return total


def _print_result(r: CaseResult) -> None:
    status = "ok " if r.ok else "ERR"
    tip = f'tip="{r.tip_message}"' if r.tip_shown else "silent"
    extra = r.error or ""
    print(
        f"  [{status}] {r.provider}:{r.model} {r.case_id} {tip} "
        f"({r.latency_ms or '-'} ms, ${r.cost_usd:.5f}) {extra}",
        file=sys.stderr,
        flush=True,
    )


async def _run(args: argparse.Namespace) -> int:
    evals_dir = find_evals_dir()
    dataset = Path(args.dataset) if args.dataset else evals_dir / "datasets"
    cases = load_cases(dataset)
    if args.case:
        wanted = set(args.case)
        cases = [c for c in cases if c.id in wanted]
    if args.game:
        cases = [c for c in cases if c.game in args.game]
    if not cases:
        print(f"no cases found in {dataset}", file=sys.stderr)
        return 1
    specs = [parse_provider(s) for s in args.providers.split(",") if s.strip()]
    judge = create_judge(args.judge)
    judge_model = getattr(judge, "model", None)

    paid = [f"{n}:{m}" for n, m in specs if n != "mock"]
    if judge_model:
        paid.append(f"judge {judge_model}")
    unpriced = [m for n, m in specs if n != "mock" and not is_priced(m)]
    estimate = estimate_run_cost(
        [(n, m) for n, m in specs if n != "mock"], len(cases), args.repeats, judge_model
    )
    print(
        f"{len(cases)} case(s) x {len(specs)} model(s) x {args.repeats} repeat(s). "
        f"Estimated spend: ${estimate:.4f} (cap ${args.max_cost:.2f}).",
        file=sys.stderr,
    )
    if unpriced:
        print(f"warning: no price on file for {', '.join(unpriced)}", file=sys.stderr)
    if paid and not args.yes:
        print(
            f"This run calls paid APIs ({', '.join(paid)}). Re-run with --yes to go ahead.",
            file=sys.stderr,
        )
        return 2

    providers: list[VisionModelProvider] = [create_provider(n, m) for n, m in specs]
    clips_dir = Path(args.clips) if args.clips else clips_dir_for(dataset)
    options = RunOptions(clips_dir=clips_dir, repeats=args.repeats, max_cost_usd=args.max_cost)
    started = datetime.now(UTC)
    try:
        results, stopped = await run_eval(cases, providers, judge, options, on_result=_print_result)
    finally:
        for p in providers:
            await p.aclose()

    out_dir = (
        Path(args.out) if args.out else evals_dir / "reports" / started.strftime("%Y%m%d-%H%M%S")
    )
    meta = {
        "started": started.isoformat(timespec="seconds"),
        "dataset": str(dataset),
        "cases": len(cases),
        "repeats": args.repeats,
        "judge": judge.name if judge else "none",
        "providers": [f"{n}:{m}" for n, m in specs],
        "stopped": stopped,
    }
    summaries = write_report(out_dir, results, meta)
    if stopped:
        print(stopped, file=sys.stderr)
    for s in summaries:
        silence = "n/a" if s.silence_accuracy is None else f"{s.silence_accuracy:.0%}"
        useful = "n/a" if s.usefulness is None else f"{s.usefulness:.2f}"
        print(
            f"{s.provider}:{s.model}: valid {s.schema_valid_rate:.0%}, silence {silence}, "
            f"useful {useful}, p95 {s.latency_p95_ms} ms, ${s.cost_per_hour_usd:.2f}/h"
        )
    print(f"report: {out_dir / 'report.md'}")
    return 0


def _add_case(args: argparse.Namespace) -> int:
    path = Path(args.dataset)
    start = args.start if args.start is not None else max(0.0, args.end - args.warmup)
    case_id = args.id or f"{args.game}_{Path(args.clip).stem}_{int(args.end * 10):05d}"
    case = EvalCase(
        id=case_id,
        game=args.game,
        clip=args.clip,
        start_s=start,
        end_s=args.end,
        tags=args.tag or [],
        labels=CaseLabels(
            expect_tip=args.tip,
            observations=args.obs or [],
            activity=args.activity,
            good_tips=args.good or [],
            bad_tips=args.bad or [],
            notes=args.notes or "",
        ),
    )
    append_case(path, case)
    print(f"added {case.id} to {path}")
    return 0


def _record(args: argparse.Namespace) -> int:
    from ..__main__ import build_source
    from ..capture import FrameRingBuffer
    from ..config import Settings
    from .record import record

    settings = Settings(
        capture="replay" if args.replay else "window",
        replay=args.replay,
        window=args.window,
        sample_fps=args.fps,
        max_width=args.max_width,
        loop=False,
    )
    buffer = FrameRingBuffer(capacity=8)
    if settings.capture == "window" and sys.platform != "win32":
        print(
            "live recording needs Windows; use --replay to re-cut an existing video",
            file=sys.stderr,
        )
        return 1
    source = build_source(settings, buffer)
    assert source is not None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(args.out) if args.out else find_evals_dir() / "clips" / f"{args.game}_{stamp}.mp4"
    print(
        f"Recording {args.seconds:.0f}s to {out}. Press Enter to mark a moment, Ctrl+C to stop.",
        file=sys.stderr,
    )
    try:
        path, marks = record(source, buffer, out, seconds=args.seconds, fps=args.fps)
    except KeyboardInterrupt:
        print("stopped", file=sys.stderr)
        return 130
    print(f"saved {path}" + (f" with {len(marks)} mark(s)" if marks else ""))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="gamesense-eval", description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--log-level", default="WARNING")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="score providers on the labeled cases")
    run.add_argument("--dataset", help="a .jsonl file or folder (default: evals/datasets)")
    run.add_argument("--clips", help="clips folder (default: evals/clips)")
    run.add_argument("--providers", default="mock", help="comma-separated name[:model] list")
    run.add_argument("--judge", default="heuristic", help="none, heuristic or anthropic[:model]")
    run.add_argument("--repeats", type=int, default=1)
    run.add_argument("--case", action="append", help="only this case id (repeatable)")
    run.add_argument("--game", action="append", help="only this game id (repeatable)")
    run.add_argument("--max-cost", type=float, default=1.0, help="stop once spend passes this")
    run.add_argument("--yes", action="store_true", help="allow calls to paid APIs")
    run.add_argument("--out", help="report folder (default: evals/reports/<timestamp>)")

    add = sub.add_parser("add-case", help="append a labeled case to a dataset")
    add.add_argument("--dataset", required=True)
    add.add_argument("--clip", required=True, help="file name inside evals/clips")
    add.add_argument("--game", required=True)
    add.add_argument("--end", type=float, required=True, help="decision moment, in seconds")
    add.add_argument("--start", type=float, help="default: end minus --warmup")
    add.add_argument("--warmup", type=float, default=3.0)
    add.add_argument("--id")
    tip = add.add_mutually_exclusive_group(required=True)
    tip.add_argument("--tip", dest="tip", action="store_true", help="a coach should speak")
    tip.add_argument("--no-tip", dest="tip", action="store_false", help="a coach should be quiet")
    add.add_argument("--obs", action="append", help="expected observation type (repeatable)")
    add.add_argument("--activity")
    add.add_argument("--good", action="append", help="an example good tip (repeatable)")
    add.add_argument("--bad", action="append", help="an example bad tip (repeatable)")
    add.add_argument("--notes")
    add.add_argument("--tag", action="append")

    rec = sub.add_parser("record", help="record gameplay to evals/clips (Windows)")
    rec.add_argument("--game", default="generic", help="used in the file name")
    rec.add_argument("--window", help="window title substring (default: foreground window)")
    rec.add_argument("--replay", help="re-cut an existing video instead of capturing")
    rec.add_argument("--seconds", type=float, default=120.0)
    rec.add_argument("--fps", type=float, default=10.0)
    rec.add_argument("--max-width", type=int, default=1280)
    rec.add_argument("--out")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    load_env_file()
    args = parse_args(argv)
    logging.basicConfig(level=args.log_level.upper(), stream=sys.stderr)
    if args.command == "run":
        code = asyncio.run(_run(args))
    elif args.command == "add-case":
        code = _add_case(args)
    else:
        code = _record(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
