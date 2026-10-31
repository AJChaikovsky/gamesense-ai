from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from gamesense_contracts import CaptureStatus, HeartbeatEvent, StatusEvent, TipEvent
from gamesense_contracts.events import ControlMessage, FeedbackMessage

from . import __version__
from .capture import CaptureSource, FrameRingBuffer
from .coaching import CoachingLoop
from .telemetry import TelemetryServer

log = logging.getLogger(__name__)

Event = HeartbeatEvent | TipEvent | StatusEvent


class EventBus:
    """Fan-out of engine events to any number of subscribers (WebSocket clients).

    Slow subscribers drop their oldest events instead of stalling the engine.
    """

    def __init__(self, max_queue: int = 64) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._max_queue = max_queue

    def publish(self, event: Event) -> None:
        for queue in self._subscribers:
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(event)

    @contextlib.asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[Event]]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._max_queue)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


class Engine:
    """Owns the capture source, ring buffer and event bus.

    The coaching loop is optional so the engine can run capture-only (tests, tools).
    """

    def __init__(
        self,
        buffer: FrameRingBuffer,
        source: CaptureSource | None = None,
        *,
        heartbeat_interval: float = 1.0,
    ) -> None:
        self.buffer = buffer
        self.source = source
        self.bus = EventBus()
        self.coaching: CoachingLoop | None = None
        self.telemetry_server: TelemetryServer | None = None
        self.heartbeat_interval = heartbeat_interval
        self._started_at = time.monotonic()
        self._tasks: list[asyncio.Task[None]] = []

    def capture_status(self) -> CaptureStatus:
        latest = self.buffer.latest()
        return CaptureStatus(
            source=self.source.kind if self.source else "none",
            running=bool(self.source and self.source.running),
            target=self.source.target if self.source else None,
            fps=round(self.buffer.fps(), 2),
            buffered_frames=len(self.buffer),
            frame_width=latest.width if latest else None,
            frame_height=latest.height if latest else None,
        )

    def heartbeat(self) -> HeartbeatEvent:
        return HeartbeatEvent(
            timestamp=datetime.now(UTC),
            engine_version=__version__,
            uptime_seconds=round(time.monotonic() - self._started_at, 2),
            capture=self.capture_status(),
            coaching=self.coaching.status() if self.coaching else None,
        )

    def handle_client_message(self, msg: FeedbackMessage | ControlMessage) -> None:
        if self.coaching is not None:
            self.coaching.handle_client_message(msg)

    async def start(self) -> None:
        self._started_at = time.monotonic()
        if self.source is not None:
            self.source.start()
            log.info("capture started: %s %s", self.source.kind, self.source.target)
        if self.telemetry_server is not None:
            try:
                port = await self.telemetry_server.start()
                log.info("game telemetry receiver on 127.0.0.1:%d", port)
            except OSError as exc:  # port taken: coach still works, just without telemetry
                log.warning("game telemetry receiver could not start: %s", exc)
        self._tasks.append(asyncio.create_task(self._heartbeat_loop(), name="heartbeat"))
        if self.coaching is not None:
            self._tasks.append(asyncio.create_task(self.coaching.run(), name="coaching"))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        if self.telemetry_server is not None:
            await self.telemetry_server.stop()
        if self.coaching is not None:
            await self.coaching.provider.aclose()
            if self.coaching.telemetry is not None:
                self.coaching.telemetry.close()
        if self.source is not None:
            # Joining the capture thread blocks briefly; keep it off the event loop.
            await asyncio.to_thread(self.source.stop)

    async def _heartbeat_loop(self) -> None:
        while True:
            self.bus.publish(self.heartbeat())
            await asyncio.sleep(self.heartbeat_interval)
