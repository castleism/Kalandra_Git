"""
GUI_OVERLAY/OWL_INTERVIEW.PY — the owl's first-use interview.

A gold-framed panel (same visual language as the owl's chat bubbles, arrow
finial pointing down at the owl) that walks through the questions in
core_engine.player_profile.QUESTIONS as clickable answer chips — plus one
free-text box for build history. Answers persist immediately, so quitting
halfway loses nothing; the interview resumes at the first unanswered
question next time.

The wording of the sensitive "how did those levels happen" question lives in
player_profile.py with the rest of the script — framed as calibration
("which mechanics have you driven yourself"), never judgment.
"""

import os

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from core_engine.player_profile import QUESTIONS, PlayerProfile
from gui_overlay.theme import BG2, FAINT, GOLD, GOLD_DARK, MUTED, TEXT
from gui_overlay.owl_guide import OWL_ARROW_PATH, MARGIN, OWL_W, TAIL_H

PANEL_W = 380


class OwlInterview(QWidget):
    """Perches above the owl; on_done(profile) fires when finished/dismissed."""

    def __init__(self, parent, owl, on_done=None):
        super().__init__(parent)
        self.owl = owl                    # the OwlGuide widget (for placement)
        self.on_done = on_done
        self.profile = PlayerProfile.load()
        self._arrow = QPixmap(OWL_ARROW_PATH) if os.path.exists(OWL_ARROW_PATH) else QPixmap()
        if not self._arrow.isNull():
            self._arrow = self._arrow.scaledToHeight(
                TAIL_H + 8, Qt.TransformationMode.SmoothTransformation)

        self._build_ui()
        self._qi = self._first_unanswered()
        self._show_question()
        self.show()
        self.raise_()

    # ---------------- UI ----------------
    def _build_ui(self):
        self.setFixedWidth(PANEL_W)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, TAIL_H + 12)
        lay.setSpacing(10)

        self.progress = QLabel("")
        self.progress.setStyleSheet(f"color:{FAINT};font-size:10px;")
        lay.addWidget(self.progress)

        self.question = QLabel("")
        self.question.setWordWrap(True)
        self.question.setStyleSheet(f"color:{TEXT};font-size:12px;")
        lay.addWidget(self.question)

        self.chips_box = QVBoxLayout()
        self.chips_box.setSpacing(6)
        lay.addLayout(self.chips_box)

        self.free_text = QLineEdit()
        self.free_text.setPlaceholderText("e.g. stat-stack Gemling — Rise of the Abyssal")
        self.free_text.returnPressed.connect(self._submit_free_text)
        self.free_text.hide()
        lay.addWidget(self.free_text)

        foot = QHBoxLayout()
        self.later = QPushButton("Ask me later")
        self.later.setFlat(True)
        self.later.setStyleSheet(f"color:{MUTED};font-size:10px;border:none;")
        self.later.clicked.connect(self._dismiss)
        foot.addWidget(self.later)
        foot.addStretch()
        self.skip = QPushButton("Skip question")
        self.skip.setFlat(True)
        self.skip.setStyleSheet(f"color:{MUTED};font-size:10px;border:none;")
        self.skip.clicked.connect(self._skip_question)
        foot.addWidget(self.skip)
        lay.addLayout(foot)

    def _chip(self, label, value):
        b = QPushButton(label)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            f"QPushButton {{ color:{GOLD}; background:transparent; text-align:left;"
            f" border:1px solid {GOLD_DARK}; border-radius:8px; padding:6px 12px;"
            f" font-size:11px; }}"
            f"QPushButton:hover {{ border-color:{GOLD}; background:#232b38; }}")
        b.clicked.connect(lambda _=False, v=value: self._answer(v))
        return b

    # ---------------- flow ----------------
    def _first_unanswered(self):
        for i, q in enumerate(QUESTIONS):
            if not self.profile.answered(q["id"]):
                return i
        return len(QUESTIONS)

    def _show_question(self):
        # Remove old chips COMPLETELY (take out of layout AND reparent away —
        # deleteLater alone leaves them as visible children for one event-loop
        # turn, which could cover/hide the new chips: the "question with no
        # answers" bug).
        while self.chips_box.count():
            item = self.chips_box.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        if self._qi >= len(QUESTIONS):
            self._finish()
            return
        q = QUESTIONS[self._qi]
        self.progress.setText(f"The owl is curious — {self._qi + 1} of {len(QUESTIONS)}")
        self.question.setText(q["ask"])
        added = 0
        if q.get("free_text"):
            self.free_text.show()
            self.free_text.setFocus()
            done = self._chip("That's the lot", "__submit__")
            done.clicked.disconnect()
            done.clicked.connect(self._submit_free_text)
            self.chips_box.addWidget(done)
            done.show()
            added += 1
        else:
            self.free_text.hide()
            for label, value in q.get("chips", []):
                b = self._chip(label, value)
                self.chips_box.addWidget(b)
                b.show()          # explicit: never trust auto-show timing
                added += 1
        if added == 0:
            # Belt and braces: a question must never dead-end the interview.
            b = self._chip("Continue", "__skip__")
            b.clicked.disconnect()
            b.clicked.connect(self._skip_question)
            self.chips_box.addWidget(b)
            b.show()
        try:
            from gui_overlay.log_bus import LOG_BUS
            LOG_BUS.push("GUI", f"Owl interview: question {self._qi + 1} "
                                f"({q['id']}) rendered with {added} chips.")
        except Exception:
            pass
        # Force the layout to recompute NOW and size the panel explicitly —
        # relying on deferred activation left the panel at its old (too
        # small) height, clipping the new chips out of view.
        self.setMinimumHeight(0)
        self.layout().activate()
        self.updateGeometry()
        self.resize(PANEL_W, max(self.sizeHint().height(), 160))
        self._place()
        self.raise_()

    def _answer(self, value):
        self.profile.set(QUESTIONS[self._qi]["id"], value)
        self.profile.save()
        self._qi += 1
        self._show_question()

    def _submit_free_text(self):
        text = self.free_text.text().strip()
        if text:
            self.profile.set(QUESTIONS[self._qi]["id"], text)
            self.profile.save()
        self._qi += 1
        self._show_question()

    def _skip_question(self):
        self._qi += 1
        self._show_question()

    def _finish(self):
        self.profile.mark_interview_done()
        self.profile.save()
        self.hide()
        self.deleteLater()
        if self.on_done:
            try:
                self.on_done(self.profile)
            except Exception:
                pass

    def _dismiss(self):
        """'Ask me later' — keep what we have, don't mark done."""
        self.profile.save()
        self.hide()
        self.deleteLater()
        if self.on_done:
            try:
                self.on_done(None)
            except Exception:
                pass

    # ---------------- placement + paint ----------------
    def _place(self):
        p = self.parentWidget()
        if p is None or self.owl is None:
            return
        x = self.owl.x() + self.owl.width() // 2 - self.width() // 2
        x = max(8, min(x, p.width() - self.width() - 8))
        y = self.owl.y() - self.height() - 2
        self.move(x, max(4, y))

    def resizeEvent(self, ev):
        self._place()
        super().resizeEvent(ev)

    def paintEvent(self, _ev):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        box = QRectF(1, 1, self.width() - 2, self.height() - TAIL_H - 2)
        path = QPainterPath()
        path.addRoundedRect(box, 10, 10)
        painter.fillPath(path, QColor(BG2))
        painter.setPen(QPen(QColor(GOLD_DARK), 1.6))
        painter.drawPath(path)
        if not self._arrow.isNull():
            aim_x = self.owl.x() + self.owl.width() // 2 - self.x() \
                if self.owl else self.width() // 2
            ax = max(6, min(aim_x - self._arrow.width() // 2,
                            self.width() - self._arrow.width() - 6))
            painter.drawPixmap(int(ax), int(box.bottom()) - 10, self._arrow)
