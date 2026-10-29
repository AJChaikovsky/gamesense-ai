from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

import numpy as np
import numpy.typing as npt

SourceKind = Literal["none", "replay", "windows"]


@dataclass(frozen=True, slots=True)
class Frame:
    """A captured frame, already downscaled for analysis (BGR, uint8)."""

    id: str
    index: int
    timestamp: float  # time.monotonic() when the frame entered the buffer
    image: npt.NDArray[np.uint8]

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    @property
    def height(self) -> int:
        return int(self.image.shape[0])


class CaptureSource(Protocol):
    """Produces frames into a FrameRingBuffer on its own thread.

    Implementations must never block the caller: start() returns immediately and
    stop() joins the worker thread.
    """

    @property
    def kind(self) -> SourceKind: ...

    @property
    def target(self) -> str: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    @property
    def running(self) -> bool: ...
