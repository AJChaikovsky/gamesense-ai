"""A tiny loopback HTTP receiver for game telemetry pushed as JSON POSTs.

CS2 Game State Integration needs a fixed URI written into a config file, so this
listens on its own fixed port rather than the engine's random API port. It only
speaks the subset of HTTP/1.1 that GSI uses (POST with Content-Length, keep-alive)
and binds to 127.0.0.1 only.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

MAX_BODY = 256 * 1024
MAX_HEADER = 16 * 1024

# Returns an HTTP status: 200 accepted, 401 bad token, 400 unusable payload.
PayloadHandler = Callable[[dict[str, Any]], int]

_REASONS = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 405: "Method Not Allowed",
            413: "Payload Too Large"}  # fmt: skip


def _response(status: int, *, close: bool) -> bytes:
    head = (
        f"HTTP/1.1 {status} {_REASONS.get(status, 'Error')}\r\n"
        "Content-Length: 0\r\n"
        f"Connection: {'close' if close else 'keep-alive'}\r\n\r\n"
    )
    return head.encode("ascii")


class TelemetryServer:
    def __init__(self, handler: PayloadHandler, *, host: str = "127.0.0.1", port: int) -> None:
        self.handler = handler
        self.host = host
        self.port = port
        self.requests = 0
        self._server: asyncio.Server | None = None

    async def start(self) -> int:
        """Start listening; returns the bound port (useful when ``port`` is 0)."""
        self._server = await asyncio.start_server(
            self._client, self.host, self.port, limit=MAX_HEADER
        )
        self.port = self._server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                status, close = await self._one_request(reader)
                if status is None:
                    break
                writer.write(_response(status, close=close))
                await writer.drain()
                if close:
                    break
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
            pass
        except ValueError:  # malformed request line or header
            with contextlib.suppress(ConnectionError):
                writer.write(_response(400, close=True))
                await writer.drain()
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _one_request(self, reader: asyncio.StreamReader) -> tuple[int | None, bool]:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
        except asyncio.IncompleteReadError as exc:
            if not exc.partial:
                return None, True  # client closed between requests
            raise
        lines = head.decode("latin-1").split("\r\n")
        method, _target, version = lines[0].split(" ", 2)
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" in line:
                name, value = line.split(":", 1)
                headers[name.strip().lower()] = value.strip()
        connection = headers.get("connection", "").lower()
        close = connection == "close" or (version == "HTTP/1.0" and connection != "keep-alive")
        length = int(headers.get("content-length", "0"))
        if length < 0 or length > MAX_BODY:
            return 413, True
        body = await reader.readexactly(length) if length else b""
        if method != "POST":
            return 405, close
        self.requests += 1
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return 400, close
        if not isinstance(payload, dict):
            return 400, close
        try:
            return self.handler(payload), close
        except Exception:
            log.exception("telemetry handler failed")
            return 200, close  # never make the game retry because of our bug
