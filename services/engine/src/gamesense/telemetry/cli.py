"""CS2 Game State Integration helper.

    uv run gamesense-gsi install                 # write the config into CS2's cfg folder
    uv run gamesense-gsi install --cs2-dir "D:\\SteamLibrary\\...\\game\\csgo\\cfg"
    uv run gamesense-gsi print                   # show the config without writing it
    uv run gamesense-gsi replay round.jsonl      # play recorded payloads into a running engine

Record real payloads while you play by starting the engine with
``--gsi-record ~/gsi/round.jsonl`` (or GAMESENSE_GSI_RECORD). Recordings hold game
state only (health, money, weapons, score), never the auth token.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..coaching.feedback import default_data_dir
from .cs2 import DEFAULT_PORT, find_cs2_cfg_dir, install, load_or_create_token
from .cs2.install import render_config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="gamesense-gsi", description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_install = sub.add_parser("install", help="write the GSI config into CS2's cfg folder")
    p_install.add_argument("--cs2-dir", type=Path, default=None, help="CS2 game/csgo/cfg folder")
    p_install.add_argument("--port", type=int, default=DEFAULT_PORT)
    p_print = sub.add_parser("print", help="print the GSI config")
    p_print.add_argument("--port", type=int, default=DEFAULT_PORT)
    p_replay = sub.add_parser("replay", help="POST a recorded .jsonl to a running engine")
    p_replay.add_argument("recording", type=Path)
    p_replay.add_argument("--port", type=int, default=DEFAULT_PORT)
    p_replay.add_argument("--speed", type=float, default=1.0, help="2 = twice as fast")
    return parser.parse_args(argv)


def load_recording(path: Path) -> list[tuple[float, dict[str, Any]]]:
    """Read a recording: one ``{"t": seconds, "payload": {...}}`` object per line.

    Bare payload objects (one per line) are accepted too and replayed 0.5 s apart.
    """
    rows: list[tuple[float, dict[str, Any]]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        obj = json.loads(line)
        if "payload" in obj:
            rows.append((float(obj.get("t", i * 0.5)), obj["payload"]))
        else:
            rows.append((i * 0.5, obj))
    return rows


def replay(path: Path, *, port: int, speed: float, token: str) -> int:
    rows = load_recording(path)
    url = f"http://127.0.0.1:{port}/"
    start = time.monotonic()
    for t, payload in rows:
        delay = t / max(speed, 0.01) - (time.monotonic() - start)
        if delay > 0:
            time.sleep(delay)
        body = json.dumps({**payload, "auth": {"token": token}}).encode()
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=3) as res:
                res.read()
        except urllib.error.HTTPError as exc:
            print(f"engine rejected payload at t={t}: HTTP {exc.code}", file=sys.stderr)
            return 1
        except urllib.error.URLError as exc:
            print(f"cannot reach the engine on port {port}: {exc.reason}", file=sys.stderr)
            return 1
    print(f"replayed {len(rows)} payloads from {path}")
    return 0


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    token = load_or_create_token(default_data_dir())
    if args.command == "print":
        print(render_config(token, args.port), end="")
    elif args.command == "install":
        cfg_dir = args.cs2_dir or find_cs2_cfg_dir()
        if cfg_dir is None or not cfg_dir.is_dir():
            raise SystemExit(
                "Could not find CS2's cfg folder. Pass it with --cs2-dir, e.g.\n"
                r'  --cs2-dir "C:\Program Files (x86)\Steam\steamapps\common'
                r'\Counter-Strike Global Offensive\game\csgo\cfg"'
            )
        path = install(cfg_dir, token, args.port)
        print(f"Wrote {path}\nRestart CS2 if it is running so it picks up the config.")
    else:
        raise SystemExit(replay(args.recording, port=args.port, speed=args.speed, token=token))


if __name__ == "__main__":
    main()
