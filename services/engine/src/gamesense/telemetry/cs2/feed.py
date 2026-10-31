"""Connects GSI updates to the coach: auth, optional recording, rules, prompt facts."""

from __future__ import annotations

import hmac
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

from gamesense_contracts import CoachingDecision

from .rules import Cs2Rules
from .state import Cs2State, observation_values, parse_state

log = logging.getLogger(__name__)

# Delivers a rule tip through the coach's gates; True when it was shown.
Deliver = Callable[[CoachingDecision], bool]


class Cs2Feed:
    source = "cs2_gsi"

    def __init__(
        self,
        token: str | None,
        deliver: Deliver,
        *,
        rules: Cs2Rules | None = None,
        record_path: Path | None = None,
        stale_after_s: float = 30.0,  # GSI sends a heartbeat every 10 s while running
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.token = token
        self.deliver = deliver
        self.rules = rules or Cs2Rules()
        self.stale_after_s = stale_after_s
        self.clock = clock
        self.state: Cs2State | None = None
        self.updates = 0
        self.rejected = 0
        self._last_update: float | None = None
        self._record: TextIO | None = None
        self._record_start: float | None = None
        if record_path is not None:
            record_path.parent.mkdir(parents=True, exist_ok=True)
            self._record = record_path.open("a", encoding="utf-8")
            log.info("recording CS2 GSI payloads to %s", record_path)

    def handle(self, payload: dict[str, Any]) -> int:
        """Handle one POSTed payload; returns the HTTP status for the game."""
        auth = payload.get("auth")
        sent = auth.get("token") if isinstance(auth, dict) else None
        if self.token and not (isinstance(sent, str) and hmac.compare_digest(self.token, sent)):
            self.rejected += 1
            return 401
        now = self.clock()
        self._write_record(payload, now)
        prev, self.state = self.state, parse_state(payload)
        self._last_update = now
        self.updates += 1
        for tip in self.rules.evaluate(self.state, prev):
            if self.deliver(tip.decision):
                self.rules.mark_delivered(tip)
                log.info("rule tip: %s", tip.decision.message)
        return 200

    def connected(self) -> bool:
        last = self._last_update
        return last is not None and self.clock() - last < self.stale_after_s

    def facts(self) -> list[str]:
        return self.state.facts() if self.state is not None and self.connected() else []

    def observations(self) -> dict[str, Any]:
        return observation_values(self.state) if self.state is not None and self.connected() else {}

    def close(self) -> None:
        if self._record is not None:
            self._record.close()
            self._record = None

    def _write_record(self, payload: dict[str, Any], now: float) -> None:
        if self._record is None:
            return
        if self._record_start is None:
            self._record_start = now
        clean = {k: v for k, v in payload.items() if k != "auth"}  # never store the token
        line = {"t": round(now - self._record_start, 3), "payload": clean}
        self._record.write(json.dumps(line, separators=(",", ":")) + "\n")
        self._record.flush()
