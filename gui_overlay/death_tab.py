"""
GUI_OVERLAY/DEATH_TAB.PY — the Death Review tab (W4-21 UI).

Front end for core_engine.death_review + obs_bridge: the overlay's watcher
captures each death (OBS replay clip + log context) while you play; this tab
is where you come afterwards. Pick an incident, scrub the final seconds
frame by frame, read the defensive audit of your CURRENT PoB build, and ask
the orb for the plain-words autopsy. The clip is a normal video file — the
folder button is there so posting it somewhere is one drag away.

All persistence is death_review's incident folders; this file is pure
presentation.
"""

import os
import threading

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QSlider, QSplitter, QTextBrowser, QVBoxLayout, QWidget,
)

from gui_overlay.theme import BG0, EMERALD, FAINT, GOLD, MUTED, TEXT


class DeathReviewTab(QWidget):
    ai_ready = pyqtSignal(str)
    obs_tested = pyqtSignal(bool, str)

    def __init__(self, parent=None, config=None, ask_ai=None):
        super().__init__(parent)
        self.config = config if config is not None else {}
        self.ask_ai = ask_ai
        self._rec = None            # selected incident dict
        self._cap = None            # cv2.VideoCapture for the scrubber
        self._frames = 0
        self._build_ui()
        self.ai_ready.connect(self._on_ai)
        self.obs_tested.connect(self._on_obs_tested)
        self._load_incidents()

    # ------------------------------------------------ UI
    def _build_ui(self):
        root = QVBoxLayout(self)
        head = QLabel("Death Review — what killed you, and what to fix")
        head.setStyleSheet(f"color:{GOLD};font-size:18px;font-weight:bold;")
        root.addWidget(head)
        sub = QLabel(
            "While the game runs, Kalandra watches the log; the moment you "
            "die it asks OBS to rewind its replay buffer into a clip. "
            "OBS setup: Tools ▸ WebSocket Server Settings (enable), and "
            "Settings ▸ Output ▸ enable the Replay Buffer.")
        sub.setStyleSheet(f"color:{MUTED};")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # -- OBS connection row ------------------------------------------
        obs = QHBoxLayout()
        obs.addWidget(QLabel("OBS websocket:"))
        self.obs_host = QLineEdit(str(self.config.get("obs_host",
                                                      "127.0.0.1")))
        self.obs_host.setFixedWidth(110)
        self.obs_port = QLineEdit(str(self.config.get("obs_port", 4455)))
        self.obs_port.setFixedWidth(60)
        self.obs_pass = QLineEdit()
        self.obs_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.obs_pass.setPlaceholderText("password (stored in OS keychain)")
        self.obs_pass.setFixedWidth(200)
        test = QPushButton("Test + save")
        test.clicked.connect(self._test_obs)
        self.obs_status = QLabel("")
        self.obs_status.setStyleSheet(f"color:{MUTED};")
        for w in (self.obs_host, QLabel(":"), self.obs_port, self.obs_pass,
                  test, self.obs_status):
            obs.addWidget(w)
        obs.addStretch()
        root.addLayout(obs)

        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)

        # -- left: incidents ----------------------------------------------
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.listw = QListWidget()
        self.listw.currentRowChanged.connect(self._pick)
        ll.addWidget(self.listw, 1)
        refresh = QPushButton("⟳ Refresh")
        refresh.clicked.connect(self._load_incidents)
        ll.addWidget(refresh)
        split.addWidget(left)

        # -- right: clip + report -----------------------------------------
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 0, 0, 0)
        self.frame_lbl = QLabel("No clip for this death.")
        self.frame_lbl.setMinimumHeight(220)
        self.frame_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.frame_lbl.setStyleSheet(
            f"background:{BG0};color:{FAINT};border:1px solid #333;")
        rl.addWidget(self.frame_lbl)
        self.scrub = QSlider(Qt.Orientation.Horizontal)
        self.scrub.setEnabled(False)
        self.scrub.valueChanged.connect(self._show_frame)
        rl.addWidget(self.scrub)

        btns = QHBoxLayout()
        self.open_btn = QPushButton("▶ Open clip")
        self.open_btn.clicked.connect(self._open_clip)
        folder_btn = QPushButton("📂 Open folder (post it later)")
        folder_btn.clicked.connect(self._open_folder)
        self.ai_btn = QPushButton("🦉 AI autopsy")
        self.ai_btn.clicked.connect(self._ai_autopsy)
        for b in (self.open_btn, folder_btn, self.ai_btn):
            btns.addWidget(b)
        btns.addStretch()
        rl.addLayout(btns)

        self.report = QTextBrowser()
        self.report.setOpenExternalLinks(True)
        self.report.setStyleSheet(f"background:{BG0};color:{TEXT};")
        rl.addWidget(self.report, 1)
        split.addWidget(right)
        split.setSizes([260, 640])

    # ------------------------------------------------ incidents
    def _load_incidents(self):
        from core_engine.death_review import recent_incidents
        self._incidents = recent_incidents()
        self.listw.clear()
        for r in self._incidents:
            stamp = r.get("stamp", "?")
            label = f"{stamp[:8]} {stamp[9:11]}:{stamp[11:13]}  — " \
                    f"{r.get('zone', '?')}" + ("  🎬" if r.get("clip") else "")
            QListWidgetItem(label, self.listw)
        if self._incidents:
            self.listw.setCurrentRow(0)
        else:
            self.report.setMarkdown(
                "_No deaths captured yet. Leave Kalandra and OBS running "
                "while you play; every death lands here automatically. "
                "(Immortality is also an acceptable outcome.)_")

    def _pick(self, row):
        self._release_cap()
        if row < 0 or row >= len(getattr(self, "_incidents", [])):
            return
        self._rec = self._incidents[row]
        self._setup_scrubber()
        self._render_report()

    # ------------------------------------------------ audit + report
    def _active_build_stats(self):
        """(stats dict, level, summary) from the ACTIVE PoB build — the audit
        always reflects the build as it is NOW, not as it was at death."""
        try:
            from core_engine.pob_bridge import KalandraPoBBridge
            path = self.config.get("active_build_path")
            if not path or not os.path.exists(path):
                return None, None, ""
            b = KalandraPoBBridge()
            xml = b.read_build_file(path)
            full = b.extract_full_build(xml)
            if not isinstance(full, dict) or full.get("error"):
                return None, None, ""
            summary = (f"{full.get('class_name', '?')} "
                       f"({full.get('ascendancy', '?')}) lvl "
                       f"{full.get('level', '?')}, main skill "
                       f"{full.get('main_skill', '?')}")
            return full.get("stats") or {}, full.get("level"), summary
        except Exception:
            return None, None, ""

    def _render_report(self):
        from core_engine.death_review import autopsy_markdown, defensive_audit
        stats, level, summary = self._active_build_stats()
        if stats is None:
            findings = []
            extra = ("\n\n_No active PoB build set — pick your character in "
                     "the overlay's selector and the audit fills in._")
        else:
            findings = defensive_audit(stats, level=level)
            extra = f"\n\n_Audited build: {summary}_" if summary else ""
        self._findings = findings
        self.report.setMarkdown(autopsy_markdown(self._rec, findings) + extra)

    # ------------------------------------------------ AI autopsy
    def _ai_autopsy(self):
        if not self._rec:
            return
        if not self.ask_ai:
            self.report.append("\n_AI is not configured — add an API key in "
                               "the overlay settings._")
            return
        from core_engine.death_review import ai_autopsy_prompt
        stats, level, summary = self._active_build_stats()
        prompt = ai_autopsy_prompt(self._rec,
                                   getattr(self, "_findings", []) or [],
                                   build_summary=summary)
        self.ai_btn.setEnabled(False)
        self.ai_btn.setText("🦉 thinking…")

        def _work():
            try:
                out = self.ask_ai(prompt) or "(no answer)"
            except Exception as e:
                out = f"AI autopsy failed: {e}"
            self.ai_ready.emit(str(out))

        threading.Thread(target=_work, daemon=True).start()

    def _on_ai(self, text):
        self.ai_btn.setEnabled(True)
        self.ai_btn.setText("🦉 AI autopsy")
        cur = self.report.toMarkdown()
        self.report.setMarkdown(cur + "\n\n---\n\n**🦉 The owl's autopsy**\n\n"
                                + text)

    # ------------------------------------------------ clip handling
    def _clip_path(self):
        c = (self._rec or {}).get("clip")
        return c if c and os.path.exists(c) else None

    def _setup_scrubber(self):
        clip = self._clip_path()
        self.scrub.setEnabled(False)
        if not clip:
            note = (self._rec or {}).get("clip_note") or ""
            self.frame_lbl.setText("No clip for this death."
                                   + (f"\n{note}" if note else ""))
            self.frame_lbl.setPixmap(QPixmap())
            return
        try:
            import cv2
            self._cap = cv2.VideoCapture(clip)
            self._frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if self._frames > 1:
                self.scrub.setRange(0, self._frames - 1)
                self.scrub.setEnabled(True)
                self.scrub.setValue(max(0, self._frames - 2))  # near the end
            else:
                self._show_first_frame_fallback()
        except Exception:
            self.frame_lbl.setText("Clip saved — scrubbing needs "
                                   "opencv-python; use ▶ Open clip instead.")

    def _show_frame(self, idx):
        if not self._cap:
            return
        try:
            import cv2
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ok, frame = self._cap.read()
            if not ok:
                return
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, _ = frame.shape
            img = QImage(frame.data, w, h, 3 * w, QImage.Format.Format_RGB888)
            self.frame_lbl.setPixmap(QPixmap.fromImage(img).scaled(
                self.frame_lbl.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        except Exception:
            pass

    def _show_first_frame_fallback(self):
        self._show_frame(0)

    def _open_clip(self):
        clip = self._clip_path()
        if clip:
            try:
                os.startfile(clip)                     # noqa — Windows
            except Exception:
                pass

    def _open_folder(self):
        if not self._rec:
            return
        from core_engine.death_review import DEATHS_DIR
        d = os.path.join(DEATHS_DIR, self._rec.get("stamp", ""))
        target = d if os.path.isdir(d) else DEATHS_DIR
        try:
            os.startfile(target)                       # noqa — Windows
        except Exception:
            pass

    def _release_cap(self):
        try:
            if self._cap is not None:
                self._cap.release()
        except Exception:
            pass
        self._cap = None

    # ------------------------------------------------ OBS settings
    def _test_obs(self):
        host = self.obs_host.text().strip() or "127.0.0.1"
        try:
            port = int(self.obs_port.text().strip() or 4455)
        except ValueError:
            port = 4455
        pw = self.obs_pass.text()
        self.config["obs_host"], self.config["obs_port"] = host, port
        try:                                           # persist non-secret bits
            from gui_overlay.mirror_window import save_config
            save_config(self.config)
        except Exception:
            pass
        if pw:                                         # secret -> OS keychain
            try:
                import keyring
                keyring.set_password("KalandraOverlay", "obs_websocket", pw)
            except Exception:
                pass
        self.obs_status.setText("testing…")

        def _work():
            try:
                from core_engine.obs_bridge import obs_status
                if not pw:
                    try:
                        import keyring
                        saved = keyring.get_password("KalandraOverlay",
                                                     "obs_websocket")
                    except Exception:
                        saved = None
                else:
                    saved = pw
                ok, msg = obs_status(host, port, saved)
            except Exception as e:
                ok, msg = False, str(e)
            self.obs_tested.emit(ok, msg)

        threading.Thread(target=_work, daemon=True).start()

    def _on_obs_tested(self, ok, msg):
        self.obs_status.setText(("🟢 " if ok else "🔴 ") + msg)
        self.obs_status.setStyleSheet(
            f"color:{EMERALD};" if ok else "color:#e06060;")
