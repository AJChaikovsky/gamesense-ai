"""Game adapters: detection, capabilities, live-coaching policy.

M1 ships detection and the policy gate; HUD regions and telemetry arrive in M4.
"""

from .registry import GENERIC, KNOWN_GAMES, GameProfile, detect_game, game_by_id

__all__ = ["GENERIC", "KNOWN_GAMES", "GameProfile", "detect_game", "game_by_id"]
