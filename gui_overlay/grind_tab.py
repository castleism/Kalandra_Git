"""
GUI_OVERLAY/GRIND_TAB.PY — the Grind Tracker tab (W4-11 UI).

Front end for core_engine.grind_tracker: snapshot what you're running
(tablets/waystones WITH their mods), time your runs, log what they paid,
and watch per-loadout chaos/hour and per-mod return correlations build up.
Rates for valuing income come live from the economy provider (poe.ninja)
with a manual fallback, so the numbers mean something.

All persistence is the tracker's SQLite; this file is pure presentation.
"""

import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from gui_overlay.theme import BG0, EMERALD, FAINT, GOLD, MUTED, TEXT


def _mk_table(cols):
    t = QTableWidget(0, len(cols))
    t.setHorizontalHeaderLabels(cols)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    return t


class GrindTab(QWidget):
    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.config = config or {}
        self._tracker = None
        self._active_run_start = None
        self._active_loadout = None
        self._rates = {}
        self._build_ui()
        self._refresh_loadouts()
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._update_timer)

    def _get_tracker(self):
        if self._tracker is None:
            try:
                from core_engine.grind_tracker import GrindTracker
                self._tracker = GrindTracker()
            except Exception:
                self._tracker = False
        return self._tracker or None

    # ------------------------------------------------ UI
    def _build_ui(self):
        root = QVBoxLayout(self)
        head = QLabel("Grind Tracker")
        head.setStyleSheet(f"color:{GOLD};font-size:18px;font-weight:bold;")
        root.addWidget(head)
        root.addWidget(QLabel(
            "Snapshot a loadout (one item per line: name | mod; mod; mod), "
            "time your runs, log the returns. Per-mod numbers are "
            "correlations from YOUR runs — they firm up as data grows."))

        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)

        # Left: snapshot + run controls
        left = QWidget(); ll = QVBoxLayout(left)
        self.loadout_name = QLineEdit()
        self.loadout_name.setPlaceholderText("Loadout name — e.g. 'juiced breach T15'")
        ll.addWidget(self.loadout_name)
        self.items_box = QPlainTextEdit()
        self.items_box.setPlaceholderText(
            "Breach Tablet x4 | 23% increased Quantity; Area contains 2 Breaches\n"
            "Waystone T15 x10 | 40% increased Rarity")
        self.items_box.setStyleSheet(f"background:{BG0};color:{TEXT};"
                                     "font-family:Consolas,monospace;font-size:11px;")
        ll.addWidget(self.items_box, 1)
        snap = QPushButton("Snapshot loadout")
        snap.setProperty("gem", "emerald")
        snap.clicked.connect(self._snapshot)
        ll.addWidget(snap)

        ll.addWidget(self._hline("Runs"))
        lrow = QHBoxLayout()
        lrow.addWidget(QLabel("Loadout:"))
        self.loadout_pick = QComboBox()
        lrow.addWidget(self.loadout_pick, 1)
        ll.addLayout(lrow)
        self.run_btn = QPushButton("▶ Start run")
        self.run_btn.clicked.connect(self._toggle_run)
        ll.addWidget(self.run_btn)
        self.timer_lbl = QLabel("")
        self.timer_lbl.setStyleSheet(f"color:{EMERALD};font-size:12px;")
        ll.addWidget(self.timer_lbl)
        self.income_box = QLineEdit()
        self.income_box.setPlaceholderText(
            "Run income — e.g. 'divine 0.4, chaos 55, exalted 12'")
        ll.addWidget(self.income_box)
        hint = QLabel("Income is valued via live poe.ninja rates when "
                      "available (chaos-equivalent).")
        hint.setStyleSheet(f"color:{FAINT};font-size:10px;")
        ll.addWidget(hint)
        split.addWidget(left)

        # Right: results
        right = QWidget(); rl = QVBoxLayout(right)
        rl.addWidget(self._hline("Loadout results"))
        self.stats_table = _mk_table(["Loadout", "Runs", "Total (c)",
                                      "Per run (c)", "Per hour (c)"])
        rl.addWidget(self.stats_table, 1)
        rl.addWidget(self._hline("Per-mod returns (correlation, best first)"))
        self.mods_table = _mk_table(["Mod", "Avg per run (c)", "Runs"])
        rl.addWidget(self.mods_table, 1)
        refresh = QPushButton("Refresh results")
        refresh.clicked.connect(self._refresh_results)
        rl.addWidget(refresh)
        split.addWidget(right)
        split.setSizes([380, 560])

    def _hline(self, text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{GOLD};font-weight:bold;font-size:12px;"
                          f"border-bottom:1px solid {MUTED};padding:4px 0;")
        return lab

    # ------------------------------------------------ parsing helpers
    @staticmethod
    def parse_items(text):
        """'Name x4 | mod; mod' per line -> [{'name','qty','mods'}].
        Forgiving: no pipe = no mods; no xN = qty 1."""
        out = []
        for line in str(text or "").splitlines():
            line = line.strip()
            if not line:
                continue
            name_part, _, mods_part = line.partition("|")
            name = name_part.strip()
            qty = 1
            low = name.lower()
            if " x" in low:
                head, _, tail = name.rpartition(" x")
                if tail.strip().isdigit():
                    name, qty = head.strip(), int(tail.strip())
            mods = [m.strip() for m in mods_part.split(";") if m.strip()]
            if name:
                out.append({"name": name, "qty": qty, "mods": mods})
        return out

    @staticmethod
    def parse_income(text):
        """'divine 0.4, chaos 55' -> [('divine', 0.4), ('chaos', 55.0)]."""
        out = []
        for part in str(text or "").replace(";", ",").split(","):
            bits = part.strip().split()
            if len(bits) >= 2:
                try:
                    out.append((bits[0].lower(), float(bits[-1])))
                except Exception:
                    continue
        return out

    # ------------------------------------------------ actions
    def _snapshot(self):
        gt = self._get_tracker()
        if not gt:
            self.timer_lbl.setText("Tracker unavailable.")
            return
        items = self.parse_items(self.items_box.toPlainText())
        if not items:
            self.timer_lbl.setText("Describe at least one item first.")
            return
        league = self.config.get("league") or "Standard"
        lid = gt.snapshot(self.loadout_name.text() or "loadout", items,
                          league=league)
        self.timer_lbl.setText(f"Loadout saved (#{lid}).")
        self._refresh_loadouts()

    def _refresh_loadouts(self):
        gt = self._get_tracker()
        self.loadout_pick.clear()
        if not gt:
            return
        try:
            with gt._conn() as c:
                rows = c.execute("SELECT id, name FROM loadouts "
                                 "ORDER BY id DESC LIMIT 50").fetchall()
            for lid, name in rows:
                self.loadout_pick.addItem(f"#{lid} {name}", lid)
        except Exception:
            pass

    def _toggle_run(self):
        if self._active_run_start is None:
            lid = self.loadout_pick.currentData()
            if lid is None:
                self.timer_lbl.setText("Snapshot / pick a loadout first.")
                return
            self._active_loadout = lid
            self._active_run_start = time.time()
            self.run_btn.setText("⏹ End run + log income")
            self._tick.start()
        else:
            minutes = (time.time() - self._active_run_start) / 60.0
            self._tick.stop()
            self._active_run_start = None
            self.run_btn.setText("▶ Start run")
            gt = self._get_tracker()
            income = self.parse_income(self.income_box.text())
            if gt and self._active_loadout is not None:
                gt.record_run(self._active_loadout, income, minutes=minutes)
                self.timer_lbl.setText(
                    f"Run logged: {minutes:.1f} min, "
                    f"{len(income)} income entr{'y' if len(income)==1 else 'ies'}.")
                self.income_box.clear()
                self._refresh_results()

    def _update_timer(self):
        if self._active_run_start is not None:
            secs = int(time.time() - self._active_run_start)
            self.timer_lbl.setText(f"Run in progress — {secs//60}:{secs%60:02d}")

    # ------------------------------------------------ results
    def _get_rates(self):
        """Live chaos-equivalent rates via the economy provider; chaos=1
        always; failure just means unpriced currencies count zero."""
        if self._rates:
            return self._rates
        rates = {"chaos": 1.0}
        try:
            from core_engine.providers import get_provider
            econ = get_provider("economy")
            league = self.config.get("league") or "Standard"
            if econ:
                fetched = econ.currency_rates(league) or {}
                for name, val in fetched.items():
                    rates[str(name).lower()] = float(val)
        except Exception:
            pass
        self._rates = rates
        return rates

    def _refresh_results(self):
        gt = self._get_tracker()
        if not gt:
            return
        rates = self._get_rates()
        try:
            with gt._conn() as c:
                loadouts = c.execute("SELECT id, name FROM loadouts "
                                     "ORDER BY id DESC LIMIT 50").fetchall()
        except Exception:
            loadouts = []
        self.stats_table.setRowCount(0)
        for lid, name in loadouts:
            st = gt.loadout_stats(lid, rates=rates)
            if st["runs"] == 0:
                continue
            r = self.stats_table.rowCount()
            self.stats_table.insertRow(r)
            for col, val in enumerate((f"#{lid} {name}", st["runs"],
                                       st["total_chaos"], st["per_run"],
                                       st["per_hour"] if st["per_hour"]
                                       is not None else "—")):
                self.stats_table.setItem(r, col, QTableWidgetItem(str(val)))
        self.mods_table.setRowCount(0)
        for row in gt.mod_returns(rates=rates):
            r = self.mods_table.rowCount()
            self.mods_table.insertRow(r)
            for col, val in enumerate((row["template"], row["avg_per_run"],
                                       row["runs"])):
                self.mods_table.setItem(r, col, QTableWidgetItem(str(val)))
