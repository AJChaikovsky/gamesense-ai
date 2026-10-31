"""Knowledge packs: loading, FTS5 retrieval, and their place in prompt assembly."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from gamesense.capture import Frame, FrameRingBuffer
from gamesense.coaching import CoachingLoop
from gamesense.games import game_by_id
from gamesense.knowledge import KnowledgeBase, PackError, default_knowledge_dir, parse_doc
from gamesense.knowledge.cli import check
from gamesense.knowledge.index import query_terms
from gamesense.knowledge.pack import split_sections
from gamesense.providers.mock import MockProvider
from gamesense.providers.prompt import system_prompt
from gamesense.telemetry.cs2 import parse_state

ROOT = default_knowledge_dir()


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    assert ROOT is not None
    return KnowledgeBase.load(ROOT)


def test_repo_packs_pass_the_checks() -> None:
    assert ROOT is not None and ROOT.name == "knowledge"
    assert check(ROOT) == []


def test_every_launch_game_has_core_and_topics(kb: KnowledgeBase) -> None:
    assert {"cs2", "fromsoft_rpg", "minecraft"} <= kb.games
    for game in ("cs2", "fromsoft_rpg", "minecraft"):
        assert 200 < len(kb.core(game)) <= 1500
    assert kb.core("generic") == ""


@pytest.mark.parametrize(
    ("game", "text", "heading"),
    [
        ("cs2", "post plant", "Post-plant as T"),
        ("cs2", "retake defuse", "Retakes and defusing as CT"),
        ("cs2", "last round of the half", "Last round of the half"),
        ("cs2", "spray recoil", "Spray control"),
        ("minecraft", "creeper_visible true", "Creepers"),
        ("minecraft", "enderman nearby", "Endermen"),
        ("minecraft", "lava below", "Lava safety"),
        ("fromsoft_rpg", "boss_fight heal flask", "When to heal"),
        ("fromsoft_rpg", "stamina empty", "Stamina management"),
    ],
)
def test_search_finds_the_right_section(
    kb: KnowledgeBase, game: str, text: str, heading: str
) -> None:
    hits = kb.search(game, query_terms([text]), limit=3)
    assert heading in [h.chunk.heading for h in hits]
    assert all(h.chunk.game == game for h in hits)


def test_query_terms_are_safe_plain_words() -> None:
    terms = query_terms(['health_low "OR 1=1; DROP TABLE chunks', "the 100 hp", "zombie zombie"])
    assert terms == ["health", "low", "drop", "table", "chunks", "zombie"]


def test_hostile_text_cannot_break_the_query(kb: KnowledgeBase) -> None:
    assert isinstance(kb.for_situation("cs2", ['") OR chunks MATCH ("*', "NEAR(a b)"]), list)


def test_snippets_respect_the_character_budget(kb: KnowledgeBase) -> None:
    snippets = kb.for_situation("cs2", ["buy economy money eco force save"], max_chars=500)
    assert snippets and sum(len(s) for s in snippets) <= 500
    assert snippets[0].startswith("[")


def test_missing_folder_gives_an_empty_knowledge_base(tmp_path: Path) -> None:
    kb = KnowledgeBase.load(tmp_path / "nope")
    assert kb.core("cs2") == "" and kb.for_situation("cs2", ["buy"]) == []


def test_parse_errors_are_reported(tmp_path: Path) -> None:
    (tmp_path / "cs2").mkdir()
    bad = tmp_path / "cs2" / "bad.md"
    bad.write_text("## no front matter\n")
    with pytest.raises(PackError, match="front matter"):
        parse_doc(bad, tmp_path)
    bad.write_text("---\ntitle: x\ngame: cs2\n---\nbody\n")
    with pytest.raises(PackError, match="source"):
        parse_doc(bad, tmp_path)
    (tmp_path / "cs2" / "ok.md").write_text(
        "---\ntitle: t\ngame: minecraft\nsource: s\nversion: v\nupdated: u\n---\n## A\n"
        + "x " * 400
    )
    bad.unlink()
    problems = check(tmp_path)
    assert any("does not match folder" in p for p in problems)
    assert any("chars (max 700)" in p for p in problems)


def test_sections_split_on_level_two_headings() -> None:
    assert split_sections("intro\n## A\none\n### sub\n## B\ntwo") == [
        ("Overview", "intro"),
        ("A", "one\n### sub"),
        ("B", "two"),
    ]


def test_cs2_state_topics() -> None:
    def state(**kw: Any) -> Any:
        player = {"steamid": "1", "team": kw.get("team", "CT"), "activity": "playing",
                  "state": {"health": kw.get("health", 100)}}  # fmt: skip
        return parse_state(
            {
                "provider": {"steamid": "1"},
                "map": {"mode": "competitive", "phase": "live", "round": kw.get("rnd", 3)},
                "round": {"phase": kw.get("phase", "live"), "bomb": kw.get("bomb")},
                "player": player,
            }
        )

    assert state(phase="freezetime", rnd=11).topics() == [
        "buy economy money",
        "last round of the half",
    ]
    assert state(health=20).topics() == ["low health"]
    assert state(bomb="planted", team="T").topics() == ["post plant"]
    assert state(bomb="planted").topics() == ["retake defuse"]
    assert state(health=0).topics() == []


# -- prompt assembly ----------------------------------------------------------------
def test_core_knowledge_is_in_the_cacheable_system_prompt(kb: KnowledgeBase) -> None:
    prompt = system_prompt(game_by_id("cs2"), kb.core("cs2"))
    assert "Key facts for this game" in prompt and "40 s after the plant" in prompt
    assert prompt == system_prompt(game_by_id("cs2"), kb.core("cs2"))  # stable prefix
    assert "Key facts" not in system_prompt(game_by_id("generic"), kb.core("generic"))


class Topics:
    source = "fake"

    def connected(self) -> bool:
        return True

    def facts(self) -> list[str]:
        return ["Bomb planted"]

    def topics(self) -> list[str]:
        return ["post plant"]

    def observations(self) -> dict[str, Any]:
        return {}

    def in_combat(self) -> bool | None:
        return None

    def close(self) -> None:
        return None


async def test_live_requests_carry_core_and_situational_knowledge(kb: KnowledgeBase) -> None:
    seen: list[Any] = []

    class Spy(MockProvider):
        async def analyze(self, request: Any) -> Any:
            seen.append(request)
            return await super().analyze(request)

    loop = CoachingLoop(
        FrameRingBuffer(capacity=4),
        Spy(latency_s=0),
        lambda e: None,
        fixed_game=game_by_id("cs2"),
        detect_foreground=lambda: None,
        knowledge=kb,
    )
    loop.telemetry = Topics()
    for i, v in enumerate([0, 200]):
        img = np.full((90, 160, 3), v, np.uint8)
        loop.buffer.append(Frame(id=f"f{i}", index=i, timestamp=float(i), image=img))
        await loop.tick(float(i))
    await asyncio.sleep(0.01)
    assert seen
    assert "Key facts for this game" in seen[0].system_prompt
    assert "Relevant game knowledge" in seen[0].context
    assert "[Post-plant as T]" in seen[0].context


def test_eval_requests_use_the_same_core_knowledge(kb: KnowledgeBase) -> None:
    from gamesense.evals.runner import build_request
    from gamesense.perception import Signals

    class Case:
        game = "minecraft"

    class Frames:
        jpegs = (b"x",)
        signals = Signals(frame_id="f0", timestamp=0.0, scene_change=0.0, activity=0.0)

    req = build_request(Case(), Frames(), kb)  # type: ignore[arg-type]
    assert kb.core("minecraft") in req.system_prompt
