"""
GUI_OVERLAY/KALANDRA_WINDOW.PY  --  Frameless golden window chrome. (W3-02)

The Mirror-of-Kalandra window: frameless, ornate gold frame with a cut gem in
each corner, a gold title bar you can drag, and gem window controls —
ruby = close, sapphire = minimize, emerald = maximize/restore (the medallion
color language the overlay already taught the player).

Classes:
  * KalandraWindow(QWidget)  — top-level tool window with the chrome.
  * KalandraDialog(QDialog)  — modal dialog with the same chrome (exec()).
  * GemButton                — round painted gem button (used by the title bar).

Helpers (W3-06 groundwork — themed replacements for QMessageBox):
  * kinfo(parent, title, text)             — themed "OK" box.
  * kconfirm(parent, title, text) -> bool  — themed Yes/No (emerald/ruby).

Behavior notes:
  * Dragging and resizing use Qt's native startSystemMove/startSystemResize
    (smooth, multi-monitor aware, snap-assist friendly on Windows 11), with a
    manual fallback for platforms that refuse them.
  * Double-click the title bar to maximize/restore. Maximized windows drop the
    rounded corners + shadow (edge-to-edge like a normal app).
  * The chrome is OPT-OUT for content: put widgets in `self.body` (a QVBoxLayout).

Standalone demo (run on Windows to eyeball the chrome before we migrate
Settings/dashboard onto it):
    python -m gui_overlay.kalandra_window
"""

import os
import sys

from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, QSize
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QCursor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QAbstractButton, QSizePolicy,
)

try:
    from gui_overlay import theme
except ImportError:
    # Run directly (e.g. `python kalandra_window.py` from inside gui_overlay/):
    # put the repo root on the path so the package import resolves.
    import os as _os
    sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from gui_overlay import theme

SHADOW = 14          # transparent margin that holds the drop shadow
TITLE_H = 40         # title-bar height (inside the frame)
RESIZE_BORDER = 6    # resize grab zone thickness
FRAME_PAD = 8        # gap between the gold band and the content

_EDGE_TO_QT = {
    "left":        Qt.Edge.LeftEdge,
    "right":       Qt.Edge.RightEdge,
    "top":         Qt.Edge.TopEdge,
    "bottom":      Qt.Edge.BottomEdge,
    "topleft":     Qt.Edge.TopEdge | Qt.Edge.LeftEdge,
    "topright":    Qt.Edge.TopEdge | Qt.Edge.RightEdge,
    "bottomleft":  Qt.Edge.BottomEdge | Qt.Edge.LeftEdge,
    "bottomright": Qt.Edge.BottomEdge | Qt.Edge.RightEdge,
}
_EDGE_TO_CURSOR = {
    "left": Qt.CursorShape.SizeHorCursor,
    "right": Qt.CursorShape.SizeHorCursor,
    "top": Qt.CursorShape.SizeVerCursor,
    "bottom": Qt.CursorShape.SizeVerCursor,
    "topleft": Qt.CursorShape.SizeFDiagCursor,
    "bottomright": Qt.CursorShape.SizeFDiagCursor,
    "topright": Qt.CursorShape.SizeBDiagCursor,
    "bottomleft": Qt.CursorShape.SizeBDiagCursor,
}


class GemButton(QAbstractButton):
    """A round, painted gem button (no stylesheet — pure painter art)."""

    def __init__(self, gem, tooltip, parent=None, radius=9):
        super().__init__(parent)
        self.gem = gem
        self.radius = radius
        self.setToolTip(tooltip)
        d = (radius + 4) * 2
        self.setFixedSize(QSize(d, d))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        r = self.radius + (1.5 if self.underMouse() else 0)
        theme.draw_gem(p, c, r, self.gem)
        if self.underMouse():   # hover halo
            p.setPen(QPen(QColor(theme.GOLD_GLOW), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, r + 3.5, r + 3.5)
        p.end()

    def enterEvent(self, ev):
        self.update()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self.update()
        super().leaveEvent(ev)


class _KalandraChrome:
    """Mixin with everything the frameless golden chrome needs.

    Subclasses must be QWidget-based and call `_chrome_init(title)` AFTER
    their QWidget/QDialog __init__.
    """

    # -- construction -------------------------------------------------------
    def _chrome_init(self, title, closable=True, minimizable=True,
                     maximizable=True):
        self.setWindowFlags(self.windowFlags()
                            | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setWindowTitle(title)     # taskbar / alt-tab still show it
        self._drag_pos = None          # manual-move fallback
        self._chrome_title = title

        outer = QVBoxLayout(self)
        m = SHADOW + 3 + FRAME_PAD     # shadow + gold band + breathing room
        outer.setContentsMargins(m, SHADOW + 3, m, m)
        outer.setSpacing(0)

        # Title bar
        self._titlebar = QWidget(self)
        self._titlebar.setFixedHeight(TITLE_H)
        self._titlebar.setMouseTracking(True)
        tb = QHBoxLayout(self._titlebar)
        tb.setContentsMargins(10, 4, 4, 0)
        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet(
            f"color:{theme.GOLD}; font-size:15px; font-weight:bold;"
            f"letter-spacing:1px; background:transparent;")
        tb.addWidget(self._title_lbl)
        tb.addStretch()
        if minimizable:
            b = GemButton("sapphire", "Minimize", self._titlebar)
            b.clicked.connect(self.showMinimized)
            tb.addWidget(b)
        if maximizable:
            self._max_btn = GemButton("emerald", "Maximize / restore", self._titlebar)
            self._max_btn.clicked.connect(self._toggle_max)
            tb.addWidget(self._max_btn)
        if closable:
            b = GemButton("ruby", "Close", self._titlebar)
            b.clicked.connect(self.close)
            tb.addWidget(b)
        outer.addWidget(self._titlebar)

        # Content area — subclasses fill self.body
        self._content = QWidget(self)
        self._content.setMouseTracking(True)
        self.body = QVBoxLayout(self._content)
        self.body.setContentsMargins(4, 6, 4, 4)
        outer.addWidget(self._content, 1)

        theme.apply(self._content)

    # -- painting ------------------------------------------------------------
    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        full = self.rect()
        if self.isMaximized():
            # Edge-to-edge: plain plate + a slim gold top rule.
            p.fillRect(full, QColor(theme.BG0))
            p.setPen(QPen(QColor(theme.GOLD_DARK), 2))
            p.drawLine(full.topLeft(), full.topRight())
            p.end()
            return
        plate = QRectF(full).adjusted(SHADOW, SHADOW, -SHADOW, -SHADOW)
        # soft drop shadow — three fading rounded rings
        for i, alpha in ((3, 18), (2, 34), (1, 58)):
            p.setPen(QPen(QColor(0, 0, 0, alpha), i * 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(plate.adjusted(-i, -i, i, i), 14 + i, 14 + i)
        # obsidian plate
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(theme.BG0)))
        p.drawRoundedRect(plate, 12, 12)
        # the golden frame + corner gems
        theme.paint_ornate_frame(p, plate.toRect(), radius=12, gems=True)
        # engraved rule under the title bar
        y = SHADOW + 3 + TITLE_H + 2
        p.setPen(QPen(QColor(theme.GOLD_DARK), 1))
        p.drawLine(int(plate.left()) + 26, y, int(plate.right()) - 26, y)
        p.end()

    # -- window controls -------------------------------------------------------
    def _toggle_max(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self.update()

    # -- drag + resize -----------------------------------------------------------
    def _edge_at(self, pos):
        if self.isMaximized():
            return None
        # Edges live on the painted plate, not the transparent shadow margin.
        x = pos.x() - SHADOW
        y = pos.y() - SHADOW
        w = self.width() - 2 * SHADOW
        h = self.height() - 2 * SHADOW
        return theme.edge_hit_test(x, y, w, h, border=RESIZE_BORDER)

    def _in_titlebar(self, pos):
        tb = self._titlebar.geometry()
        # geometry() is in parent coords (this window) already.
        return tb.contains(pos) or (SHADOW <= pos.y() <= tb.bottom()
                                    and SHADOW <= pos.x() <= self.width() - SHADOW)

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(ev)
        pos = ev.position().toPoint()
        edge = self._edge_at(pos)
        wh = self.windowHandle()
        if edge and wh is not None:
            if not wh.startSystemResize(_EDGE_TO_QT[edge]):
                pass   # fallback below still catches movement
            ev.accept()
            return
        if self._in_titlebar(pos):
            started = bool(wh is not None and wh.startSystemMove())
            if not started:
                self._drag_pos = (ev.globalPosition().toPoint()
                                  - self.frameGeometry().topLeft())
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        pos = ev.position().toPoint()
        if self._drag_pos is not None and (ev.buttons()
                                           & Qt.MouseButton.LeftButton):
            self.move(ev.globalPosition().toPoint() - self._drag_pos)
            ev.accept()
            return
        edge = self._edge_at(pos)
        self.setCursor(QCursor(_EDGE_TO_CURSOR.get(
            edge, Qt.CursorShape.ArrowCursor)))
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._drag_pos = None
        super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        if (ev.button() == Qt.MouseButton.LeftButton
                and self._in_titlebar(ev.position().toPoint())
                and getattr(self, "_max_btn", None) is not None):
            self._toggle_max()
            ev.accept()
            return
        super().mouseDoubleClickEvent(ev)


class KalandraWindow(_KalandraChrome, QWidget):
    """Top-level golden window. Fill `self.body` with your content."""

    def __init__(self, title="Kalandra", parent=None, **chrome):
        super().__init__(parent)
        self._chrome_init(title, **chrome)


class KalandraDialog(_KalandraChrome, QDialog):
    """Modal golden dialog — use exactly like a QDialog (exec/accept/reject)."""

    def __init__(self, title="Kalandra", parent=None, **chrome):
        super().__init__(parent)
        self._chrome_init(title, **chrome)


# ---------------------------------------------------------------------------
# THE MIRROR ITSELF — the window IS a blown-up Mirror of Kalandra
# ---------------------------------------------------------------------------

class _MirrorChrome:
    """Frameless window drawn AS the mirror_of_kalandra.png art, alpha-masked
    to its exact shape. Content lives inside the glass oval; the three face
    medallions on the top arc are the window buttons (their gems are already
    the right colors in the art): RED face = close, BLUE face = minimize,
    GREEN face = maximize/restore. Drag anywhere on the gold to move; drag
    the bottom-right star rosette to resize (aspect stays locked so the
    mirror never distorts)."""

    _art = None          # class-level QPixmap cache (cropped art)

    @classmethod
    def _load_art(cls):
        if cls._art is None:
            from PyQt6.QtGui import QPixmap
            assets = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "assets")
            # Preferred: the squared frame; fallback: the original mirror.
            pm = QPixmap(os.path.join(assets, getattr(
                theme, "MIRROR_ART_FILE", "mirror_frame_square.png")))
            if pm.isNull():
                pm = QPixmap(os.path.join(assets, "mirror_of_kalandra.png"))
            if not pm.isNull():
                x, y, w, h = theme.MIRROR_ART_CROP
                cls._art = pm.copy(x, y, w, h)
            else:
                cls._art = QPixmap()   # missing art -> painted fallback
        return cls._art

    def _mirror_init(self, title):
        self.setWindowFlags(self.windowFlags()
                            | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setWindowTitle(title)
        self._mirror_title = title
        self._scaled = None            # cached scaled art
        self._hover = None             # hovered hotspot name
        self._sizing = None            # (start_global, start_size) while gripping
        self._premax = None            # geometry before maximize
        self._min_w = 520

        # Content container positioned inside the glass by _relayout().
        self._content = QWidget(self)
        self._content.setMouseTracking(True)
        self.body = QVBoxLayout(self._content)
        self.body.setContentsMargins(6, 6, 6, 6)
        theme.apply(self._content, extra=(
            f"QWidget {{ background:transparent; }}"
            f"QFrame#card {{ background:rgba(12,14,18,0.55); }}"))
        self.resize(760, int(760 / theme.MIRROR_ASPECT))

    # -- geometry ------------------------------------------------------------
    def _relayout(self):
        lay = theme.mirror_layout(self.width(), self.height())
        x, y, w, h = lay["content"]
        self._content.setGeometry(x, y, w, h)
        # Refresh caches: scaled art + shape mask.
        art = self._load_art()
        if not art.isNull():
            self._scaled = art.scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            try:
                self.setMask(self._scaled.mask())
            except Exception:
                pass   # mask is cosmetic; never let it kill the window

    def resizeEvent(self, ev):
        # Lock the aspect so the mirror never stretches.
        w = max(self._min_w, self.width())
        want_h = int(round(w / theme.MIRROR_ASPECT))
        if abs(want_h - self.height()) > 2:
            self.resize(w, want_h)     # triggers one corrective resize
            return
        self._relayout()
        super().resizeEvent(ev)

    # -- painting -------------------------------------------------------------
    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._scaled is not None and not self._scaled.isNull():
            p.drawPixmap(0, 0, self._scaled)
        else:
            # Art missing: fall back to the rectangular ornate frame.
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.fillRect(self.rect(), QColor(theme.BG0))
            theme.paint_ornate_frame(p, self.rect())
        lay = theme.mirror_layout(self.width(), self.height())
        # Title, engraved into the glass top.
        if self._mirror_title:
            p.setPen(QPen(QColor(theme.GOLD)))
            f = p.font(); f.setBold(True)
            f.setPixelSize(max(11, int(self.height() * 0.030)))
            f.setLetterSpacing(f.SpacingType.PercentageSpacing, 108)
            p.setFont(f)
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(self._mirror_title)
            p.drawText(int((self.width() - tw) / 2),
                       lay["title_y"] + fm.ascent(), self._mirror_title)
        # Hover glow ring over the medallion under the cursor.
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        glow = {"close": theme.RUBY_LIGHT, "minimize": theme.SAPPHIRE_LIGHT,
                "maximize": theme.EMERALD_LIGHT, "grip": theme.GOLD_GLOW}
        if self._hover in glow:
            src = lay["buttons"].get(self._hover) or lay["grip"]
            cx, cy, r = src
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(glow[self._hover]), 2.5))
            p.drawEllipse(QPointF(cx, cy), r * 0.92, r * 0.92)
        p.end()

    # -- interaction -----------------------------------------------------------
    def _hit(self, pos):
        return theme.mirror_hit(self.width(), self.height(),
                                pos.x(), pos.y())

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(ev)
        hit = self._hit(ev.position().toPoint())
        if hit == "close":
            self.close(); ev.accept(); return
        if hit == "minimize":
            self.showMinimized(); ev.accept(); return
        if hit == "maximize":
            self._toggle_mirror_max(); ev.accept(); return
        if hit == "grip":
            self._sizing = (ev.globalPosition().toPoint(),
                            self.size())
            ev.accept(); return
        # Anywhere else on the mirror: move the window.
        wh = self.windowHandle()
        if not (wh is not None and wh.startSystemMove()):
            self._drag_pos = (ev.globalPosition().toPoint()
                              - self.frameGeometry().topLeft())
        ev.accept()

    def mouseMoveEvent(self, ev):
        gp = ev.globalPosition().toPoint()
        if self._sizing is not None and (ev.buttons()
                                         & Qt.MouseButton.LeftButton):
            start, size0 = self._sizing
            dx = gp.x() - start.x()
            w = max(self._min_w, size0.width() + dx)
            self.resize(w, int(round(w / theme.MIRROR_ASPECT)))
            ev.accept(); return
        if getattr(self, "_drag_pos", None) is not None and \
                (ev.buttons() & Qt.MouseButton.LeftButton):
            self.move(gp - self._drag_pos)
            ev.accept(); return
        hit = self._hit(ev.position().toPoint())
        if hit != self._hover:
            self._hover = hit
            tips = {"close": "Close", "minimize": "Minimize",
                    "maximize": "Maximize / restore",
                    "grip": "Drag to resize"}
            self.setToolTip(tips.get(hit, ""))
            self.setCursor(Qt.CursorShape.PointingHandCursor if hit
                           else Qt.CursorShape.ArrowCursor)
            self.update()
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._sizing = None
        self._drag_pos = None
        super().mouseReleaseEvent(ev)

    def leaveEvent(self, ev):
        if self._hover is not None:
            self._hover = None
            self.update()
        super().leaveEvent(ev)

    def _toggle_mirror_max(self):
        """'Maximize' = grow to fit the screen while keeping the mirror's
        shape (never a distorted fullscreen rectangle)."""
        scr = self.screen() or QApplication.primaryScreen()
        if scr is None:
            return
        avail = scr.availableGeometry()
        if self._premax is not None:
            self.setGeometry(self._premax)
            self._premax = None
            return
        self._premax = self.geometry()
        w = avail.width()
        h = int(round(w / theme.MIRROR_ASPECT))
        if h > avail.height():
            h = avail.height()
            w = int(round(h * theme.MIRROR_ASPECT))
        self.setGeometry(avail.x() + (avail.width() - w) // 2,
                         avail.y() + (avail.height() - h) // 2, w, h)


class MirrorWindow(_MirrorChrome, QWidget):
    """Top-level window shaped as the Mirror of Kalandra."""

    def __init__(self, title="Kalandra", parent=None):
        super().__init__(parent)
        self._mirror_init(title)


class MirrorDialog(_MirrorChrome, QDialog):
    """Modal mirror — same shape, QDialog semantics (exec/accept/reject)."""

    def __init__(self, title="Kalandra", parent=None):
        super().__init__(parent)
        self._mirror_init(title)


# ---------------------------------------------------------------------------
# CHRISTIAN'S FRAME — nine-sliced Window.png + medallion window buttons
# ---------------------------------------------------------------------------

def _assets_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def draw_nine_slice(p, pm, w, h, src_b, dst_b):
    """Draw pixmap `pm` onto a w×h target: corners fixed, edges/center
    stretched (classic nine-slice)."""
    from PyQt6.QtCore import QRect
    sw, sh = pm.width(), pm.height()
    sb = min(src_b, sw // 3, sh // 3)
    db = dst_b
    # (dst, src) rect pairs
    pieces = [
        # corners
        (QRect(0, 0, db, db),                 QRect(0, 0, sb, sb)),
        (QRect(w - db, 0, db, db),            QRect(sw - sb, 0, sb, sb)),
        (QRect(0, h - db, db, db),            QRect(0, sh - sb, sb, sb)),
        (QRect(w - db, h - db, db, db),       QRect(sw - sb, sh - sb, sb, sb)),
        # edges
        (QRect(db, 0, w - 2 * db, db),        QRect(sb, 0, sw - 2 * sb, sb)),
        (QRect(db, h - db, w - 2 * db, db),   QRect(sb, sh - sb, sw - 2 * sb, sb)),
        (QRect(0, db, db, h - 2 * db),        QRect(0, sb, sb, sh - 2 * sb)),
        (QRect(w - db, db, db, h - 2 * db),   QRect(sw - sb, sb, sb, sh - 2 * sb)),
        # center (the glass)
        (QRect(db, db, w - 2 * db, h - 2 * db),
         QRect(sb, sb, sw - 2 * sb, sh - 2 * sb)),
    ]
    for dst, src in pieces:
        if dst.width() > 0 and dst.height() > 0:
            p.drawPixmap(dst, pm, src)


class _FrameChrome:
    """Frameless window skinned with Christian's Window.png (nine-slice, so it
    resizes freely with no distortion) and his medallion buttons top-right:
    Close (red gem), Maximize (blue gem), Minimize (green gem). Drag the gold
    border or the title strip to move; the outer rim resizes."""

    _frame_art = None
    _btn_art = None

    @classmethod
    def _load_frame(cls):
        from PyQt6.QtGui import QPixmap
        if cls._frame_art is None:
            cls._frame_art = QPixmap(os.path.join(
                _assets_dir(), theme.FRAME_ART_FILE))
            cls._btn_art = {}
            for name, fn in theme.FRAME_BTN_FILES.items():
                pm = QPixmap(os.path.join(_assets_dir(), fn))
                if not pm.isNull():
                    cls._btn_art[name] = pm
        return cls._frame_art

    def _frame_init(self, title):
        self.setWindowFlags(self.windowFlags()
                            | Qt.WindowType.FramelessWindowHint)
        self.setMouseTracking(True)
        self.setWindowTitle(title)
        self._frame_title = title
        self._hover = None
        self._drag_pos = None
        self.setMinimumSize(320, 240)
        self._load_frame()

        self._content = QWidget(self)
        self._content.setMouseTracking(True)
        self.body = QVBoxLayout(self._content)
        self.body.setContentsMargins(4, 4, 4, 4)
        theme.apply(self._content, extra="QWidget { background:transparent; }")
        self.resize(720, 560)

    # -- layout ---------------------------------------------------------------
    def _relayout(self):
        lay = theme.frame_layout(self.width(), self.height())
        x, y, w, h = lay["content"]
        self._content.setGeometry(x, y, w, h)

    def resizeEvent(self, ev):
        self._relayout()
        super().resizeEvent(ev)

    # -- painting ---------------------------------------------------------------
    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        pm = self._load_frame()
        if pm is not None and not pm.isNull():
            draw_nine_slice(p, pm, self.width(), self.height(),
                            theme.FRAME_SRC_BORDER, theme.FRAME_DST_BORDER)
        else:
            p.fillRect(self.rect(), QColor(theme.BG0))
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            theme.paint_ornate_frame(p, self.rect())
        lay = theme.frame_layout(self.width(), self.height())
        # Title (top-left, ON the gold border band — dark shadow keeps it
        # readable over the celtic engraving).
        if self._frame_title:
            f = p.font(); f.setBold(True); f.setPixelSize(15)
            f.setLetterSpacing(f.SpacingType.PercentageSpacing, 106)
            p.setFont(f)
            tx, ty = lay["title"]
            by = int(ty + p.fontMetrics().ascent() / 2 - 1)
            p.setPen(QPen(QColor(0, 0, 0, 170)))
            for ox, oy in ((1, 1), (1, 0), (0, 1)):
                p.drawText(int(tx) + ox, by + oy, self._frame_title)
            p.setPen(QPen(QColor(theme.GOLD_LIGHT)))
            p.drawText(int(tx), by, self._frame_title)
        # Medallion buttons.
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rings = {"close": theme.RUBY_LIGHT, "minimize": theme.EMERALD_LIGHT,
                 "maximize": theme.SAPPHIRE_LIGHT}
        for name, (cx, cy, r) in lay["buttons"].items():
            art = (self._btn_art or {}).get(name)
            d = int(r * 2)
            if art is not None:
                p.drawPixmap(int(cx - r), int(cy - r), d, d, art)
            else:
                theme.draw_gem(p, QPointF(cx, cy), r * 0.6,
                               {"close": "ruby", "minimize": "emerald",
                                "maximize": "sapphire"}[name])
            if self._hover == name:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(rings[name]), 2.5))
                p.drawEllipse(QPointF(cx, cy), r + 2.5, r + 2.5)
        p.end()

    # -- interaction --------------------------------------------------------------
    def _hit(self, pos):
        return theme.frame_hit(self.width(), self.height(), pos.x(), pos.y())

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(ev)
        hit = self._hit(ev.position().toPoint())
        if hit == "close":
            self.close(); ev.accept(); return
        if hit == "minimize":
            self.showMinimized(); ev.accept(); return
        if hit == "maximize":
            if self.isMaximized():
                self.showNormal()
            else:
                self.showMaximized()
            ev.accept(); return
        if hit in _EDGE_TO_QT and not self.isMaximized():
            wh = self.windowHandle()
            if wh is not None:
                wh.startSystemResize(_EDGE_TO_QT[hit])
            ev.accept(); return
        if hit == "title":
            wh = self.windowHandle()
            if not (wh is not None and wh.startSystemMove()):
                self._drag_pos = (ev.globalPosition().toPoint()
                                  - self.frameGeometry().topLeft())
            ev.accept(); return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._drag_pos is not None and (ev.buttons()
                                           & Qt.MouseButton.LeftButton):
            self.move(ev.globalPosition().toPoint() - self._drag_pos)
            ev.accept(); return
        hit = self._hit(ev.position().toPoint())
        if hit != self._hover:
            self._hover = hit
            tips = {"close": "Close", "minimize": "Minimize",
                    "maximize": "Maximize / restore"}
            self.setToolTip(tips.get(hit, ""))
            self.update()
        cursors = dict(_EDGE_TO_CURSOR)
        self.setCursor(QCursor(
            cursors.get(hit, Qt.CursorShape.PointingHandCursor
                        if hit in ("close", "minimize", "maximize")
                        else Qt.CursorShape.ArrowCursor)))
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._drag_pos = None
        super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        if (ev.button() == Qt.MouseButton.LeftButton
                and self._hit(ev.position().toPoint()) == "title"):
            if self.isMaximized():
                self.showNormal()
            else:
                self.showMaximized()
            ev.accept(); return
        super().mouseDoubleClickEvent(ev)

    def leaveEvent(self, ev):
        if self._hover is not None:
            self._hover = None
            self.update()
        super().leaveEvent(ev)


class KalandraFrameWindow(_FrameChrome, QWidget):
    """Top-level window in Christian's celtic-gold frame."""

    def __init__(self, title="Kalandra", parent=None):
        super().__init__(parent)
        self._frame_init(title)


class KalandraFrameDialog(_FrameChrome, QDialog):
    """Modal dialog in the same frame (exec/accept/reject)."""

    def __init__(self, title="Kalandra", parent=None):
        super().__init__(parent)
        self._frame_init(title)


# ---------------------------------------------------------------------------
# Themed message boxes (W3-06 groundwork)
# ---------------------------------------------------------------------------

def _msg_dialog(parent, title, text, buttons):
    dlg = KalandraFrameDialog(title, parent)
    dlg.resize(430, 300)
    dlg.body.addStretch()
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(f"color:{theme.TEXT}; font-size:13px; background:transparent;")
    dlg.body.addWidget(lbl)
    row = QHBoxLayout()
    row.addStretch()
    for label, gem, result in buttons:
        b = QPushButton(label)
        b.setProperty("gem", gem)
        b.clicked.connect(lambda _, r=result: dlg.done(r))
        row.addWidget(b)
    row.addStretch()
    dlg.body.addLayout(row)
    dlg.body.addStretch()
    return dlg


def kinfo(parent, title, text):
    """Themed information box (gold frame, emerald OK)."""
    _msg_dialog(parent, title, text, [("OK", "emerald", 1)]).exec()


def kconfirm(parent, title, text, yes="Yes", no="No"):
    """Themed Yes/No. Returns True on the emerald button."""
    return _msg_dialog(parent, title, text,
                       [(no, "ruby", 0), (yes, "emerald", 1)]).exec() == 1


# ---------------------------------------------------------------------------
# Standalone demo — run this on Windows to eyeball the chrome
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = KalandraFrameWindow("KALANDRA — WINDOW DEMO")
    lbl = QLabel(
        "Christian's frame, live.\n\n"
        "• Medallions top-right: red gem closes, blue maximizes,\n"
        "  green minimizes (hover for the glow ring)\n"
        "• Drag the gold border or title strip to move\n"
        "• Drag the outer rim to resize — any size, no distortion\n"
        "• Double-click the title strip to maximize/restore\n")
    lbl.setWordWrap(True)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    win.body.addStretch()
    win.body.addWidget(lbl)
    row = QHBoxLayout()
    row.addStretch()
    b1 = QPushButton("kinfo() demo")
    b1.clicked.connect(lambda: kinfo(win, "WELL MET, EXILE",
                                     "This message box wears your frame too."))
    b2 = QPushButton("kconfirm() demo")
    b2.setProperty("gem", "diamond")
    b2.clicked.connect(lambda: kinfo(
        win, "RESULT", f"You chose: <b>{kconfirm(win, 'CONFIRM', 'Sell your mirror?', 'Sell', 'Never')}</b>"))
    row.addWidget(b1)
    row.addWidget(b2)
    row.addStretch()
    win.body.addLayout(row)
    win.body.addStretch()
    win.resize(900, 700)
    win.show()
    sys.exit(app.exec())
