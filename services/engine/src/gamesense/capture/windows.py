"""Live Windows capture (Windows Graphics Capture). Implemented in M1.

Planned: ``windows-capture`` (WGC) as the primary backend with ``dxcam``
(DXGI Desktop Duplication) as a fallback, targeting a single game window and
writing downscaled frames into the shared FrameRingBuffer.
"""
