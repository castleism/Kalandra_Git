"""
GUI_OVERLAY/DASHBOARD.PY
The Kalandra dashboard: a single, PoE2-styled window that hosts all the tools in
tabs. The floating mirror overlay stays your always-on-top in-game companion;
this dashboard is the alt-tab workspace.

Tabs:
  * Build Sim     -- live stats from the headless Path of Building engine.
  * Price Check   -- paste an item; opens the official PoE2 trade search.
  * Exchange      -- live currency/economy tracker (poe.ninja public data).
  * Crafting      -- natural-language craft planner (+ Craft of Exile link).
  * Filter Editor -- edit your local .filter directly (Show/Hide/Minimal).
  * Live Search   -- opens the official-API live trade search (manual buy).
  * Craft of Exile / FilterBlade / poe.ninja -- embedded web tools.

Embedded web tools use Qt WebEngine when PyQt6-WebEngine is installed; otherwise
each web tab shows a clean "Open in browser" fallback. Web views are created
LAZILY and wrapped in try/except, so a missing/broken WebEngine can never crash
the dashboard.

Install (for embedded browsing):  pip install PyQt6-WebEngine
"""

import threading

from PyQt6.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QPlainTextEdit, QCheckBox, QFileDialog, QLineEdit, QComboBox, QListWidget,
    QListWidgetItem, QTextEdit, QMessageBox, QSplitter, QApplication,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, QUrl, QObject, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont

# Only probe availability here; do NOT instantiate any web view at import time.
try:
    import PyQt6.QtWebEngineWidgets as _qtwe  # noqa: F401
    WEBENGINE_AVAILABLE = True
except Exception:
    WEBENGINE_AVAILABLE = False


GOLD = "#c8aa6e"
TEAL = "#3fb6b6"
BG0 = "#0c0e12"
BG1 = "#14181f"
BG2 = "#1b212b"
TEXT = "#e8e6df"
MUTED = "#9aa4b2"

DASH_QSS = f"""
QWidget {{ background:{BG0}; color:{TEXT}; font-size:13px; }}
QLabel#title {{ color:{GOLD}; font-size:20px; font-weight:bold; letter-spacing:1px; }}
QLabel#subtitle {{ color:{MUTED}; font-size:12px; }}
QTabWidget::pane {{ border:1px solid #2a313d; background:{BG1}; }}
QTabBar::tab {{
    background:{BG1}; color:{MUTED}; padding:9px 16px; margin-right:2px;
    border:1px solid #232a35; border-bottom:none;
    border-top-left-radius:6px; border-top-right-radius:6px;
}}
QTabBar::tab:selected {{ background:{BG2}; color:{GOLD}; border-color:{GOLD}; }}
QTabBar::tab:hover {{ color:{TEXT}; }}
QPushButton {{
    background:{BG2}; color:{TEXT}; border:1px solid #3a4350;
    padding:8px 14px; border-radius:6px;
}}
QPushButton:hover {{ background:#283040; border-color:{GOLD}; }}
QFrame#card {{ background:{BG1}; border:1px solid #2a313d; border-radius:10px; }}
"""


class _Bridge(QObject):
    buildsim_text = pyqtSignal(str)


class WebTab(QWidget):
    """Embedded web view, created lazily and crash-safe; falls back to a button."""
    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url
        self._loaded = False
        self.view = None
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        if not WEBENGINE_AVAILABLE:
            self._show_fallback("Embedded browser not installed.")

    def _show_fallback(self, reason):
        card = QFrame(); card.setObjectName("card")
        cl = QVBoxLayout(card)
        t = QLabel(reason or "Web view unavailable")
        t.setStyleSheet(f"color:{GOLD};font-size:15px;font-weight:bold;")
        cl.addWidget(t)
        msg = QLabel("Install the embedded browser to view this inside the dashboard:\n"
                     "    pip install PyQt6-WebEngine\n\nOr open it in your browser:")
        msg.setStyleSheet(f"color:{MUTED};")
        cl.addWidget(msg)
        btn = QPushButton(f"Open {self.url}")
        btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.url)))
        cl.addWidget(btn)
        cl.addStretch()
        self.lay.addWidget(card)

    def ensure_loaded(self):
        if self._loaded:
            return
        self._loaded = True
        if not WEBENGINE_AVAILABLE:
            return
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            self.view = QWebEngineView()
            self.lay.addWidget(self.view)
            self.view.setUrl(QUrl(self.url))
        except Exception as e:
            self._show_fallback(f"Web view failed to start ({e}).")


def _placeholder(title, lines):
    w = QWidget()
    outer = QVBoxLayout(w)
    card = QFrame(); card.setObjectName("card")
    cl = QVBoxLayout(card)
    h = QLabel(title)
    h.setStyleSheet(f"color:{GOLD};font-size:16px;font-weight:bold;")
    cl.addWidget(h)
    for ln in lines:
        lab = QLabel(ln); lab.setStyleSheet(f"color:{MUTED};"); lab.setWordWrap(True)
        cl.addWidget(lab)
    tag = QLabel("Status: planned — shell ready, wiring next.")
    tag.setStyleSheet(f"color:{TEAL};font-size:11px;margin-top:8px;")
    cl.addWidget(tag)
    cl.addStretch()
    outer.addWidget(card)
    return w


class TerminalTab(QWidget):
    """Live, filterable view of everything Kalandra does on the backend.
    Subscribes to the app-wide LOG_BUS so any backend event (a button press, a
    DB sync, a voice/AI exchange) shows here in real time."""

    def __init__(self, parent=None):
        super().__init__(parent)
        try:
            from gui_overlay.log_bus import LOG_BUS, GROUP_ORDER, group_for
        except Exception:
            from log_bus import LOG_BUS, GROUP_ORDER, group_for
        self._bus = LOG_BUS
        self._group_for = group_for
        self._order = GROUP_ORDER

        lay = QVBoxLayout(self)

        intro = QLabel("Live backend activity. Tick the event types you want to see.")
        intro.setStyleSheet(f"color:{MUTED};font-size:11px;")
        lay.addWidget(intro)

        frow = QHBoxLayout()
        frow.addWidget(QLabel("Show:"))
        self._checks = {}
        for g in self._order:
            cb = QCheckBox(g); cb.setChecked(True)
            cb.stateChanged.connect(self._rebuild)
            self._checks[g] = cb
            frow.addWidget(cb)
        frow.addStretch()
        lay.addLayout(frow)

        crow = QHBoxLayout()
        self._auto = QCheckBox("Auto-scroll"); self._auto.setChecked(True)
        crow.addWidget(self._auto)
        clr = QPushButton("Clear view"); clr.clicked.connect(lambda: self.view.clear())
        crow.addWidget(clr)
        sav = QPushButton("Save log…"); sav.clicked.connect(self._save)
        crow.addWidget(sav)
        crow.addStretch()
        lay.addLayout(crow)

        self.view = QPlainTextEdit(); self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(6000)
        self.view.setStyleSheet("QPlainTextEdit{background:#08090c;color:#d7dbe0;"
                                "font-family:Consolas,monospace;font-size:12px;border:1px solid #2a313d;}")
        lay.addWidget(self.view, 1)

        # Show what already happened, then go live.
        for (ts, cat, msg) in list(getattr(self._bus, "history", [])):
            self._maybe_append(ts, cat, msg)
        if getattr(self._bus, "emitted", None) is not None:
            self._bus.emitted.connect(self._on_log)

    def _active(self):
        return {g for g, cb in self._checks.items() if cb.isChecked()}

    def _passes(self, cat):
        return self._group_for(cat) in self._active()

    def _color(self, cat):
        return {"Database": "#5bd66f", "Voice & AI": "#e0b15a", "Build / PoB": "#5ad0d0",
                "GUI / Actions": "#9aa4b2", "Capture": "#d98a94"}.get(
                    self._group_for(cat), "#cfe3ea")

    def _append_line(self, ts, cat, msg):
        import html as _h
        self.view.appendHtml(
            f'<span style="color:#6b7280">[{ts}]</span> '
            f'<span style="color:{self._color(cat)}">[{_h.escape(cat)}]</span> '
            f'<span style="color:#d7dbe0">{_h.escape(msg)}</span>')
        if self._auto.isChecked():
            sb = self.view.verticalScrollBar(); sb.setValue(sb.maximum())

    def _maybe_append(self, ts, cat, msg):
        if self._passes(cat):
            self._append_line(ts, cat, msg)

    def _on_log(self, ts, cat, msg):
        self._maybe_append(ts, cat, msg)

    def _rebuild(self):
        self.view.clear()
        for (ts, cat, msg) in list(getattr(self._bus, "history", [])):
            self._maybe_append(ts, cat, msg)

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save terminal log",
                                              "kalandra_log.txt", "Text (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                for (ts, cat, msg) in list(getattr(self._bus, "history", [])):
                    if self._passes(cat):
                        f.write(f"[{ts}] [{cat}] {msg}\n")
        except Exception:
            pass


class ReserveTab(QWidget):
    """Unique / BIS Reserve: snapshot items you're holding for future builds or
    upgrades. Left = your reserve list; right = add/edit a snapshot (paste the
    raw item tooltip straight from the game). Backed by reserve_tracker so it
    persists across restarts and is fed to the AI as context."""

    def __init__(self, tracker=None, parent=None):
        super().__init__(parent)
        self.tracker = tracker
        if self.tracker is None:
            try:
                from core_engine.reserve_tracker import ReserveTracker
                self.tracker = ReserveTracker()
            except Exception:
                self.tracker = None
        self._editing_id = None
        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        root = QVBoxLayout(self)
        head = QLabel("Unique / BIS Reserve")
        head.setStyleSheet(f"color:{GOLD};font-size:18px;font-weight:bold;")
        root.addWidget(head)
        root.addWidget(QLabel(
            "Snapshot items you're keeping in reserve for future build ideas or "
            "upgrades. Paste the item straight from the game (Ctrl+C on the "
            "tooltip). The Orb sees your reserve and can factor it into advice."))

        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)

        # ---- left: the list ----
        left = QWidget(); ll = QVBoxLayout(left)
        self.search = QLineEdit(); self.search.setPlaceholderText("Filter reserve...")
        self.search.textChanged.connect(self._refresh_list)
        ll.addWidget(self.search)
        self.listw = QListWidget()
        self.listw.currentItemChanged.connect(self._on_pick)
        ll.addWidget(self.listw, 1)
        lrow = QHBoxLayout()
        del_btn = QPushButton("Delete"); del_btn.clicked.connect(self._delete)
        new_btn = QPushButton("New / Clear"); new_btn.clicked.connect(self._clear_form)
        lrow.addWidget(new_btn); lrow.addWidget(del_btn)
        ll.addLayout(lrow)
        split.addWidget(left)

        # ---- right: the editor ----
        right = QWidget(); rl = QVBoxLayout(right)
        rl.addWidget(QLabel("Name"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Mageblood (or leave blank to auto-detect from paste)")
        rl.addWidget(self.name_edit)

        crow = QHBoxLayout()
        cbox = QWidget(); cl = QVBoxLayout(cbox); cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(QLabel("Category"))
        self.cat_combo = QComboBox()
        try:
            from core_engine.reserve_tracker import CATEGORIES
        except Exception:
            CATEGORIES = ["Unique", "BIS", "Reserve", "Crafting base", "Other"]
        self.cat_combo.addItems(CATEGORIES)
        cl.addWidget(self.cat_combo)
        crow.addWidget(cbox)
        bbox = QWidget(); bl = QVBoxLayout(bbox); bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(QLabel("Earmarked for build"))
        self.build_edit = QLineEdit()
        self.build_edit.setPlaceholderText("e.g. Gemling Mercenary crit bow")
        bl.addWidget(self.build_edit)
        crow.addWidget(bbox)
        rl.addLayout(crow)

        rl.addWidget(QLabel("Tags (comma-separated)"))
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("e.g. crit, lightning, helmet, endgame")
        rl.addWidget(self.tags_edit)

        rl.addWidget(QLabel("Note"))
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("Why you're saving it / what it's for")
        rl.addWidget(self.note_edit)

        prow = QHBoxLayout()
        prow.addWidget(QLabel("Item text (paste the in-game tooltip)"))
        prow.addStretch()
        paste_btn = QPushButton("Paste from clipboard")
        paste_btn.clicked.connect(self._paste_clip)
        prow.addWidget(paste_btn)
        rl.addLayout(prow)
        self.item_text = QTextEdit()
        self.item_text.setPlaceholderText("Item Class: ...\nRarity: ...\n...")
        self.item_text.setMinimumHeight(140)
        rl.addWidget(self.item_text, 1)

        save_btn = QPushButton("Save snapshot")
        save_btn.setStyleSheet(f"background:{BG2};border:1px solid {GOLD};color:{GOLD};font-weight:bold;")
        save_btn.clicked.connect(self._save)
        rl.addWidget(save_btn)
        self.status = QLabel(""); self.status.setStyleSheet(f"color:{MUTED};font-size:11px;")
        rl.addWidget(self.status)
        split.addWidget(right)
        split.setSizes([360, 620])

    # ---- data ops ----
    def _refresh_list(self):
        if not self.tracker:
            return
        term = self.search.text().strip() if hasattr(self, "search") else ""
        items = self.tracker.search(term) if term else self.tracker.all()
        self.listw.blockSignals(True)
        self.listw.clear()
        for e in items:
            tags = (" — " + ", ".join(e["tags"])) if e.get("tags") else ""
            label = f"[{e.get('category','Reserve')}] {e.get('name','?')}{tags}"
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, e)
            self.listw.addItem(it)
        self.listw.blockSignals(False)
        if not items:
            self.status.setText("Reserve is empty — add your first snapshot on the right.")

    def _on_pick(self, cur, _prev):
        if not cur:
            return
        e = cur.data(Qt.ItemDataRole.UserRole) or {}
        self._editing_id = e.get("id")
        self.name_edit.setText(e.get("name", ""))
        idx = self.cat_combo.findText(e.get("category", "Reserve"))
        self.cat_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.build_edit.setText(e.get("build_for", ""))
        self.tags_edit.setText(", ".join(e.get("tags", [])))
        self.note_edit.setText(e.get("note", ""))
        self.item_text.setPlainText(e.get("item_text", ""))
        self.status.setText(f"Editing: {e.get('name','?')} (saved {e.get('created','')})")

    def _clear_form(self):
        self._editing_id = None
        self.name_edit.clear(); self.build_edit.clear(); self.tags_edit.clear()
        self.note_edit.clear(); self.item_text.clear()
        self.cat_combo.setCurrentIndex(0)
        self.listw.clearSelection()
        self.status.setText("New snapshot — fill it in and Save.")

    def _paste_clip(self):
        try:
            txt = QApplication.clipboard().text()
        except Exception:
            txt = ""
        if txt:
            self.item_text.setPlainText(txt)
            self.status.setText("Pasted from clipboard.")
        else:
            self.status.setText("Clipboard was empty.")

    def _save(self):
        if not self.tracker:
            self.status.setText("Reserve store unavailable.")
            return
        name = self.name_edit.text().strip()
        item_text = self.item_text.toPlainText().strip()
        if not (name or item_text):
            self.status.setText("Add a name or paste an item first.")
            return
        fields = dict(
            name=name, item_text=item_text, category=self.cat_combo.currentText(),
            tags=self.tags_edit.text(), note=self.note_edit.text().strip(),
            build_for=self.build_edit.text().strip())
        if self._editing_id:
            self.tracker.update(self._editing_id, **fields)
            self.status.setText("Updated.")
        else:
            e = self.tracker.add(**fields)
            self._editing_id = e.get("id")
            self.status.setText("Saved to reserve.")
        self._refresh_list()

    def _delete(self):
        if not (self.tracker and self._editing_id):
            self.status.setText("Pick an item to delete.")
            return
        if QMessageBox.question(self, "Delete reserved item",
                                "Remove this item from your reserve?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.tracker.delete(self._editing_id)
        self._clear_form()
        self._refresh_list()
        self.status.setText("Deleted.")


class IssuesTab(QWidget):
    """Known Issues / Changelog: bugs, data errors, AI hallucinations, and feature
    requests found while using Kalandra. Export the open items as Markdown to hand
    to the developer/AI to action, then ship the next revision."""

    def __init__(self, tracker=None, parent=None):
        super().__init__(parent)
        self.tracker = tracker
        if self.tracker is None:
            try:
                from core_engine.issue_tracker import IssueTracker
                self.tracker = IssueTracker()
            except Exception:
                self.tracker = None
        self._editing_id = None
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        head = QLabel("Known Issues & Changelog")
        head.setStyleSheet(f"color:{GOLD};font-size:18px;font-weight:bold;")
        root.addWidget(head)
        root.addWidget(QLabel(
            "Log bugs, data errors, AI mistakes, and feature ideas as you use "
            "Kalandra. Use 'Copy changelog' to hand the open items to the dev/AI."))

        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)

        # left: list + filters
        left = QWidget(); ll = QVBoxLayout(left)
        frow = QHBoxLayout()
        self.show_all = QCheckBox("Show resolved too")
        self.show_all.stateChanged.connect(self._refresh)
        frow.addWidget(self.show_all); frow.addStretch()
        ll.addLayout(frow)
        self.listw = QListWidget()
        self.listw.currentItemChanged.connect(self._on_pick)
        ll.addWidget(self.listw, 1)
        brow = QHBoxLayout()
        self.resolve_btn = QPushButton("Mark resolved"); self.resolve_btn.clicked.connect(self._resolve)
        self.del_btn = QPushButton("Delete"); self.del_btn.clicked.connect(self._delete)
        brow.addWidget(self.resolve_btn); brow.addWidget(self.del_btn)
        ll.addLayout(brow)
        xrow = QHBoxLayout()
        copy_btn = QPushButton("Copy changelog for Claude")
        copy_btn.setStyleSheet(f"border:1px solid {GOLD};color:{GOLD};")
        copy_btn.clicked.connect(self._copy_changelog)
        save_btn = QPushButton("Save changelog…"); save_btn.clicked.connect(self._save_changelog)
        xrow.addWidget(copy_btn); xrow.addWidget(save_btn)
        ll.addLayout(xrow)
        split.addWidget(left)

        # right: add / edit
        right = QWidget(); rl = QVBoxLayout(right)
        rl.addWidget(QLabel("Title"))
        self.title_edit = QLineEdit(); self.title_edit.setPlaceholderText("Short summary of the issue")
        rl.addWidget(self.title_edit)
        crow = QHBoxLayout()
        tb = QWidget(); tbl = QVBoxLayout(tb); tbl.setContentsMargins(0,0,0,0)
        tbl.addWidget(QLabel("Type"))
        self.type_combo = QComboBox()
        try:
            from core_engine.issue_tracker import TYPES, SEVERITIES
        except Exception:
            TYPES = ["bug","db-error","hallucination","feature","correction","other"]
            SEVERITIES = ["low","medium","high","critical"]
        self.type_combo.addItems(TYPES); tbl.addWidget(self.type_combo)
        crow.addWidget(tb)
        sb = QWidget(); sbl = QVBoxLayout(sb); sbl.setContentsMargins(0,0,0,0)
        sbl.addWidget(QLabel("Severity"))
        self.sev_combo = QComboBox(); self.sev_combo.addItems(SEVERITIES)
        self.sev_combo.setCurrentText("medium"); sbl.addWidget(self.sev_combo)
        crow.addWidget(sb)
        rl.addLayout(crow)
        rl.addWidget(QLabel("Details"))
        self.details_edit = QTextEdit(); self.details_edit.setMinimumHeight(90)
        self.details_edit.setPlaceholderText("What happened / what it should do")
        rl.addWidget(self.details_edit)
        rl.addWidget(QLabel("Context (optional — paste the chat exchange, etc.)"))
        self.ctx_edit = QTextEdit(); self.ctx_edit.setMinimumHeight(80)
        rl.addWidget(self.ctx_edit, 1)
        srow = QHBoxLayout()
        save = QPushButton("Save issue"); save.setStyleSheet(f"border:1px solid {GOLD};color:{GOLD};font-weight:bold;")
        save.clicked.connect(self._save)
        newb = QPushButton("New / Clear"); newb.clicked.connect(self._clear)
        srow.addWidget(newb); srow.addWidget(save)
        rl.addLayout(srow)
        self.status = QLabel(""); self.status.setStyleSheet(f"color:{MUTED};font-size:11px;")
        rl.addWidget(self.status)
        split.addWidget(right)
        split.setSizes([420, 560])

    def _refresh(self):
        if not self.tracker:
            return
        items = self.tracker.all()
        if not self.show_all.isChecked():
            items = [e for e in items if e.get("status") not in ("resolved","wont-fix")]
        self.listw.blockSignals(True)
        self.listw.clear()
        for e in items:
            mark = "✓ " if e.get("status") in ("resolved","wont-fix") else ""
            label = f"{mark}[{e.get('type','?')}/{e.get('severity','?')}] {e.get('title','?')}"
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, e)
            self.listw.addItem(it)
        self.listw.blockSignals(False)
        n = self.tracker.open_count()
        self.status.setText(f"{n} open issue(s).")

    def _on_pick(self, cur, _prev):
        if not cur:
            return
        e = cur.data(Qt.ItemDataRole.UserRole) or {}
        self._editing_id = e.get("id")
        self.title_edit.setText(e.get("title",""))
        i = self.type_combo.findText(e.get("type","bug")); self.type_combo.setCurrentIndex(i if i>=0 else 0)
        i = self.sev_combo.findText(e.get("severity","medium")); self.sev_combo.setCurrentIndex(i if i>=0 else 0)
        self.details_edit.setPlainText(e.get("details",""))
        self.ctx_edit.setPlainText(e.get("context",""))
        self.status.setText(f"Editing: {e.get('title','?')} ({e.get('status','open')})")

    def _clear(self):
        self._editing_id = None
        self.title_edit.clear(); self.details_edit.clear(); self.ctx_edit.clear()
        self.type_combo.setCurrentIndex(0); self.sev_combo.setCurrentText("medium")
        self.listw.clearSelection()
        self.status.setText("New issue — fill it in and Save.")

    def _save(self):
        if not self.tracker:
            return
        title = self.title_edit.text().strip()
        if not title:
            self.status.setText("Add a title first."); return
        fields = dict(title=title, type=self.type_combo.currentText(),
                      severity=self.sev_combo.currentText(),
                      details=self.details_edit.toPlainText().strip(),
                      context=self.ctx_edit.toPlainText().strip())
        if self._editing_id:
            self.tracker.update(self._editing_id, **fields)
        else:
            e = self.tracker.add(**fields); self._editing_id = e.get("id")
        self._refresh()
        self.status.setText("Saved.")

    def _resolve(self):
        if self._editing_id and self.tracker:
            self.tracker.set_status(self._editing_id, "resolved")
            self._refresh(); self.status.setText("Marked resolved.")

    def _delete(self):
        if not (self._editing_id and self.tracker):
            return
        if QMessageBox.question(self, "Delete issue", "Remove this issue?") \
                == QMessageBox.StandardButton.Yes:
            self.tracker.delete(self._editing_id); self._clear(); self._refresh()

    def _copy_changelog(self):
        if not self.tracker:
            return
        md = self.tracker.export_markdown(only_open=True)
        try:
            QApplication.clipboard().setText(md)
            self.status.setText("Changelog copied — paste it to Claude to action the fixes.")
        except Exception as e:
            self.status.setText(f"Copy failed: {e}")

    def _save_changelog(self):
        if not self.tracker:
            return
        md = self.tracker.export_markdown(only_open=True)
        try:
            path, _ = QFileDialog.getSaveFileName(self, "Save changelog",
                                                  "kalandra_changelog.md", "Markdown (*.md)")
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(md)
                self.status.setText(f"Saved: {path}")
        except Exception as e:
            self.status.setText(f"Save failed: {e}")


class BuildTab(QWidget):
    """Shows the CURRENTLY LOADED Path of Building character — class, scaling
    profile, every skill group, equipped items, and tree-socketed jewels — built
    straight from the parse (no LuaJIT simulator required, so it always works).
    This is the 'PoB tab': what the overlay's green Character Selector loads."""

    def __init__(self, build_provider=None, parent=None):
        super().__init__(parent)
        self.build_provider = build_provider   # callable -> dict (see overlay.current_build_view)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.head = QLabel("No build loaded")
        self.head.setStyleSheet(f"color:{GOLD};font-size:17px;font-weight:bold;")
        top.addWidget(self.head)
        top.addStretch()
        rb = QPushButton("Refresh"); rb.clicked.connect(self.refresh)
        top.addWidget(rb)
        lay.addLayout(top)
        self.hint = QLabel("")
        self.hint.setStyleSheet(f"color:{MUTED};font-size:11px;")
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        self.view = QTextEdit(); self.view.setReadOnly(True)
        self.view.setStyleSheet(f"background:{BG0};color:{TEXT};"
                                "font-family:Consolas,monospace;font-size:12px;")
        lay.addWidget(self.view, 1)

    def refresh(self):
        data = {}
        try:
            if self.build_provider:
                data = self.build_provider() or {}
        except Exception as e:
            data = {"error": str(e)}
        if data.get("error"):
            self.head.setText("Build unavailable")
            self.view.setPlainText("Could not read the build: " + data["error"])
            return
        if not data.get("loaded"):
            self.head.setText("No build loaded")
            self.hint.setText("")
            self.view.setPlainText(
                "No Path of Building build is loaded yet.\n\n"
                "Load one from the overlay: click the green Character Selector "
                "medallion, then 'Load my saved PoB builds' and 'Set active' — or "
                "paste a PoB code / pobb.in link. It will appear here.")
            return
        self.head.setText(data.get("character") or "Loaded build")
        sc = data.get("scaling") or {}
        bits = []
        if sc.get("damage_types"):
            bits.append("scales via " + ", ".join(sc["damage_types"][:3]))
        if sc.get("mechanics"):
            bits.append("mechanics: " + ", ".join(sc["mechanics"][:4]))
        bits.append("crit-based" if sc.get("crit_based") else "non-crit")
        self.hint.setText("Scaling profile: " + "; ".join(bits))

        lines = []
        if data.get("sim"):
            lines.append("LIVE PoB SIM (recomputed by the engine): " + data["sim"] + "\n")
        if data.get("summary"):
            lines.append(data["summary"])
        jewels = data.get("jewels") or []
        if jewels:
            lines.append("\nTREE JEWELS:")
            for j in jewels:
                mods = ("  " + " | ".join(j.get("mods", []))) if j.get("mods") else ""
                lines.append(f"  - {j.get('name','?')}{mods}")
        if data.get("guidance"):
            lines.append("\n" + data["guidance"])
        self.view.setPlainText("\n".join(lines))


class FilterEditorTab(QWidget):
    """Edit a Path of Exile 2 loot filter (.filter) locally — flip blocks between
    Show / Hide / Minimal and save. Pure file editing, fully ToS-clean. Saving
    writes a .bak backup first."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc = None
        self._build_ui()
        self._scan()

    def _build_ui(self):
        root = QVBoxLayout(self)
        head = QLabel("Filter Editor")
        head.setStyleSheet(f"color:{GOLD};font-size:18px;font-weight:bold;")
        root.addWidget(head)
        root.addWidget(QLabel("Edit your loot filter directly — flip blocks between "
                              "Show / Hide / Minimal. A .bak backup is written on save."))
        pick = QHBoxLayout()
        self.file_combo = QComboBox()
        self.file_combo.currentIndexChanged.connect(self._load_selected)
        pick.addWidget(self.file_combo, 1)
        rb = QPushButton("Rescan"); rb.clicked.connect(self._scan); pick.addWidget(rb)
        br = QPushButton("Browse…"); br.clicked.connect(self._browse); pick.addWidget(br)
        root.addLayout(pick)
        self.stats = QLabel(""); self.stats.setStyleSheet(f"color:{MUTED};font-size:11px;")
        root.addWidget(self.stats)

        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)
        left = QWidget(); ll = QVBoxLayout(left)
        self.search = QLineEdit(); self.search.setPlaceholderText("Filter blocks…")
        self.search.textChanged.connect(self._refresh_list)
        ll.addWidget(self.search)
        self.listw = QListWidget()
        self.listw.currentItemChanged.connect(self._on_pick)
        ll.addWidget(self.listw, 1)
        arow = QHBoxLayout()
        for act, col in (("Show", "#2f6a44"), ("Hide", "#6a2f33"), ("Minimal", "#5a5320")):
            btn = QPushButton(act)
            btn.setStyleSheet(f"border:1px solid {col};")
            btn.clicked.connect(lambda _c, a=act: self._set_action(a))
            arow.addWidget(btn)
        ll.addLayout(arow)
        split.addWidget(left)
        right = QWidget(); rl = QVBoxLayout(right)
        rl.addWidget(QLabel("Block contents (read-only preview)"))
        self.view = QTextEdit(); self.view.setReadOnly(True)
        self.view.setStyleSheet(f"background:{BG0};color:{TEXT};font-family:Consolas,monospace;font-size:12px;")
        rl.addWidget(self.view, 1)
        save = QPushButton("Save filter (writes .bak first)")
        save.setStyleSheet(f"border:1px solid {GOLD};color:{GOLD};font-weight:bold;")
        save.clicked.connect(self._save)
        rl.addWidget(save)
        self.status = QLabel(""); self.status.setStyleSheet(f"color:{MUTED};font-size:11px;")
        rl.addWidget(self.status)
        split.addWidget(right)
        split.setSizes([460, 520])

    def _scan(self):
        try:
            from core_engine.filter_editor import find_filters
            files = find_filters()
        except Exception as e:
            files = []
            self.status.setText(f"Scan error: {e}")
        self.file_combo.blockSignals(True)
        self.file_combo.clear()
        for p in files:
            import os
            self.file_combo.addItem(os.path.basename(p), p)
        self.file_combo.blockSignals(False)
        if files:
            self._load_selected()
        else:
            self.stats.setText("No .filter files found. Use Browse… to pick one.")

    def _browse(self):
        try:
            path, _ = QFileDialog.getOpenFileName(self, "Open filter", "", "Filters (*.filter)")
        except Exception:
            path = ""
        if path:
            import os
            self.file_combo.addItem(os.path.basename(path), path)
            self.file_combo.setCurrentIndex(self.file_combo.count() - 1)

    def _load_selected(self):
        path = self.file_combo.currentData()
        if not path:
            return
        try:
            from core_engine.filter_editor import FilterDocument
            self.doc = FilterDocument.load(path)
            self._refresh_list()
            s = self.doc.stats()
            self.stats.setText(f"{s['total']} blocks — Show {s['Show']}, Hide {s['Hide']}, "
                               f"Minimal {s.get('Minimal', 0)}")
            self.status.setText("Loaded: " + path)
        except Exception as e:
            self.status.setText(f"Load error: {e}")

    def _refresh_list(self):
        if not self.doc:
            return
        term = (self.search.text() or "").strip().lower()
        self.listw.blockSignals(True)
        self.listw.clear()
        colors = {"Show": "#7fd6a0", "Hide": "#e08a90", "Minimal": "#d9cf8a"}
        for i, blk in enumerate(self.doc.blocks):
            summ = blk.summary()
            if term and term not in summ.lower() and term not in blk.action.lower():
                continue
            it = QListWidgetItem(f"[{blk.action}] {summ}")
            it.setData(Qt.ItemDataRole.UserRole, i)
            try:
                from PyQt6.QtGui import QColor
                it.setForeground(QColor(colors.get(blk.action, "#e8e6df")))
            except Exception:
                pass
            self.listw.addItem(it)
        self.listw.blockSignals(False)

    def _on_pick(self, cur, _prev):
        if not (cur and self.doc):
            return
        i = cur.data(Qt.ItemDataRole.UserRole)
        if i is None or not (0 <= i < len(self.doc.blocks)):
            return
        blk = self.doc.blocks[i]
        self.view.setPlainText(blk.header_line() + "\n" + "\n".join(blk.body))

    def _set_action(self, action):
        cur = self.listw.currentItem()
        if not (cur and self.doc):
            self.status.setText("Pick a block first.")
            return
        i = cur.data(Qt.ItemDataRole.UserRole)
        if self.doc.set_action(i, action):
            self._refresh_list()
            # reselect
            for r in range(self.listw.count()):
                if self.listw.item(r).data(Qt.ItemDataRole.UserRole) == i:
                    self.listw.setCurrentRow(r); break
            s = self.doc.stats()
            self.stats.setText(f"{s['total']} blocks — Show {s['Show']}, Hide {s['Hide']}, "
                               f"Minimal {s.get('Minimal', 0)}  (unsaved)")

    def _save(self):
        if not (self.doc and self.doc.path):
            self.status.setText("Nothing loaded to save.")
            return
        if QMessageBox.question(self, "Save filter",
                                "Overwrite your filter file? A .bak backup is written first.") \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            import shutil, os
            if os.path.exists(self.doc.path):
                shutil.copy2(self.doc.path, self.doc.path + ".bak")
            self.doc.save()
            self.status.setText("Saved. Backup: " + self.doc.path + ".bak  "
                                "(reload your filter in-game)")
        except Exception as e:
            self.status.setText(f"Save failed: {e}")


class ExchangeTab(QWidget):
    """Live PoE2 currency/economy from poe.ninja's public JSON API (no login,
    no key). Read-only, polite caching, fully ToS-clean. Fetches off the UI
    thread so the dashboard never freezes."""

    rows_ready = pyqtSignal(list, str)   # (rows, status)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ninja = None
        self._build_ui()
        self.rows_ready.connect(self._on_rows)

    def _build_ui(self):
        root = QVBoxLayout(self)
        head = QLabel("Currency Exchange")
        head.setStyleSheet(f"color:{GOLD};font-size:18px;font-weight:bold;")
        root.addWidget(head)
        root.addWidget(QLabel("Relative currency values and trade volume from "
                              "poe.ninja's public economy data. Read-only, no login."))
        row = QHBoxLayout()
        row.addWidget(QLabel("League:"))
        self.league = QComboBox()
        self.league.setEditable(True)
        self.league.addItems(["Rise of the Abyssal", "Dawn of the Hunt", "Standard",
                              "Hardcore"])
        row.addWidget(self.league, 1)
        self.refresh_btn = QPushButton("Refresh prices")
        self.refresh_btn.clicked.connect(self._refresh)
        row.addWidget(self.refresh_btn)
        root.addLayout(row)
        self.status = QLabel("Pick a league and Refresh.")
        self.status.setStyleSheet(f"color:{MUTED};font-size:11px;")
        root.addWidget(self.status)

        self.filter_box = QLineEdit()
        self.filter_box.setPlaceholderText("Filter by currency name…")
        self.filter_box.textChanged.connect(self._apply_filter)
        root.addWidget(self.filter_box)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Currency", "Value", "Volume"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        try:
            self.table.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.Stretch)
            self.table.horizontalHeader().setSectionResizeMode(
                1, QHeaderView.ResizeMode.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(
                2, QHeaderView.ResizeMode.ResizeToContents)
        except Exception:
            pass
        self.table.setStyleSheet(
            f"QTableWidget{{background:{BG0};color:{TEXT};gridline-color:#2a313d;}}"
            f"QHeaderView::section{{background:{BG2};color:{GOLD};border:0;padding:6px;}}")
        root.addWidget(self.table, 1)
        self._all_rows = []

    def _refresh(self):
        league = (self.league.currentText() or "").strip() or "Standard"
        self.status.setText(f"Fetching {league}…")
        self.refresh_btn.setEnabled(False)

        def _work():
            rows, status = [], ""
            try:
                if self._ninja is None:
                    from core_engine.poe_ninja import PoENinja
                    self._ninja = PoENinja()
                if not self._ninja.available:
                    status = ("poe.ninja unreachable (requests not installed or no "
                              "network). Prices need an internet connection.")
                else:
                    rows = self._ninja.get_currency(league) or []
                    if not rows:
                        status = (f"No rows for '{league}'. Check the exact league name "
                                  f"on poe.ninja/poe2/economy.")
                    else:
                        status = f"{len(rows)} currencies — {league} (via poe.ninja)."
            except Exception as e:
                status = f"Fetch failed: {e}"
            self.rows_ready.emit(rows, status)

        threading.Thread(target=_work, daemon=True).start()

    def _on_rows(self, rows, status):
        self.refresh_btn.setEnabled(True)
        self.status.setText(status)
        # Sort by value desc when numeric.
        def _num(v):
            try:
                return float(v)
            except Exception:
                return -1.0
        self._all_rows = sorted(rows, key=lambda r: _num(r.get("value")), reverse=True)
        self._apply_filter()

    def _apply_filter(self):
        term = (self.filter_box.text() or "").strip().lower()
        rows = [r for r in self._all_rows
                if not term or term in str(r.get("name", "")).lower()]
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            name = str(r.get("name", "?"))
            val = r.get("value")
            vol = r.get("volume")
            val_s = f"{float(val):,.2f}" if _is_number(val) else str(val)
            vol_s = f"{float(vol):,.0f}" if _is_number(vol) else (str(vol) if vol is not None else "")
            self.table.setItem(i, 0, QTableWidgetItem(name))
            vi = QTableWidgetItem(val_s); vi.setForeground(_qcolor(GOLD))
            self.table.setItem(i, 1, vi)
            self.table.setItem(i, 2, QTableWidgetItem(vol_s))


class PriceCheckTab(QWidget):
    """Paste an item copied from the game (Ctrl+C in-game) and Kalandra parses it
    and opens the matching search on the OFFICIAL PoE2 trade site. No automated
    buying, no price fabrication — you read real listings yourself, per GGG ToS."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        head = QLabel("Price Check")
        head.setStyleSheet(f"color:{GOLD};font-size:18px;font-weight:bold;")
        root.addWidget(head)
        root.addWidget(QLabel("Paste an item (Ctrl+C in-game, then Ctrl+V here). "
                              "Kalandra reads it and opens the official trade search "
                              "— you see real listings and buy manually."))
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("Paste item text here…")
        self.input.setStyleSheet(f"background:{BG0};color:{TEXT};"
                                 "font-family:Consolas,monospace;font-size:12px;")
        root.addWidget(self.input, 1)

        row = QHBoxLayout()
        row.addWidget(QLabel("League:"))
        self.league = QComboBox(); self.league.setEditable(True)
        self.league.addItems(["Rise of the Abyssal", "Dawn of the Hunt", "Standard",
                              "Hardcore"])
        row.addWidget(self.league, 1)
        parse_btn = QPushButton("Read item")
        parse_btn.clicked.connect(self._parse)
        row.addWidget(parse_btn)
        self.open_btn = QPushButton("Open trade search")
        self.open_btn.setStyleSheet(f"border:1px solid {GOLD};color:{GOLD};")
        self.open_btn.clicked.connect(self._open_trade)
        self.open_btn.setEnabled(False)
        row.addWidget(self.open_btn)
        root.addLayout(row)

        self.summary = QTextEdit(); self.summary.setReadOnly(True)
        self.summary.setMaximumHeight(170)
        self.summary.setStyleSheet(f"background:{BG1};color:{TEXT};font-size:12px;")
        root.addWidget(self.summary)
        self._parsed = None

    def _parse(self):
        text = self.input.toPlainText()
        info = _parse_item_text(text)
        self._parsed = info
        if not info.get("name") and not info.get("base"):
            self.summary.setPlainText("Couldn't read an item. Copy it in-game with "
                                      "Ctrl+C (hover the item, press C), then paste here.")
            self.open_btn.setEnabled(False)
            return
        lines = []
        if info.get("rarity"):
            lines.append(f"Rarity: {info['rarity']}")
        if info.get("name"):
            lines.append(f"Name: {info['name']}")
        if info.get("base"):
            lines.append(f"Base: {info['base']}")
        if info.get("item_class"):
            lines.append(f"Class: {info['item_class']}")
        if info.get("ilvl"):
            lines.append(f"Item Level: {info['ilvl']}")
        if info.get("mods"):
            lines.append("Mods:")
            for m in info["mods"][:12]:
                lines.append(f"  • {m}")
        lines.append("\nUnique items search by name; rare/magic search by base type. "
                     "Click 'Open trade search' to see live listings.")
        self.summary.setPlainText("\n".join(lines))
        self.open_btn.setEnabled(True)

    def _open_trade(self):
        league = (self.league.currentText() or "Standard").strip()
        url = _trade_search_url(self._parsed or {}, league)
        try:
            QDesktopServices.openUrl(QUrl(url))
            self.summary.append("\nOpened: " + url)
        except Exception as e:
            self.summary.append(f"\nCouldn't open browser: {e}\n{url}")


class CraftingTab(QWidget):
    """A plain-language crafting planner. Describe what you want; Kalandra lays out
    the realistic path (mod groups, where to source the base, what tier to aim
    for) and links the deterministic Craft of Exile simulator for probabilities.
    No game automation."""

    def __init__(self, parent=None, brain_provider=None):
        super().__init__(parent)
        self._brain = brain_provider
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        head = QLabel("Crafting Planner")
        head.setStyleSheet(f"color:{GOLD};font-size:18px;font-weight:bold;")
        root.addWidget(head)
        root.addWidget(QLabel("Describe the item you want to craft in plain language. "
                              "Kalandra outlines a realistic plan; Craft of Exile gives "
                              "exact odds."))
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText(
            "e.g. 'spear with high physical and attack speed for a melee mercenary'")
        self.input.setMaximumHeight(90)
        self.input.setStyleSheet(f"background:{BG0};color:{TEXT};font-size:12px;")
        root.addWidget(self.input)
        row = QHBoxLayout()
        plan_btn = QPushButton("Plan craft")
        plan_btn.clicked.connect(self._plan)
        row.addWidget(plan_btn)
        coe = QPushButton("Open Craft of Exile")
        coe.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://www.craftofexile.com/?game=poe2")))
        row.addWidget(coe)
        row.addStretch()
        root.addLayout(row)
        self.out = QTextEdit(); self.out.setReadOnly(True)
        self.out.setStyleSheet(f"background:{BG1};color:{TEXT};font-size:12px;")
        root.addWidget(self.out, 1)

    def _plan(self):
        goal = (self.input.toPlainText() or "").strip()
        if not goal:
            self.out.setPlainText("Describe the item you want first.")
            return
        brain = None
        if callable(self._brain):
            try:
                brain = self._brain()
            except Exception:
                brain = None
        if brain is None:
            self.out.setPlainText(_offline_craft_guidance(goal))
            return
        self.out.setPlainText("Planning…")

        def _work():
            try:
                prompt = (
                    "You are a Path of Exile 2 crafting advisor. Give a concise, "
                    "step-by-step crafting plan for this goal. Use ONLY real PoE2 "
                    "mechanics (currency orbs, essences, runes, omens). If unsure, "
                    "say so. Goal: " + goal)
                ans = brain.ask(prompt) if hasattr(brain, "ask") else None
                text = ans or _offline_craft_guidance(goal)
            except Exception as e:
                text = _offline_craft_guidance(goal) + f"\n\n(AI unavailable: {e})"
            self._emit(text)

        threading.Thread(target=_work, daemon=True).start()

    # marshal AI result back to UI thread
    def _emit(self, text):
        try:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.out.setPlainText(text))
        except Exception:
            self.out.setPlainText(text)


class LiveSearchTab(QWidget):
    """Set up a live trade search. Kalandra opens the official PoE2 'live search'
    in your browser; when a listing matches, you whisper and buy manually. No
    auto-buy, no automation — fully within GGG's ToS."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        head = QLabel("Live Search")
        head.setStyleSheet(f"color:{GOLD};font-size:18px;font-weight:bold;")
        root.addWidget(head)
        root.addWidget(QLabel("Open the official trade site's live search and keep it "
                              "running in your browser. PoE2's trade site pushes a sound "
                              "on each new match — you whisper the seller yourself."))
        row = QHBoxLayout()
        row.addWidget(QLabel("League:"))
        self.league = QComboBox(); self.league.setEditable(True)
        self.league.addItems(["Rise of the Abyssal", "Dawn of the Hunt", "Standard",
                              "Hardcore"])
        row.addWidget(self.league, 1)
        open_btn = QPushButton("Open trade site")
        open_btn.setStyleSheet(f"border:1px solid {GOLD};color:{GOLD};")
        open_btn.clicked.connect(self._open)
        row.addWidget(open_btn)
        root.addLayout(row)
        info = QTextEdit(); info.setReadOnly(True)
        info.setStyleSheet(f"background:{BG1};color:{TEXT};font-size:12px;")
        info.setPlainText(
            "How live search works (ToS-clean):\n"
            "  1. Open the trade site and build your search (filters, price cap).\n"
            "  2. Switch the result mode to 'Live'. The site holds the connection\n"
            "     open and chimes on every new matching listing.\n"
            "  3. Click the listing's 'Whisper' to copy the buy message, alt-tab\n"
            "     into the game, and paste it. You complete the trade by hand.\n\n"
            "Kalandra never logs in, queries, or buys for you — that would break\n"
            "GGG's automation rules. It just gets you to the right page fast.")
        root.addWidget(info, 1)

    def _open(self):
        league = (self.league.currentText() or "Standard").strip()
        from urllib.parse import quote
        url = f"https://www.pathofexile.com/trade2/search/poe2/{quote(league)}"
        try:
            QDesktopServices.openUrl(QUrl(url))
        except Exception:
            pass


# -- small helpers shared by the economy / trade tabs ------------------------
from core_engine.trade_tools import (  # noqa: E402
    is_number as _is_number,
    parse_item_text as _parse_item_text,
    trade_search_url as _trade_search_url,
    offline_craft_guidance as _offline_craft_guidance,
)


def _qcolor(hexstr):
    try:
        from PyQt6.QtGui import QColor
        return QColor(hexstr)
    except Exception:
        return None


# Canonical dashboard tabs (label, default-on). Users pick which to show in
# Settings; the order here is the order they appear.
DASHBOARD_TABS = [
    ("Terminal", True),
    ("Build (PoB)", True),
    ("Build Sim", True),
    ("Reserve / BIS", True),
    ("Issues / Changelog", True),
    ("Price Check", True),
    ("Exchange", True),
    ("Crafting", True),
    ("Filter Editor", True),
    ("Live Search", True),
    ("Craft of Exile", True),
    ("FilterBlade", True),
    ("poe.ninja", True),
]
_DASHBOARD_TAB_DEFAULTS = dict(DASHBOARD_TABS)


class KalandraDashboard(QWidget):
    def __init__(self, config=None, pob_sim=None, accounts=None, parent=None,
                 issues=None, build_provider=None):
        super().__init__(parent)
        self.config = config or {}
        self.pob_sim = pob_sim
        self.accounts = accounts
        self.issues = issues
        self.build_provider = build_provider
        self._web_tabs = {}          # set BEFORE any tab is added (avoids slot crash)
        self._bridge = _Bridge()
        self._bridge.buildsim_text.connect(self._set_buildsim_text)

        try:
            from version import KALANDRA_VERSION as _KV
        except Exception:
            _KV = "0.0.0"
        self.setWindowTitle(f"Kalandra v{_KV} — Dashboard")
        self.resize(1180, 760)
        self.setStyleSheet(DASH_QSS)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        header = QHBoxLayout()
        title = QLabel("KALANDRA"); title.setObjectName("title")
        sub = QLabel("  single pane for every PoE2 tool"); sub.setObjectName("subtitle")
        header.addWidget(title)
        header.addWidget(sub)
        header.addStretch()
        if not WEBENGINE_AVAILABLE:
            warn = QLabel("web tabs disabled — pip install PyQt6-WebEngine")
            warn.setStyleSheet(f"color:{MUTED};font-size:11px;")
            header.addWidget(warn)
        root.addLayout(header)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_tab = None

        # Build all tabs first, THEN connect currentChanged, so the initial
        # signal can't fire into a half-built state. Each tab is only added if
        # the user has it enabled (Settings -> Dashboard tabs).
        if self._tab_on("Terminal"):
            try:
                self.tabs.addTab(TerminalTab(), "Terminal")
            except Exception as e:
                self.tabs.addTab(_placeholder("Terminal", [f"Terminal unavailable: {e}"]), "Terminal")
        if self._tab_on("Build (PoB)"):
            try:
                self._build_tab = BuildTab(self.build_provider)
                self.tabs.addTab(self._build_tab, "Build (PoB)")
            except Exception as e:
                self._build_tab = None
                self.tabs.addTab(_placeholder("Build (PoB)", [f"Build view unavailable: {e}"]),
                                 "Build (PoB)")
        if self._tab_on("Build Sim"):
            self.tabs.addTab(self._build_sim_tab(), "Build Sim")
        if self._tab_on("Reserve / BIS"):
            try:
                self.tabs.addTab(ReserveTab(), "Reserve / BIS")
            except Exception as e:
                self.tabs.addTab(_placeholder("Reserve / BIS", [f"Reserve unavailable: {e}"]),
                                 "Reserve / BIS")
        if self._tab_on("Issues / Changelog"):
            try:
                self.tabs.addTab(IssuesTab(self.issues), "Issues / Changelog")
            except Exception as e:
                self.tabs.addTab(_placeholder("Issues / Changelog", [f"Issues unavailable: {e}"]),
                                 "Issues / Changelog")
        if self._tab_on("Price Check"):
            try:
                self.tabs.addTab(PriceCheckTab(), "Price Check")
            except Exception as e:
                self.tabs.addTab(_placeholder("Price Check", [f"Unavailable: {e}"]),
                                 "Price Check")
        if self._tab_on("Exchange"):
            try:
                self.tabs.addTab(ExchangeTab(), "Exchange")
            except Exception as e:
                self.tabs.addTab(_placeholder("Currency Exchange", [f"Unavailable: {e}"]),
                                 "Exchange")
        if self._tab_on("Crafting"):
            try:
                self.tabs.addTab(CraftingTab(brain_provider=None), "Crafting")
            except Exception as e:
                self.tabs.addTab(_placeholder("Crafting Planner", [f"Unavailable: {e}"]),
                                 "Crafting")
        if self._tab_on("Filter Editor"):
            try:
                self.tabs.addTab(FilterEditorTab(), "Filter Editor")
            except Exception as e:
                self.tabs.addTab(_placeholder("Filter Editor", [
                    f"Filter editor unavailable: {e}"]), "Filter Editor")
        if self._tab_on("Live Search"):
            try:
                self.tabs.addTab(LiveSearchTab(), "Live Search")
            except Exception as e:
                self.tabs.addTab(_placeholder("Live Search", [f"Unavailable: {e}"]),
                                 "Live Search")

        for label, url in [
            ("Craft of Exile", "https://www.craftofexile.com/"),
            ("FilterBlade", "https://www.filterblade.xyz/"),
            ("poe.ninja", "https://poe.ninja/poe2"),
        ]:
            if self._tab_on(label):
                wt = WebTab(url)
                self._web_tabs[self.tabs.count()] = wt
                self.tabs.addTab(wt, label)

        if self.tabs.count() == 0:
            self.tabs.addTab(_placeholder("No tabs enabled", [
                "You've hidden every dashboard tab.",
                "Re-enable some in Settings -> Dashboard tabs."]), "Dashboard")

        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _tab_on(self, label):
        prefs = (self.config or {}).get("dashboard_tabs", {}) or {}
        if label in prefs:
            return bool(prefs[label])
        return _DASHBOARD_TAB_DEFAULTS.get(label, True)

    def show_tab(self, label):
        """Select a tab by its label (e.g. 'Build (PoB)') and refresh it."""
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == label:
                self.tabs.setCurrentIndex(i)
                w = self.tabs.widget(i)
                if hasattr(w, "refresh"):
                    try:
                        w.refresh()
                    except Exception:
                        pass
                return True
        return False

    def show_build_tab(self):
        return self.show_tab("Build (PoB)")

    def _build_sim_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        card = QFrame(); card.setObjectName("card")
        cl = QVBoxLayout(card)
        h = QLabel("Path of Building — live sandbox")
        h.setStyleSheet(f"color:{GOLD};font-size:16px;font-weight:bold;")
        cl.addWidget(h)
        cl.addWidget(QLabel("Loads the active character and shows its real computed "
                            "stats from the headless engine."))
        # Buttons FIRST so they're always reachable no matter how long the output.
        brow = QHBoxLayout()
        btn = QPushButton("Refresh build stats")
        btn.clicked.connect(self._refresh_buildsim)
        brow.addWidget(btn)
        st = QPushButton("Run self-test (diagnose the engine)")
        st.setToolTip("Boots the headless engine and reports exactly what your PoB "
                      "install exposes. If the live numbers don't work, copy this output "
                      "to the developer for a one-round fix.")
        st.clicked.connect(self._run_sim_selftest)
        brow.addWidget(st)
        cp = QPushButton("Copy self-test output")
        cp.clicked.connect(self._copy_selftest)
        brow.addWidget(cp)
        brow.addStretch()
        cl.addLayout(brow)
        # Scrolling, read-only output — never grows the window.
        self.buildsim_label = QTextEdit()
        self.buildsim_label.setReadOnly(True)
        self.buildsim_label.setPlainText("No build loaded yet.")
        self.buildsim_label.setStyleSheet(f"background:{BG0};color:{TEXT};"
                                          "font-family:Consolas,monospace;font-size:12px;")
        cl.addWidget(self.buildsim_label, 1)
        lay.addWidget(card)
        self._last_selftest = ""
        return w

    def _refresh_buildsim(self):
        if not self.pob_sim:
            self._bridge.buildsim_text.emit("PoB simulator not available.")
            return
        def _work():
            try:
                if not self.pob_sim.available:
                    self._bridge.buildsim_text.emit(self.pob_sim.availability_message())
                elif not self.pob_sim.has_build():
                    self._bridge.buildsim_text.emit(
                        "No build loaded. Load a character in the overlay (green medallion).")
                else:
                    self._bridge.buildsim_text.emit("LIVE: " + self.pob_sim.stats_summary())
            except Exception as e:
                self._bridge.buildsim_text.emit(f"Error: {e}")
        threading.Thread(target=_work, daemon=True).start()

    def _run_sim_selftest(self):
        if not self.pob_sim:
            self._bridge.buildsim_text.emit("PoB simulator module not available.")
            return
        self._bridge.buildsim_text.emit("Running self-test (booting the engine)...")
        def _work():
            import json as _json
            try:
                rep = self.pob_sim.self_test()
                self._last_selftest = _json.dumps(rep, indent=2, default=str)
                status = rep.get("status", "?")
                self._bridge.buildsim_text.emit(
                    f"Self-test status: {status}\n\n{self._last_selftest}")
            except Exception as e:
                self._bridge.buildsim_text.emit(f"Self-test error: {e}")
        threading.Thread(target=_work, daemon=True).start()

    def _copy_selftest(self):
        try:
            QApplication.clipboard().setText(self._last_selftest or "(run the self-test first)")
        except Exception:
            pass

    def _set_buildsim_text(self, text):
        if hasattr(self, "buildsim_label"):
            self.buildsim_label.setPlainText(text)

    def _on_tab_changed(self, idx):
        wt = self._web_tabs.get(idx)
        if wt is not None:
            wt.ensure_loaded()

    def closeEvent(self, event):
        # Hide instead of destroy: reopening is instant, and we avoid tearing
        # down embedded web views (which can crash Qt WebEngine). The app keeps
        # running because the overlay owns the real exit path.
        event.ignore()
        self.hide()


if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    try:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    except Exception:
        pass
    app = QApplication(sys.argv)
    KalandraDashboard().show()
    sys.exit(app.exec())
