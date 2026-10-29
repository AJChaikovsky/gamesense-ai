"""Frame acquisition: capture sources and the in-memory ring buffer."""

from .base import CaptureSource, Frame
from .replay import ReplaySource
from .ring_buffer import FrameRingBuffer
from .windows import WindowsCaptureSource

__all__ = ["CaptureSource", "Frame", "FrameRingBuffer", "ReplaySource", "WindowsCaptureSource"]
