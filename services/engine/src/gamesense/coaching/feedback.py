"""Append-only log of the player's tip ratings, used to grow the eval set.

Only the tip text and its metadata are written, never frames or screenshots.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gamesense_contracts import CoachingDecision
from gamesense_contracts.events import FeedbackMessage

log = logging.getLogger(__name__)


def default_data_dir() -> Path:
    raw = os.environ.get("GAMESENSE_DATA_DIR")
    return Path(raw).expanduser() if raw else Path.home() / ".gamesense"


class FeedbackLog:
    def __init__(self, path: Path, *, remember: int = 50) -> None:
        self.path = path
        self._tips: OrderedDict[str, CoachingDecision] = OrderedDict()
        self._remember = remember
        self._lock = threading.Lock()

    def remember_tip(self, decision: CoachingDecision) -> None:
        """Keep recent tips so a later rating can be stored with the tip's text."""
        self._tips[decision.id] = decision
        while len(self._tips) > self._remember:
            self._tips.popitem(last=False)

    def record(self, msg: FeedbackMessage, **context: Any) -> dict[str, Any] | None:
        decision = self._tips.get(msg.tip_id)
        if decision is None:
            log.debug("feedback for unknown tip %s ignored", msg.tip_id)
            return None
        row: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "rating": msg.rating,
            "tip_id": decision.id,
            "message": decision.message,
            "detail": decision.detail,
            "category": decision.category,
            "action": decision.action,
            "priority": decision.priority,
            "confidence": decision.confidence,
            **context,
        }
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row) + "\n")
        except OSError as exc:
            log.warning("could not save feedback to %s: %s", self.path, exc)
        return row
