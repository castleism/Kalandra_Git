"""
GUI_OVERLAY/CRAFT_HUNTER.PY — the Craft Hunter tab (CH-P1 UI of
docs/CRAFT_HUNTER_SPEC.md).

Front end for core_engine.craft_hunter: build the target-mod list (with
autocomplete fed from the scraped localized_knowledge.db), get the in-game
stash-search regex for free, and — while armed — have every in-game Ctrl+C
answered with HIT (stop!) or FALSE ALARM (keep going). The clipboard route
comes in via mirror_window._on_clipboard_item -> dashboard.notify_craft_confirm;
this file is pure presentation plus config persistence.

Compliance (spec §2, hard rule): read-only. We parse what the game writes to
the clipboard and paint a verdict for the HUMAN; no input is ever intercepted,
suppressed, or sent. P2's tooltip OCR will bolt onto the same engine.
"""

import math
import os
import threading

from PyQt6.QtCore import QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QCompleter, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from gui_overlay.theme import (
    BG0, BG1, COLOR_WARN, EMERALD, FAINT, GOLD, GOLD_LIGHT, MUTED, RUBY, TEXT,
)

ALARM_WAV = os.path.join("gui_overlay", "assets", "sfx", "craft_alarm.wav")

_TOAST = None      # single live toast (a new confirm replaces the old one)
_FLASH = None      # single live flash alarm


def play_alarm_sound():
    """Loud, distinct hit sound. winsound (stdlib, async, Windows) plays the
    bundled chirp; anywhere else — or with the asset missing — fall back to
    the system beep. Never raises."""
    try:
        import winsound
        if os.path.exists(ALARM_WAV):
            winsound.PlaySound(ALARM_WAV,
                               winsound.SND_FILENAME | winsound.SND_ASYNC)
            return
    except Exception:
        pass
    try:
        QApplication.beep()
    except Exception:
        pass


def show_flash_alarm():
    """Fire the full-screen stop flash (3 gold pulses). Click-through and
    input-transparent by construction — it can only be LOOKED at."""
    global _FLASH
    try:
        if _FLASH is not None:
            _FLASH.close()
    except Exception:
        pass
    try:
        _FLASH = FlashAlarm()
        _FLASH.show()
    except Exception:
        _FLASH = None


class FlashAlarm(QWidget):
    """Spec §5: full-screen transparent CLICK-THROUGH flash, three pulses in
    the theme accent, then gone. WindowTransparentForInput +
    WA_TransparentForMouseEvents mean every click lands on whatever is
    underneath (the game) exactly as if we weren't there."""

    PULSES = 3
    PERIOD_MS = 420

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool
                         | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                          True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        try:
            from PyQt6.QtGui import QCursor
            scr = (QApplication.screenAt(QCursor.pos())
                   or QApplication.primaryScreen())
            self.setGeometry(scr.geometry())
        except Exception:
            pass
        self._t0 = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def _phase(self):
        import time as _t
        if self._t0 is None:
            self._t0 = _t.time()
        return (_t.time() - self._t0) * 1000.0 / self.PERIOD_MS

    def _tick(self):
        if self._phase() >= self.PULSES:
            self._timer.stop()
            self.close()
            return
        self.update()

    def paintEvent(self, _ev):
        ph = self._phase()
        if ph >= self.PULSES:
            return
        # sine envelope per pulse: 0 -> peak -> 0
        alpha = max(0.0, math.sin((ph % 1.0) * math.pi))
        p = QPainter(self)
        edge = QColor(GOLD)
        w, h = self.width(), self.height()
        thick = max(24, w // 28)
        for i in range(4):                       # feathered border glow
            a = int(150 * alpha * (1.0 - i / 4.0))
            edge.setAlpha(max(0, a))
            pen = QPen(edge)
            pen.setWidth(thick // (i + 1) + 2)
            p.setPen(pen)
            inset = i * (thick // 3)
            p.drawRect(inset, inset, w - 2 * inset - 1, h - 2 * inset - 1)
        wash = QColor(GOLD)
        wash.setAlpha(int(28 * alpha))           # faint full-screen wash
        p.fillRect(self.rect(), wash)
        p.end()


class CalibrateOverlay(QWidget):
    """Spec §7: one-time tooltip calibration. The screen dims, the user drags
    a rectangle over the item tooltip, and the region (PHYSICAL pixels, for
    mss) is handed to on_done. ESC cancels. This window intentionally DOES
    take the mouse — it only exists during the drag, over a dimmed screen."""

    def __init__(self, on_done):
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.on_done = on_done
        self._origin = None
        self._rect = QRect()
        try:
            from PyQt6.QtGui import QCursor
            self._screen = (QApplication.screenAt(QCursor.pos())
                            or QApplication.primaryScreen())
            self.setGeometry(self._screen.geometry())
        except Exception:
            self._screen = None

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 130))
        if not self._rect.isNull():
            p.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_Clear)
            p.fillRect(self._rect, Qt.GlobalColor.transparent)
            p.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver)
            pen = QPen(QColor(GOLD))
            pen.setWidth(2)
            p.setPen(pen)
            p.drawRect(self._rect)
            p.drawText(self._rect.adjusted(0, -22, 0, 0).topLeft(),
                       f"{self._rect.width()}×{self._rect.height()} — "
                       "release to save")
        else:
            p.setPen(QColor(TEXT))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Drag a box over the item TOOLTIP area — ESC cancels")
        p.end()

    def mousePressEvent(self, ev):
        self._origin = ev.position().toPoint()
        self._rect = QRect(self._origin, self._origin)
        self.update()

    def mouseMoveEvent(self, ev):
        if self._origin is not None:
            self._rect = QRect(self._origin,
                               ev.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, ev):
        r = QRect(self._origin, ev.position().toPoint()).normalized() \
            if self._origin is not None else QRect()
        self.close()
        if r.width() >= 8 and r.height() >= 8 and self.on_done:
            dpr = 1.0
            gx = gy = 0
            try:
                dpr = float(self._screen.devicePixelRatio())
                g = self._screen.geometry()
                gx, gy = g.x(), g.y()
            except Exception:
                pass
            self.on_done({
                "left": int((gx + r.x()) * dpr),
                "top": int((gy + r.y()) * dpr),
                "width": int(r.width() * dpr),
                "height": int(r.height() * dpr),
            })

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(ev)


def _f8_down():
    """Is F8 physically held right now? Passive GetAsyncKeyState READ (the
    exact pattern ghost mode uses for Ctrl) — not a hook, nothing is
    intercepted or consumed; the game still receives its F8. False on
    non-Windows / any error."""
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x77) & 0x8000)
    except Exception:
        return False


def show_hunt_toast(res):
    """Float the clipboard-confirm verdict near the cursor. HIT = green
    stop card + system beep; miss = quiet red 'keep going'. Purely visual —
    dismiss by click/ESC or let it fade (never traps the cursor)."""
    global _TOAST
    try:
        if _TOAST is not None:
            _TOAST.close()
    except Exception:
        pass
    try:
        _TOAST = HuntToast(res)
        _TOAST.show()
        if res.get("hit"):
            QApplication.beep()
    except Exception:
        _TOAST = None


class HuntToast(QWidget):
    def __init__(self, res):
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        hit = bool(res.get("hit"))
        near = bool(res.get("near_miss")) and not hit
        edge = EMERALD if hit else (COLOR_WARN if near else RUBY)
        self.setStyleSheet(
            f"QWidget{{background:{BG1};color:{TEXT};font-size:13px;"
            f"border:2px solid {edge};border-radius:6px;}}"
            f"QLabel{{border:none;background:transparent;}}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        head = QLabel("⛔ TARGET HIT — STOP" if hit
                      else ("NEAR MISS — right mod, roll off" if near
                            else "FALSE ALARM — keep going"))
        head.setStyleSheet(
            f"color:{edge};font-size:16px;"
            f"font-weight:bold;background:transparent;border:none;")
        lay.addWidget(head)
        for t, ok, detail in (res.get("results") or [])[:4]:
            mod = t.get("mod") or t.get("mod_line") or "?"
            if isinstance(mod, list):
                mod = " + ".join(mod)
            line = QLabel(("✅ " if ok else "· ") + f"{mod} — {detail}")
            line.setStyleSheet(f"color:{TEXT if ok else MUTED};"
                               "background:transparent;border:none;")
            lay.addWidget(line)
        try:
            from PyQt6.QtGui import QCursor
            pos = QCursor.pos()
            scr = QApplication.screenAt(pos) or QApplication.primaryScreen()
            g = scr.availableGeometry()
            self.adjustSize()
            x = min(max(pos.x() + 18, g.left()), g.right() - self.width() - 8)
            y = min(max(pos.y() - self.height() - 12, g.top()),
                    g.bottom() - self.height() - 8)
            self.move(x, y)
        except Exception:
            pass
        QTimer.singleShot(8000 if hit else 4000, self.close)

    def mousePressEvent(self, _ev):
        self.close()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(ev)


class CraftHunterTab(QWidget):
    """Target list + live stash regex + clipboard-confirm status + (P2) the
    OCR tooltip watcher with calibration and the flash/sound alarm."""

    _suggestions_ready = pyqtSignal(list)
    _alarm_ready = pyqtSignal(dict)        # watcher thread -> UI thread
    _watch_status = pyqtSignal(str)

    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.config = config if config is not None else {}
        self._stats = {"checks": 0, "hits": 0}
        self._watcher = None
        self._calib = None
        self._build_ui()
        self._suggestions_ready.connect(self._apply_suggestions)
        self._alarm_ready.connect(self._on_alarm_ui)
        self._watch_status.connect(self._on_watch_status)
        self._load_targets_from_config()
        self._load_suggestions()
        self._refresh_regex()
        # F8 arm/disarm: passive key-state poll (ghost mode's Ctrl pattern) —
        # listen-only, the game still gets its own F8.
        self._f8_was = False
        self._f8_timer = QTimer(self)
        self._f8_timer.timeout.connect(self._poll_f8)
        self._f8_timer.start(150)

    # ------------------------------------------------ UI
    def _build_ui(self):
        root = QVBoxLayout(self)
        head = QLabel("Craft Hunter — stop the instant your mod lands")
        head.setStyleSheet(f"color:{GOLD};font-size:18px;font-weight:bold;")
        root.addWidget(head)
        sub = QLabel(
            "List the mod rolls you're hunting, paste the generated search "
            "into the in-game stash/vendor box (the GAME highlights hits), "
            "and while the hunt is armed every in-game Ctrl+C over the item "
            "answers HIT or keep-going. Read-only, always: Kalandra never "
            "blocks or sends a single input — you stay the one crafting.")
        sub.setStyleSheet(f"color:{MUTED};")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # -- add-target row ------------------------------------------------
        row = QHBoxLayout()
        self.mod_box = QComboBox()
        self.mod_box.setEditable(True)
        self.mod_box.setMinimumWidth(340)
        self.mod_box.lineEdit().setPlaceholderText(
            "mod line, # = the number — e.g.  #% increased Spell Damage")
        row.addWidget(self.mod_box, 1)
        self.min_edit = QLineEdit()
        self.min_edit.setPlaceholderText("min")
        self.min_edit.setFixedWidth(60)
        self.min_edit.setToolTip(
            "Inclusive. Applies to the FIRST # in the line "
            "('Adds # to #...' checks the first number).")
        self.max_edit = QLineEdit()
        self.max_edit.setPlaceholderText("max")
        self.max_edit.setFixedWidth(60)
        self.max_edit.setToolTip("Inclusive; leave empty for open-ended.")
        row.addWidget(self.min_edit)
        row.addWidget(self.max_edit)
        add = QPushButton("＋ Add target")
        add.clicked.connect(self._add_from_row)
        row.addWidget(add)
        root.addLayout(row)

        # -- target table ----------------------------------------------------
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Mod line", "min", "max", ""])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 420)
        self.table.setColumnWidth(1, 60)
        self.table.setColumnWidth(2, 60)
        self.table.setColumnWidth(3, 40)
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(lambda _i: self._table_edited())
        root.addWidget(self.table, 1)

        # -- mode + arm -----------------------------------------------------
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Stop when"))
        self.mode_box = QComboBox()
        self.mode_box.addItems(["ANY target hits", "ALL targets hit"])
        self.mode_box.currentIndexChanged.connect(lambda _i: self._persist())
        mode_row.addWidget(self.mode_box)
        self.arm_btn = QPushButton()
        self.arm_btn.setCheckable(True)
        self.arm_btn.setToolTip("F8 toggles this too (works while in game).")
        self.arm_btn.clicked.connect(self._toggle_armed)
        mode_row.addWidget(self.arm_btn)
        self.lamp = QLabel("")
        self.lamp.setStyleSheet(f"color:{MUTED};")
        mode_row.addWidget(self.lamp)
        mode_row.addStretch()
        hints = QPushButton("🔨 Route hints")
        hints.setToolTip("Essence/Chaos/Omen crafting routes for these "
                         "targets (offline heuristic + live prices when the "
                         "Exchange tab has them).")
        hints.clicked.connect(self._route_hints)
        mode_row.addWidget(hints)
        self.stats_lbl = QLabel("session: 0 confirms · 0 hits")
        self.stats_lbl.setStyleSheet(f"color:{FAINT};")
        mode_row.addWidget(self.stats_lbl)
        root.addLayout(mode_row)

        # -- P2: OCR tooltip watcher --------------------------------------
        watch_row = QHBoxLayout()
        watch_row.addWidget(QLabel("Live watcher:"))
        cal_btn = QPushButton("📐 Calibrate tooltip")
        cal_btn.setToolTip("Drag a box over where the item tooltip sits "
                           "while you craft (hover the item first, alt-tab "
                           "here, click this). Re-do it if you move the "
                           "stash window or change monitors.")
        cal_btn.clicked.connect(self._calibrate)
        watch_row.addWidget(cal_btn)
        self.watch_btn = QPushButton("👁 Start watcher")
        self.watch_btn.setCheckable(True)
        self.watch_btn.clicked.connect(self._toggle_watcher)
        watch_row.addWidget(self.watch_btn)
        self.autopause_box = QCheckBox("pause after hit")
        self.autopause_box.setChecked(
            bool(self._hcfg().get("auto_pause", True)))
        self.autopause_box.toggled.connect(self._save_watch_opts)
        watch_row.addWidget(self.autopause_box)
        self.fg_only_box = QCheckBox("only while game is foreground")
        self.fg_only_box.setChecked(bool(self._hcfg().get("fg_only", True)))
        self.fg_only_box.toggled.connect(self._save_watch_opts)
        watch_row.addWidget(self.fg_only_box)
        self.watch_lamp = QLabel("")
        self.watch_lamp.setStyleSheet(f"color:{MUTED};")
        watch_row.addWidget(self.watch_lamp)
        watch_row.addStretch()
        root.addLayout(watch_row)
        self._refresh_watch_lamp("stopped")

        # -- stash regex ------------------------------------------------------
        rx_row = QHBoxLayout()
        rx_row.addWidget(QLabel("In-game search:"))
        self.rx_edit = QLineEdit()
        self.rx_edit.setReadOnly(True)
        self.rx_edit.setStyleSheet(
            f"background:{BG0};color:{GOLD_LIGHT};"
            "font-family:Consolas,monospace;")
        rx_row.addWidget(self.rx_edit, 1)
        self.rx_len = QLabel("0/50")
        self.rx_len.setStyleSheet(f"color:{FAINT};")
        rx_row.addWidget(self.rx_len)
        copy = QPushButton("📋 Copy")
        copy.clicked.connect(self._copy_regex)
        rx_row.addWidget(copy)
        root.addLayout(rx_row)
        self.rx_note = QLabel("")
        self.rx_note.setStyleSheet(f"color:{MUTED};")
        self.rx_note.setWordWrap(True)
        root.addWidget(self.rx_note)

        # -- confirm banner ---------------------------------------------------
        self.banner = QLabel("Arm the hunt, then Ctrl+C the item in game "
                             "after each craft — the verdict lands here "
                             "(and in a toast by your cursor).")
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet(
            f"background:{BG0};color:{FAINT};border:1px solid #333;"
            "padding:10px;font-size:14px;")
        root.addWidget(self.banner)
        self._sync_armed_ui()

    # ------------------------------------------------ targets <-> table
    def _hcfg(self):
        c = self.config.get("craft_hunter")
        if not isinstance(c, dict):
            c = {}
            self.config["craft_hunter"] = c
        c.setdefault("targets", [])
        c.setdefault("mode", "any")
        c.setdefault("armed", False)
        return c

    def _load_targets_from_config(self):
        c = self._hcfg()
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for t in c["targets"]:
            self._append_row(t.get("mod", ""), t.get("min"), t.get("max"))
        self.table.blockSignals(False)
        self.mode_box.setCurrentIndex(1 if c.get("mode") == "all" else 0)

    def _append_row(self, mod, lo, hi):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(str(mod)))
        self.table.setItem(r, 1, QTableWidgetItem(
            "" if lo is None else f"{lo:g}" if isinstance(lo, float) else str(lo)))
        self.table.setItem(r, 2, QTableWidgetItem(
            "" if hi is None else f"{hi:g}" if isinstance(hi, float) else str(hi)))
        rm = QPushButton("✕")
        rm.setFixedWidth(32)
        rm.clicked.connect(lambda _c, btn=rm: self._remove_row_of(btn))
        self.table.setCellWidget(r, 3, rm)

    def _remove_row_of(self, btn):
        for r in range(self.table.rowCount()):
            if self.table.cellWidget(r, 3) is btn:
                self.table.removeRow(r)
                break
        self._table_edited()

    @staticmethod
    def _num_or_none(s):
        s = (s or "").strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None

    def _targets_from_table(self):
        out = []
        for r in range(self.table.rowCount()):
            mod = (self.table.item(r, 0).text()
                   if self.table.item(r, 0) else "").strip()
            if not mod:
                continue
            out.append({
                "mod": mod,
                "min": self._num_or_none(
                    self.table.item(r, 1).text() if self.table.item(r, 1) else ""),
                "max": self._num_or_none(
                    self.table.item(r, 2).text() if self.table.item(r, 2) else ""),
            })
        return out

    def _add_from_row(self):
        mod = self.mod_box.currentText().strip()
        if not mod:
            return
        self.table.blockSignals(True)
        self._append_row(mod, self._num_or_none(self.min_edit.text()),
                         self._num_or_none(self.max_edit.text()))
        self.table.blockSignals(False)
        self.mod_box.setCurrentText("")
        self.min_edit.clear()
        self.max_edit.clear()
        self._table_edited()

    def _table_edited(self):
        self._persist()
        self._refresh_regex()

    def _persist(self):
        c = self._hcfg()
        c["targets"] = self._targets_from_table()
        c["mode"] = "all" if self.mode_box.currentIndex() == 1 else "any"
        try:                                    # same save path as every tab
            from gui_overlay.mirror_window import save_config
            save_config(self.config)
        except Exception:
            pass

    # ------------------------------------------------ arm / disarm
    def _toggle_armed(self):
        c = self._hcfg()
        c["armed"] = bool(self.arm_btn.isChecked())
        self._persist()
        self._sync_armed_ui()

    def _sync_armed_ui(self):
        armed = bool(self._hcfg().get("armed"))
        self.arm_btn.setChecked(armed)
        self.arm_btn.setText("🛑 Disarm hunt" if armed else "🎯 Arm hunt")
        self.lamp.setText("● armed — Ctrl+C in game to confirm"
                          if armed else "○ disarmed")
        self.lamp.setStyleSheet(
            f"color:{EMERALD};" if armed else f"color:{MUTED};")

    # ------------------------------------------------ P2: watcher wiring
    def _save_watch_opts(self):
        c = self._hcfg()
        c["auto_pause"] = bool(self.autopause_box.isChecked())
        c["fg_only"] = bool(self.fg_only_box.isChecked())
        self._persist()

    def _calibrate(self):
        def _done(region):
            c = self._hcfg()
            c["region"] = region
            self._persist()
            self._refresh_watch_lamp("calibrated")
        try:
            self._calib = CalibrateOverlay(_done)
            self._calib.show()
            self._calib.activateWindow()
        except Exception as e:
            self.watch_lamp.setText(f"calibration failed: {e}")

    def _toggle_watcher(self):
        if self.watch_btn.isChecked():
            self._start_watcher()
        else:
            self._stop_watcher()

    def _start_watcher(self):
        from core_engine.craft_hunter import (available_ocr, make_grabber,
                                              make_ocr, TooltipWatcher)
        c = self._hcfg()
        targets = self._targets_from_table()
        kind, msg = available_ocr()
        region = c.get("region") or {}
        problem = None
        if not targets:
            problem = "add at least one target first"
        elif kind is None:
            problem = msg
        elif not region:
            problem = "calibrate the tooltip region first"
        grab = make_grabber(region) if not problem else None
        ocr = make_ocr() if not problem else None
        if not problem and grab is None:
            problem = "screen capture unavailable (mss/numpy missing?)"
        if not problem and ocr is None:
            problem = msg
        if problem:
            self.watch_btn.setChecked(False)
            self._refresh_watch_lamp("blocked: " + problem)
            return
        fg = None
        if self.fg_only_box.isChecked():
            try:
                from gui_overlay.game_watch import game_foreground
                fg = game_foreground
            except Exception:
                fg = None
        self._watcher = TooltipWatcher(
            targets, mode=c.get("mode", "any"), grab=grab, ocr=ocr,
            on_alarm=self._alarm_ready.emit,
            on_status=self._watch_status.emit,
            foreground=fg, auto_pause=self.autopause_box.isChecked())
        self._watcher.start()
        self.watch_btn.setText("👁 Stop watcher")
        self._refresh_watch_lamp("watching")

    def _stop_watcher(self):
        if self._watcher is not None:
            try:
                self._watcher.stop()
            except Exception:
                pass
            self._watcher = None
        self.watch_btn.setChecked(False)
        self.watch_btn.setText("👁 Start watcher")
        self._refresh_watch_lamp("stopped")

    def _refresh_watch_lamp(self, status):
        pretty = {
            "stopped": ("○ watcher off", MUTED),
            "calibrated": ("📐 region saved — start the watcher", EMERALD),
            "watching": ("● watching the tooltip", EMERALD),
            "checked": ("● watching the tooltip", EMERALD),
            "unchanged": ("● watching the tooltip", EMERALD),
            "near-miss": ("◐ near miss seen — right mod, roll off",
                          COLOR_WARN),
            "hit": ("⛔ HIT — paused; press Start to re-arm" ,
                    EMERALD),
            "paused": ("⏸ paused after hit — Stop/Start to re-arm", GOLD),
            "game-not-foreground": ("… waiting for the game window", MUTED),
            "no-frame": ("⚠ capture failed — re-calibrate?", RUBY),
            "not-configured": ("⚠ watcher lost its config", RUBY),
        }.get(status)
        if pretty is None:
            pretty = (status, RUBY if status.startswith(("blocked", "ocr-"))
                      else MUTED)
        self.watch_lamp.setText(pretty[0])
        self.watch_lamp.setStyleSheet(f"color:{pretty[1]};")

    def _on_watch_status(self, status):
        self._refresh_watch_lamp(status)

    def _on_alarm_ui(self, res):
        """Watcher hit, marshalled onto the UI thread: flash + sound + toast
        + banner. The clipboard confirm (Ctrl+C) stays the authoritative
        verdict — the banner says so."""
        c = self._hcfg()
        if c.get("flash", True):
            show_flash_alarm()
        if c.get("sound", True):
            play_alarm_sound()
        show_hunt_toast(res)
        bits = []
        for t, ok, detail in (res.get("results") or []):
            mod = t.get("mod") or t.get("mod_line") or "?"
            if isinstance(mod, list):
                mod = " + ".join(mod)
            bits.append(("✅ " if ok else "· ") + f"{mod} — {detail}")
        self.banner.setText("⛔ TOOLTIP HIT — STOP CRAFTING\n" + "\n".join(bits)
                            + "\nConfirm with Ctrl+C on the item — the "
                            "clipboard check is the authoritative verdict.")
        self.banner.setStyleSheet(
            f"background:{BG0};padding:10px;font-size:14px;"
            f"color:{EMERALD};border:2px solid {EMERALD};")
        if self.autopause_box.isChecked():
            self.watch_btn.setChecked(False)
            self.watch_btn.setText("👁 Start watcher")

    # ------------------------------------------------ F8 arm toggle
    def _poll_f8(self):
        down = _f8_down()
        if down and not self._f8_was:          # key-down edge
            self.arm_btn.click()
        self._f8_was = down

    # ------------------------------------------------ P3: route hints
    def _route_hints(self):
        targets = self._targets_from_table()
        if not targets:
            self.banner.setText("Add targets first — then I'll sketch the "
                                "essence/chaos/omen routes to hit them.")
            return
        words = []
        for t in targets:
            mod = t.get("mod") or ""
            words.append(mod.replace("#", "").strip())
        goal = "rare with " + ", ".join(w for w in words if w)
        try:
            from core_engine.trade_tools import offline_craft_guidance
            econ = None
            try:
                from gui_overlay import dashboard as _dash
                econ = _dash.LAST_ECON_ROWS or None
            except Exception:
                pass
            self.banner.setText(offline_craft_guidance(goal, econ))
            self.banner.setStyleSheet(
                f"background:{BG0};color:{TEXT};border:1px solid {GOLD};"
                "padding:10px;font-size:12px;")
        except Exception as e:
            self.banner.setText(f"Route hints unavailable: {e}")

    # ------------------------------------------------ stash regex
    def _refresh_regex(self):
        try:
            from core_engine.craft_hunter import STASH_REGEX_BUDGET, stash_regex
            rx, notes = stash_regex(self._targets_from_table())
            self.rx_edit.setText(rx)
            self.rx_len.setText(f"{len(rx)}/{STASH_REGEX_BUDGET}")
            self.rx_note.setText(" ".join(notes))
        except Exception as e:
            self.rx_edit.setText("")
            self.rx_note.setText(f"regex generator error: {e}")

    def _copy_regex(self):
        try:
            QApplication.clipboard().setText(self.rx_edit.text())
            self.rx_note.setText("Copied — paste into the in-game "
                                 "stash/vendor search box.")
        except Exception:
            pass

    # ------------------------------------------------ autocomplete
    def _load_suggestions(self):
        def _work():
            try:
                import os
                from core_engine.craft_hunter import mod_suggestions
                from core_engine.database_handler import KalandraDBHandler
                db = os.path.join(KalandraDBHandler._configured_db_dir(),
                                  "localized_knowledge.db")
                self._suggestions_ready.emit(mod_suggestions(db))
            except Exception:
                try:
                    from core_engine.craft_hunter import BUILTIN_MOD_LINES
                    self._suggestions_ready.emit(list(BUILTIN_MOD_LINES))
                except Exception:
                    pass
        threading.Thread(target=_work, daemon=True).start()

    def _apply_suggestions(self, lines):
        try:
            self.mod_box.blockSignals(True)
            cur = self.mod_box.currentText()
            self.mod_box.clear()
            self.mod_box.addItems(lines)
            self.mod_box.setCurrentText(cur)
            self.mod_box.blockSignals(False)
            comp = QCompleter(lines, self.mod_box)
            comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            comp.setFilterMode(Qt.MatchFlag.MatchContains)
            self.mod_box.setCompleter(comp)
        except Exception:
            pass

    # ------------------------------------------------ clipboard confirm inbox
    def on_clipboard_result(self, res, _raw_text=""):
        """Called (UI thread) by the dashboard when an armed in-game Ctrl+C
        was checked against the targets."""
        if not res or not res.get("checked"):
            return
        self._stats["checks"] += 1
        hit = bool(res.get("hit"))
        near = bool(res.get("near_miss")) and not hit
        if hit:
            self._stats["hits"] += 1
        # P3: orbs-per-hit estimate — each confirm ≈ one craft attempt.
        rate = (f" · ~{self._stats['checks'] / self._stats['hits']:.0f} "
                "confirms/hit" if self._stats["hits"] else "")
        self.stats_lbl.setText(f"session: {self._stats['checks']} confirms · "
                               f"{self._stats['hits']} hits{rate}")
        bits = []
        for t, ok, detail in (res.get("results") or []):
            mod = t.get("mod") or t.get("mod_line") or "?"
            if isinstance(mod, list):
                mod = " + ".join(mod)
            bits.append(("✅ " if ok else "· ") + f"{mod} — {detail}")
        self.banner.setText(("⛔ TARGET HIT — STOP\n" if hit else
                             ("Near miss — right mod, roll off. Annul/aug "
                              "call is yours.\n" if near
                              else "False alarm — keep going.\n"))
                            + "\n".join(bits))
        self.banner.setStyleSheet(
            f"background:{BG0};padding:10px;font-size:14px;"
            + (f"color:{EMERALD};border:2px solid {EMERALD};" if hit
               else (f"color:{COLOR_WARN};border:2px solid {COLOR_WARN};"
                     if near else f"color:{TEXT};border:1px solid {RUBY};")))
