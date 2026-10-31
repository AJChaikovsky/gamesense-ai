"""Known games, how to recognise them, and whether live coaching is allowed."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import Literal

Genre = Literal["fps", "rpg", "sandbox", "moba", "mmo", "other"]


@dataclass(frozen=True, slots=True)
class GameProfile:
    game_id: str
    name: str
    genre: Genre
    tier: Literal[1, 2, 3] = 1
    process_names: tuple[str, ...] = ()
    title_patterns: tuple[str, ...] = ()
    live_allowed: bool = True
    policy_reason: str | None = None
    coaching_focus: tuple[str, ...] = field(default_factory=tuple)

    def matches(self, process_name: str | None, title: str | None) -> bool:
        proc = (process_name or "").lower()
        if proc and proc in (p.lower() for p in self.process_names):
            if not self.title_patterns:
                return True
            return any(
                fnmatch.fnmatch((title or "").lower(), t.lower()) for t in self.title_patterns
            )
        return False


GENERIC = GameProfile(
    game_id="generic",
    name="Unrecognised game",
    genre="other",
    tier=1,
    coaching_focus=("survival", "positioning", "resource management"),
)

KNOWN_GAMES: tuple[GameProfile, ...] = (
    GameProfile(
        game_id="cs2",
        name="Counter-Strike 2",
        genre="fps",
        tier=3,  # official telemetry via Game State Integration (telemetry/cs2)
        process_names=("cs2.exe", "cs2"),
        coaching_focus=("economy", "crosshair placement", "utility", "positioning", "trading"),
    ),
    GameProfile(
        game_id="fromsoft_rpg",
        name="FromSoftware-style action RPG",
        genre="rpg",
        process_names=(
            "eldenring.exe",
            "nightreign.exe",
            "sekiro.exe",
            "darksoulsiii.exe",
            "darksoulsremastered.exe",
            "armoredcore6.exe",
        ),
        coaching_focus=("stamina management", "healing timing", "boss patterns", "spacing"),
    ),
    GameProfile(
        game_id="minecraft",
        name="Minecraft",
        genre="sandbox",
        process_names=("javaw.exe", "java", "minecraft.windows.exe"),
        title_patterns=("minecraft*",),
        coaching_focus=("survival", "hunger", "night safety", "progression", "inventory"),
    ),
    # Publisher policy: Riot prohibits third-party apps that draw gameplay conclusions
    # for players during play, so live coaching is blocked for its titles.
    GameProfile(
        game_id="league_of_legends",
        name="League of Legends",
        genre="moba",
        process_names=("league of legends.exe",),
        live_allowed=False,
        policy_reason="Riot Games does not allow live third-party gameplay advice.",
    ),
    GameProfile(
        game_id="valorant",
        name="VALORANT",
        genre="fps",
        process_names=("valorant-win64-shipping.exe",),
        live_allowed=False,
        policy_reason="Riot Games does not allow live third-party gameplay advice.",
    ),
)

_BY_ID = {g.game_id: g for g in (*KNOWN_GAMES, GENERIC)}


def detect_game(process_name: str | None, title: str | None) -> GameProfile:
    for game in KNOWN_GAMES:
        if game.matches(process_name, title):
            return game
    return GENERIC


def game_by_id(game_id: str) -> GameProfile:
    try:
        return _BY_ID[game_id]
    except KeyError as exc:
        raise ValueError(f"unknown game id {game_id!r}; known: {sorted(_BY_ID)}") from exc
