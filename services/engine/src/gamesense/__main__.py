"""Run the GameSense engine.

    uv run gamesense-engine --replay evals/clips/sample.mp4 --game minecraft
    uv run gamesense-engine --capture window --window "Counter-Strike 2" --provider anthropic

Settings also come from environment variables or a .env file at the repo root
(see .env.example). On startup the engine prints one JSON line to stdout,
``{"event": "ready", "port": <port>}``, which the desktop app waits for.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import secrets
import socket
import sys

import uvicorn

from . import __version__
from .api.server import create_app
from .capture import FrameRingBuffer, ReplaySource
from .capture.base import CaptureSource
from .coaching import CoachingConfig, CoachingLoop
from .coaching.trigger import TriggerPolicy
from .config import DEFAULT_MODELS, Settings, load_env_file
from .engine import Engine
from .games import game_by_id
from .providers import create_provider

log = logging.getLogger("gamesense")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="gamesense-engine", description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind address (keep it local)")
    parser.add_argument("--port", type=int, default=0, help="0 picks a free port")
    parser.add_argument("--token", default=None, help="local API token (default: $GAMESENSE_TOKEN)")
    parser.add_argument("--capture", choices=["auto", "replay", "window", "none"], default=None)
    parser.add_argument("--replay", default=None, help="video file to replay")
    parser.add_argument("--window", default=None, help="window title to capture (Windows)")
    parser.add_argument("--game", default=None, help="force a game id, e.g. cs2, minecraft")
    parser.add_argument("--provider", choices=sorted(DEFAULT_MODELS), default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--budget", type=float, default=None, help="hourly spend cap in USD")
    parser.add_argument("--no-coach", action="store_true", help="capture only, no model calls")
    parser.add_argument("--no-loop", action="store_true", help="stop replay at end of clip")
    parser.add_argument("--sample-fps", type=float, default=4.0)
    parser.add_argument("--buffer-seconds", type=float, default=60.0)
    parser.add_argument("--max-width", type=int, default=1280)
    parser.add_argument("--log-level", default=os.environ.get("GAMESENSE_LOG_LEVEL", "INFO"))
    parser.add_argument("--version", action="version", version=__version__)
    return parser.parse_args(argv)


def settings_from(args: argparse.Namespace) -> Settings:
    s = Settings.from_env()
    if args.provider:
        s.provider = args.provider
        s.model = args.model or DEFAULT_MODELS[args.provider]
    elif args.model:
        s.model = args.model
    if args.capture:
        s.capture = args.capture
    s.replay = args.replay or s.replay
    s.window = args.window or s.window
    s.game = args.game or s.game
    if args.budget is not None:
        s.hourly_budget_usd = args.budget
    s.sample_fps = args.sample_fps
    s.buffer_seconds = args.buffer_seconds
    s.max_width = args.max_width
    s.loop = not args.no_loop
    return s


def build_source(s: Settings, buffer: FrameRingBuffer) -> CaptureSource | None:
    mode = s.capture
    if mode == "auto":
        mode = "replay" if s.replay else ("window" if sys.platform == "win32" else "none")
    if mode == "replay":
        if not s.replay:
            raise SystemExit("--capture replay needs --replay PATH")
        return ReplaySource(
            s.replay, buffer, sample_fps=s.sample_fps, max_width=s.max_width, loop=s.loop
        )
    if mode == "window":
        from .capture.windows import WindowsCaptureSource

        return WindowsCaptureSource(
            s.window, buffer, sample_fps=s.sample_fps, max_width=s.max_width
        )
    return None


def build_engine(s: Settings, *, coach: bool = True) -> Engine:
    buffer = FrameRingBuffer(capacity=max(1, round(s.buffer_seconds * s.sample_fps)))
    engine = Engine(buffer, build_source(s, buffer))
    if coach:
        config = CoachingConfig(
            tick_hz=s.sample_fps,
            frames_per_call=s.frames_per_call,
            model_frame_width=s.model_frame_width,
            hourly_budget_usd=s.hourly_budget_usd,
            trigger=TriggerPolicy(
                scene_change_threshold=s.scene_change_threshold,
                min_interval_s=s.min_call_interval,
                heartbeat_s=s.heartbeat_trigger_seconds,
            ),
        )
        engine.coaching = CoachingLoop(
            buffer,
            create_provider(s.provider, s.model),
            engine.bus.publish,
            config=config,
            fixed_game=game_by_id(s.game) if s.game else None,
        )
        log.info(
            "coach: provider=%s model=%s budget=$%.2f/h game=%s",
            s.provider,
            s.model,
            s.hourly_budget_usd,
            s.game or "auto-detect",
        )
    return engine


async def serve(args: argparse.Namespace, s: Settings) -> None:
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        log.warning("binding to non-loopback address %s", args.host)
    explicit_token = args.token or os.environ.get("GAMESENSE_TOKEN")
    token = explicit_token or secrets.token_urlsafe(24)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.host, args.port))
    port = sock.getsockname()[1]

    app = create_app(build_engine(s, coach=not args.no_coach), token)
    config = uvicorn.Config(app, log_level=args.log_level.lower(), lifespan="on")
    server = uvicorn.Server(config)

    ready: dict[str, object] = {"event": "ready", "port": port}
    if not explicit_token:
        ready["token"] = token  # only echoed when we generated it ourselves
    print(json.dumps(ready), flush=True)
    await server.serve(sockets=[sock])


def main(argv: list[str] | None = None) -> None:
    load_env_file()
    args = parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        stream=sys.stderr,  # stdout is reserved for the ready line
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(serve(args, settings_from(args)))


if __name__ == "__main__":
    main()
