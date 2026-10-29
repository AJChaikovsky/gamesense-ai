"""Labeled eval cases, stored as JSONL under ``evals/datasets/``.

One line per case. A case points at a moment in a clip: the model sees the frames
just before ``end_s``, as the live coach would at that instant. Labels say what a
good coach should notice and whether it should speak at all.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaseLabels(_Strict):
    expect_tip: bool = Field(description="Should a good coach say something at this moment?")
    observations: list[str] = Field(
        default_factory=list,
        description=(
            'Facts a good coach should notice, as snake_case types, e.g. "health_low". '
            'Use "|" for accepted alternatives, e.g. "night|nightfall".'
        ),
    )
    activity: str | None = Field(default=None, description='e.g. "combat", "menu".')
    good_tips: list[str] = Field(default_factory=list, description="Examples of helpful tips.")
    bad_tips: list[str] = Field(
        default_factory=list, description="Tips that would be wrong, unhelpful or ungrounded."
    )
    notes: str = Field(default="", description="What is happening, for the judge and humans.")


class EvalCase(_Strict):
    id: str
    game: str = Field(description="Game id, e.g. cs2, fromsoft_rpg, minecraft, generic.")
    clip: str = Field(description="Clip path, relative to the dataset file's clips folder.")
    start_s: float = Field(ge=0.0, description="Warm-up start; the fast path runs from here.")
    end_s: float = Field(gt=0.0, description="The decision moment.")
    labels: CaseLabels
    tags: list[str] = Field(default_factory=list)


def clips_dir_for(dataset: Path) -> Path:
    """Clips live in ``evals/clips/`` next to ``evals/datasets/`` (file or folder)."""
    folder = dataset.resolve() if dataset.is_dir() else dataset.resolve().parent
    return folder.parent / "clips"


def load_cases(path: Path) -> list[EvalCase]:
    """Load one JSONL file, or every ``*.jsonl`` file in a folder."""
    files = sorted(path.glob("*.jsonl")) if path.is_dir() else [path]
    cases: list[EvalCase] = []
    seen: set[str] = set()
    for file in files:
        for lineno, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip() or line.lstrip().startswith("//"):
                continue
            try:
                case = EvalCase.model_validate_json(line)
            except ValueError as exc:
                raise ValueError(f"{file}:{lineno}: invalid case: {exc}") from exc
            if case.end_s <= case.start_s:
                raise ValueError(f"{file}:{lineno}: end_s must be after start_s")
            if case.id in seen:
                raise ValueError(f"{file}:{lineno}: duplicate case id {case.id!r}")
            seen.add(case.id)
            cases.append(case)
    return cases


def append_case(path: Path, case: EvalCase) -> None:
    existing = {c.id for c in load_cases(path)} if path.exists() else set()
    if case.id in existing:
        raise ValueError(f"case id {case.id!r} already exists in {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(case.model_dump(mode="json", exclude_defaults=False)) + "\n")
