"""
GUI_OVERLAY/OWL_GUIDE.PY — Kalandra's owl, your walkthrough companion.

The owl decoration from the bottom of the Mirror of Kalandra, cut out as its
own face (assets/owl_face.png). It perches in the corner of menu windows and
talks in chat bubbles: a short intro the first time you open each tab, and a
click-through walkthrough of the current tab any time you click it.

The bubble's pointer is the gold arrow finial that hangs off the owl on the
mirror art (assets/owl_arrow.png) — it points AT things: down at the owl when
it's just chatting, up at the tab bar when it's introducing a tab.

Design rules (match theme.py):
  * Never crash the host window: every hook is wrapped; a missing PNG just
    means the owl doesn't appear.
  * State (welcome done / which tabs were introduced) persists in the same
    data_engine/config.json the rest of the app uses, under "owl_guide".
"""

import os

from PyQt6.QtCore import Qt, QEvent, QRectF, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PyQt6.QtWidgets import QWidget

from gui_overlay.theme import BG2, GOLD_DARK, GOLD_GLOW, MUTED, TEXT

ASSETS_DIR = os.path.join("gui_overlay", "assets")
OWL_FACE_PATH = os.path.join(ASSETS_DIR, "owl_face.png")
OWL_ARROW_PATH = os.path.join(ASSETS_DIR, "owl_arrow.png")

OWL_W = 96          # on-screen owl width (source art is 260x213)
MARGIN = 16         # gap from the parent's corner
BUBBLE_TEXT_W = 300  # wrap width for bubble text
TAIL_H = 30         # height reserved for the arrow tail

# ---------------------------------------------------------------------------
# The script. First line of each list doubles as the tab's first-visit intro.
# ---------------------------------------------------------------------------
WELCOME_TIPS = [
    "Hoo! I'm the owl from the Mirror's frame. Click me any time for a "
    "walkthrough of whichever tab you're looking at.",
    "New here? Start on the Build (PoB) tab — load your character with the "
    "green selector on the mirror overlay, then everything else lights up "
    "around it.",
    "Too many tabs? Settings → Dashboard tabs lets you hide the ones you "
    "don't use. I'll be in the corner if you need me.",
]

OWL_TIPS = {
    "Death Review": [
        "Every death lands here automatically: the moment the game log "
        "says you were slain, I ask OBS to rewind its replay buffer into "
        "a clip — the killer is already on film.",
        "The audit under the clip reads your CURRENT Path of Building "
        "numbers and lists the holes: uncapped resistances, negative "
        "chaos res, a pool too thin for your level.",
        "Press the AI autopsy button and I will connect what is on "
        "screen to the fixes — cheapest, highest-impact repairs first.",
    ],
    "Companion": [
        "This is our fireside — every chat with the Orb lives here as a "
        "thread, and everything Kalandra does shows up as color-coded notes "
        "between the messages.",
        "Threads on the left keep conversations separate — later, each of "
        "your characters gets its own orb and its own thread.",
        "The action notes are the Terminal's firehose made friendly: syncs in "
        "blue, build events in green, trouble in red.",
    ],
    "Terminal": [
        "This is Kalandra's live logbook — every backend event (button "
        "presses, DB syncs, voice/AI exchanges) streams here in real time.",
        "Use the filter box to narrow the firehose when you're chasing one "
        "specific event.",
    ],
    "Build (PoB)": [
        "Your currently loaded Path of Building character — class, skills, "
        "items, jewels — parsed straight from the build file.",
        "Load a character with the green selector medallion on the mirror "
        "overlay; this tab updates to match.",
        "No LuaJIT needed here — this view always works, even before the "
        "sim engine is set up.",
    ],
    "Build Sim": [
        "Real computed stats from the headless Path of Building engine for "
        "your active character.",
        "Hit 'Refresh build stats' after loading or changing a build.",
        "Numbers missing? 'Run self-test' diagnoses exactly what your PoB "
        "install exposes — copy the output to the developer for a fix.",
    ],
    "PoB (live)": [
        "This is the REAL Path of Building app living inside the tab — your "
        "own install, adopted into the dashboard.",
        "Use PoB's own import to pull characters from GGG. Any build you "
        "save is noticed and offered as your active character.",
    ],
    "PoE Overlay 2": [
        "PoE Overlay 2, containerized here just like PoB — the real app, "
        "adopted into the tab.",
    ],
    "Reserve / BIS": [
        "Your Unique / best-in-slot reserve: snapshot items you're holding "
        "for future builds or upgrades.",
        "Paste the raw item tooltip straight from the game (Ctrl+C on the "
        "item) into the editor on the right.",
        "Everything here persists across restarts and is fed to the AI as "
        "context when you ask about upgrades.",
    ],
    "Issues / Changelog": [
        "Found a bug, data error, or AI hallucination? Log it here so it "
        "actually gets fixed.",
        "Export the open items as Markdown to hand to the developer, then "
        "watch the changelog for the next revision.",
    ],
    "Price Check": [
        "Copy an item in game with Ctrl+C, paste it here, and the mod board "
        "shows every mod's search tier plus your own price history per mod.",
        "'Open trade search' sends the search to the Trade Site tab — a "
        "full-size browser — and switches you there.",
        "No price fabrication — you read real listings yourself. Searches "
        "can be saved by name and re-run any time.",
    ],
    "Trade Site": [
        "The official PoE2 trade site, full size. Price Check sends its "
        "searches here — or browse it directly.",
        "Whisper and buy manually as always; Kalandra never automates "
        "trades.",
    ],
    "Exchange": [
        "Live PoE2 currency economy from poe.ninja — rates, your holdings "
        "(including Gold), and live portfolio value.",
        "Check the day-over-day movers for buy/sell hints before you dump "
        "that stack of Chaos.",
    ],
    "Crafting": [
        "Describe the item you want in plain language; Kalandra lays out a "
        "realistic crafting path — mod groups, base sourcing, target tiers.",
        "Routes come annotated with live currency costs, and the Orb can "
        "refine the plan via AI.",
        "Probabilities? The Craft of Exile tab has the deterministic "
        "simulator linked from your plan.",
    ],
    "Filter Editor": [
        "Edit your loot filter in plain language — SHOW / HIDE / Minimal "
        "per block, with painted color swatches and a live label preview.",
        "Saving writes a .bak backup first, so experiment freely.",
    ],
    "Live Search": [
        "Build a live trade search without leaving the app — flip it to "
        "'Live' and it chimes on matches while you play.",
        "When something matches, you whisper and buy manually — no "
        "automation, fully ToS-clean.",
    ],
    "Grind Tracker": [
        "Snapshot what you're grinding with — tablets, waystones, their mods "
        "— then time your runs and log what they paid.",
        "One item per line: 'Breach Tablet x4 | 23% increased Quantity'. "
        "The pipe separates name from mods; semicolons separate mods.",
        "The per-mod table shows which mods correlate with income across "
        "YOUR runs — honest numbers that firm up as you log more.",
    ],
    "Craft of Exile": [
        "The Craft of Exile simulator, embedded. Use it to get exact odds "
        "for the plan the Crafting tab drew up.",
    ],
    "FilterBlade": [
        "FilterBlade, embedded — build a filter visually here, then "
        "fine-tune the saved .filter file in the Filter Editor tab.",
    ],
    "poe.ninja": [
        "poe.ninja, embedded — the raw economy data behind the Exchange "
        "tab, plus build ladders to steal ideas from.",
    ],
}


def _load_owl_state(config):
    st = (config or {}).get("owl_guide")
    return st if isinstance(st, dict) else {}


class OwlBubble(QWidget):
    """A gold-framed chat bubble whose tail is the mirror's arrow finial.

    tail='down' points at the owl below; tail='up' points at the tab bar
    above. `aim_x` (parent coords) is where the arrow tip should sit."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._text = ""
        self._counter = ""
        self._tail = "down"
        self._aim_x = 0
        self._arrow = QPixmap(OWL_ARROW_PATH) if os.path.exists(OWL_ARROW_PATH) else QPixmap()
        self._arrow_scaled = {}
        self._font = QFont()
        self._font.setPointSize(10)
        self._counter_font = QFont()
        self._counter_font.setPointSize(8)
        self.hide()

    def _arrow_pm(self, direction):
        pm = self._arrow_scaled.get(direction)
        if pm is None and not self._arrow.isNull():
            base = self._arrow.scaledToHeight(
                TAIL_H + 8, Qt.TransformationMode.SmoothTransformation)
            if direction == "up":
                base = base.transformed(QTransform().rotate(180),
                                        Qt.TransformationMode.SmoothTransformation)
            self._arrow_scaled[direction] = base
            pm = base
        return pm

    def show_tip(self, text, counter, tail, aim_x):
        self._text, self._counter, self._tail, self._aim_x = text, counter, tail, aim_x
        fm = QFontMetrics(self._font)
        r = fm.boundingRect(0, 0, BUBBLE_TEXT_W, 10000,
                            int(Qt.TextFlag.TextWordWrap), text)
        pad = 14
        box_w = min(BUBBLE_TEXT_W, r.width()) + 2 * pad
        box_h = r.height() + 2 * pad + 16          # +16 for the counter line
        self.resize(box_w, box_h + TAIL_H)
        self._place()
        self.show()
        self.raise_()

    def _place(self):
        p = self.parentWidget()
        if p is None:
            return
        x = self._aim_x - self.width() // 2
        x = max(8, min(x, p.width() - self.width() - 8))
        if self._tail == "down":
            # sits above the owl; arrow hangs below the box pointing down
            y = p.height() - MARGIN - int(OWL_W * 213 / 260) - self.height() - 4
        else:
            # sits under the tab bar; arrow rises above the box pointing up
            y = MARGIN + 34
        self.move(x, max(4, y))

    def mousePressEvent(self, ev):
        # Clicking the bubble = same as clicking the owl (advance / close).
        owl = getattr(self.parentWidget(), "_owl_guide", None)
        if owl is not None:
            owl.advance()
        ev.accept()

    def paintEvent(self, _ev):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        box_h = self.height() - TAIL_H
        box_y = TAIL_H if self._tail == "up" else 0
        box = QRectF(1, box_y + 1, self.width() - 2, box_h - 2)

        path = QPainterPath()
        path.addRoundedRect(box, 9, 9)
        painter.fillPath(path, QColor(BG2))
        painter.setPen(QPen(QColor(GOLD_DARK), 1.6))
        painter.drawPath(path)

        # Arrow finial tail, tip aimed at the target.
        pm = self._arrow_pm(self._tail)
        if pm is not None and not pm.isNull():
            ax = self._aim_x - self.x() - pm.width() // 2
            ax = max(6, min(ax, self.width() - pm.width() - 6))
            if self._tail == "down":
                ay = box_y + box_h - 10          # hangs below the box
            else:
                ay = box_y - pm.height() + 10    # rises above the box
            painter.drawPixmap(int(ax), int(ay), pm)

        pad = 14
        painter.setPen(QPen(QColor(TEXT)))
        painter.setFont(self._font)
        painter.drawText(QRectF(box.x() + pad, box.y() + pad - 4,
                                box.width() - 2 * pad, box.height() - 2 * pad - 8),
                         int(Qt.TextFlag.TextWordWrap), self._text)
        painter.setPen(QPen(QColor(MUTED)))
        painter.setFont(self._counter_font)
        painter.drawText(QRectF(box.x() + pad, box.bottom() - 22,
                                box.width() - 2 * pad, 18),
                         int(Qt.AlignmentFlag.AlignRight), self._counter)


class OwlGuide(QWidget):
    """The owl face from the mirror, perched in a corner of a tabbed window.

    Usage (host window):
        self._owl_guide = OwlGuide(self, self.tabs, config=self.config)

    First-ever open -> welcome bubbles. First visit to each tab -> that tab's
    intro (arrow pointing up at the tab). Click the owl -> step through the
    current tab's walkthrough tips."""

    def __init__(self, parent, tabs, config=None, tips=None):
        super().__init__(parent)
        self.tabs = tabs
        self.config = config if isinstance(config, dict) else {}
        self.tips = tips or OWL_TIPS
        self._tip_idx = -1
        self._mode = "tab"          # "welcome" or "tab"
        self._hover = False

        self._face = QPixmap(OWL_FACE_PATH) if os.path.exists(OWL_FACE_PATH) else QPixmap()
        if self._face.isNull():
            self.hide()
            return
        h = int(OWL_W * self._face.height() / self._face.width())
        self._face = self._face.scaledToWidth(
            OWL_W, Qt.TransformationMode.SmoothTransformation)
        self.setFixedSize(OWL_W, h)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Kalandra's owl — click for a walkthrough of this tab")
        self.setMouseTracking(True)

        self.bubble = OwlBubble(parent)
        parent._owl_guide = self          # lets the bubble find us
        parent.installEventFilter(self)
        try:
            tabs.currentChanged.connect(self._on_tab_changed)
        except Exception:
            pass

        self._reposition()
        self.show()
        self.raise_()
        # After the window settles: welcome on first-ever open, else the
        # current tab's intro if it hasn't been seen.
        QTimer.singleShot(700, self._first_greeting)

    # ---------------- state persistence ----------------
    def _state(self):
        return _load_owl_state(self.config)

    def _save_state(self, st):
        try:
            self.config["owl_guide"] = st
            from gui_overlay.mirror_window import load_config, save_config
            disk = load_config()
            disk["owl_guide"] = st
            save_config(disk)
        except Exception:
            pass

    # ---------------- geometry ----------------
    def _reposition(self):
        p = self.parentWidget()
        if p is None:
            return
        self.move(p.width() - self.width() - MARGIN,
                  p.height() - self.height() - MARGIN)
        if self.bubble.isVisible():
            self.bubble._place()

    def eventFilter(self, obj, ev):
        if obj is self.parentWidget() and ev.type() in (QEvent.Type.Resize,
                                                        QEvent.Type.Show):
            self._reposition()
            self.raise_()
            if self.bubble.isVisible():
                self.bubble.raise_()
        return False

    # ---------------- talking ----------------
    def _current_label(self):
        try:
            return self.tabs.tabText(self.tabs.currentIndex())
        except Exception:
            return ""

    def _tab_aim_x(self):
        """X (parent coords) of the current tab's header — the arrow target."""
        try:
            # Grouped dashboard: ask the wrapper for the inner tab's center.
            if hasattr(self.tabs, "current_tab_center_in"):
                pt = self.tabs.current_tab_center_in(self.parentWidget())
                if pt is not None:
                    return pt.x()
            bar = self.tabs.tabBar()
            r = bar.tabRect(self.tabs.currentIndex())
            return bar.mapTo(self.parentWidget(), r.center()).x()
        except Exception:
            return self.parentWidget().width() // 2

    def _owl_aim_x(self):
        return self.x() + self.width() // 2

    def _tips_for(self, label):
        return self.tips.get(label) or [
            f"The {label} tab. I don't have a walkthrough written for this "
            "one yet — poke around, nothing here bites."]

    def _speak(self, tips, idx, tail):
        n = len(tips)
        counter = f"{idx + 1}/{n} — click for more" if n > 1 and idx + 1 < n \
            else (f"{idx + 1}/{n}" if n > 1 else "")
        aim = self._tab_aim_x() if tail == "up" else self._owl_aim_x()
        self.bubble.show_tip(tips[idx], counter, tail, aim)

    def _first_greeting(self):
        st = self._state()
        if not st.get("welcome_done"):
            self._mode = "welcome"
            self._tip_idx = 0
            self._speak(WELCOME_TIPS, 0, "down")
            st["welcome_done"] = True
            self._save_state(st)
        else:
            # Freshness first: a stale active build is the most useful thing
            # the owl can tell a returning player about.
            if not self._check_build_freshness():
                self._on_tab_changed(self.tabs.currentIndex())

    # ---------------- build freshness (owl-guided re-import) ----------------
    def _check_build_freshness(self):
        """If the active build file is older than build_stale_days (default 3),
        walk the player through pulling the up-to-date character via PoB's own
        import. Prompts ONCE per staleness (path+mtime remembered); a fresh
        save resets the reminder. Returns True if the walkthrough started."""
        try:
            import time as _time
            path = self.config.get("active_build_path") or ""
            if not path or not os.path.exists(path):
                return False
            mtime = os.path.getmtime(path)
            days = (_time.time() - mtime) / 86400.0
            try:
                limit = float(self.config.get("build_stale_days", 3))
            except Exception:
                limit = 3.0
            if days < max(limit, 0.5):
                return False
            seen_key = f"{path}:{int(mtime)}"
            st = self._state()
            if st.get("freshness_seen") == seen_key:
                return False
            st["freshness_seen"] = seen_key
            self._save_state(st)
            name = os.path.splitext(os.path.basename(path))[0]
            self.walk_through([
                f"Heads up — your active build ({name}) was last saved "
                f"{int(days)} day{'s' if int(days) != 1 else ''} ago. Your "
                "real character has probably outgrown it: new levels, new "
                "gear, maybe a respec. Click me and I'll walk you through "
                "pulling the fresh copy.",
                "Step 1: open the PoB (live) tab — that's your actual Path "
                "of Building app, contained in the dashboard.",
                "Step 2: in PoB, open Import/Export Build → 'Import from "
                "account' → enter your account name, pick this character, "
                "and Import. That pulls your CURRENT gear, tree and level "
                "straight from GGG.",
                "Step 3: save the build in PoB (Ctrl+S). Kalandra watches "
                "the Builds folder — it will notice the save and offer the "
                "fresh version as your active character. Accept, and the "
                "sheet, sim and reviews all update to match reality.",
            ])
            return True
        except Exception:
            return False

    def walk_through(self, steps):
        """Generic owl-guided walkthrough: a temporary step list the player
        clicks through (used by the freshness prompt; reusable anywhere)."""
        if not steps:
            return
        self._mode = "walk"
        self._walk_tips = list(steps)
        self._tip_idx = 0
        self._speak(self._walk_tips, 0, "down")

    def _on_tab_changed(self, _idx):
        self._mode = "tab"
        self._tip_idx = -1
        label = self._current_label()
        st = self._state()
        seen = st.get("seen_tabs") or []
        if label and label not in seen:
            self._tip_idx = 0
            self._speak(self._tips_for(label), 0, "up")
            st["seen_tabs"] = seen + [label]
            self._save_state(st)
        elif self.bubble.isVisible():
            self.bubble.hide()

    def advance(self):
        """Next tip; wraps up (hides) after the last one. Owl + bubble clicks."""
        was_welcome = self._mode == "welcome"
        if self._mode == "walk":
            tips = getattr(self, "_walk_tips", None) or ["(walkthrough ended)"]
        elif self._mode == "welcome":
            tips = WELCOME_TIPS
        else:
            tips = self._tips_for(self._current_label())
        self._tip_idx += 1
        if self._tip_idx >= len(tips):
            self._tip_idx = -1
            self._mode = "tab"
            self.bubble.hide()
            if was_welcome:
                self._maybe_interview()
            return
        tail = "down" if self._mode in ("welcome", "walk") or self._tip_idx > 0 \
            else "up"
        self._speak(tips, self._tip_idx, tail)

    def _maybe_interview(self, force=False):
        """First-use interview: gauge experience/playstyle so every explanation
        lands at the right depth. Resumable; 'Ask me later' respected."""
        try:
            from core_engine.player_profile import PlayerProfile
            from gui_overlay.owl_interview import OwlInterview
            prof = PlayerProfile.load()
            if not force and prof.interview_done():
                return
            self.bubble.hide()
            self._interview = OwlInterview(
                self.parentWidget(), self, on_done=self._interview_done)
        except Exception:
            pass

    def _interview_done(self, profile):
        self._interview = None
        if profile is None:
            return
        # New-player arc: brand-new (or buildless) players get walked into
        # the build finder — a Companion conversation that narrows playstyle
        # and ends with a followed build + roadmap (core_engine.build_seeker).
        is_new = profile.get("background") == "new" or \
            (profile.get("peak_level") == "lt90"
             and not (profile.get("build_history") or "").strip())
        if is_new:
            self.bubble.show_tip(
                "One more thing — if you haven't picked a build to follow "
                "yet, that's the single best first step: a guide teaches you "
                "which mechanics work together. Click me and I'll help you "
                "find one that fits how you like to play.", "", "down",
                self._owl_aim_x())
            self._offer_finder = True
        else:
            self.bubble.show_tip(
                "Perfect — I'll pitch everything to that. Right-click me any "
                "time to redo the interview.", "", "down", self._owl_aim_x())

    def _start_build_finder(self):
        """Hand the new player to the Companion chat, seeded with the build
        finder conversation (playstyle Q&A -> archetype suggestions ->
        roadmap offer). The dashboard hosts us, so switch its tab and seed."""
        try:
            host = self.parentWidget()
            if hasattr(host, "show_tab"):
                host.show_tab("Companion")
            comp = None
            if hasattr(host, "tabs"):
                for i in range(host.tabs.count()):
                    if host.tabs.tabText(i) == "Companion":
                        comp = host.tabs.widget(i)
                        break
            if comp is not None and hasattr(comp, "start_build_finder"):
                comp.start_build_finder()
        except Exception:
            pass

    # ---------------- input + paint ----------------
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            if getattr(self, "_offer_finder", False):
                self._offer_finder = False
                self.bubble.hide()
                self._start_build_finder()
                ev.accept()
                return
            if not self.bubble.isVisible():
                self._mode = "tab"
                self._tip_idx = -1
            self.advance()
            ev.accept()
        elif ev.button() == Qt.MouseButton.RightButton:
            self._maybe_interview(force=True)
            ev.accept()

    def enterEvent(self, ev):
        self._hover = True
        self.update()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self._hover = False
        self.update()
        super().leaveEvent(ev)

    def paintEvent(self, _ev):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._hover:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            glow = QColor(GOLD_GLOW)
            glow.setAlpha(60)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(self.rect().adjusted(2, 6, -2, -2))
        painter.drawPixmap(0, (self.height() - self._face.height()) // 2, self._face)
