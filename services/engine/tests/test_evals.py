from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import cv2
import pytest
from gamesense.capture import FrameRingBuffer, ReplaySource
from gamesense.evals.cli import estimate_run_cost, main
from gamesense.evals.dataset import CaseLabels, EvalCase, append_case, load_cases
from gamesense.evals.frames import extract
from gamesense.evals.judge import HeuristicJudge
from gamesense.evals.record import record
from gamesense.evals.report import percentile, summarize
from gamesense.evals.runner import CaseResult, RunOptions, run_eval
from gamesense.evals.scoring import observation_matches, perception_recall, tip_shown
from gamesense.providers import LiveAnalysis, LiveObservation, LiveTip
from gamesense.providers.mock import MockProvider
from gamesense.tools.make_sample_clip import make_clip

REPO = Path(__file__).resolve().parents[3]
SAMPLE_DATASET = REPO / "evals" / "datasets" / "sample.jsonl"


@pytest.fixture(scope="module")
def evals_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A throwaway evals/ folder with the committed sample dataset and a fresh clip."""
    root = tmp_path_factory.mktemp("repo") / "evals"
    (root / "datasets").mkdir(parents=True)
    shutil.copy(SAMPLE_DATASET, root / "datasets" / "sample.jsonl")
    make_clip(root / "clips" / "sample.mp4", seconds=5.0, fps=10)
    return root


def _analysis(types: list[str], confidence: float | None = 0.8) -> LiveAnalysis:
    tip = None
    if confidence is not None:
        tip = LiveTip(
            category="survivability",
            action="heal_now",
            message="Back off and heal",
            detail=None,
            priority="important",
            confidence=confidence,
            expires_in_seconds=8,
            valid_while=[],
            evidence=types[:1],
        )
    return LiveAnalysis(
        activity="combat",
        observations=[
            LiveObservation(type=t, value="true", confidence=0.9, kind="observed") for t in types
        ],
        unknowns=[],
        tip=tip,
    )


def test_sample_dataset_is_valid() -> None:
    cases = load_cases(SAMPLE_DATASET)
    assert {c.id for c in cases} == {"sample_damage_flash", "sample_quiet"}


def test_load_cases_rejects_bad_rows(tmp_path: Path) -> None:
    good = SAMPLE_DATASET.read_text().splitlines()[0]
    dup = tmp_path / "dup.jsonl"
    dup.write_text(f"{good}\n{good}\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_cases(dup)
    backwards = tmp_path / "backwards.jsonl"
    row = json.loads(good) | {"start_s": 5.0, "end_s": 4.0}
    backwards.write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="end_s"):
        load_cases(backwards)


def test_append_case_refuses_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "mc.jsonl"
    case = EvalCase(
        id="c1",
        game="minecraft",
        clip="mc.mp4",
        start_s=0,
        end_s=3,
        labels=CaseLabels(expect_tip=False),
    )
    append_case(path, case)
    with pytest.raises(ValueError):
        append_case(path, case)
    assert [c.id for c in load_cases(path)] == ["c1"]


@pytest.mark.parametrize(
    ("label", "predicted", "expected"),
    [
        ("health_low", "low_health", True),
        ("health_low", "player_health_low", True),
        ("health_low", "health_full", False),
        ("night|nightfall", "nightfall_soon", True),
        ("enemy_visible", "enemy", False),
    ],
)
def test_observation_matching(label: str, predicted: str, expected: bool) -> None:
    assert observation_matches(label, predicted) is expected


def test_perception_recall_and_tip_shown() -> None:
    labels = CaseLabels(expect_tip=True, observations=["health_low", "enemy_visible"])
    assert perception_recall(labels, _analysis(["low_health", "sunset"])) == 0.5
    assert perception_recall(labels, None) == 0.0
    assert perception_recall(CaseLabels(expect_tip=False), _analysis([])) is None
    assert tip_shown(_analysis([], confidence=0.9))
    assert not tip_shown(_analysis([], confidence=0.3))
    assert not tip_shown(_analysis([], confidence=None))


async def test_heuristic_judge() -> None:
    judge = HeuristicJudge()
    labels = CaseLabels(expect_tip=True, good_tips=["Back off and heal"], bad_tips=["Push now"])
    case = EvalCase(id="c", game="generic", clip="x", start_s=0, end_s=1, labels=labels)
    assert (await judge.judge(case, _analysis(["hp"]), [])).usefulness == 5
    quiet = case.model_copy(update={"labels": CaseLabels(expect_tip=False)})
    assert (await judge.judge(quiet, _analysis(["hp"]), [])).usefulness == 1


def test_extract_frames_sees_the_damage_flash(evals_dir: Path) -> None:
    clip = evals_dir / "clips" / "sample.mp4"
    flash = extract(clip, 2.0, 4.25)
    quiet = extract(clip, 1.0, 3.0)
    assert len(flash.jpegs) == 2 and flash.jpegs[0][:2] == b"\xff\xd8"
    assert flash.frame_times == pytest.approx([4.0, 4.25])
    assert flash.signals.activity > 0.01 > quiet.signals.activity


async def test_run_eval_with_mock(evals_dir: Path) -> None:
    cases = load_cases(evals_dir / "datasets")
    options = RunOptions(clips_dir=evals_dir / "clips", repeats=2)
    results, stopped = await run_eval(cases, [MockProvider(latency_s=0)], HeuristicJudge(), options)
    assert stopped is None and len(results) == 4
    by_case = {r.case_id: r for r in results}
    assert by_case["sample_damage_flash"].tip_shown
    assert by_case["sample_damage_flash"].usefulness == 5
    assert not by_case["sample_quiet"].tip_shown
    [summary] = summarize(results)
    assert summary.silence_accuracy == 1.0 and summary.schema_valid_rate == 1.0
    assert summary.false_alarm_rate == 0.0 and summary.cost_per_hour_usd == 0.0


async def test_run_eval_stops_at_cost_cap(evals_dir: Path) -> None:
    class Pricey(MockProvider):
        async def analyze(self, request: Any) -> Any:
            result = await super().analyze(request)
            return type(result)(result.analysis, result.usage, result.latency_ms, 0.6)

    cases = load_cases(evals_dir / "datasets")
    options = RunOptions(clips_dir=evals_dir / "clips", max_cost_usd=1.0, repeats=3)
    results, stopped = await run_eval(cases, [Pricey(latency_s=0)], None, options)
    assert len(results) == 2 and stopped is not None


def test_summary_counts_errors_and_percentiles() -> None:
    ok = CaseResult("p", "m", "a", "generic", 0, True, latency_ms=100, silence_correct=True)
    bad = CaseResult("p", "m", "b", "generic", 0, False, error="boom")
    [s] = summarize([ok, bad])
    assert s.errors == 1 and s.schema_valid_rate == 0.5
    assert percentile([100, 200, 300, 400], 50) == 200
    assert percentile([100, 200, 300, 400], 95) == 400
    assert percentile([], 50) is None


def test_cli_run_writes_report(evals_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = evals_dir / "reports" / "test"
    with pytest.raises(SystemExit) as exit_info:
        main(["run", "--dataset", str(evals_dir / "datasets"), "--out", str(out)])
    assert exit_info.value.code == 0
    assert "mock:mock-coach" in (out / "report.md").read_text()
    summary = json.loads((out / "summary.json").read_text())
    assert summary["models"][0]["silence_accuracy"] == 1.0
    assert len((out / "results.jsonl").read_text().splitlines()) == 2


def test_cli_refuses_paid_run_without_yes(evals_dir: Path) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["run", "--dataset", str(evals_dir / "datasets"), "--providers", "anthropic"])
    assert exit_info.value.code == 2


def test_cost_estimate() -> None:
    assert estimate_run_cost([], 10, 1, None) == 0.0
    haiku = estimate_run_cost([("anthropic", "claude-haiku-5-5")], 10, 1, None)
    assert haiku == pytest.approx(10 * (3100 * 0.10 + 250 * 0.50) / 1e6)


def test_cli_add_case(tmp_path: Path) -> None:
    path = tmp_path / "mc.jsonl"
    argv = ["add-case", "--dataset", str(path), "--clip", "mc_001.mp4", "--game", "minecraft"]
    argv += ["--end", "42.5", "--tip", "--obs", "night_falling", "--good", "Find shelter"]
    with pytest.raises(SystemExit):
        main(argv)
    [case] = load_cases(path)
    assert case.id == "minecraft_mc_001_00425" and case.start_s == 39.5
    assert case.labels.expect_tip and case.labels.observations == ["night_falling"]


def test_record_from_replay(sample_clip: Path, tmp_path: Path) -> None:
    buffer = FrameRingBuffer(capacity=8)
    source = ReplaySource(str(sample_clip), buffer, sample_fps=10, loop=True)
    out, marks = record(
        source, buffer, tmp_path / "rec.mp4", seconds=1.0, fps=10, marks_from_stdin=False
    )
    cap = cv2.VideoCapture(str(out))
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    assert frames == 10 and marks == []


async def test_anthropic_judge_sends_frames_and_parses() -> None:
    from types import SimpleNamespace

    from gamesense.evals.judge import AnthropicJudge

    sent: dict[str, Any] = {}

    async def create(**kwargs: Any) -> Any:
        sent.update(kwargs)
        text = json.dumps({"usefulness": 4, "grounded": True, "reason": "fits the moment"})
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(input_tokens=3000, output_tokens=100),
        )

    judge = AnthropicJudge(client=SimpleNamespace(messages=SimpleNamespace(create=create)))
    case = load_cases(SAMPLE_DATASET)[0]
    verdict = await judge.judge(case, _analysis(["damage_taken"]), [b"\xff\xd8jpeg"])
    assert verdict.usefulness == 4 and verdict.grounded is True
    assert verdict.cost_usd == pytest.approx((3000 * 2 + 100 * 10) / 1e6)
    assert sent["model"] == "claude-sonnet-5-5"
    assert sent["messages"][0]["content"][0]["type"] == "image"
