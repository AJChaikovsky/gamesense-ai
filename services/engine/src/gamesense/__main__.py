"""Run the GameSense engine.

    uv run gamesense-engine --replay evals/clips/sample.mp4

On startup the engine prints one JSON line to stdout,
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
from .engine import Engine

log = logging.getLogger("gamesense")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="gamesense-engine", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="bind address (keep it local)")
    parser.add_argument("--port", type=int, default=0, help="0 picks a free port")
    parser.add_argument(
        "--token",
        default=os.environ.get("GAMESENSE_TOKEN"),
        help="auth token for the local API (default: $GAMESENSE_TOKEN, else random)",
    )
    parser.add_argument("--replay", default=os.environ.get("GAMESENSE_REPLAY"), help="video file")
    parser.add_argument("--no-loop", action="store_true", help="stop replay at end of clip")
    parser.add_argument("--sample-fps", type=float, default=4.0)
    parser.add_argument("--buffer-seconds", type=float, default=60.0)
    parser.add_argument("--max-width", type=int, default=1280)
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--version", action="version", version=__version__)
    return parser.parse_args(argv)


def build_engine(args: argparse.Namespace) -> Engine:
    buffer = FrameRingBuffer(capacity=max(1, round(args.buffer_seconds * args.sample_fps)))
    source: CaptureSource | None = None
    if args.replay:
        source = ReplaySource(
            args.replay,
            buffer,
            sample_fps=args.sample_fps,
            max_width=args.max_width,
            loop=not args.no_loop,
        )
    return Engine(buffer, source)


async def serve(args: argparse.Namespace) -> None:
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        log.warning("binding to non-loopback address %s", args.host)
    token = args.token or secrets.token_urlsafe(24)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.host, args.port))
    port = sock.getsockname()[1]

    app = create_app(build_engine(args), token)
    config = uvicorn.Config(app, log_level=args.log_level.lower(), lifespan="on")
    server = uvicorn.Server(config)

    ready: dict[str, object] = {"event": "ready", "port": port}
    if not args.token:
        ready["token"] = token  # only echoed when we generated it ourselves
    print(json.dumps(ready), flush=True)
    await server.serve(sockets=[sock])


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        stream=sys.stderr,  # stdout is reserved for the ready line
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(serve(args))


if __name__ == "__main__":
    main()
