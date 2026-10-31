"""Official telemetry adapters (CS2 Game State Integration, later Minecraft mod bridge).

Telemetry is data the game itself publishes for third-party tools. Nothing here
reads game memory or sends input to the game.
"""

from typing import Any, Protocol

from .gsi_server import TelemetryServer


class TelemetryFeed(Protocol):
    """A live game data feed the coach can consult (exact facts, no model needed)."""

    source: str

    def connected(self) -> bool: ...

    def facts(self) -> list[str]: ...

    def observations(self) -> dict[str, Any]: ...

    def close(self) -> None: ...


__all__ = ["TelemetryFeed", "TelemetryServer"]
