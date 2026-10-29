"""Fast-path signals (frame diff now; HUD crops and OCR in M3/M4) and GameState assembly."""

from .fast_path import FastPath, Signals

__all__ = ["FastPath", "Signals"]
