from __future__ import annotations

import asyncio
import contextlib
import hmac
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect, status
from gamesense_contracts import client_message_adapter
from pydantic import ValidationError

from .. import __version__
from ..engine import Engine

log = logging.getLogger(__name__)


def _token_ok(expected: str, provided: str | None) -> bool:
    return provided is not None and hmac.compare_digest(expected, provided)


def create_app(engine: Engine, token: str) -> FastAPI:
    """Build the local API. Every route requires the per-launch token.

    The desktop app receives the token from the process that launched the engine,
    so other local processes cannot read events or control the engine.
    """

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await engine.start()
        try:
            yield
        finally:
            await engine.stop()

    app = FastAPI(title="GameSense Engine", version=__version__, lifespan=lifespan)

    @app.get("/health")
    async def health(x_gamesense_token: str | None = Header(default=None)) -> dict[str, object]:
        if not _token_ok(token, x_gamesense_token):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
        return {"ok": True, "version": __version__, "capture": engine.capture_status()}

    @app.websocket("/ws")
    async def events(websocket: WebSocket) -> None:
        if not _token_ok(token, websocket.query_params.get("token")):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        await websocket.accept()
        async with engine.bus.subscribe() as queue:
            await websocket.send_text(engine.heartbeat().model_dump_json())
            receiver = asyncio.create_task(_receive(websocket, engine))
            try:
                while not receiver.done():
                    get = asyncio.create_task(queue.get())
                    done, _ = await asyncio.wait(
                        {get, receiver}, return_when=asyncio.FIRST_COMPLETED
                    )
                    if get in done:
                        await websocket.send_text(get.result().model_dump_json())
                    else:
                        get.cancel()
            except WebSocketDisconnect:
                pass
            finally:
                receiver.cancel()

    return app


async def _receive(websocket: WebSocket, engine: Engine) -> None:
    """Apply client messages (feedback, pause/resume) until the socket closes."""
    with contextlib.suppress(WebSocketDisconnect):
        while True:
            raw = await websocket.receive_text()
            try:
                engine.handle_client_message(client_message_adapter.validate_json(raw))
            except ValidationError:
                log.warning("ignoring invalid client message: %.200s", raw)
