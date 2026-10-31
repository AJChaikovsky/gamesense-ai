"""CS2 Game State Integration: parsing, rules, receiver, installer and replay.

The fixtures in fixtures/cs2_gsi are recorded-format payload sequences (see the
README there), replayed with their original timing against a fake clock.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from gamesense.capture import FrameRingBuffer
from gamesense.coaching import CoachingLoop
from gamesense.games import game_by_id
from gamesense.providers.mock import MockProvider
from gamesense.telemetry import TelemetryServer
from gamesense.telemetry.cli import load_recording, replay
from gamesense.telemetry.cs2 import (
    Cs2Feed,
    find_cs2_cfg_dir,
    install,
    load_or_create_token,
    observation_values,
    parse_state,
)
from gamesense.telemetry.cs2.install import render_config
from gamesense_contracts import CoachingDecision, TipEvent

FIXTURES = Path(__file__).parent / "fixtures" / "cs2_gsi"
TOKEN = "gsi-test-token"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _rows(name: str) -> list[tuple[float, dict[str, Any]]]:
    return [(t, {**p, "auth": {"token": TOKEN}}) for t, p in load_recording(FIXTURES / name)]


def _play(name: str, deliver: Any = None) -> tuple[list[tuple[float, CoachingDecision]], Cs2Feed]:
    """Replay a fixture through a feed; returns (time, tip) for every delivered tip."""
    clock = FakeClock()
    delivered: list[tuple[float, CoachingDecision]] = []

    def accept(decision: CoachingDecision) -> bool:
        ok = deliver(decision, clock.now) if deliver else True
        if ok:
            delivered.append((round(clock.now - 1000.0, 3), decision))
        return bool(ok)

    feed = Cs2Feed(TOKEN, accept, clock=clock)
    for t, payload in _rows(name):
        clock.now = 1000.0 + t
        assert feed.handle(payload) == 200
    return delivered, feed


# -- parsing ------------------------------------------------------------------------
def test_parse_is_lenient_about_types_and_missing_sections() -> None:
    s = parse_state(
        {
            "provider": {"steamid": "1"},
            "map": {"mode": "competitive", "round": "4", "phase": "live"},
            "player": {"steamid": "1", "state": {"health": "37", "helmet": "true", "money": None}},
            "phase_countdowns": {"phase_ends_in": "4.5"},
        }
    )
    assert s.map_round == 4 and s.health == 37 and s.helmet is True and s.money is None
    assert s.phase_ends_in == 4.5 and s.is_self and s.alive and s.weapons == ()
    assert parse_state({}).is_self is False
    assert parse_state({"player": "garbage", "map": []}).health is None


@pytest.mark.parametrize(
    ("mode", "rnd", "pistol", "last"),
    [
        ("competitive", 0, True, False),
        ("competitive", 11, False, True),
        ("competitive", 12, True, False),
        ("competitive", 23, False, True),
        ("competitive", 26, False, True),  # last round of the first overtime half
        ("competitive", 27, False, False),
        ("scrimcomp2v2", 7, False, True),
        ("casual", 11, False, False),
    ],
)
def test_round_math(mode: str, rnd: int, pistol: bool, last: bool) -> None:
    s = parse_state({"map": {"mode": mode, "round": rnd}})
    assert s.is_pistol_round is pistol and s.is_last_round_of_half is last


def test_spectated_player_is_not_treated_as_self() -> None:
    _, feed = _play("ct_dead_spectating.jsonl")
    assert feed.state is not None and not feed.state.is_self and not feed.state.alive
    assert "health" not in observation_values(feed.state)
    assert feed.facts() == ["Player is dead or spectating"]


# -- rules --------------------------------------------------------------------------
def test_ct_round_rules_fire_once_each_at_the_right_moment() -> None:
    delivered, _ = _play("ct_forgot_armor.jsonl")
    actions = [(t, d.action) for t, d in delivered]
    assert actions == [
        (9.4, "buy_armor"),  # waits until freeze time is nearly over
        (9.4, "buy_defuse_kit"),
        (52.3, "play_for_trades_low_hp"),
        (66.0, "clear_site_before_defuse"),
    ]
    armor = delivered[0][1]
    assert armor.priority == "important" and armor.id.startswith("rule_")
    assert {c.observation_type for c in armor.valid_while} == {"armor", "money"}
    assert armor.expires_in_seconds == 14  # 5.6 s of freeze time + 8 s of buy time


def test_t_side_last_round_of_half_and_post_plant() -> None:
    delivered, _ = _play("t_last_round_of_half.jsonl")
    assert [d.action for _, d in delivered] == ["spend_last_round_of_half", "hold_post_plant"]


@pytest.mark.parametrize("name", ["ct_dead_spectating.jsonl", "warmup_and_menu.jsonl"])
def test_no_tips_when_dead_in_warmup_or_in_menus(name: str) -> None:
    delivered, _ = _play(name)
    assert delivered == []


def test_a_held_back_tip_is_offered_again_on_the_next_update() -> None:
    first_call = {"kit": True}

    def deliver(d: CoachingDecision, now: float) -> bool:
        if d.action == "buy_defuse_kit" and first_call["kit"]:
            first_call["kit"] = False
            return False  # e.g. the cooldown said too soon
        return True

    delivered, _ = _play("ct_forgot_armor.jsonl", deliver)
    assert (13.1, "buy_defuse_kit") in [(t, d.action) for t, d in delivered]


# -- feed ---------------------------------------------------------------------------
def test_feed_rejects_wrong_token_and_tracks_connection() -> None:
    clock = FakeClock()
    feed = Cs2Feed(TOKEN, lambda d: True, clock=clock)
    payload = _rows("ct_forgot_armor.jsonl")[0][1]
    assert feed.handle({**payload, "auth": {"token": "nope"}}) == 401
    assert feed.handle({k: v for k, v in payload.items() if k != "auth"}) == 401
    assert feed.state is None and feed.rejected == 2 and not feed.connected()
    assert feed.handle(payload) == 200 and feed.connected()
    assert "Money $4750" in feed.facts() and feed.observations()["money"] == 4750
    clock.now += 31
    assert not feed.connected() and feed.facts() == [] and feed.observations() == {}


def test_recording_round_trips_without_the_token(tmp_path: Path) -> None:
    out = tmp_path / "rec" / "round.jsonl"
    clock = FakeClock()
    feed = Cs2Feed(TOKEN, lambda d: True, record_path=out, clock=clock)
    for t, payload in _rows("ct_forgot_armor.jsonl")[:3]:
        clock.now = 1000.0 + t
        feed.handle(payload)
    feed.close()
    assert TOKEN not in out.read_text()
    rows = load_recording(out)
    assert [t for t, _ in rows] == [0.0, 6.2, 9.4]
    assert rows[1][1]["player"]["state"]["money"] == 1850


# -- coaching loop integration -----------------------------------------------------
def _loop(game: str = "cs2") -> tuple[CoachingLoop, list[Any]]:
    events: list[Any] = []
    loop = CoachingLoop(
        FrameRingBuffer(capacity=4),
        MockProvider(latency_s=0),
        events.append,
        fixed_game=game_by_id(game),
        detect_foreground=lambda: None,
    )
    return loop, events


def test_rule_tips_go_through_the_coach_cooldown() -> None:
    loop, events = _loop()
    delivered, feed = _play("ct_forgot_armor.jsonl", lambda d, now: loop.submit_local(d, now))
    loop.telemetry = feed
    # The kit tip lands 0 s after the armor tip, then again 3.7 s later: both too soon.
    assert [d.action for _, d in delivered] == [
        "buy_armor",
        "play_for_trades_low_hp",
        "clear_site_before_defuse",
    ]
    assert [e.decision.action for e in events if isinstance(e, TipEvent)] == [
        d.action for _, d in delivered
    ]
    assert loop.suppressed["too_soon"] == 2
    status = loop.status()
    assert status.local_tips == 3 and status.tips_delivered == 3 and status.calls == 0


def test_rule_tips_respect_pause() -> None:
    loop, events = _loop()
    loop.paused = True
    delivered, _ = _play("ct_forgot_armor.jsonl", lambda d, now: loop.submit_local(d, now))
    assert delivered == [] and events == []


async def test_model_prompt_gets_live_game_data() -> None:
    seen: list[str] = []

    class Spy(MockProvider):
        async def analyze(self, request: Any) -> Any:
            seen.append(request.context)
            return await super().analyze(request)

    import numpy as np
    from gamesense.capture import Frame

    loop = CoachingLoop(
        FrameRingBuffer(capacity=4),
        Spy(latency_s=0),
        lambda e: None,
        fixed_game=game_by_id("cs2"),
        detect_foreground=lambda: None,
    )
    _, feed = _play("ct_forgot_armor.jsonl")
    feed.clock = lambda: 1000.0 + 80  # still fresh
    loop.telemetry = feed
    for i, v in enumerate([0, 200]):
        img = np.full((90, 160, 3), v, np.uint8)
        loop.buffer.append(Frame(id=f"f{i}", index=i, timestamp=float(i), image=img))
        await loop.tick(float(i))
    await asyncio.sleep(0.01)
    assert seen and "Live game data (exact, reported by the game)" in seen[0]
    assert "Map de_mirage (competitive)" in seen[0]
    assert loop.status().telemetry == "cs2_gsi"


# -- HTTP receiver -----------------------------------------------------------------
async def _post(port: int, body: bytes, *, extra: str = "", method: str = "POST") -> int:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(
        f"{method} / HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\n{extra}\r\n".encode()
        + body
    )
    await writer.drain()
    status_line = await reader.readline()
    writer.close()
    return int(status_line.split()[1])


async def test_receiver_accepts_gsi_posts_and_keeps_connections_alive() -> None:
    got: list[dict[str, Any]] = []
    server = TelemetryServer(lambda p: got.append(p) or 200, port=0)
    port = await server.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        for i in range(2):  # two requests on one keep-alive connection, like CS2
            body = json.dumps({"n": i}).encode()
            writer.write(
                b"POST / HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
                + body
            )
            await writer.drain()
            assert (await reader.readline()).startswith(b"HTTP/1.1 200")
            while (await reader.readline()) != b"\r\n":
                pass
        writer.close()
        assert [p["n"] for p in got] == [0, 1]
        assert await _post(port, b"not json") == 400
        assert await _post(port, b"[1, 2]") == 400
        assert await _post(port, b"", method="GET") == 405
        assert await _post(port, b"{}", extra="X-Ignored: yes\r\n") == 200
    finally:
        await server.stop()


async def test_receiver_rejects_oversized_bodies() -> None:
    server = TelemetryServer(lambda p: 200, port=0)
    port = await server.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"POST / HTTP/1.1\r\nContent-Length: 99999999\r\n\r\n")
        await writer.drain()
        assert (await reader.readline()).startswith(b"HTTP/1.1 413")
        writer.close()
    finally:
        await server.stop()


async def test_replay_cli_drives_a_running_feed(tmp_path: Path) -> None:
    loop, events = _loop()
    feed = Cs2Feed(TOKEN, loop.submit_local)
    server = TelemetryServer(feed.handle, port=0)
    port = await server.start()
    try:
        code = await asyncio.to_thread(
            replay, FIXTURES / "ct_forgot_armor.jsonl", port=port, speed=1000.0, token=TOKEN
        )
        bad = await asyncio.to_thread(
            replay, FIXTURES / "ct_forgot_armor.jsonl", port=port, speed=1000.0, token="wrong"
        )
    finally:
        await server.stop()
    assert code == 0 and bad == 1 and feed.updates == 9
    # Replayed in well under a second, so the cooldown lets only the first tip through.
    assert [e.decision.action for e in events if isinstance(e, TipEvent)] == ["buy_armor"]


# -- installer ----------------------------------------------------------------------
def test_config_and_token(tmp_path: Path) -> None:
    token = load_or_create_token(tmp_path)
    assert token == load_or_create_token(tmp_path) and len(token) >= 24
    cfg = render_config(token, 4000)
    assert '"uri" "http://127.0.0.1:4000/"' in cfg and f'"token" "{token}"' in cfg
    assert '"player_state" "1"' in cfg and "allplayers" not in cfg
    assert cfg.count("{") == cfg.count("}")


def test_finds_cs2_in_a_secondary_steam_library(tmp_path: Path) -> None:
    steam = tmp_path / "Steam"
    (steam / "steamapps").mkdir(parents=True)
    library = tmp_path / "Games" / "SteamLibrary"
    cfg_dir = library / "steamapps/common/Counter-Strike Global Offensive/game/csgo/cfg"
    cfg_dir.mkdir(parents=True)
    escaped = str(library).replace("\\", "\\\\")
    (steam / "steamapps" / "libraryfolders.vdf").write_text(
        f'"libraryfolders"\n{{\n\t"0"\n\t{{\n\t\t"path"\t\t"{steam}"\n\t}}\n'
        f'\t"1"\n\t{{\n\t\t"path"\t\t"{escaped}"\n\t}}\n}}\n'
    )
    assert find_cs2_cfg_dir([tmp_path / "missing", steam]) == cfg_dir
    written = install(cfg_dir, "tok", 3727)
    assert written.name == "gamestate_integration_gamesense.cfg" and "tok" in written.read_text()
    assert find_cs2_cfg_dir([tmp_path / "missing"]) is None


def test_engine_attaches_the_gsi_receiver() -> None:
    from gamesense.__main__ import build_engine
    from gamesense.config import Settings

    engine = build_engine(Settings(capture="none", gsi_port=45127))
    assert engine.telemetry_server is not None and engine.telemetry_server.port == 45127
    assert engine.coaching is not None and engine.coaching.telemetry is not None
    off = build_engine(Settings(capture="none", gsi_port=0))
    assert off.telemetry_server is None
