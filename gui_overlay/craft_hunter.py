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

import threading

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QCompleter, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from gui_overlay.theme import (
    BG0, BG1, EMERALD, FAINT, GOLD, GOLD_LIGHT, MUTED, RUBY, TEXT,
)

_TOAST = None      # single live toast (a new confirm replaces the old one)


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
        edge = EMERALD if hit else RUBY
        self.setStyleSheet(
            f"QWidget{{background:{BG1};color:{TEXT};font-size:13px;"
            f"border:2px solid {edge};border-radius:6px;}}"
            f"QLabel{{border:none;background:transparent;}}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        head = QLabel("⛔ TARGET HIT — STOP" if hit
                      else "FALSE ALARM — keep going")
        head.setStyleSheet(
            f"color:{EMERALD if hit else RUBY};font-size:16px;"
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
    """Target list + live stash regex + clipboard-confirm status."""

    _suggestions_ready = pyqtSignal(list)

    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.config = config if config is not None else {}
        self._stats = {"checks": 0, "hits": 0}
        self._build_ui()
        self._suggestions_ready.connect(self._apply_suggestions)
        self._load_targets_from_config()
        self._load_suggestions()
        self._refresh_regex()

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
        self.arm_btn.clicked.connect(self._toggle_armed)
        mode_row.addWidget(self.arm_btn)
        self.lamp = QLabel("")
        self.lamp.setStyleSheet(f"color:{MUTED};")
        mode_row.addWidget(self.lamp)
        mode_row.addStretch()
        self.stats_lbl = QLabel("session: 0 confirms · 0 hits")
        self.stats_lbl.setStyleSheet(f"color:{FAINT};")
        mode_row.addWidget(self.stats_lbl)
        root.addLayout(mode_row)

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
        if hit:
            self._stats["hits"] += 1
        self.stats_lbl.setText(f"session: {self._stats['checks']} confirms · "
                               f"{self._stats['hits']} hits")
        bits = []
        for t, ok, detail in (res.get("results") or []):
            mod = t.get("mod") or t.get("mod_line") or "?"
            if isinstance(mod, list):
                mod = " + ".join(mod)
            bits.append(("✅ " if ok else "· ") + f"{mod} — {detail}")
        self.banner.setText(("⛔ TARGET HIT — STOP\n" if hit
                             else "False alarm — keep going.\n")
                            + "\n".join(bits))
        self.banner.setStyleSheet(
            f"background:{BG0};padding:10px;font-size:14px;"
            + (f"color:{EMERALD};border:2px solid {EMERALD};" if hit
               else f"color:{TEXT};border:1px solid {RUBY};"))
