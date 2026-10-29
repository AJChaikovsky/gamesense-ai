from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from gamesense.api.server import create_app
from gamesense.capture import FrameRingBuffer, ReplaySource
from gamesense.engine import Engine
from gamesense_contracts import HeartbeatEvent, engine_event_adapter
from starlette.websockets import WebSocketDisconnect

TOKEN = "test-token"


def _client(source_clip: Path | None = None) -> TestClient:
    buf = FrameRingBuffer(capacity=50)
    source = ReplaySource(source_clip, buf, sample_fps=10) if source_clip else None
    return TestClient(create_app(Engine(buf, source, heartbeat_interval=0.05), TOKEN))


def test_health_requires_token() -> None:
    with _client() as client:
        assert client.get("/health").status_code == 401
        assert client.get("/health", headers={"x-gamesense-token": "wrong"}).status_code == 401
        res = client.get("/health", headers={"x-gamesense-token": TOKEN})
        assert res.status_code == 200 and res.json()["ok"] is True


def test_websocket_rejects_bad_token() -> None:
    with (
        _client() as client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws?token=wrong") as ws,
    ):
        ws.receive_text()


def test_websocket_streams_heartbeats_with_capture(sample_clip: Path) -> None:
    with _client(sample_clip) as client, client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        events = [engine_event_adapter.validate_json(ws.receive_text()) for _ in range(10)]
    assert all(isinstance(e, HeartbeatEvent) for e in events)
    last = events[-1]
    assert isinstance(last, HeartbeatEvent)
    assert last.capture.source == "replay"
    assert last.capture.buffered_frames > 0


def test_websocket_client_messages_reach_coaching() -> None:
    from gamesense.coaching import CoachingLoop
    from gamesense.providers.mock import MockProvider

    buf = FrameRingBuffer(capacity=10)
    engine = Engine(buf, None, heartbeat_interval=0.05)
    engine.coaching = CoachingLoop(buf, MockProvider(latency_s=0), engine.bus.publish)
    with (
        TestClient(create_app(engine, TOKEN)) as client,
        client.websocket_connect(f"/ws?token={TOKEN}") as ws,
    ):
        ws.send_text('{"type":"control","action":"pause"}')
        ws.send_text('{"type":"feedback","tip_id":"t1","rating":"not_useful"}')
        ws.send_text("garbage")
        for _ in range(20):
            event = engine_event_adapter.validate_json(ws.receive_text())
            if (
                isinstance(event, HeartbeatEvent)
                and event.coaching
                and event.coaching.paused
                and engine.coaching.feedback
            ):
                break
        else:
            raise AssertionError("pause/feedback never applied")
    assert engine.coaching.feedback[0].rating == "not_useful"
