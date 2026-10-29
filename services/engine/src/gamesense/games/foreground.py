"""Find the foreground window's title and process (Windows only; None elsewhere)."""

from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WindowInfo:
    title: str
    process_name: str | None
    pid: int
    hwnd: int = 0


def foreground_window() -> WindowInfo | None:
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    import psutil

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        name: str | None = psutil.Process(pid.value).name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        name = None
    return WindowInfo(title=buf.value, process_name=name, pid=pid.value, hwnd=int(hwnd))
