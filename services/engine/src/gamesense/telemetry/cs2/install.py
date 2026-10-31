"""Writes the CS2 Game State Integration config that points the game at the engine.

CS2 reads every ``gamestate_integration_*.cfg`` in its ``game/csgo/cfg`` folder at
launch and then POSTs JSON to the configured URI whenever the game state changes.
This is Valve's official telemetry interface; it reads nothing from game memory.
"""

from __future__ import annotations

import os
import re
import secrets
import sys
from pathlib import Path

DEFAULT_PORT = 3727
CFG_NAME = "gamestate_integration_gamesense.cfg"
TOKEN_FILE = "cs2_gsi_token"
_CS2_CFG = Path("steamapps", "common", "Counter-Strike Global Offensive", "game", "csgo", "cfg")

# Sections the local player is allowed to receive. Spectator-only sections
# (allplayers_*, bomb, grenades) are left out: the game ignores them for players.
DATA_SECTIONS = (
    "provider",
    "map",
    "map_round_wins",
    "round",
    "phase_countdowns",
    "player_id",
    "player_state",
    "player_weapons",
    "player_match_stats",
)


def load_or_create_token(data_dir: Path) -> str:
    """The shared secret CS2 sends with every update, kept in the data dir."""
    path = data_dir / TOKEN_FILE
    if path.is_file():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(24)
    data_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n", encoding="utf-8")
    return token


def render_config(token: str, port: int = DEFAULT_PORT) -> str:
    data = "\n".join(f'        "{name}" "1"' for name in DATA_SECTIONS)
    return f'''"GameSense"
{{
    "uri" "http://127.0.0.1:{port}/"
    "timeout" "1.1"
    "buffer" "0.1"
    "throttle" "0.25"
    "heartbeat" "10.0"
    "auth"
    {{
        "token" "{token}"
    }}
    "data"
    {{
{data}
    }}
}}
'''


def steam_roots() -> list[Path]:
    """Likely Steam install folders on this machine, most likely first."""
    roots: list[Path] = []
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                roots.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
        except OSError:
            pass
        for env in ("ProgramFiles(x86)", "ProgramFiles"):
            if base := os.environ.get(env):
                roots.append(Path(base) / "Steam")
    else:
        home = Path.home()
        roots += [home / ".steam" / "steam", home / ".local" / "share" / "Steam"]
        roots.append(home / "Library" / "Application Support" / "Steam")
    return list(dict.fromkeys(roots))


def library_folders(steam_root: Path) -> list[Path]:
    """The Steam root plus every library listed in its libraryfolders.vdf."""
    folders = [steam_root]
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    if vdf.is_file():
        text = vdf.read_text(encoding="utf-8", errors="replace")
        for raw in re.findall(r'"path"\s+"([^"]+)"', text):
            folders.append(Path(raw.replace("\\\\", "\\")))
    return list(dict.fromkeys(folders))


def find_cs2_cfg_dir(roots: list[Path] | None = None) -> Path | None:
    for root in roots if roots is not None else steam_roots():
        for library in library_folders(root):
            candidate = library / _CS2_CFG
            if candidate.is_dir():
                return candidate
    return None


def install(cfg_dir: Path, token: str, port: int = DEFAULT_PORT) -> Path:
    """Write (or overwrite) the GameSense GSI config. CS2 picks it up on next launch."""
    path = cfg_dir / CFG_NAME
    path.write_text(render_config(token, port), encoding="utf-8")
    return path
