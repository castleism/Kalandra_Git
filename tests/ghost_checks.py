"""
Ghost-mode checks: game_watch helpers (headless degradation) + the
fade/click-through state logic mirrored from mirror_window.
Run: python3 tests/ghost_checks.py
"""
import os, sys, traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = 0
FAIL = 0
FAILURES = []

def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  FAIL: {name}")

def guard(name, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
    except Exception as e:
        FAIL += 1
        FAILURES.append(f"{name}: {e!r}")
        print(f"  CRASH: {name}: {e!r}")
        traceback.print_exc()

print("=== game_watch (headless: everything degrades, nothing raises) ===")
from gui_overlay import game_watch

IS_WIN = os.name == "nt"
guard("foreground_title never raises", game_watch.foreground_title)
guard("game_foreground never raises", game_watch.game_foreground)
guard("ctrl_down never raises", game_watch.ctrl_down)
guard("set_click_through never raises",
      lambda: game_watch.set_click_through(12345, True))
if not IS_WIN:
    check("no-win: title ''", game_watch.foreground_title() == "")
    check("no-win: game False", game_watch.game_foreground() is False)
    check("no-win: ctrl False", game_watch.ctrl_down() is False)
    check("no-win: click-through False",
          game_watch.set_click_through(1, True) is False)
check("null hwnd refused", game_watch.set_click_through(None, True) is False)
guard("foreground_exe never raises", game_watch.foreground_exe)
if not IS_WIN:
    check("no-win: exe ''", game_watch.foreground_exe() == "")

print("=== is_game: exe wins, exact-title fallback, browsers never match ===")
ig = game_watch.is_game
check("PoE1 exe", ig("pathofexile.exe", "") is True)
check("PoE2 steam exe", ig("pathofexilesteam.exe", "whatever") is True)
check("x64 exe", ig("pathofexile_x64.exe", "") is True)
check("case handled", ig("PathOfExile.exe".lower(), "") or ig("PathOfExile.exe", ""))
check("browser exe NEVER matches even with game title",
      ig("chrome.exe", "Trade - Path of Exile - Google Chrome") is False)
check("firefox + wiki tab no match",
      ig("firefox.exe", "Path of Exile Wiki") is False)
check("no exe: exact title matches", ig("", "Path of Exile 2") is True)
check("no exe: exact title (PoE1)", ig("", "  path of exile  ") is True)
check("no exe: loose title REJECTED",
      ig("", "Trade - Path of Exile") is False)
check("no exe no title", ig("", "") is False)
check("None-safe", ig(None, None) is False)
check("needles lowercase", all(n == n.lower()
      for n in game_watch.GAME_EXE_NEEDLES + game_watch.GAME_TITLE_EXACT))

print("=== ghost state logic (mirrors mirror_window._ghost_opacities) ===")

class Sim:
    def __init__(self):
        self.config = {}
        self.opacity_multiplier = 0.97
        self.game_mode = False
        self._ctrl_override = False

    def _ghost_opacities(self):
        # keep in lockstep with mirror_window._ghost_opacities
        if self.game_mode and not self._ctrl_override:
            try:
                fade = float(self.config.get("game_fade_frame", 0.15))
            except Exception:
                fade = 0.15
            fade = min(max(fade, 0.0), 1.0)
            return (self.opacity_multiplier * fade,
                    self.opacity_multiplier * 0.92)
        return self.opacity_multiplier, self.opacity_multiplier

s = Sim()
check("normal: frame==orb==multiplier", s._ghost_opacities() == (0.97, 0.97))
s.game_mode = True
f, o = s._ghost_opacities()
check("ghosted: frame is a whisper", abs(f - 0.97 * 0.15) < 1e-9)
check("ghosted: orb stays visible", abs(o - 0.97 * 0.92) < 1e-9)
s._ctrl_override = True
check("ctrl: solid again", s._ghost_opacities() == (0.97, 0.97))
s._ctrl_override = False
s.config["game_fade_frame"] = 0.3
check("config fade respected",
      abs(s._ghost_opacities()[0] - 0.97 * 0.3) < 1e-9)
s.config["game_fade_frame"] = "junk-not-float"
guard("junk config never crashes paint", s._ghost_opacities)
check("junk config falls back to default",
      abs(s._ghost_opacities()[0] - 0.97 * 0.15) < 1e-9)
s.config["game_fade_frame"] = 99
check("fade clamped to [0,1]", s._ghost_opacities()[0] <= 0.97)
s.config["game_fade_frame"] = -3
check("negative fade clamped to 0", s._ghost_opacities()[0] == 0.0)

def want_ct(game, ctrl, cfg=True):
    return game and not ctrl and cfg

check("game+noctrl -> click-through", want_ct(True, False) is True)
check("game+ctrl -> clickable", want_ct(True, True) is False)
check("no game -> clickable", want_ct(False, False) is False)
check("config off -> never click-through", want_ct(True, False, False) is False)

print(f"\n{'='*50}\nRESULT: {PASS} passed, {FAIL} failed")
if FAILURES:
    print("FAILURES:")
    for fl in FAILURES:
        print("  -", fl)
    sys.exit(1)
print("ALL GREEN")
