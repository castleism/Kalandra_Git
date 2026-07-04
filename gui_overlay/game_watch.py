"""
GUI_OVERLAY/GAME_WATCH.PY — is the game up, and is Ctrl held? (ghost mode)

Tiny Windows helpers behind the overlay's ghost mode: when Path of Exile
is the foreground window the mirror fades to a whisper and stops eating
clicks (WS_EX_TRANSPARENT); holding Ctrl makes it solid + clickable again.

Everything here fails soft: on non-Windows (or if any user32 call throws)
the answers are False/no-op, so importing this module can never hurt the
overlay — and the stress suite can exercise it headless on Linux.

Detection is by the foreground window's PROCESS EXECUTABLE (PathOfExile*.exe
— covers PoE1, PoE2, Steam and standalone builds), with an EXACT title match
as fallback. A loose title 'contains' match is NOT safe: a browser tab named
"Trade - Path of Exile" would ghost the overlay while you browse (real bug,
2026-07-04). Purely passive: we only READ the foreground window and key
state; nothing is ever sent to the game.
"""

import ctypes
import os

# Foreground process exe basename must CONTAIN one of these (lowercase)...
GAME_EXE_NEEDLES = ("pathofexile",)
# ...or, if the exe can't be read, the window title must EQUAL one of these
# (lowercase, stripped). Exact equality so browser/editor tabs that merely
# mention the game never match.
GAME_TITLE_EXACT = ("path of exile", "path of exile 2")

_VK_CONTROL = 0x11
_GWL_EXSTYLE = -20
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_LAYERED = 0x00080000
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _user32():
    try:
        return ctypes.windll.user32
    except Exception:
        return None


def foreground_title():
    """Title of the current foreground window, '' if unknowable."""
    u = _user32()
    if not u:
        return ""
    try:
        hwnd = u.GetForegroundWindow()
        if not hwnd:
            return ""
        n = u.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 2)
        u.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value or ""
    except Exception:
        return ""


def foreground_exe():
    """Basename (lowercase) of the foreground window's process executable,
    '' if unknowable."""
    u = _user32()
    if not u:
        return ""
    try:
        hwnd = u.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = ctypes.c_ulong(0)
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False,
                            pid.value)
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = ctypes.c_ulong(1024)
            if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value or "").lower()
            return ""
        finally:
            k32.CloseHandle(h)
    except Exception:
        return ""


def is_game(exe, title, exe_needles=GAME_EXE_NEEDLES,
            titles_exact=GAME_TITLE_EXACT):
    """Pure decision (unit-tested): exe basename wins; exact title only as
    fallback when the exe is unreadable. Loose title matching is forbidden —
    browser tabs mention the game constantly."""
    exe = (exe or "").lower()
    if exe:
        return any(n in exe for n in exe_needles)
    title = (title or "").lower().strip()
    return title in titles_exact


def game_foreground():
    """True when the actual GAME (not a browser tab about it) has focus."""
    return is_game(foreground_exe(), foreground_title())


def ctrl_down():
    """True while a Ctrl key is physically held (global, any window)."""
    u = _user32()
    if not u:
        return False
    try:
        return bool(u.GetAsyncKeyState(_VK_CONTROL) & 0x8000)
    except Exception:
        return False


def set_click_through(hwnd, enabled):
    """Toggle WS_EX_TRANSPARENT on a native window: True = clicks fall
    through to whatever is underneath (the game). Uses SetWindowLongPtrW so
    the window is NOT recreated (no flicker, no focus steal).
    Returns True if the style was applied."""
    u = _user32()
    if not u or not hwnd:
        return False
    try:
        get_long = getattr(u, "GetWindowLongPtrW", u.GetWindowLongW)
        set_long = getattr(u, "SetWindowLongPtrW", u.SetWindowLongW)
        style = get_long(int(hwnd), _GWL_EXSTYLE)
        if enabled:
            new = style | _WS_EX_TRANSPARENT | _WS_EX_LAYERED
        else:
            new = style & ~_WS_EX_TRANSPARENT
        if new != style:
            set_long(int(hwnd), _GWL_EXSTYLE, new)
        return True
    except Exception:
        return False
