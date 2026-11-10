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


@dataclass(frozen=True, slots=True)
class WindowCandidate:
    """A visible top-level window that capture could target."""

    title: str
    process_name: str | None
    hwnd: int
    area: int


# Windows that share a game's name but are never the game itself.
_TERMINALS = frozenset(
    {"powershell.exe", "pwsh.exe", "windowsterminal.exe", "cmd.exe", "conhost.exe"}
)
_SKIP_WORDS = ("launcher", "gamesense")


def pick_window(query: str, candidates: list[WindowCandidate]) -> WindowCandidate | None:
    """Choose the game window whose title contains ``query`` (case-insensitive).

    Launchers, terminals and our own windows are skipped unless the query names them,
    so "Minecraft" finds the game even while the Minecraft Launcher is open. An exact
    title match wins; otherwise the largest window does.
    """
    q = query.strip().lower()
    if not q:
        return None
    matches = []
    for c in candidates:
        title = c.title.lower()
        if q not in title:
            continue
        if any(word in title and word not in q for word in _SKIP_WORDS):
            continue
        if (c.process_name or "").lower() in _TERMINALS:
            continue
        matches.append(c)
    if not matches:
        return None
    return max(matches, key=lambda c: (c.title.lower() == q, c.area))


def list_windows() -> list[WindowCandidate]:
    """Visible, non-minimized top-level windows with a title (empty off Windows)."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    import psutil

    user32 = ctypes.windll.user32
    found: list[WindowCandidate] = []

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
        if area == 0:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            name: str | None = psutil.Process(pid.value).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            name = None
        found.append(WindowCandidate(buf.value, name, int(hwnd), area))
        return True

    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(enum_proc(callback), 0)
    return found


def find_window(query: str) -> WindowCandidate | None:
    """The best game window for ``query`` on this machine, or None."""
    return pick_window(query, list_windows())
