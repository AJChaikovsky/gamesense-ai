"""Parses CS2 Game State Integration payloads into a typed snapshot.

GSI payloads are loosely typed JSON (numbers sometimes arrive as strings, whole
sections disappear while dead or in menus), so parsing never raises: anything
missing becomes ``None`` and the rules treat it as unknown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# GSI weapon "type" values that count as a primary weapon.
PRIMARY_TYPES = frozenset({"Rifle", "SniperRifle", "Submachine Gun", "Shotgun", "Machine Gun"})
GUN_TYPES = PRIMARY_TYPES | {"Pistol"}

# Rounds per half by GSI map mode; modes not listed get no half-based rules.
HALF_LENGTH = {"competitive": 12, "scrimcomp2v2": 8}
OVERTIME_HALF = 3
# Modes with a real economy where buy and round rules make sense.
ECONOMY_MODES = frozenset({"competitive", "scrimcomp2v2", "casual"})


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1")
    if isinstance(value, int):
        return value != 0
    return None


@dataclass(frozen=True, slots=True)
class Weapon:
    name: str
    type: str | None
    state: str | None  # "active", "holstered", "reloading"
    ammo_clip: int | None = None
    ammo_clip_max: int | None = None
    ammo_reserve: int | None = None

    @property
    def is_gun(self) -> bool:
        return self.type in GUN_TYPES

    @property
    def clip_fraction(self) -> float | None:
        if self.ammo_clip is None or not self.ammo_clip_max:
            return None
        return self.ammo_clip / self.ammo_clip_max


@dataclass(frozen=True, slots=True)
class Cs2State:
    """One GSI update, from the point of view of the local player."""

    provider_steamid: str | None = None
    timestamp: int | None = None
    # map
    mode: str | None = None
    map_name: str | None = None
    map_phase: str | None = None  # "warmup", "live", "intermission", "gameover"
    map_round: int | None = None  # rounds completed so far (0 during the first round)
    score_ct: int | None = None
    score_t: int | None = None
    losses_ct: int | None = None  # consecutive round losses (drives the loss bonus)
    losses_t: int | None = None
    # round
    round_phase: str | None = None  # "freezetime", "live", "over"
    bomb: str | None = None  # "planted", "defused", "exploded"
    win_team: str | None = None
    phase_ends_in: float | None = None
    # player (may be a spectated teammate while dead; see ``is_self``)
    player_steamid: str | None = None
    team: str | None = None  # "CT" or "T"
    activity: str | None = None  # "playing", "menu", "textinput"
    health: int | None = None
    armor: int | None = None
    helmet: bool | None = None
    defusekit: bool | None = None
    money: int | None = None
    flashed: int | None = None
    round_kills: int | None = None
    equip_value: int | None = None
    weapons: tuple[Weapon, ...] = field(default_factory=tuple)

    # -- derived ------------------------------------------------------------------
    @property
    def is_self(self) -> bool:
        """True when the player block describes the local player, not a spectated one."""
        return bool(self.player_steamid) and self.player_steamid == self.provider_steamid

    @property
    def alive(self) -> bool:
        return self.is_self and (self.health or 0) > 0

    @property
    def in_game(self) -> bool:
        return self.is_self and self.activity == "playing" and self.map_phase == "live"

    @property
    def has_economy(self) -> bool:
        return self.mode in ECONOMY_MODES

    @property
    def active_weapon(self) -> Weapon | None:
        return next((w for w in self.weapons if w.state in ("active", "reloading")), None)

    @property
    def has_primary(self) -> bool:
        return any(w.type in PRIMARY_TYPES for w in self.weapons)

    @property
    def team_losses(self) -> int | None:
        return {"CT": self.losses_ct, "T": self.losses_t}.get(self.team or "")

    @property
    def half_length(self) -> int | None:
        return HALF_LENGTH.get(self.mode or "")

    @property
    def is_pistol_round(self) -> bool:
        half = self.half_length
        return half is not None and self.map_round in (0, half)

    @property
    def is_last_round_of_half(self) -> bool:
        half, r = self.half_length, self.map_round
        if half is None or r is None:
            return False
        if r < 2 * half:
            return r in (half - 1, 2 * half - 1)
        return (r - 2 * half) % OVERTIME_HALF == OVERTIME_HALF - 1

    def facts(self) -> list[str]:
        """Short, model-friendly facts for the prompt's context block."""
        if not self.is_self:
            return ["Player is dead or spectating"] if self.player_steamid else []
        out: list[str] = []
        if self.map_name:
            score = (
                f", score CT {self.score_ct} - T {self.score_t}"
                if self.score_ct is not None and self.score_t is not None
                else ""
            )
            out.append(f"Map {self.map_name} ({self.mode or 'unknown mode'}){score}")
        if self.round_phase:
            out.append(f"Round {(self.map_round or 0) + 1}, phase {self.round_phase}")
        if self.team:
            out.append(f"Team {self.team}")
        if self.health is not None:
            armor = f", armor {self.armor}{' + helmet' if self.helmet else ''}"
            out.append(f"Health {self.health}{armor if self.armor is not None else ''}")
        if self.money is not None:
            out.append(f"Money ${self.money}")
        active = self.active_weapon
        if active is not None:
            ammo = f" ({active.ammo_clip}/{active.ammo_clip_max})" if active.is_gun else ""
            out.append(f"Holding {active.name.removeprefix('weapon_')}{ammo}")
        if self.bomb:
            out.append(f"Bomb {self.bomb}")
        return out


def parse_weapons(raw: dict[str, Any]) -> tuple[Weapon, ...]:
    weapons = []
    for key in sorted(raw, key=lambda k: _int(k.rsplit("_", 1)[-1]) or 0):
        w = _dict(raw[key])
        name = _str(w.get("name"))
        if name is None:
            continue
        weapons.append(
            Weapon(
                name=name,
                type=_str(w.get("type")),
                state=_str(w.get("state")),
                ammo_clip=_int(w.get("ammo_clip")),
                ammo_clip_max=_int(w.get("ammo_clip_max")),
                ammo_reserve=_int(w.get("ammo_reserve")),
            )
        )
    return tuple(weapons)


def parse_state(payload: dict[str, Any]) -> Cs2State:
    provider = _dict(payload.get("provider"))
    map_ = _dict(payload.get("map"))
    round_ = _dict(payload.get("round"))
    player = _dict(payload.get("player"))
    pstate = _dict(player.get("state"))
    countdown = _dict(payload.get("phase_countdowns"))
    ct, t = _dict(map_.get("team_ct")), _dict(map_.get("team_t"))
    return Cs2State(
        provider_steamid=_str(provider.get("steamid")),
        timestamp=_int(provider.get("timestamp")),
        mode=_str(map_.get("mode")),
        map_name=_str(map_.get("name")),
        map_phase=_str(map_.get("phase")),
        map_round=_int(map_.get("round")),
        score_ct=_int(ct.get("score")),
        score_t=_int(t.get("score")),
        losses_ct=_int(ct.get("consecutive_round_losses")),
        losses_t=_int(t.get("consecutive_round_losses")),
        round_phase=_str(round_.get("phase")),
        bomb=_str(round_.get("bomb")),
        win_team=_str(round_.get("win_team")),
        phase_ends_in=_float(countdown.get("phase_ends_in")),
        player_steamid=_str(player.get("steamid")),
        team=_str(player.get("team")),
        activity=_str(player.get("activity")),
        health=_int(pstate.get("health")),
        armor=_int(pstate.get("armor")),
        helmet=_bool(pstate.get("helmet")),
        defusekit=_bool(pstate.get("defusekit")),
        money=_int(pstate.get("money")),
        flashed=_int(pstate.get("flashed")),
        round_kills=_int(pstate.get("round_kills")),
        equip_value=_int(pstate.get("equip_value")),
        weapons=parse_weapons(_dict(player.get("weapons"))),
    )


def observation_values(state: Cs2State) -> dict[str, Any]:
    """Telemetry facts keyed by observation type, as used in tips' ``valid_while``."""
    values: dict[str, Any] = {
        "round_phase": state.round_phase,
        "bomb": state.bomb,
        "map_round": state.map_round,
        "alive": state.alive,
    }
    if state.is_self:
        values |= {
            "team": state.team,
            "health": state.health,
            "armor": state.armor,
            "helmet": state.helmet,
            "defusekit": state.defusekit,
            "money": state.money,
            "has_primary": state.has_primary,
        }
    return {k: v for k, v in values.items() if v is not None}
