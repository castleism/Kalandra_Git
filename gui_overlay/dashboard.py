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
from PyQt6.QtCore import Qt, QUrl, QObject, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QDesktopServices, QFont

# Only probe availability here; do NOT instantiate any web view at import time.
try:
    import PyQt6.QtWebEngineWidgets as _qtwe  # noqa: F401
    WEBENGINE_AVAILABLE = True
except Exception:
    WEBENGINE_AVAILABLE = False


# W3-01: the palette + stylesheet live in ONE place now (gui_overlay/theme.py).
# The names below stay importable so existing tab code keeps working.
from gui_overlay.theme import (   # noqa: F401  (re-exported for tab modules)
    GOLD, GOLD_LIGHT, GOLD_DARK, TEAL, BG0, BG1, BG2, TEXT, MUTED, FAINT,
    RUBY, SAPPHIRE, EMERALD, DIAMOND, kalandra_qss, set_gem,
)

DASH_QSS = kalandra_qss()

# W3-05: the dashboard wears Christian's frame chrome.
from gui_overlay.kalandra_window import KalandraFrameWindow, kinfo, kconfirm  # noqa: E402


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


class TradeSiteTab(WebTab):
    """The official PoE2 trade site in its OWN full-size tab. Price Check
    pushes searches here (open_search) instead of squeezing a browser into
    its bottom strip."""

    DEFAULT_URL = "https://www.pathofexile.com/trade2/search/poe2"

    def __init__(self, parent=None):
        super().__init__(self.DEFAULT_URL, parent)

    def open_search(self, url):
        """Navigate to a specific search URL (creates the view on demand)."""
        self.url = url or self.DEFAULT_URL
        self.ensure_loaded()
        if self.view is not None:
            try:
                self.view.setUrl(QUrl(self.url))
            except Exception:
                pass


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

    def __init__(self, tracker=None, parent=None, config=None):
        super().__init__(parent)
        self.tracker = tracker
        self.config = config if isinstance(config, dict) else {}
        if self.tracker is None:
            try:
                from core_engine.reserve_tracker import ReserveTracker
                self.tracker = ReserveTracker()
            except Exception:
                self.tracker = None
        self._editing_id = None
        self._build_ui()
        self._refresh_list()
        self._refresh_snapshots()

    def _build_ui(self):
        root = QVBoxLayout(self)
        head = QLabel("Unique / BIS Reserve")
        head.setStyleSheet(f"color:{GOLD};font-size:18px;font-weight:bold;")
        root.addWidget(head)
        root.addWidget(QLabel(
            "Snapshot items you're keeping in reserve for future build ideas or "
            "upgrades. Paste the item straight from the game (Ctrl+C on the "
            "tooltip). The Orb sees your reserve and can factor it into advice."))

        # W3-31: the snapshot strip — screenshots from the ruby medallion,
        # newest first, so you can eyeball an item while filing it.
        snap_row = QHBoxLayout()
        snap_row.addWidget(QLabel("Snapshots:"))
        self.snap_combo = QComboBox()
        self.snap_combo.setMinimumWidth(220)
        snap_row.addWidget(self.snap_combo, 1)
        ob = QPushButton("View snapshot")
        ob.clicked.connect(self._open_snapshot)
        snap_row.addWidget(ob)
        fb = QPushButton("Open folder")
        fb.clicked.connect(self._open_snap_folder)
        snap_row.addWidget(fb)
        rs = QPushButton("Rescan")
        rs.clicked.connect(self._refresh_snapshots)
        snap_row.addWidget(rs)
        pb = QPushButton("Paste item from clipboard")
        pb.setProperty("gem", "emerald")
        pb.setToolTip("Copied an item in game (Ctrl+C)? This drops it straight "
                      "into the editor below.")
        pb.clicked.connect(self._paste_clipboard_item)
        snap_row.addWidget(pb)
        root.addLayout(snap_row)

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
    # -- W3-31: snapshot strip -------------------------------------------------
    def _snap_dir(self):
        return self.config.get("dir_snapshots", "data_engine/snapshots")

    def _refresh_snapshots(self):
        import os
        try:
            d = self._snap_dir()
            files = []
            if os.path.isdir(d):
                for fn in os.listdir(d):
                    if fn.lower().endswith((".png", ".jpg")):
                        p = os.path.join(d, fn)
                        files.append((os.path.getmtime(p), fn, p))
            files.sort(reverse=True)
            self.snap_combo.blockSignals(True)
            self.snap_combo.clear()
            for _mt, fn, p in files[:30]:
                self.snap_combo.addItem(fn, p)
            if not files:
                self.snap_combo.addItem("(no snapshots yet — the ruby "
                                        "medallion takes them)", None)
            self.snap_combo.blockSignals(False)
        except Exception:
            pass

    def _open_snapshot(self):
        p = self.snap_combo.currentData()
        if p:
            QDesktopServices.openUrl(QUrl.fromLocalFile(p))

    def _open_snap_folder(self):
        import os
        d = self._snap_dir()
        try:
            os.makedirs(d, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(d)))
        except Exception:
            pass

    def _paste_clipboard_item(self):
        self._paste_clip()

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
        # W3-32: push to the GitHub repo (token in Settings -> GitHub row).
        grow = QHBoxLayout()
        gh_issue = QPushButton("Post selected → GitHub")
        gh_issue.setProperty("gem", "sapphire")
        gh_issue.setToolTip("Create a GitHub Issue from the selected entry "
                            "(castleism/Kalandra_Git).")
        gh_issue.clicked.connect(self._github_post_issue)
        gh_log = QPushButton("Publish changelog → GitHub")
        gh_log.setProperty("gem", "diamond")
        gh_log.setToolTip("Publish the open items as a GitHub pre-release "
                          "changelog entry.")
        gh_log.clicked.connect(self._github_publish_changelog)
        grow.addWidget(gh_issue); grow.addWidget(gh_log)
        ll.addLayout(grow)
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
        if kconfirm(self, "DELETE ISSUE", "Remove this issue?",
                    "Delete", "Keep"):
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

    # -- W3-32: GitHub sync ---------------------------------------------------
    def _github(self):
        from core_engine.github_sync import GitHubSync
        try:
            from core_engine.account_manager import AccountManager
            token_provider = AccountManager().get_secret
        except Exception:
            token_provider = None
        return GitHubSync(token_provider=token_provider)

    def _gh_status(self, ok, msg):
        from PyQt6.QtCore import QTimer
        color = EMERALD if ok else RUBY
        show = ("🟢 " if ok else "⚠ ") + str(msg)
        QTimer.singleShot(0, lambda: (
            self.status.setStyleSheet(f"color:{color};font-size:11px;"),
            self.status.setText(show)))

    def _github_post_issue(self):
        cur = self.listw.currentItem()
        entry = cur.data(Qt.ItemDataRole.UserRole) if cur else None
        if not entry:
            self.status.setText("Pick an issue in the list first.")
            return
        self.status.setText("Posting to GitHub...")
        def _work():
            try:
                ok, msg = self._github().post_issue(entry)
            except Exception as e:
                ok, msg = False, str(e)
            self._gh_status(ok, msg if not ok else f"Posted: {msg}")
        threading.Thread(target=_work, daemon=True).start()

    def _github_publish_changelog(self):
        if not self.tracker:
            return
        md = self.tracker.export_markdown(only_open=True)
        self.status.setText("Publishing changelog to GitHub...")
        def _work():
            try:
                ok, msg = self._github().publish_changelog(md)
            except Exception as e:
                ok, msg = False, str(e)
            self._gh_status(ok, msg if not ok else f"Published: {msg}")
        threading.Thread(target=_work, daemon=True).start()


class BuildTab(QWidget):
    """Shows the CURRENTLY LOADED Path of Building character — class, scaling
    profile, every skill group, equipped items, and tree-socketed jewels — built
    straight from the parse (no LuaJIT simulator required, so it always works).
    This is the 'PoB tab': what the overlay's green Character Selector loads."""

    VIEW_CONTAINER = "container"
    VIEW_TEXT = "text"
    art_ready = pyqtSignal(str, str)     # (slot_key, image_path)
    review_ready = pyqtSignal(str, str)  # (reply, error) — AI review lands here

    # Paperdoll positions (row, col) — laid out like Path of Building.
    _SLOT_POS = {
        "weapon 1": (0, 0), "helmet": (0, 1), "weapon 2": (0, 2),
        "gloves": (1, 0), "body armour": (1, 1), "amulet": (1, 2),
        "ring 1": (2, 0), "belt": (2, 1), "ring 2": (2, 2),
        "boots": (3, 1),
    }
    _RARITY_COL = {"unique": "#af6025", "rare": "#d9cf8a",
                   "magic": "#8888ff", "normal": "#a8a8a8"}

    def __init__(self, build_provider=None, parent=None, config=None,
                 ask_ai=None, sim_stats=None):
        super().__init__(parent)
        self.build_provider = build_provider   # callable -> dict (see overlay.current_build_view)
        self.config = config if isinstance(config, dict) else {}
        self.ask_ai = ask_ai                   # overlay.ask_ai_text
        self.sim_stats = sim_stats             # callable -> live sim summary str
        self.mode = self.config.get("build_view_mode", self.VIEW_CONTAINER)
        if self.mode not in (self.VIEW_CONTAINER, self.VIEW_TEXT):
            self.mode = self.VIEW_CONTAINER
        self._last = {}
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.head = QLabel("No build loaded")
        self.head.setStyleSheet(f"color:{GOLD};font-size:17px;font-weight:bold;")
        top.addWidget(self.head)
        top.addStretch()
        # W3-10: containerized PoB view <-> full text breakdown.
        self.toggle_btn = QPushButton()
        self.toggle_btn.setProperty("gem", "diamond")
        self.toggle_btn.setToolTip("Switch between the containerized build view "
                                   "and the full text breakdown.")
        self.toggle_btn.clicked.connect(self._toggle_view)
        top.addWidget(self.toggle_btn)
        # W4-05: the Orb's written review of THIS character in the text view.
        rev = QPushButton("AI review")
        rev.setProperty("gem", "diamond")
        rev.setToolTip(
            "The Orb reads the full parse + live sim numbers and writes a "
            "review: how the build actually does its damage (mechanism and "
            "scaling), how the gear serves it, passives + support choices, "
            "and where DPS or defence is hiding — nearby nodes, support "
            "swaps, weak gear slots.")
        rev.clicked.connect(self._ai_review)
        top.addWidget(rev)
        # W3-12 v1: shareable HTML character sheet with the REAL PoB numbers.
        exp = QPushButton("Export sheet (HTML)")
        exp.setProperty("gem", "sapphire")
        exp.setToolTip("Write a themed character page (poe.ninja-style, but "
                       "with your build's real PoB stats) and open it.")
        exp.clicked.connect(self._export_sheet)
        top.addWidget(exp)
        rb = QPushButton("Refresh"); rb.clicked.connect(self.refresh)
        top.addWidget(rb)
        lay.addLayout(top)
        self.hint = QLabel("")
        self.hint.setStyleSheet(f"color:{MUTED};font-size:11px;")
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)

        # Text view (the classic full breakdown).
        self.view = QTextEdit(); self.view.setReadOnly(True)
        self.view.setStyleSheet(f"background:{BG0};color:{TEXT};"
                                "font-family:Consolas,monospace;font-size:12px;")
        lay.addWidget(self.view, 1)

        # Container view = the ONE-PAGE character sheet (poe.ninja-style):
        # headline stats, resistances, scaling profile, full equipment with
        # mods, and every skill group — all scrollable on a single page.
        # (The old paperdoll split lives on in the HTML export's tooltips.)
        self.container = QWidget()
        cv = QVBoxLayout(self.container)
        cv.setContentsMargins(0, 0, 0, 0)
        self.sim_lbl = QLabel("")
        self.sim_lbl.setStyleSheet(f"color:{EMERALD};font-size:12px;font-weight:bold;")
        self.sim_lbl.setWordWrap(True)
        cv.addWidget(self.sim_lbl)
        from PyQt6.QtWidgets import QTextBrowser
        self.sheet_view = QTextBrowser()
        self.sheet_view.setOpenExternalLinks(True)
        self.sheet_view.setStyleSheet(
            f"QTextBrowser {{ background:{BG0}; border:none; }}")
        cv.addWidget(self.sheet_view, 1)
        lay.addWidget(self.container, 1)
        self._gear_cards = {}
        self.art_ready.connect(self._on_art)
        self.review_ready.connect(self._on_review_ready)

        self._apply_mode()

    def _ai_review(self):
        """W4-05: the Orb's deep character review, grounded in the parse +
        live sim. Asks for damage MECHANISM deduction (how the build actually
        kills — e.g. a Corrupted Blood scaler is not a bleed build; the
        knowledge-corrections layer rides along in the AI context), gear/
        passive/support analysis, and concrete sim-checkable improvements."""
        data = self._last or {}
        if not data.get("loaded"):
            self.hint.setText("Load a character first — then ask for its review.")
            return
        if not self.ask_ai:
            self.hint.setText("AI channel not connected — configure a brain "
                              "in Settings.")
            return
        sim = ""
        try:
            sim = (self.sim_stats() or "") if self.sim_stats else ""
        except Exception:
            pass
        import json as _json
        build_txt = _json.dumps(data, ensure_ascii=False, default=str)[:9000]
        prompt = (
            "Write a structured review of my currently loaded PoE2 character. "
            "Use ONLY the parse and sim numbers below plus the verified facts "
            "in your context — no invented mods or numbers.\n\n"
            "Cover, in order:\n"
            "1. DAMAGE MECHANISM — deduce how this build actually deals its "
            "damage and what scales it (skill + supports + gear + passives "
            "working together). If the mechanism is unusual (e.g. Corrupted "
            "Blood stacking, ailment conversion), name it and explain the "
            "scaling chain explicitly.\n"
            "2. GEAR — how each notable piece serves the build; which slot is "
            "weakest and why.\n"
            "3. PASSIVES + SUPPORTS — do the tree and support choices match "
            "the mechanism? Any dead or low-value picks?\n"
            "4. IMPROVEMENTS — nearby passive nodes worth pathing to, support "
            "gem swaps, and the single biggest gear upgrade; for each, say "
            "what the live sim should show if it works (so I can verify in "
            "the Build Sim tab).\n"
            "5. DEFENCE — where I'm most likely to die and the cheapest fix.")
        sim_note = sim if sim else \
            "(sim not running — flag every suggestion as unverified)"
        prompt += f"\n\nLIVE SIM: {sim_note}\n\nFULL PARSE:\n{build_txt}"
        self.hint.setText("The Orb is reading the build… (review lands in "
                          "the text view)")
        if self.mode != self.VIEW_TEXT:
            self._toggle_view()

        # The ask_ai callback fires on a WORKER thread; QTimer.singleShot
        # can't start timers there (the review looked like it did nothing).
        # A queued signal marshals it to the UI thread properly.
        def _cb(reply, error=None):
            self.review_ready.emit(reply or "", error or "")
        try:
            self.ask_ai(prompt, _cb)
        except Exception as e:
            self.hint.setText(f"Review failed: {e}")

    def _on_review_ready(self, reply, error):
        if reply and not error:
            self.view.setPlainText(reply)
            self.hint.setText("Review written. Regenerate any time — it also "
                              "lands in the character's folio.")
            try:
                from core_engine.character_folio import CharacterFolio
                name = (self._last or {}).get("character") or "character"
                CharacterFolio(name).write_doc("review", reply)
            except Exception:
                pass
        else:
            self.hint.setText(f"Review failed: {error or 'no reply'}")

    def _export_sheet(self):
        data = self._last or {}
        if not data.get("loaded"):
            self.hint.setText("Load a character first — then export its sheet.")
            return
        try:
            import os
            from core_engine.character_sheet import build_character_sheet_html
            html = build_character_sheet_html(data)
            d = os.path.join("data_engine", "exports")
            os.makedirs(d, exist_ok=True)
            safe = "".join(ch if ch.isalnum() or ch in "-_" else "_"
                           for ch in (data.get("character") or "character"))
            path = os.path.abspath(os.path.join(d, f"{safe}_sheet.html"))
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            self.hint.setText(f"Character sheet exported: {path}")
        except Exception as e:
            self.hint.setText(f"Export failed: {e}")

    # -- view switching ------------------------------------------------------
    def _toggle_view(self):
        self.mode = (self.VIEW_TEXT if self.mode == self.VIEW_CONTAINER
                     else self.VIEW_CONTAINER)
        self.config["build_view_mode"] = self.mode
        try:   # persist (lazy import avoids a circular module load)
            from gui_overlay.mirror_window import save_config
            save_config(self.config)
        except Exception:
            pass
        self._apply_mode()

    def _apply_mode(self):
        container = self.mode == self.VIEW_CONTAINER
        self.container.setVisible(container)
        self.view.setVisible(not container)
        # Label = the view the click TAKES you to (it read backwards before).
        self.toggle_btn.setText("View: Text ≡" if container else "View: Sheet ▣")

    # -- data ---------------------------------------------------------------
    def refresh(self):
        data = {}
        try:
            if self.build_provider:
                data = self.build_provider() or {}
        except Exception as e:
            data = {"error": str(e)}
        self._last = data
        if data.get("error"):
            self.head.setText("Build unavailable")
            self.view.setPlainText("Could not read the build: " + data["error"])
            self._fill_sheet(None)
            return
        if not data.get("loaded"):
            self.head.setText("No build loaded")
            self.hint.setText("")
            self.view.setPlainText(
                "No Path of Building build is loaded yet.\n\n"
                "Load one from the overlay: click the green Character Selector "
                "medallion, then 'Load my saved PoB builds' and 'Set active' — or "
                "paste a PoB code / pobb.in link. It will appear here.")
            self._fill_sheet(None)
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

        # Text view content (unchanged behavior).
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

        # Container view content: the one-page character sheet.
        self._fill_sheet(data)

    def _fill_sheet(self, data):
        """Render the poe.ninja-style one-pager into the container view."""
        if not hasattr(self, "sheet_view"):
            return
        if not data or not data.get("loaded"):
            self.sim_lbl.setText("")
            self.sheet_view.setHtml(
                "<div style='color:#9aa4b2;font-size:13px;padding:20px;'>"
                "No build loaded.<br><br>Load a character from the overlay "
                "(green medallion → 'Load my saved PoB builds' or paste a "
                "PoB code) and the full character sheet appears here — "
                "stats, resistances, gear with mods, and every skill link, "
                "poe.ninja style but with YOUR real PoB numbers.</div>")
            return
        self.sim_lbl.setText(("LIVE SIM: " + data["sim"]) if data.get("sim")
                             else "")
        try:
            from core_engine.character_sheet import build_character_sheet_html
            self.sheet_view.setHtml(
                build_character_sheet_html(data, embedded=True))
        except Exception as e:
            self.sheet_view.setPlainText(f"Sheet render failed: {e}")

    _STAT_CHIPS = [  # (PoB PlayerStat key, label, accent)
        ("TotalDPS", "DPS", "#e87284"), ("CombinedDPS", "Combined DPS", "#e87284"),
        ("Life", "Life", "#e87284"), ("EnergyShield", "ES", "#7aa2e8"),
        ("Mana", "Mana", "#7aa2e8"), ("Armour", "Armour", "#c8aa6e"),
        ("Evasion", "Evasion", "#72d6a4"), ("CritChance", "Crit %", "#f0d9a8"),
        ("CritMultiplier", "Crit Multi", "#f0d9a8"), ("Str", "Str", "#e08a90"),
        ("Dex", "Dex", "#8fd6a0"), ("Int", "Int", "#8ab0e8"),
    ]

    def _gear_card(self, it):
        """One slot card: rarity frame, art (async), full tooltip on hover."""
        rarity = (it.get("rarity") or "").lower()
        col = self._RARITY_COL.get(rarity, "#6b7280")
        card = QFrame()
        card.setFixedSize(150, 118)
        card.setStyleSheet(f"QFrame{{background:{BG1};border:2px solid {col};"
                           f"border-radius:6px;}}")
        v = QVBoxLayout(card); v.setContentsMargins(4, 4, 4, 4); v.setSpacing(2)
        slot_lbl = QLabel(str(it.get("slot") or ""))
        slot_lbl.setStyleSheet(f"color:{MUTED};font-size:9px;border:none;")
        v.addWidget(slot_lbl)
        art = QLabel(); art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        art.setStyleSheet("border:none;")
        art.setMinimumHeight(52)
        v.addWidget(art, 1)
        name_lbl = QLabel(str(it.get("name") or "?"))
        name_lbl.setWordWrap(True)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet(f"color:{col};font-size:10px;font-weight:bold;"
                               f"border:none;")
        v.addWidget(name_lbl)
        # poe.ninja-style hover: the full item, rarity-colored, in a tooltip.
        mods = "".join(f"<br><span style='color:#8fa0c0;'>{m}</span>"
                       for m in (it.get("mods") or []))
        base = it.get("base") or ""
        card.setToolTip(
            f"<b style='color:{col};'>{it.get('name', '?')}</b>"
            + (f"<br><span style='color:#9aa4b2;'>{base}</span>"
               if base and base != it.get("name") else "")
            + (f"<br><span style='color:#7d8694;'>{rarity.title()}</span>"
               if rarity else "")
            + ("<hr>" if mods else "") + mods)
        return card, art

    def _on_art(self, key, path):
        art_lbl = self._gear_cards.get(key)
        if art_lbl is None or not path:
            return
        try:
            from PyQt6.QtGui import QPixmap
            pm = QPixmap(path)
            if not pm.isNull():
                art_lbl.setPixmap(pm.scaled(
                    64, 52, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
        except Exception:
            pass

    def _fill_container(self, full, sim_text):
        # clear the paperdoll
        while self.gear_grid.count():
            w = self.gear_grid.takeAt(0).widget()
            if w is not None and w is not self.gear_empty:
                w.deleteLater()
        self._gear_cards = {}
        self.skills_list.clear()
        self.sim_lbl.setText(("LIVE SIM: " + sim_text) if sim_text else "")
        if not isinstance(full, dict) or full.get("error"):
            self.stats_lbl.setText("")
            self.gear_empty.setVisible(True)
            self.gear_grid.addWidget(self.gear_empty, 0, 0, 1, 3)
            return
        self.gear_empty.setVisible(False)
        # headline chips
        stats = full.get("stats") or {}
        chips = []
        for key, label, color in self._STAT_CHIPS:
            v = stats.get(key)
            if v in (None, "", "0", "0.0"):
                continue
            try:
                fv = float(v)
                v = f"{fv:,.0f}" if abs(fv) >= 100 else f"{fv:g}"
            except (TypeError, ValueError):
                pass
            chips.append(f"<span style='color:{color};'><b>{label}</b> {v}</span>")
            if len(chips) >= 10:
                break
        who = (f"{full.get('class_name','?')} / {full.get('ascendancy','None')} "
               f"&nbsp;Lv{full.get('level','?')}")
        main = full.get("main_skill")
        if main:
            who += f" &nbsp;—&nbsp; main skill: <b style='color:{GOLD};'>{main}</b>"
        self.stats_lbl.setText(who + "<br>" + " &nbsp;·&nbsp; ".join(chips))
        # items -> paperdoll grid (PoB layout); extras flow below.
        items = full.get("items") or []
        extra_row = 4
        extra_col = 0
        art_jobs = []
        for it in items:
            key = str(it.get("slot") or it.get("name") or "?")
            card, art_lbl = self._gear_card(it)
            pos = self._SLOT_POS.get(key.lower())
            if pos:
                self.gear_grid.addWidget(card, pos[0], pos[1])
            else:
                self.gear_grid.addWidget(card, extra_row, extra_col)
                extra_col += 1
                if extra_col > 2:
                    extra_col = 0
                    extra_row += 1
            self._gear_cards[key] = art_lbl
            art_jobs.append((key, it.get("name") or "", it.get("base") or ""))
        # fetch art off-thread; cached items resolve instantly
        if art_jobs:
            def _art_work(jobs=art_jobs):
                try:
                    from core_engine.item_art import get_art
                    for key, name, base in jobs:
                        p = get_art(name, base)
                        if p:
                            self.art_ready.emit(key, p)
                except Exception:
                    pass
            threading.Thread(target=_art_work, daemon=True).start()
        # skills
        for grp in (full.get("skills") or []):
            if isinstance(grp, dict):
                label = str(grp.get("active") or grp.get("label") or "?")
                sups = grp.get("supports") or []
                if sups:
                    label += "  ←  " + ", ".join(str(s) for s in sups)
                is_main = bool(grp.get("is_main"))
            else:
                label = str(grp)
                is_main = False
            item = QListWidgetItem(("★ " if is_main else "  ") + label)
            if is_main:
                item.setForeground(_qcolor(GOLD))
            self.skills_list.addItem(item)


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
        self.listw.setIconSize(QSize(22, 22))
        self.listw.currentItemChanged.connect(self._on_pick)
        ll.addWidget(self.listw, 1)
        arow = QHBoxLayout()
        for act, gem in (("Show", "emerald"), ("Hide", "ruby"),
                         ("Minimal", "diamond")):
            btn = QPushButton(act)
            btn.setProperty("gem", gem)
            btn.clicked.connect(lambda _c, a=act: self._set_action(a))
            arow.addWidget(btn)
        ll.addLayout(arow)
        split.addWidget(left)
        right = QWidget(); rl = QVBoxLayout(right)
        # W3-30: what the block MEANS, in plain language...
        self.desc = QLabel("Pick a block on the left.")
        self.desc.setWordWrap(True)
        self.desc.setStyleSheet(f"color:{GOLD_LIGHT};font-size:13px;font-weight:bold;")
        rl.addWidget(self.desc)
        # ...how the label will actually LOOK in game...
        rl.addWidget(QLabel("In-game label preview:"))
        self.preview = QLabel("  Divine Orb  ")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(56)
        rl.addWidget(self.preview)
        # ...and only then the raw filterese, for the curious.
        rl.addWidget(QLabel("Raw block (read-only):"))
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

    @staticmethod
    def _swatch_icon(style):
        """A little 22x22 chip painted with the block's actual label colors."""
        from PyQt6.QtGui import QPixmap, QPainter, QColor, QIcon, QPen
        pm = QPixmap(22, 22)
        pm.fill(QColor(*(style.get("bg") or (30, 30, 30))))
        p = QPainter(pm)
        p.setPen(QPen(QColor(*(style.get("border") or (90, 90, 90))), 2))
        p.drawRect(1, 1, 19, 19)
        p.setPen(QColor(*(style.get("text") or (200, 200, 200))))
        f = p.font(); f.setBold(True); f.setPixelSize(13); p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "A")
        p.end()
        return QIcon(pm)

    def _refresh_list(self):
        if not self.doc:
            return
        term = (self.search.text() or "").strip().lower()
        self.listw.blockSignals(True)
        self.listw.clear()
        colors = {"Show": "#7fd6a0", "Hide": "#e08a90", "Minimal": "#d9cf8a"}
        for i, blk in enumerate(self.doc.blocks):
            try:
                label = blk.describe()
            except Exception:
                label = f"[{blk.action}] {blk.summary()}"
            if term and term not in label.lower() and term not in blk.action.lower():
                continue
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, i)
            try:
                from PyQt6.QtGui import QColor
                it.setForeground(QColor(colors.get(blk.action, "#e8e6df")))
                it.setIcon(self._swatch_icon(blk.style()))
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
        try:
            self.desc.setText(blk.describe())
        except Exception:
            self.desc.setText(blk.summary())
        # Live in-game-style label preview from the block's own colors.
        try:
            st = blk.style()
            tr, tg, tb = st.get("text") or (200, 200, 200)
            br, bgc, bb = st.get("bg") or (12, 12, 12)
            rr, rg, rb = st.get("border") or (90, 90, 90)
            fpx = int((st.get("font") or 32) * 0.55) + 4
            # sample text: first BaseType if present, else the class
            sample = "Item Label"
            for c in blk.conditions():
                if c.startswith("BaseType"):
                    sample = c.split('"')[1] if '"' in c else sample
                    break
                if c.startswith("Class"):
                    sample = (c.split('"')[1] if '"' in c
                              else c.split()[-1]).rstrip("s")
            self.preview.setText(f"  {sample}  ")
            self.preview.setStyleSheet(
                f"background:rgb({br},{bgc},{bb});color:rgb({tr},{tg},{tb});"
                f"border:2px solid rgb({rr},{rg},{rb});"
                f"font-size:{fpx}px;font-weight:bold;")
        except Exception:
            pass
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
        if not kconfirm(self, "SAVE FILTER",
                        "Overwrite your filter file? A .bak backup is "
                        "written first.", "Save", "Cancel"):
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


# Latest economy rows fetched by the Exchange tab — shared so the crafting
# planner and the clipboard price popup can annotate with live prices.
LAST_ECON_ROWS = []

# The currencies a player actually stockpiles (holdings grid, W3-25).
HOLDING_NAMES = ["Divine Orb", "Exalted Orb", "Chaos Orb", "Regal Orb",
                 "Orb of Alchemy", "Orb of Annulment", "Orb of Chance",
                 "Vaal Orb", "Orb of Augmentation", "Orb of Transmutation",
                 "Mirror of Kalandra", "Gold"]


class ExchangeTab(QWidget):
    """Live PoE2 currency/economy from poe.ninja's public JSON API (no login,
    no key). Read-only, polite caching, fully ToS-clean. Fetches off the UI
    thread so the dashboard never freezes. Also: your currency holdings
    (incl. Gold) with live portfolio value (W3-25), and day-over-day movers
    with buy/sell hints (W3-26)."""

    rows_ready = pyqtSignal(list, str)   # (rows, status)
    insights_ready = pyqtSignal(str)

    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self._ninja = None
        self.config = config if isinstance(config, dict) else {}
        self._build_ui()
        self.rows_ready.connect(self._on_rows)
        self.insights_ready.connect(self._on_insights)

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

        # Left: market table | Right: holdings + daily insights.
        split = QSplitter(Qt.Orientation.Horizontal)
        lw = QWidget(); lv = QVBoxLayout(lw); lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(self.table, 1)
        split.addWidget(lw)

        rw = QWidget(); rv = QVBoxLayout(rw); rv.setContentsMargins(6, 0, 0, 0)
        h2 = QLabel("My currency")
        h2.setStyleSheet(f"color:{GOLD};font-size:14px;font-weight:bold;")
        rv.addWidget(h2)
        rv.addWidget(QLabel("What you're holding (counts). Gold included."))
        self.hold_tbl = QTableWidget(len(HOLDING_NAMES), 2)
        self.hold_tbl.setHorizontalHeaderLabels(["Currency", "Count"])
        self.hold_tbl.verticalHeader().setVisible(False)
        saved = (self.config.get("holdings") or {})
        for i, name in enumerate(HOLDING_NAMES):
            it = QTableWidgetItem(name)
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.hold_tbl.setItem(i, 0, it)
            self.hold_tbl.setItem(i, 1, QTableWidgetItem(str(saved.get(name, 0))))
        try:
            self.hold_tbl.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.Stretch)
        except Exception:
            pass
        rv.addWidget(self.hold_tbl, 1)
        hrow = QHBoxLayout()
        save_h = QPushButton("Save holdings")
        save_h.setProperty("gem", "emerald")
        save_h.clicked.connect(self._save_holdings)
        hrow.addWidget(save_h)
        scan_h = QPushButton("Scan currency-tab screenshot…")
        scan_h.setProperty("gem", "sapphire")
        scan_h.setToolTip(
            "In game: open your currency stash tab and screenshot it (the "
            "ruby medallion on the mirror, or any screenshot). Kalandra OCRs "
            "the counts and fills the table — review, then Save holdings.")
        scan_h.clicked.connect(self._scan_holdings_screenshot)
        hrow.addWidget(scan_h)
        hrow.addStretch()
        rv.addLayout(hrow)
        tip_h = QLabel("Tip: screenshot your currency stash tab in game and "
                       "scan it here — counts fill in automatically; you "
                       "confirm before saving.")
        tip_h.setWordWrap(True)
        tip_h.setStyleSheet(f"color:{MUTED};font-size:10px;")
        rv.addWidget(tip_h)
        self.worth_lbl = QLabel("Portfolio: refresh prices to value it.")
        self.worth_lbl.setStyleSheet(f"color:{GOLD_LIGHT};font-weight:bold;")
        self.worth_lbl.setWordWrap(True)
        rv.addWidget(self.worth_lbl)

        h3 = QLabel("Today's market")
        h3.setStyleSheet(f"color:{GOLD};font-size:14px;font-weight:bold;")
        rv.addWidget(h3)
        self.insights = QTextEdit(); self.insights.setReadOnly(True)
        self.insights.setPlaceholderText("Refresh prices — movers vs the 7-day "
                                         "average and buy/sell hints appear here.")
        self.insights.setStyleSheet(f"background:{BG0};color:{TEXT};font-size:12px;")
        rv.addWidget(self.insights, 1)
        split.addWidget(rw)
        split.setSizes([560, 400])
        root.addWidget(split, 1)
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
            # W3-26: snapshot history + movers (own DB connection: worker thread).
            if rows:
                try:
                    from core_engine.database_handler import KalandraDBHandler
                    wdb = KalandraDBHandler()
                    try:
                        self._ninja.store_history(wdb, league, rows)
                        ins = self._ninja.daily_insights(wdb, league, rows)
                        txt = []
                        if ins["movers"]:
                            txt.append("MOVERS vs 7-day average:")
                            for name, value, avg_v, delta in ins["movers"]:
                                arrow = "▲" if delta > 0 else "▼"
                                txt.append(f"  {arrow} {name}: {value:,.2f} ex "
                                           f"({delta:+.0f}%)")
                            txt.append("")
                        txt.extend(ins["advice"])
                        self.insights_ready.emit("\n".join(txt))
                    finally:
                        wdb.close()
                except Exception as e:
                    self.insights_ready.emit(f"Insights unavailable: {e}")

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
        global LAST_ECON_ROWS
        LAST_ECON_ROWS = list(self._all_rows)
        self._apply_filter()
        self._update_worth()

    def _on_insights(self, text):
        self.insights.setPlainText(text)

    # -- W3-25: holdings -----------------------------------------------------
    def _holdings(self):
        out = {}
        for i in range(self.hold_tbl.rowCount()):
            name = self.hold_tbl.item(i, 0).text()
            try:
                out[name] = max(0.0, float(self.hold_tbl.item(i, 1).text() or 0))
            except (TypeError, ValueError):
                out[name] = 0.0
        return out

    def _scan_holdings_screenshot(self):
        """OCR a currency-tab screenshot into the holdings table. Counts land
        in the table for REVIEW — nothing saves until 'Save holdings'."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Pick a currency-tab screenshot", "data_engine/snapshots",
            "Images (*.png *.jpg *.jpeg)")
        if not path:
            return
        try:
            import pytesseract
            from PIL import Image
        except Exception:
            self.worth_lbl.setText(
                "Screenshot scanning needs OCR: pip install pytesseract "
                "pillow (plus the Tesseract engine — see Setup & "
                "Dependencies).")
            return
        try:
            text = pytesseract.image_to_string(Image.open(path))
        except Exception as e:
            self.worth_lbl.setText(f"OCR failed: {e}")
            return
        # Match "1,234" style counts near currency names, and "23x Chaos Orb"
        # tooltip style. Case-insensitive, tolerant of OCR noise.
        import re
        low = text.lower()
        found = {}
        for i in range(self.hold_tbl.rowCount()):
            name = self.hold_tbl.item(i, 0).text()
            n = name.lower()
            for pat in (rf"([\d,]+)\s*x?\s*{re.escape(n)}",
                        rf"{re.escape(n)}\s*x?\s*([\d,]+)"):
                m = re.search(pat, low)
                if m:
                    try:
                        found[name] = int(m.group(1).replace(",", ""))
                    except Exception:
                        pass
                    break
        if not found:
            self.worth_lbl.setText(
                "No currency counts recognized in that screenshot — make "
                "sure the stash tab text is readable (hover tooltips OCR "
                "best), or type the counts directly.")
            return
        for i in range(self.hold_tbl.rowCount()):
            name = self.hold_tbl.item(i, 0).text()
            if name in found:
                self.hold_tbl.setItem(i, 1, QTableWidgetItem(str(found[name])))
        self.worth_lbl.setText(
            f"Scanned {len(found)} currency counts from the screenshot — "
            f"review the table, then 'Save holdings'.")

    def _save_holdings(self):
        self.config["holdings"] = self._holdings()
        try:
            from gui_overlay.mirror_window import save_config
            save_config(self.config)
        except Exception:
            pass
        self._update_worth()
        self.status.setText("Holdings saved.")

    def _update_worth(self):
        if not self._all_rows:
            return
        prices = {str(r.get("name", "")).lower(): r.get("value")
                  for r in self._all_rows}
        total_ex = 0.0
        missing = []
        for name, count in self._holdings().items():
            if count <= 0:
                continue
            v = prices.get(name.lower())
            if _is_number(v):
                total_ex += float(v) * count
            elif name != "Gold":
                missing.append(name)
        gold = self._holdings().get("Gold", 0)
        div = prices.get("divine orb")
        div_s = (f"  (≈ {total_ex / float(div):,.1f} Divine)"
                 if _is_number(div) and float(div) > 0 else "")
        note = f"  — no price for: {', '.join(missing)}" if missing else ""
        gold_s = f"  +  {gold:,.0f} Gold (vendor economy)" if gold else ""
        self.worth_lbl.setText(
            f"Portfolio: ~{total_ex:,.1f} Exalted{div_s}{gold_s}{note}")

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


# W3-21 (remaining half): the trade site's stat-id map, so 'Open trade
# search' can pre-fill the parsed item's filters via ?q=<query JSON>.
# Memory -> week-old disk cache -> ONE background fetch; callers always get a
# dict and fall back to the plain URL while it's empty. Same fixed-host rule
# as everything else (pathofexile.com, descriptive UA, timeout).
_TRADE_STATS = {"index": None, "fetching": False}
_TRADE_STATS_CACHE = "data_engine/trade_stats_poe2.json"


def _trade_stats_index():
    import os
    idx = _TRADE_STATS["index"]
    if idx is not None:
        return idx
    try:                                       # fresh-enough disk cache?
        import json as _json
        import time as _time
        if (os.path.exists(_TRADE_STATS_CACHE)
                and _time.time() - os.path.getmtime(_TRADE_STATS_CACHE)
                < 7 * 86400):
            with open(_TRADE_STATS_CACHE, "r", encoding="utf-8") as f:
                data = _json.load(f)
            from core_engine.trade_tools import build_stats_index
            idx = build_stats_index(data)
            if idx:
                _TRADE_STATS["index"] = idx
                return idx
    except Exception:
        pass
    if not _TRADE_STATS["fetching"]:
        _TRADE_STATS["fetching"] = True

        def _work():
            try:
                import json as _json
                import requests
                r = requests.get(
                    "https://www.pathofexile.com/api/trade2/data/stats",
                    headers={"User-Agent":
                             "KalandraOverlay/0.1 "
                             "(github.com/castleism/Kalandra_Git)"},
                    timeout=25)
                if r.ok:
                    data = r.json()
                    from core_engine.trade_tools import build_stats_index
                    idx2 = build_stats_index(data)
                    if idx2:
                        _TRADE_STATS["index"] = idx2
                        os.makedirs("data_engine", exist_ok=True)
                        with open(_TRADE_STATS_CACHE, "w",
                                  encoding="utf-8") as f:
                            _json.dump(data, f)
            except Exception:
                pass
            finally:
                _TRADE_STATS["fetching"] = False
        threading.Thread(target=_work, daemon=True).start()
    return {}


class PriceCheckTab(QWidget):
    """Paste an item copied from the game (Ctrl+C in-game) and Kalandra parses it
    and opens the matching search on the OFFICIAL PoE2 trade site. No automated
    buying, no price fabrication — you read real listings yourself, per GGG ToS.
    W3-22: searches can be saved by name and re-run any time.
    W3-21: when the stat-id map is cached, the search opens with the item's
    filters already in the query (premium/good mods enabled at their rolls)."""

    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.config = config if isinstance(config, dict) else {}
        self._build_ui()
        self._reload_saved()
        _trade_stats_index()          # warm the stat map in the background

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
        scan_btn = QPushButton("Scan screenshot…")
        scan_btn.setProperty("gem", "sapphire")
        scan_btn.setToolTip("Pick an item screenshot (e.g. a ruby-medallion "
                            "snapshot); Kalandra OCRs the tooltip text into "
                            "the box and parses it for the trade search.")
        scan_btn.clicked.connect(self._scan_image)
        row.addWidget(scan_btn)
        self.open_btn = QPushButton("Open trade search")
        self.open_btn.setStyleSheet(f"border:1px solid {GOLD};color:{GOLD};")
        self.open_btn.clicked.connect(self._open_trade)
        self.open_btn.setEnabled(False)
        row.addWidget(self.open_btn)
        root.addLayout(row)

        # W3-22: saved searches — save the pasted item + league under a name.
        srow = QHBoxLayout()
        self.saved_combo = QComboBox()
        self.saved_combo.currentIndexChanged.connect(self._load_search)
        srow.addWidget(self.saved_combo, 1)
        sv = QPushButton("Save search")
        sv.setProperty("gem", "emerald")
        sv.clicked.connect(self._save_search)
        srow.addWidget(sv)
        dl = QPushButton("Delete")
        dl.setProperty("gem", "ruby")
        dl.clicked.connect(self._delete_search)
        srow.addWidget(dl)
        root.addLayout(srow)

        self.summary = QTextEdit(); self.summary.setReadOnly(True)
        self.summary.setMaximumHeight(110)
        self.summary.setStyleSheet(f"background:{BG1};color:{TEXT};font-size:12px;")
        root.addWidget(self.summary)

        # The mod-value board gets the tab's full height (the browser used
        # to squat here in an unusable strip — it now lives in its own
        # 'Trade Site' tab; 'Open trade search' pushes searches over there).
        # Per-mod: search tier, what the mod does for price, and YOUR ledger
        # median for that mod template as local data accrues.
        self.mods_table = QTableWidget(0, 4)
        self.mods_table.setHorizontalHeaderLabels(
            ["Mod", "Tier", "Why", "Your median (n)"])
        hh = self.mods_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.mods_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self.mods_table, 1)
        self._parsed = None
        self.open_trade_site = None   # dashboard injects: url -> Trade Site tab

    def _parse(self):
        text = self.input.toPlainText()
        info = _parse_item_text(text)
        self._parsed = info
        if not info.get("name") and not info.get("base"):
            self.summary.setPlainText("Couldn't read an item. Copy it in-game with "
                                      "Ctrl+C (hover the item, press C), then paste here.")
            self.open_btn.setEnabled(False)
            return
        head_bits = [b for b in (info.get("rarity"), info.get("name"),
                                 info.get("base"), info.get("item_class"),
                                 f"ilvl {info['ilvl']}" if info.get("ilvl") else None)
                     if b]
        html = ["<b>" + " · ".join(head_bits) + "</b>"]
        # W3-21/23 + W4-12: per-mod value board — tier, why, and YOUR ledger
        # median per mod template — in the big table (browser moved out).
        tier_col = {"premium": "#f0d9a8", "good": "#8fd6a0",
                    "neutral": "#9aa4b2", "filler": "#7d8694",
                    "downside": "#e08a90"}
        tier_tag = {"premium": "★ PREMIUM", "good": "＋ good",
                    "neutral": "· neutral", "filler": "— filler",
                    "downside": "▼ downside"}
        led = None
        try:
            from core_engine.price_ledger import PriceLedger, mod_template
            led = PriceLedger()
        except Exception:
            pass
        league = (self.league.currentText() or "Standard").strip()
        self.mods_table.setRowCount(0)
        try:
            from core_engine.trade_tools import mod_insights
            rows = mod_insights(info)["mods"]
        except Exception:
            rows = [(m, "neutral", "") for m in (info.get("mods") or [])]
        for m, tier, tip in rows[:40]:
            r = self.mods_table.rowCount()
            self.mods_table.insertRow(r)
            it_mod = QTableWidgetItem(str(m))
            it_tier = QTableWidgetItem(tier_tag.get(tier, tier))
            _c = _qcolor(tier_col.get(tier, "#9aa4b2"))
            if _c is not None:
                it_tier.setForeground(_c)
            it_why = QTableWidgetItem(str(tip or ""))
            med = ""
            if led is not None:
                try:
                    tpl, _vals = mod_template(m)
                    mv = led.mod_value(tpl, league=league)
                    if mv:
                        med = f"~{mv[0]:g} {mv[1]} ({mv[2]})"
                except Exception:
                    pass
            it_med = QTableWidgetItem(med)
            for col, it in enumerate((it_mod, it_tier, it_why, it_med)):
                self.mods_table.setItem(r, col, it)
        try:
            from core_engine.trade_tools import mod_insights
            advice = mod_insights(info)["advice"]
            if advice:
                html.append("")
                html.append("<b style='color:#f0c987;'>Search strategy:</b> "
                            + "  →  ".join(advice))
        except Exception:
            pass
        html.append("<i>Uniques search by name; rares by base type. 'Open "
                    "trade search' opens listings in the Trade Site tab. "
                    "'Your median' fills in as your price-check history grows "
                    "— sockets/quality/base adjustments sharpen with it.</i>")
        self.summary.setHtml("<br>".join(html))
        self.open_btn.setEnabled(True)
        # W4-12 (local-first): remember this check in the price ledger — the
        # seed data for mod-value estimates. Local SQLite only; the community
        # upload layer is opt-in and separate. When the ledger already knows
        # enough about these mods, show its estimate (clearly labeled as your
        # own historical data, not a market quote).
        try:
            from core_engine.price_ledger import PriceLedger
            led2 = PriceLedger()
            led2.log_check(info, league=league)
            est = led2.estimate_item(info, league=league)
            if est:
                self.summary.setHtml(
                    self.summary.toHtml() +
                    f"<br><span style='color:#8fd6a0;'>Ledger estimate: "
                    f"~{est['estimate']} {est['currency']} "
                    f"({est['known_mods']}/{est['total_mods']} mods known from "
                    f"your {led2.stats()['priced']} priced checks — your own "
                    f"history, not a market quote)</span>")
        except Exception:
            pass

    def _open_trade(self):
        league = (self.league.currentText() or "Standard").strip()
        url = _trade_search_url(self._parsed or {}, league)
        # W3-21: pre-fill the query when the stat map is ready; plain search
        # page otherwise (and the map keeps downloading for next time).
        try:
            idx = _trade_stats_index()
            if idx and self._parsed:
                from core_engine.trade_tools import (build_trade_query,
                                                     trade_query_url)
                qy, matched, total, notes = build_trade_query(self._parsed,
                                                              idx)
                url = trade_query_url(qy, league)
                note = (f"Search opened with filters pre-filled: "
                        f"{matched}/{total} mods mapped to trade stats "
                        "(premium/good enabled at your rolls, the rest one "
                        "click away).")
                if notes:
                    note += " " + " ".join(notes)
                self.summary.setHtml(
                    self.summary.toHtml()
                    + f"<br><span style='color:#8fd6a0;'>{note}</span>")
            elif self._parsed and (self._parsed.get("mods")):
                self.summary.setHtml(
                    self.summary.toHtml()
                    + "<br><span style='color:#9aa4b2;'>Stat map still "
                    "downloading — plain search this time; filters will "
                    "pre-fill once it's cached.</span>")
        except Exception:
            pass
        # The search opens in the dedicated Trade Site tab (full-size browser)
        # — the dashboard injects open_trade_site and switches tabs. External
        # browser only as a fallback when the tab isn't available.
        if self.open_trade_site:
            try:
                self.open_trade_site(url)
                return
            except Exception:
                pass
        try:
            QDesktopServices.openUrl(QUrl(url))
        except Exception as e:
            self.summary.append(f"\nCouldn't open browser: {e}\n{url}")

    def _scan_image(self):
        """W3-33 v1: OCR an item screenshot into the paste box, then parse —
        the same pipeline as Ctrl+C, so 'Open trade search' ties it straight
        to the official trade site."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Pick an item screenshot", "data_engine/snapshots",
            "Images (*.png *.jpg *.jpeg)")
        if not path:
            return
        self.summary.setHtml("<i>Scanning screenshot…</i>")

        def _work():
            text, err = "", None
            try:
                import pytesseract
                from PIL import Image
                img = Image.open(path).convert("L")
                img = img.resize((img.width * 2, img.height * 2))
                img = img.point(lambda p: 255 if p > 110 else 0)
                text = pytesseract.image_to_string(img)
            except ImportError:
                err = ("OCR needs:  pip install pytesseract pillow  plus the "
                       "Tesseract program (tesseract-ocr.github.io). The "
                       "AI-vision scanner (no install) is next on the roadmap "
                       "(W3-33).")
            except Exception as e:
                err = f"Scan failed: {e}"
            from PyQt6.QtCore import QTimer
            def _done():
                if err:
                    self.summary.setHtml(err)
                elif text.strip():
                    self.input.setPlainText(text)
                    self._parse()
                else:
                    self.summary.setHtml("No readable text found — crop "
                                         "tighter to the tooltip and retry.")
            QTimer.singleShot(0, _done)
        threading.Thread(target=_work, daemon=True).start()

    # -- W3-22: saved searches -------------------------------------------------
    def _saved(self):
        s = self.config.get("saved_searches")
        return s if isinstance(s, list) else []

    def _persist_saved(self, items):
        self.config["saved_searches"] = items
        try:
            from gui_overlay.mirror_window import save_config
            save_config(self.config)
        except Exception:
            pass
        self._reload_saved()

    def _reload_saved(self):
        if not hasattr(self, "saved_combo"):
            return
        self.saved_combo.blockSignals(True)
        self.saved_combo.clear()
        self.saved_combo.addItem("— saved searches —", None)
        for s in self._saved():
            self.saved_combo.addItem(s.get("name", "?"), s)
        self.saved_combo.blockSignals(False)

    def _save_search(self):
        text = self.input.toPlainText().strip()
        if not text:
            self.summary.setPlainText("Paste an item first, then save it as a search.")
            return
        info = _parse_item_text(text)
        default = info.get("name") or info.get("base") or "search"
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Save search", "Name:",
                                        text=default)
        if not (ok and name.strip()):
            return
        items = [s for s in self._saved() if s.get("name") != name.strip()]
        items.append({"name": name.strip(), "text": text,
                      "league": (self.league.currentText() or "Standard")})
        self._persist_saved(items)
        self.summary.append(f"\nSaved search '{name.strip()}'.")

    def _load_search(self, _idx):
        s = self.saved_combo.currentData()
        if not s:
            return
        self.input.setPlainText(s.get("text", ""))
        if s.get("league"):
            self.league.setCurrentText(s["league"])
        self._parse()

    def _delete_search(self):
        s = self.saved_combo.currentData()
        if not s:
            return
        self._persist_saved([x for x in self._saved()
                             if x.get("name") != s.get("name")])
        self.summary.append(f"\nDeleted search '{s.get('name')}'.")


class CraftingTab(QWidget):
    """A plain-language crafting planner. Describe what you want; Kalandra lays out
    the realistic path (mod groups, where to source the base, what tier to aim
    for) and links the deterministic Craft of Exile simulator for probabilities.
    No game automation."""

    def __init__(self, parent=None, brain_provider=None, ask_ai=None):
        super().__init__(parent)
        self._brain = brain_provider
        self.ask_ai = ask_ai      # overlay.ask_ai_text(text, on_reply) — W3-13
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
        # The structured, price-annotated plan shows IMMEDIATELY (W3-13);
        # the AI brain (when connected) then refines it in place.
        base_plan = _offline_craft_guidance(goal, LAST_ECON_ROWS or None)
        self.out.setPlainText(base_plan)
        if callable(self.ask_ai):
            self.out.append("\n──────────\nAsking the Orb for a tailored "
                            "step-by-step refinement…")
            prompt = (
                "You are a Path of Exile 2 crafting advisor. Refine this draft "
                "plan into a concrete, numbered step-by-step for the goal. Use "
                "ONLY real PoE2 mechanics (currency orbs, essences, runes, "
                "omens, no PoE1-isms). Keep it tight; flag any step where the "
                "draft is wrong.\n\nGOAL: " + goal + "\n\nDRAFT:\n" + base_plan)

            def _on_reply(reply, error=None):
                text = (base_plan if not reply else
                        base_plan + "\n\n══════ THE ORB'S REFINEMENT ══════\n"
                        + reply)
                if error:
                    text += f"\n\n(AI unavailable: {error})"
                self._emit(text)
            try:
                self.ask_ai(prompt, _on_reply)
            except Exception as e:
                self._emit(base_plan + f"\n\n(AI unavailable: {e})")

    # marshal AI result back to UI thread
    def _emit(self, text):
        try:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.out.setPlainText(text))
        except Exception:
            self.out.setPlainText(text)


class PobLiveTab(QWidget):
    """THE actual Path of Building app, containerized in this tab (Windows
    window re-parenting: we launch your own PoB install, adopt its window via
    QWindow.fromWinId, and it lives here). Use PoB's own import to pull
    updated characters from GGG; every build you SAVE in PoB is noticed by
    the file-watcher and offered for hot-reload as your active character."""

    def __init__(self, parent=None, config=None, on_build_saved=None):
        super().__init__(parent)
        self.config = config if isinstance(config, dict) else {}
        self.on_build_saved = on_build_saved   # overlay.load_build_from_file
        self._proc = None
        self._container = None
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        head = QLabel("Path of Building — live")
        head.setStyleSheet(f"color:{GOLD};font-size:18px;font-weight:bold;")
        row.addWidget(head)
        row.addStretch()
        self.embed_btn = QPushButton("Launch && embed PoB here")
        self.embed_btn.setProperty("gem", "emerald")
        self.embed_btn.clicked.connect(self._launch_embed)
        row.addWidget(self.embed_btn)
        ext = QPushButton("Launch external ↗")
        ext.clicked.connect(lambda: self._launch(embed=False))
        row.addWidget(ext)
        root.addLayout(row)
        self.status = QLabel("PoB opens INSIDE this tab. Import your GGG "
                             "characters with PoB's own importer; saving a "
                             "build there auto-offers it to Kalandra.")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color:{MUTED};font-size:11px;")
        root.addWidget(self.status)
        self.host = QVBoxLayout()
        root.addLayout(self.host, 1)
        # hot-reload watcher on the PoB builds folder
        try:
            from PyQt6.QtCore import QFileSystemWatcher
            import os
            d = self.config.get("pob_builds_dir") or ""
            if d and os.path.isdir(d):
                self._watch = QFileSystemWatcher([d])
                self._watch.directoryChanged.connect(self._builds_changed)
        except Exception:
            pass

    EXE_KEY = "pob_exe"
    DIR_KEY = "pob_install_dir"
    TITLE_MATCH = "Path of Building"
    EXE_CANDS = ("Path of Building.exe", "PathOfBuilding.exe",
                 "PathOfBuilding-PoE2.exe")

    def _pob_exe(self):
        import os
        exe = self.config.get(self.EXE_KEY) or ""
        if not exe:
            d = self.config.get(self.DIR_KEY) or ""
            for cand in self.EXE_CANDS:
                p = os.path.join(d, cand)
                if d and os.path.exists(p):
                    exe = p
                    break
        if not (exe and os.path.exists(exe)):
            from PyQt6.QtWidgets import QFileDialog
            exe, _ = QFileDialog.getOpenFileName(
                self, f"Locate {self.TITLE_MATCH}", "", "Programs (*.exe)")
            if exe:
                self.config[self.EXE_KEY] = exe
                # Keep the install dir in sync so the mirror's Character
                # Selector ("Load my saved PoB builds") scans THIS install's
                # Builds folder — one PoB, one truth.
                if not self.config.get(self.DIR_KEY):
                    self.config[self.DIR_KEY] = os.path.dirname(exe)
                try:
                    from gui_overlay.mirror_window import save_config
                    save_config(self.config)
                except Exception:
                    pass
        return exe if exe and os.path.exists(exe) else None

    def _launch(self, embed=True):
        exe = self._pob_exe()
        if not exe:
            self.status.setText("PoB not found — set its path in Settings → "
                                "Setup & Dependencies first.")
            return None
        import subprocess, os
        try:
            self._proc = subprocess.Popen([exe], cwd=os.path.dirname(exe))
            self.status.setText("PoB launching…" + (" adopting its window…"
                                                    if embed else ""))
            return self._proc
        except Exception as e:
            self.status.setText(f"Couldn't launch PoB: {e}")
            return None

    def _launch_embed(self):
        if self._launch(embed=True) is None:
            return
        from PyQt6.QtCore import QTimer
        self._tries = 0
        QTimer.singleShot(1500, self._adopt)

    def _adopt(self):
        """Find PoB's top-level window by title and re-parent it in here."""
        import sys
        if sys.platform != "win32":
            self.status.setText("Embedding is Windows-only.")
            return
        try:
            import ctypes
            u32 = ctypes.windll.user32
            found = []

            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            def _enum(hwnd, _l):
                buf = ctypes.create_unicode_buffer(256)
                u32.GetWindowTextW(hwnd, buf, 256)
                if self.TITLE_MATCH in buf.value and u32.IsWindowVisible(hwnd):
                    found.append(int(hwnd))
                return True
            u32.EnumWindows(_enum, None)
            if not found:
                self._tries += 1
                if self._tries < 20:
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(700, self._adopt)
                else:
                    self.status.setText("Couldn't find the PoB window to embed "
                                        "— it's running externally instead.")
                return
            from PyQt6.QtGui import QWindow
            self._hwnd = found[0]
            win = QWindow.fromWinId(self._hwnd)
            self._container = QWidget.createWindowContainer(win, self)
            self._container.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self._container.installEventFilter(self)
            self.host.addWidget(self._container, 1)
            self.status.setText("PoB embedded — click inside it once to give "
                                "it the keyboard. Saves are picked up "
                                "automatically.")
            self.embed_btn.setEnabled(False)
            from PyQt6.QtCore import QTimer as _QT
            _QT.singleShot(400, self._focus_pob)
        except Exception as e:
            self.status.setText(f"Embed failed (PoB still runs externally): {e}")

    def _focus_pob(self):
        """Keyboard for the embedded PoB: attach our input thread to PoB's
        thread and hand it Win32 focus (reparented foreign windows don't get
        keystrokes otherwise)."""
        hwnd = getattr(self, "_hwnd", None)
        if not hwnd:
            return
        try:
            import ctypes
            u32 = ctypes.windll.user32
            k32 = ctypes.windll.kernel32
            tgt = u32.GetWindowThreadProcessId(hwnd, None)
            cur = k32.GetCurrentThreadId()
            u32.AttachThreadInput(cur, tgt, True)
            u32.SetFocus(hwnd)
            u32.AttachThreadInput(cur, tgt, False)
        except Exception:
            pass

    def eventFilter(self, obj, ev):
        # Any click or focus landing on the container -> keyboard goes to PoB.
        if obj is getattr(self, "_container", None):
            from PyQt6.QtCore import QEvent
            if ev.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.FocusIn,
                             QEvent.Type.Enter):
                self._focus_pob()
        return super().eventFilter(obj, ev)

    def shutdown(self):
        """App is closing: leave no orphaned or mangled window behind.

        Rules (Christian, 2026-07-04): a PoB/Overlay WE launched gets a
        graceful close (WM_CLOSE to its window, terminate only as fallback);
        an EXTERNAL instance we merely adopted is NOT ours to close — its
        window is released back to the desktop untouched."""
        import sys
        hwnd = getattr(self, "_hwnd", None)
        proc = getattr(self, "_proc", None)
        hwnd_is_ours = False
        if hwnd and proc is not None and sys.platform == "win32":
            try:
                import ctypes
                u32 = ctypes.windll.user32
                pid = ctypes.c_ulong(0)
                u32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd),
                                             ctypes.byref(pid))
                hwnd_is_ours = (pid.value == proc.pid)
            except Exception:
                pass
        if proc is not None and proc.poll() is None:
            if hwnd_is_ours:
                try:
                    import ctypes
                    ctypes.windll.user32.PostMessageW(
                        ctypes.c_void_p(hwnd), 0x0010, 0, 0)   # WM_CLOSE
                except Exception:
                    pass
            try:
                proc.wait(timeout=4)
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass
        if hwnd and not hwnd_is_ours and sys.platform == "win32":
            # Adopted an external instance: hand its window back, untouched.
            try:
                import ctypes
                u32 = ctypes.windll.user32
                u32.SetParent(ctypes.c_void_p(hwnd), None)
                u32.ShowWindow(ctypes.c_void_p(hwnd), 9)       # SW_RESTORE
            except Exception:
                pass
        self._hwnd = None
        self._proc = None

    def _builds_changed(self, _path):
        import os
        d = self.config.get("pob_builds_dir") or ""
        try:
            xs = [(os.path.getmtime(os.path.join(d, f)), os.path.join(d, f))
                  for f in os.listdir(d) if f.lower().endswith(".xml")]
            if not xs:
                return
            xs.sort(reverse=True)
            newest = xs[0][1]
            if callable(self.on_build_saved):
                self.on_build_saved(newest)
                self.status.setText("Build saved in PoB → reloaded as your "
                                    f"active character: {os.path.basename(newest)}")
        except Exception:
            pass


class Overlay2LiveTab(PobLiveTab):
    """PoE Overlay 2, containerized exactly like PoB (window adoption)."""
    EXE_KEY = "overlay2_exe"
    DIR_KEY = "overlay2_dir"
    TITLE_MATCH = "PoE Overlay"
    EXE_CANDS = ("PoE Overlay.exe", "PoE-Overlay.exe", "poe-overlay.exe")


class LiveSearchTab(QWidget):
    """Set up a live trade search — INSIDE the dashboard (W3-24).

    The official PoE2 trade site loads in an embedded web view (when
    PyQt6-WebEngine is installed) so you never leave the app: build the
    search, flip it to 'Live', and it chimes on matches while you play.
    When a listing matches you whisper and buy manually. No auto-buy, no
    automation — fully within GGG's ToS. Falls back to the external
    browser when the embedded view is unavailable."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.web = None
        self._build_ui()

    def _trade_url(self):
        league = (self.league.currentText() or "Standard").strip()
        from urllib.parse import quote
        return f"https://www.pathofexile.com/trade2/search/poe2/{quote(league)}"

    def _build_ui(self):
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        head = QLabel("Live Search")
        head.setStyleSheet(f"color:{GOLD};font-size:18px;font-weight:bold;")
        row.addWidget(head)
        row.addSpacing(14)
        row.addWidget(QLabel("League:"))
        self.league = QComboBox(); self.league.setEditable(True)
        self.league.addItems(["Rise of the Abyssal", "Dawn of the Hunt", "Standard",
                              "Hardcore"])
        row.addWidget(self.league, 1)
        go_btn = QPushButton("Open here")
        go_btn.setProperty("gem", "emerald")
        go_btn.setToolTip("Load the trade site inside this tab.")
        go_btn.clicked.connect(self._open_embedded)
        row.addWidget(go_btn)
        ext_btn = QPushButton("Browser ↗")
        ext_btn.setToolTip("Open in your external browser instead.")
        ext_btn.clicked.connect(self._open_external)
        row.addWidget(ext_btn)
        root.addLayout(row)

        hint = QLabel("Build your search → flip results to 'Live' → the site chimes "
                      "on each match; you whisper and buy by hand (ToS-clean — "
                      "Kalandra never logs in, queries, or buys for you).")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # The embedded view (same crash-safe lazy pattern as WebTab).
        self.web_holder = QVBoxLayout()
        root.addLayout(self.web_holder, 1)
        if not WEBENGINE_AVAILABLE:
            note = QFrame(); note.setObjectName("card")
            nl = QVBoxLayout(note)
            t = QLabel("Embedded browser not installed")
            t.setStyleSheet(f"color:{GOLD};font-size:14px;font-weight:bold;")
            nl.addWidget(t)
            m = QLabel("The trade site will open in your external browser.\n"
                       "To keep it inside this tab:  pip install PyQt6-WebEngine")
            m.setStyleSheet(f"color:{MUTED};")
            nl.addWidget(m)
            self.web_holder.addWidget(note)
            self.web_holder.addStretch()

    def _open_embedded(self):
        if not WEBENGINE_AVAILABLE:
            self._open_external()
            return
        try:
            if self.web is None:
                from PyQt6.QtWebEngineWidgets import QWebEngineView
                self.web = QWebEngineView()
                self.web_holder.addWidget(self.web, 1)
            self.web.setUrl(QUrl(self._trade_url()))
        except Exception:
            # Broken WebEngine install must never take the tab down.
            self.web = None
            self._open_external()

    def _open_external(self):
        try:
            QDesktopServices.openUrl(QUrl(self._trade_url()))
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
    ("Companion", True),
    ("Terminal", True),
    ("Build (PoB)", True),
    ("Build Sim", True),
    ("PoB (live)", True),
    ("PoE Overlay 2", False),
    ("Reserve / BIS", True),
    ("Issues / Changelog", True),
    ("Price Check", True),
    ("Trade Site", True),
    ("Exchange", True),
    ("Crafting", True),
    ("Craft Hunter", True),
    ("Filter Editor", True),
    ("Live Search", True),
    ("Grind Tracker", True),
    ("Craft of Exile", True),
    ("FilterBlade", True),
    ("poe.ninja", True),
]
_DASHBOARD_TAB_DEFAULTS = dict(DASHBOARD_TABS)


# Category layout for the dashboard (Christian, 2026-07-04): top-level
# group tabs, tools nested inside. Unknown/custom labels land in "Other".
TAB_GROUPS = [
    ("🦉 Companion", ["Companion", "Terminal"]),
    ("⚔ Build Planning", ["Build (PoB)", "Build Sim", "PoB (live)",
                           "PoE Overlay 2", "Death Review"]),
    ("💰 Items & Trading", ["Price Check", "Trade Site", "Live Search",
                             "Exchange", "Reserve / BIS", "poe.ninja"]),
    ("🔨 Crafting", ["Crafting", "Craft Hunter", "Craft of Exile"]),
    ("📊 Loot & Filters", ["Filter Editor", "FilterBlade", "Grind Tracker"]),
    ("🛠 Other", []),
]
_GROUP_OF = {lbl: g for g, lbls in TAB_GROUPS for lbl in lbls}
_GROUP_ORDER = [g for g, _ in TAB_GROUPS]


class GroupedTabs(QWidget):
    """Two-level tabs that quack like the QTabWidget the rest of the code
    was written against: addTab / count / widget / tabText / currentIndex /
    setCurrentIndex / setCurrentWidget / currentChanged all speak FLAT
    indices, while the UI shows category tabs with the tools nested inside.
    Indices are stable (assigned in add order), so the lazy web-tab loader
    and every other consumer keeps working unchanged."""

    currentChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.outer = QTabWidget()
        lay.addWidget(self.outer)
        self._flat = []        # [(widget, label)] in add order = flat index
        self._inner = {}       # group name -> inner QTabWidget
        self.outer.currentChanged.connect(lambda _i: self._announce())

    def _group_for(self, label):
        return _GROUP_OF.get(label, "🛠 Other")

    def _inner_for(self, gname):
        if gname in self._inner:
            return self._inner[gname]
        inner = QTabWidget()
        inner.currentChanged.connect(lambda _i: self._announce())
        # Insert the group page at its canonical position among those present.
        want = _GROUP_ORDER.index(gname) if gname in _GROUP_ORDER else 999
        pos = 0
        for i in range(self.outer.count()):
            g = self.outer.tabText(i)
            have = _GROUP_ORDER.index(g) if g in _GROUP_ORDER else 999
            if have < want:
                pos = i + 1
        self.outer.insertTab(pos, inner, gname)
        self._inner[gname] = inner
        return inner

    def _announce(self):
        idx = self.currentIndex()
        if idx >= 0:
            self.currentChanged.emit(idx)

    # ---- QTabWidget-compatible surface (flat indices) ----
    def addTab(self, w, label):
        self._inner_for(self._group_for(label)).addTab(w, str(label))
        self._flat.append((w, str(label)))
        return len(self._flat) - 1

    def count(self):
        return len(self._flat)

    def widget(self, i):
        return self._flat[i][0] if 0 <= i < len(self._flat) else None

    def tabText(self, i):
        return self._flat[i][1] if 0 <= i < len(self._flat) else ""

    def currentIndex(self):
        inner = self.outer.currentWidget()
        if not isinstance(inner, QTabWidget):
            return -1
        w = inner.currentWidget()
        for i, (fw, _l) in enumerate(self._flat):
            if fw is w:
                return i
        return -1

    def setCurrentWidget(self, w):
        for gname, inner in self._inner.items():
            if inner.indexOf(w) >= 0:
                self.outer.setCurrentWidget(inner)
                inner.setCurrentWidget(w)
                return

    def setCurrentIndex(self, i):
        w = self.widget(i)
        if w is not None:
            self.setCurrentWidget(w)

    def tabBar(self):
        inner = self.outer.currentWidget()
        return inner.tabBar() if isinstance(inner, QTabWidget) \
            else self.outer.tabBar()

    def current_tab_center_in(self, ref):
        """Center of the CURRENT inner tab header, mapped into `ref` coords
        (the owl's arrow aims with this)."""
        inner = self.outer.currentWidget()
        if not isinstance(inner, QTabWidget):
            return None
        bar = inner.tabBar()
        r = bar.tabRect(inner.currentIndex())
        return bar.mapTo(ref, r.center())


class KalandraDashboard(KalandraFrameWindow):
    def __init__(self, config=None, pob_sim=None, accounts=None, parent=None,
                 issues=None, build_provider=None, ask_ai=None,
                 on_build_saved=None):
        try:
            from version import KALANDRA_VERSION as _KV0
        except Exception:
            _KV0 = "0.0.0"
        super().__init__(f"KALANDRA v{_KV0} — DASHBOARD", parent)
        self.config = config or {}
        self.pob_sim = pob_sim
        self.accounts = accounts
        self.issues = issues
        self.build_provider = build_provider
        self.ask_ai = ask_ai          # overlay.ask_ai_text (thread + callback)
        self.on_build_saved = on_build_saved   # overlay.load_build_from_file
        self._web_tabs = {}          # set BEFORE any tab is added (avoids slot crash)
        self._bridge = _Bridge()
        self._bridge.buildsim_text.connect(self._set_buildsim_text)

        self.resize(1180, 760)
        self._build_ui()

    def _build_ui(self):
        root = self.body

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

        self.tabs = GroupedTabs()
        root.addWidget(self.tabs, 1)
        self._build_tab = None

        # Build all tabs first, THEN connect currentChanged, so the initial
        # signal can't fire into a half-built state. Each tab is only added if
        # the user has it enabled (Settings -> Dashboard tabs).
        if self._tab_on("Companion"):
            try:
                from gui_overlay.companion_tab import CompanionTab
                self.tabs.addTab(CompanionTab(ask_ai=self.ask_ai,
                                              config=self.config), "Companion")
            except Exception as e:
                self.tabs.addTab(_placeholder("Companion", [f"Unavailable: {e}"]),
                                 "Companion")
        if self._tab_on("Terminal"):
            try:
                self.tabs.addTab(TerminalTab(), "Terminal")
            except Exception as e:
                self.tabs.addTab(_placeholder("Terminal", [f"Terminal unavailable: {e}"]), "Terminal")
        if self._tab_on("Build (PoB)"):
            try:
                self._build_tab = BuildTab(
                    self.build_provider, config=self.config,
                    ask_ai=self.ask_ai,
                    sim_stats=(lambda: self.pob_sim.stats_summary()
                               if self.pob_sim and self.pob_sim.has_build()
                               else ""))
                self.tabs.addTab(self._build_tab, "Build (PoB)")
            except Exception as e:
                self._build_tab = None
                self.tabs.addTab(_placeholder("Build (PoB)", [f"Build view unavailable: {e}"]),
                                 "Build (PoB)")
        if self._tab_on("Build Sim"):
            self.tabs.addTab(self._build_sim_tab(), "Build Sim")
        if self._tab_on("PoB (live)"):
            try:
                self.tabs.addTab(PobLiveTab(config=self.config,
                                            on_build_saved=self.on_build_saved),
                                 "PoB (live)")
            except Exception as e:
                self.tabs.addTab(_placeholder("PoB (live)", [f"Unavailable: {e}"]),
                                 "PoB (live)")
        if self._tab_on("PoE Overlay 2"):
            try:
                self.tabs.addTab(Overlay2LiveTab(config=self.config),
                                 "PoE Overlay 2")
            except Exception as e:
                self.tabs.addTab(_placeholder("PoE Overlay 2",
                                              [f"Unavailable: {e}"]),
                                 "PoE Overlay 2")
        if self._tab_on("Reserve / BIS"):
            try:
                self.tabs.addTab(ReserveTab(config=self.config), "Reserve / BIS")
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
                self._price_tab = PriceCheckTab(config=self.config)
                self.tabs.addTab(self._price_tab, "Price Check")
            except Exception as e:
                self._price_tab = None
                self.tabs.addTab(_placeholder("Price Check", [f"Unavailable: {e}"]),
                                 "Price Check")
        self._trade_tab = None
        if self._tab_on("Trade Site"):
            try:
                self._trade_tab = TradeSiteTab()
                self._web_tabs[self.tabs.count()] = self._trade_tab
                self.tabs.addTab(self._trade_tab, "Trade Site")
            except Exception as e:
                self.tabs.addTab(_placeholder("Trade Site", [f"Unavailable: {e}"]),
                                 "Trade Site")
        # Price Check pushes searches into the full-size Trade Site tab.
        if getattr(self, "_price_tab", None) is not None and self._trade_tab is not None:
            def _open_in_trade(url):
                self._trade_tab.open_search(url)
                self.tabs.setCurrentWidget(self._trade_tab)
            self._price_tab.open_trade_site = _open_in_trade
        if self._tab_on("Exchange"):
            try:
                self.tabs.addTab(ExchangeTab(config=self.config), "Exchange")
            except Exception as e:
                self.tabs.addTab(_placeholder("Currency Exchange", [f"Unavailable: {e}"]),
                                 "Exchange")
        if self._tab_on("Crafting"):
            try:
                self.tabs.addTab(CraftingTab(ask_ai=self.ask_ai), "Crafting")
            except Exception as e:
                self.tabs.addTab(_placeholder("Crafting Planner", [f"Unavailable: {e}"]),
                                 "Crafting")
        if self._tab_on("Craft Hunter"):
            try:
                from gui_overlay.craft_hunter import CraftHunterTab
                self._craft_hunter_tab = CraftHunterTab(config=self.config)
                self.tabs.addTab(self._craft_hunter_tab, "Craft Hunter")
            except Exception as e:
                self.tabs.addTab(_placeholder("Craft Hunter",
                                              [f"Unavailable: {e}"]),
                                 "Craft Hunter")
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

        if self._tab_on("Grind Tracker"):
            try:
                from gui_overlay.grind_tab import GrindTab
                self.tabs.addTab(GrindTab(config=self.config), "Grind Tracker")
            except Exception as e:
                self.tabs.addTab(_placeholder("Grind Tracker",
                                              [f"Unavailable: {e}"]),
                                 "Grind Tracker")

        if self._tab_on("Death Review"):
            try:
                from gui_overlay.death_tab import DeathReviewTab
                self.tabs.addTab(DeathReviewTab(config=self.config,
                                                ask_ai=self.ask_ai),
                                 "Death Review")
            except Exception as e:
                self.tabs.addTab(_placeholder("Death Review",
                                              [f"Unavailable: {e}"]),
                                 "Death Review")

        for label, url in [
            ("Craft of Exile", "https://www.craftofexile.com/"),
            ("FilterBlade", "https://www.filterblade.xyz/"),
            ("poe.ninja", "https://poe.ninja/poe2"),
        ]:
            if self._tab_on(label):
                wt = WebTab(url)
                self._web_tabs[self.tabs.count()] = wt
                self.tabs.addTab(wt, label)

        # User-defined tabs (Settings -> Custom tabs): a website in a contained
        # browser (like poe.ninja) or a program adopted into the tab (like
        # PoB). Config: custom_tabs = [{name, kind: web|app, url|exe}].
        import re as _re
        for ct in (self.config.get("custom_tabs") or []):
            try:
                name = (ct.get("name") or "Custom").strip()[:24] or "Custom"
                if ct.get("kind") == "web" and ct.get("url"):
                    wt = WebTab(ct["url"])
                    self._web_tabs[self.tabs.count()] = wt
                    self.tabs.addTab(wt, name)
                elif ct.get("kind") == "app" and ct.get("exe"):
                    import os as _os
                    slug = "custom_" + _re.sub(r"\W+", "_", name.lower())
                    self.config.setdefault(slug + "_exe", ct["exe"])
                    base = _os.path.basename(ct["exe"])
                    cls = type("CustomAppTab_" + slug, (PobLiveTab,), {
                        "EXE_KEY": slug + "_exe",
                        "DIR_KEY": slug + "_dir",
                        "TITLE_MATCH": _os.path.splitext(base)[0],
                        "EXE_CANDS": (base,),
                    })
                    self.tabs.addTab(cls(config=self.config), name)
            except Exception as e:
                self.tabs.addTab(_placeholder(ct.get("name", "Custom"),
                                              [f"Custom tab failed: {e}"]),
                                 ct.get("name", "Custom"))

        if self.tabs.count() == 0:
            self.tabs.addTab(_placeholder("No tabs enabled", [
                "You've hidden every dashboard tab.",
                "Re-enable some in Settings -> Dashboard tabs."]), "Dashboard")

        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Kalandra's owl (the mirror's bottom decoration, now a guide): perches
        # in the corner and walks the user through each tab in chat bubbles.
        # Purely additive - if the art or module is missing, no owl, no crash.
        try:
            from gui_overlay.owl_guide import OwlGuide
            self._owl_guide = OwlGuide(self, self.tabs, config=self.config)
        except Exception:
            self._owl_guide = None

    def _tab_on(self, label):
        prefs = (self.config or {}).get("dashboard_tabs", {}) or {}
        if not prefs:
            # Defensive: if this dashboard was built with a config object that
            # missed the user's saved toggles, the file on disk is the truth.
            try:
                from gui_overlay.mirror_window import load_config
                prefs = load_config().get("dashboard_tabs", {}) or {}
            except Exception:
                prefs = {}
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
        up = QPushButton("Suggest upgrades (AI)")
        up.setProperty("gem", "diamond")
        up.setToolTip("The Orb reads your loaded build + live sim numbers and "
                      "proposes concrete upgrades (gear, gems, passives). W3-11.")
        up.clicked.connect(self._suggest_upgrades)
        brow.addWidget(up)
        setpob = QPushButton("Set PoB folder…")
        setpob.setProperty("gem", "sapphire")
        setpob.setToolTip("Point the sim at your Path of Building install — "
                          "the folder that contains HeadlessWrapper.lua (or "
                          "its src/ subfolder does).")
        setpob.clicked.connect(self._set_pob_folder)
        brow.addWidget(setpob)
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

    # -- W3-11: the AI upgrade guide ------------------------------------------
    def _suggest_upgrades(self):
        if not callable(self.ask_ai):
            self._bridge.buildsim_text.emit(
                "Connect an AI brain (Settings) to get upgrade guidance.")
            return
        view = {}
        try:
            view = self.build_provider() if self.build_provider else {}
        except Exception as e:
            view = {"error": str(e)}
        if not view.get("loaded"):
            self._bridge.buildsim_text.emit(
                "Load a character first (green medallion) — then I can "
                "suggest upgrades against its real stats.")
            return
        self._bridge.buildsim_text.emit(
            "The Orb is studying your build for upgrade paths…")
        prompt = (
            "You are a Path of Exile 2 build advisor. Based on this ACTUAL "
            "parsed build (and live sim numbers when present), propose the "
            "3-5 highest-impact upgrades. For each: WHAT to change (exact "
            "slot/gem/passive), WHY (which weakness it fixes), and a rough "
            "COST bracket. Use only real PoE2 mechanics; prefer fixing "
            "glaring defensive holes before damage. Format as a numbered "
            "list.\n\nBUILD:\n" + (view.get("summary") or "")[:6000]
            + ("\n\nLIVE SIM: " + view["sim"] if view.get("sim") else ""))

        def _on_reply(reply, error=None):
            self._bridge.buildsim_text.emit(
                ("UPGRADE GUIDE (the Orb, from your real build):\n\n" + reply)
                if reply else f"Upgrade guidance failed: {error}")
        try:
            self.ask_ai(prompt, _on_reply)
        except Exception as e:
            self._bridge.buildsim_text.emit(f"Upgrade guidance failed: {e}")

    def notify_craft_confirm(self, res, raw_text=""):
        """Used by the overlay's clipboard watcher (CH-P1): an armed in-game
        Ctrl+C was checked against the hunt targets — show the verdict in the
        Craft Hunter tab (the cursor-side toast is the overlay's job)."""
        tab = getattr(self, "_craft_hunter_tab", None)
        if tab is not None:
            try:
                tab.on_clipboard_result(res, raw_text)
            except Exception:
                pass

    def prefill_price_check(self, item_text):
        """Used by the clipboard price popup (W3-20): open the Price Check tab
        with the copied item already parsed."""
        tab = getattr(self, "_price_tab", None)
        if tab is not None:
            tab.input.setPlainText(item_text)
            try:
                tab._parse()
            except Exception:
                pass
        self.show_tab("Price Check")

    def _set_buildsim_text(self, text):
        if hasattr(self, "buildsim_label"):
            self.buildsim_label.setPlainText(text)

    def _set_pob_folder(self):
        """One-click fix for 'PoB install not found': pick the folder, we
        verify HeadlessWrapper.lua (root or src/), save pob_install_dir, and
        refresh the sim readiness message."""
        import os
        start = self.config.get("pob_install_dir") or \
            os.path.dirname(self.config.get("pob_exe") or "") or ""
        d = QFileDialog.getExistingDirectory(self, "Pick your Path of Building "
                                                   "folder", start)
        if not d:
            return
        found = None
        for cand in (d, os.path.join(d, "src")):
            if os.path.exists(os.path.join(cand, "HeadlessWrapper.lua")):
                found = d
                break
        if not found:
            self._bridge.buildsim_text.emit(
                f"That folder has no HeadlessWrapper.lua (checked {d} and its "
                f"src/). Pick the PoB install or source folder — for the "
                f"bundled copy: tools/PathOfBuildingCommunity-PathOfBuilding-"
                f"PoE2.")
            return
        self.config["pob_install_dir"] = found
        try:
            from gui_overlay.mirror_window import save_config
            save_config(self.config)
        except Exception:
            pass
        self._bridge.buildsim_text.emit(
            f"PoB folder set: {found}\nRe-run 'Refresh build stats' — if the "
            f"engine still isn't ready, 'Run self-test' will say exactly why.")

    def _on_tab_changed(self, idx):
        wt = self._web_tabs.get(idx)
        if wt is not None:
            wt.ensure_loaded()

    def shutdown_embedded(self):
        """Called by the overlay's exit path: gracefully close every
        containerized program we launched (PoB, PoE Overlay 2, custom app
        tabs) and release any adopted external windows."""
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if hasattr(w, "shutdown"):
                try:
                    w.shutdown()
                except Exception:
                    pass

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
