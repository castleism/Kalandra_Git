"""
GUI_OVERLAY/MIRROR_WINDOW.PY
Purpose: A premium, frameless, transparent desktop overlay window utilizing PyQt6.
Renders a bobbing Mirror of Kalandra frame with an interactive, glowing Divine Orb core.

Interactive Hotspots (Gemstone Medallions):
- Top Left  (Ruby):     Voice Channel Toggle (single click) | Text Chat window (double click)
                        -> single: records mic, transcribes, optional AI spoken reply
                        -> double: opens a typed chat to the SAME AI (same build + DB context)
- Top Middle(Sapphire): DB Sync & Scour       -> REAL poe2db crawl into the local database
- Top Right (Emerald):  Active Character Selector
- Bottom Left (Red):    Snapshot (single click) | Screen Recording (double click) -> REAL mp4
- Bottom Right (Blue):  Settings / Accounts panel

Geometry note: the mirror PNG is a SQUARE canvas holding a LANDSCAPE oval. Button
positions are stored as FRACTIONS of the square image so they always sit exactly on
the painted medallions (see MEDALLION_LAYOUT).

Backend wiring (all guarded -- the overlay still launches if a dependency is missing):
    core_engine.media_recorder  -> real screen recording
    core_engine.voice_engine    -> local Whisper STT + local TTS + cloud AI brain
    core_engine.scraper         -> real poe2db crawler
    core_engine.database_handler-> SQLite knowledge base
    core_engine.account_manager -> secure (keyring) account/integration storage
    core_engine.data_sources    -> startup freshness check
"""

import sys
import math
import os
import re          # orb-art tolerant filename matching
import json
import time
import threading
import traceback
from datetime import datetime

# ----------------------------------------------------
# 0. DIRECTORY PATH CORRECTION
# ----------------------------------------------------
try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
    os.chdir(PROJECT_ROOT)
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
except Exception:
    PROJECT_ROOT = os.getcwd()

try:
    from version import KALANDRA_VERSION
except Exception:
    KALANDRA_VERSION = "0.0.0"

try:
    from gui_overlay.log_bus import LOG_BUS
except Exception:
    try:
        from log_bus import LOG_BUS
    except Exception:
        LOG_BUS = None

# ----------------------------------------------------
# 1. ENVIRONMENT DIAGNOSTIC HANDLER
# ----------------------------------------------------
try:
    from PyQt6.QtWidgets import (
        QApplication, QWidget, QMessageBox, QInputDialog, QDialog, QVBoxLayout,
        QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QFrame,
        QComboBox, QGridLayout, QListWidget, QListWidgetItem, QTextEdit,
        QCheckBox
    )
    from PyQt6.QtCore import (Qt, QTimer, QPoint, QPointF, QRectF, QObject,
                              pyqtSignal, QUrl, QEvent)
    from PyQt6.QtGui import (
        QPainter, QColor, QPen, QBrush, QFont, QRadialGradient,
        QLinearGradient, QPixmap, QPainterPath, QDesktopServices
    )
    PYQT_AVAILABLE = True
except ImportError as e:
    PYQT_AVAILABLE = False
    IMPORT_ERROR_MSG = str(e)

ParentClass = QWidget if PYQT_AVAILABLE else object

# ----------------------------------------------------
# 1b. GUARDED BACKEND IMPORTS (overlay must launch even if these fail)
# ----------------------------------------------------
_BACKEND_ERRORS = {}

def _safe_import(label, importer):
    try:
        return importer()
    except Exception as e:  # noqa
        _BACKEND_ERRORS[label] = str(e)
        return None

KalandraDBHandler = _safe_import("database_handler",
    lambda: __import__("core_engine.database_handler", fromlist=["KalandraDBHandler"]).KalandraDBHandler)
KalandraTimeMatrix = _safe_import("time_matrix",
    lambda: __import__("core_engine.time_matrix", fromlist=["KalandraTimeMatrix"]).KalandraTimeMatrix)
ScreenRecorder = _safe_import("media_recorder",
    lambda: __import__("core_engine.media_recorder", fromlist=["ScreenRecorder"]).ScreenRecorder)
VoiceEngine = _safe_import("voice_engine",
    lambda: __import__("core_engine.voice_engine", fromlist=["VoiceEngine"]).VoiceEngine)
KalandraScraper = _safe_import("scraper",
    lambda: __import__("core_engine.scraper", fromlist=["KalandraScraper"]).KalandraScraper)
AccountManager = _safe_import("account_manager",
    lambda: __import__("core_engine.account_manager", fromlist=["AccountManager"]).AccountManager)
PoEAccount = _safe_import("poe_account",
    lambda: __import__("core_engine.poe_account", fromlist=["PoEAccount"]).PoEAccount)
PoENinja = _safe_import("poe_ninja",
    lambda: __import__("core_engine.poe_ninja", fromlist=["PoENinja"]).PoENinja)
WikiScraper = _safe_import("wiki_scraper",
    lambda: __import__("core_engine.wiki_scraper", fromlist=["WikiScraper"]).WikiScraper)
ObsidianExporter = _safe_import("obsidian_export",
    lambda: __import__("core_engine.obsidian_export", fromlist=["ObsidianExporter"]).ObsidianExporter)
KalandraPoBBridge = _safe_import("pob_bridge",
    lambda: __import__("core_engine.pob_bridge", fromlist=["KalandraPoBBridge"]).KalandraPoBBridge)
PoE2DataExtractor = _safe_import("poe2_data_extract",
    lambda: __import__("core_engine.poe2_data_extract", fromlist=["PoE2DataExtractor"]).PoE2DataExtractor)
FreshnessChecker = _safe_import("data_sources",
    lambda: __import__("core_engine.data_sources", fromlist=["FreshnessChecker"]).FreshnessChecker)
KalandraTimeMatrix = _safe_import("time_matrix",
    lambda: __import__("core_engine.time_matrix", fromlist=["KalandraTimeMatrix"]).KalandraTimeMatrix)
PoBSimulator = _safe_import("pob_sim",
    lambda: __import__("core_engine.pob_sim", fromlist=["PoBSimulator"]).PoBSimulator)
OodleExtractor = _safe_import("oodle_extractor",
    lambda: __import__("core_engine.oodle_extractor", fromlist=["OodleExtractor"]).OodleExtractor)
ReserveTracker = _safe_import("reserve_tracker",
    lambda: __import__("core_engine.reserve_tracker", fromlist=["ReserveTracker"]).ReserveTracker)
KnowledgeCorrections = _safe_import("knowledge_corrections",
    lambda: __import__("core_engine.knowledge_corrections", fromlist=["KnowledgeCorrections"]).KnowledgeCorrections)
KalandraTagGraph = _safe_import("tag_graph",
    lambda: __import__("core_engine.tag_graph", fromlist=["KalandraTagGraph"]).KalandraTagGraph)
IssueTracker = _safe_import("issue_tracker",
    lambda: __import__("core_engine.issue_tracker", fromlist=["IssueTracker"]).IssueTracker)

# Provider pages for the "Get a key" helper buttons. Pulled from the voice
# engine's provider registry so it stays in sync, with a couple of extras.
try:
    from core_engine.voice_engine import PROVIDERS as _AI_PROVIDERS
except Exception:
    _AI_PROVIDERS = {}
API_KEY_URLS = {pid: p.get("key_url", "") for pid, p in _AI_PROVIDERS.items() if p.get("key_url")}
API_KEY_URLS.setdefault("openai", "https://platform.openai.com/api-keys")
API_KEY_URLS.setdefault("gemini", "https://aistudio.google.com/app/apikey")
API_KEY_URLS["elevenlabs"] = "https://elevenlabs.io/app/settings/api-keys"
API_KEY_URLS["github"] = ("https://github.com/settings/tokens/new"
                          "?scopes=repo&description=Kalandra%20overlay")
# poe.ninja has no key portal — its JSON is public. The button opens the
# site so the "key (optional)" row is never a dead end.
API_KEY_URLS["poeninja"] = "https://poe.ninja/poe2/economy"

# Home/site URLs for every linked service in Settings — powers the
# "Open site" buttons so each integration is clickable and testable.
SERVICE_URLS = {
    "pathofexile":      "https://www.pathofexile.com/my-account",
    "poeninja":         "https://poe.ninja/poe2/economy",
    "poe2_forums":      "https://www.pathofexile.com/forum",   # PoE2 sections live here
    "youtube":          "https://www.youtube.com/results?search_query=path+of+exile+2+builds",
    "pathofbuilding":   "https://pathofbuilding.community/",
    "poe_overlay":      "https://github.com/PoE-Overlay-Community/PoE-Overlay-Community-Fork",
    "neversink":        "https://www.filterblade.xyz/?game=Poe2",
    "exiled_exchange2": "https://kvan7.github.io/Exiled-Exchange-2/",
    "craftofexile2":    "https://www.craftofexile.com/?game=poe2",
    "maxroll":          "https://maxroll.gg/poe2",
    "mobalytics":       "https://mobalytics.gg/poe-2",
    "poe2wiki":         "https://www.poe2wiki.net/wiki/Path_of_Exile_2_Wiki",
}

# Direct sign-in pages for services with user accounts (the generic site URL
# often lands on content, not the login). Used by the Settings rows so
# "connect my account" is always one click, never a web hunt.
LINK_SIGNIN_URLS = {
    "maxroll":       "https://maxroll.gg/login",
    "mobalytics":    "https://app.mobalytics.gg/",
    "neversink":     "https://www.filterblade.xyz/Account",
    "craftofexile2": "https://www.craftofexile.com/?game=poe2",
    "poe2wiki":      "https://www.poe2wiki.net/index.php?title=Special:UserLogin",
    "poe2_forums":   "https://www.pathofexile.com/login",
}

# Major email providers for the Email (account backup) row. Each entry:
# (label, sign-in URL, app-password/help URL).
EMAIL_PROVIDERS = [
    ("Gmail",       "https://mail.google.com/",      "https://myaccount.google.com/apppasswords"),
    ("Outlook",     "https://outlook.live.com/",     "https://account.live.com/proofs/AppPassword"),
    ("Yahoo Mail",  "https://mail.yahoo.com/",       "https://login.yahoo.com/account/security"),
    ("Proton Mail", "https://mail.proton.me/",       "https://account.proton.me/u/0/mail/imap-smtp"),
    ("iCloud Mail", "https://www.icloud.com/mail/",  "https://account.apple.com/account/manage"),
]


# ----------------------------------------------------
# 2. CINEMATIC LIVE TERMINAL LOGGER
# ----------------------------------------------------
class KalandraConsoleLogger:
    def __init__(self):
        # Bounded: a big export/import can emit tens of thousands of lines;
        # an ever-growing list slowly bloats memory over a long session.
        from collections import deque as _dq
        self.session_logs = _dq(maxlen=8000)
        self.active_project_tag = "Stormweaver Build Theory"
        # Terminal "still working" heartbeat (animated ellipses).
        self._print_lock = threading.Lock()
        self._hb_active = False
        self._hb_label = "working"
        self._hb_thread = None
        self._hb_on_line = False
        self.log_event("SYSTEM", "Kalandra Console Logger initialized successfully.")

    @staticmethod
    def _safe_print(s):
        """Print that can NEVER raise. On a non-UTF-8 Windows console, printing
        CJK/Thai/Cyrillic text (e.g. poe2db's language menu that leaks into RAG
        snippets) raises UnicodeEncodeError -- and because this runs inside a Qt
        signal handler, an unhandled error there aborts the WHOLE app. So we
        fall back to an encodable form rather than ever letting it propagate."""
        try:
            print(s)
            return
        except Exception:
            pass
        try:
            import sys as _sys
            enc = getattr(_sys.stdout, "encoding", None) or "utf-8"
            _sys.stdout.write(s.encode(enc, "replace").decode(enc, "replace") + "\n")
            _sys.stdout.flush()
        except Exception:
            pass

    def log_event(self, category, message):
        # This whole method runs inside a Qt slot; it must NEVER raise, or PyQt6
        # will abort the process. Everything is wrapped defensively.
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            message = str(message)
            log_entry = f"[{timestamp}] [{category}] {message}"
            self.session_logs.append(log_entry)

            color_code = "\033[94m"
            if category == "SYSTEM":
                color_code = "\033[95m"
            elif category == "DATABASE":
                color_code = "\033[92m"
            elif category in ("OCR", "VOICE"):
                color_code = "\033[93m"
            elif category in ("POB", "STARTUP"):
                color_code = "\033[96m"
            elif category == "SHUTDOWN":
                color_code = "\033[91m"
            reset_code = "\033[0m"
            # Keep the console line readable: very long messages (big RAG dumps)
            # are truncated here, but the full text still goes to the Terminal tab.
            console_msg = log_entry if len(log_entry) <= 600 else (log_entry[:600] + " …")
            with self._print_lock:
                if self._hb_on_line:
                    self._safe_print("\r" + " " * 64 + "\r")
                    self._hb_on_line = False
                self._safe_print(f"{color_code}{console_msg}{reset_code}")
        except Exception:
            pass
        # Mirror every event onto the app-wide bus (the dashboard Terminal tab).
        if LOG_BUS is not None:
            try:
                LOG_BUS.push(category, message)
            except Exception:
                pass

    # -- "still working" heartbeat -------------------------------------------
    def start_heartbeat(self, label="working"):
        self._hb_label = label
        if self._hb_active:
            return
        self._hb_active = True
        self._hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._hb_thread.start()

    def _heartbeat_loop(self):
        frames = [".  ", ".. ", "...", " ..", "  .", "   "]
        i = 0
        while self._hb_active:
            with self._print_lock:
                try:
                    print(f"\r\033[96m{self._hb_label}{frames[i % len(frames)]}\033[0m",
                          end="", flush=True)
                except Exception:
                    pass  # console gone / redirected — never let this thread die
                self._hb_on_line = True
            i += 1
            time.sleep(0.4)

    def stop_heartbeat(self):
        # Called from Qt slots — must NEVER raise (PyQt6 would abort the app).
        self._hb_active = False
        with self._print_lock:
            if self._hb_on_line:
                try:
                    print("\r" + " " * 64 + "\r", end="", flush=True)
                except Exception:
                    pass
                self._hb_on_line = False

    def dump_transcript_on_exit(self):
        transcripts_dir = "data_engine/transcripts"
        os.makedirs(transcripts_dir, exist_ok=True)
        safe_project_name = self.active_project_tag.replace(" ", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(transcripts_dir, f"transcript_{safe_project_name}_{timestamp}.txt")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("=========================================================\n")
                f.write(f"         KALANDRA SESSION TRANSCRIPT: {self.active_project_tag.upper()}\n")
                f.write(f"         DATE/TIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=========================================================\n\n")
                for entry in self.session_logs:
                    f.write(entry + "\n")
            print(f"\n\033[92m[DATABASE] Session transcript saved to: {filepath}\033[0m")
        except Exception as e:
            print(f"Error saving session transcript: {str(e)}")


logger = KalandraConsoleLogger()


# ----------------------------------------------------
# 2b. SMALL JSON CONFIG (AI brain choice, whisper model, etc.)
# ----------------------------------------------------
CONFIG_PATH = "data_engine/config.json"
DEFAULT_CONFIG = {"ai_brain": "openai", "whisper_model": "base", "speak_replies": True,
                  "crawl_concurrency": 10, "crawl_max_pages": 80000,
                  "wiki_concurrency": 3,
                  "openai_model": "gpt-4o-mini", "gemini_model": "gemini-2.5-flash",
                  "dir_snapshots": "data_engine/snapshots",
                  "dir_clips": "data_engine/clips",
                  "dir_transcripts": "data_engine/transcripts",
                  "dir_vault": "data_engine/vault",
                  "dir_game_data": "data_engine/game_data",
                  "dir_pob": "data_engine/pob",
                  "voice_id": "", "voice_rate": 0}

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
    except Exception:
        # A corrupt config must never be silently eaten: preserve the
        # evidence so settings can be salvaged, then run on defaults.
        try:
            import shutil
            shutil.copy2(CONFIG_PATH, CONFIG_PATH + ".corrupt.bak")
        except Exception:
            pass
    return cfg

def save_config(cfg):
    """ATOMIC config save: write a fresh temp file, then os.replace() it
    over the old one. In-place rewrites corrupted config.json when the file
    grew (2026-07-04: truncated mid-string, silently reverting every
    setting to defaults) — a rename of a complete new file cannot."""
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        # Verify the temp parses before it replaces the real file.
        with open(tmp, "r", encoding="utf-8") as f:
            json.load(f)
        os.replace(tmp, CONFIG_PATH)
    except Exception:
        pass


ORB_ART_DIR = os.path.join("gui_overlay", "assets", "orbs", "2d")

def find_orb_art(slug):
    """Locate the 2D sprite for a companion-orb slug, tolerantly.

    Exact match is 2d/<slug>.png, but users drop files in with all kinds of
    names ('Orb_of_Chance.png', 'chance orb.PNG', 'chance-orb.png'...), so we
    normalize each filename (lowercase, alphanumerics only, strip 'orb'/'of')
    and match that against the slug. Returns a path or None.
    """
    exact = os.path.join(ORB_ART_DIR, f"{slug}.png")
    if os.path.exists(exact):
        return exact
    try:
        want = re.sub(r"[^a-z]", "", slug.lower())
        for fn in os.listdir(ORB_ART_DIR):
            if not fn.lower().endswith(".png"):
                continue
            # tolerate numbering, 'orb', 'of', plurals: '9_Chance_Orbs.png' -> 'chance'
            norm = re.sub(r"[^a-z]", "", fn[:-4].lower())
            norm = norm.replace("orb", "").replace("of", "").rstrip("s")
            if norm == want or norm == want.rstrip("s"):
                return os.path.join(ORB_ART_DIR, fn)
    except Exception:
        pass
    return None


# ----------------------------------------------------
# 2c. THREAD -> UI SIGNAL BRIDGE
# ----------------------------------------------------
if PYQT_AVAILABLE:
    # W3-04/05/06: every window/dialog wears Christian's frame chrome.
    from gui_overlay.kalandra_window import (KalandraFrameDialog,
                                             KalandraFrameWindow,
                                             kinfo, kconfirm)

    class WorkerSignals(QObject):
        log = pyqtSignal(str, str)          # category, message
        sync_finished = pyqtSignal(dict)    # stats dict
        sync_state = pyqtSignal(bool)       # active?
        voice_result = pyqtSignal(str, str) # transcript, reply
        record_finished = pyqtSignal(dict)  # {video, audio, transcript}
        export_finished = pyqtSignal(dict)  # {notes, path}
        chars_finished = pyqtSignal(dict)   # {ok, characters, error}
        mouth = pyqtSignal(float)           # 0..1 mouth-open level (lip-sync)
        viseme = pyqtSignal(str)            # current mouth shape (Rhubarb A..H/X)
        speaking = pyqtSignal(bool)         # orb is talking
        death_captured = pyqtSignal(dict)   # W4-21: incident record saved
        subtitle = pyqtSignal(str)          # the orb's reply text (subtitles)
        sync_progress = pyqtSignal(float)   # current crawl rate (pages/min)
        sync_needed = pyqtSignal(bool)      # startup found data is out of date
        open_build = pyqtSignal()           # verbal request to view the build/PoB tab
        char_notify = pyqtSignal(bool)      # badge the character selector
        sim_updated = pyqtSignal()          # live sim finished computing; refresh views


# ----------------------------------------------------
# 2b. TEXT CHAT WINDOW  (double-click the mic medallion)
# ----------------------------------------------------
if PYQT_AVAILABLE:
    class ChatDialog(KalandraFrameDialog):
        """Type to the same AI brain that the voice channel uses -- same RAG
        knowledge base, same full PoB build context, same live sim numbers --
        just without speaking. A signal bridge keeps worker-thread replies
        marshalled safely onto the UI thread."""

        _reply_ready = pyqtSignal(str, str)   # (role, text)

        def __init__(self, ask_fn, parent=None, flag_fn=None, open_build_fn=None):
            super().__init__(f"KALANDRA v{KALANDRA_VERSION} — CHAT WITH THE ORB",
                             parent)
            self.ask_fn = ask_fn              # overlay.ask_ai_text(text, on_reply)
            self.flag_fn = flag_fn            # overlay._flag_last_answer(q, a, note)
            self.open_build_fn = open_build_fn   # overlay.open_dashboard_build
            self._busy = False
            self._last_q = ""
            self._last_a = ""
            self.setMinimumSize(440, 520)
            self.setStyleSheet(
                "QDialog{background-color:#12151b;}"
                "QTextEdit{background-color:#0c0e13;color:#e8e8ee;border:1px solid #2a2f3a;"
                "border-radius:8px;padding:8px;font-size:13px;}"
                "QLineEdit{background-color:#0c0e13;color:#fff;border:1px solid #2a2f3a;"
                "border-radius:8px;padding:8px;font-size:13px;}"
                "QPushButton{background-color:#7a2533;color:#fff;border:none;border-radius:8px;"
                "padding:8px 16px;font-weight:bold;}"
                "QPushButton:hover{background-color:#9c2f41;}"
                "QPushButton:disabled{background-color:#3a3f4a;color:#888;}"
                "QLabel{color:#9aa0ab;font-size:11px;}")

            lay = self.body
            self.transcript = QTextEdit()
            self.transcript.setReadOnly(True)
            lay.addWidget(self.transcript, 1)

            self.status = QLabel("Same AI, same build & database context — just typed.")
            lay.addWidget(self.status)

            # Flag the last answer as a tracked issue (e.g. a hallucination), so
            # it lands in the changelog you can hand back to the dev/AI to fix.
            self.flag_btn = QPushButton("⚑ Flag last answer as wrong / an issue")
            self.flag_btn.setStyleSheet(
                "QPushButton{background:#3a2f1a;border:1px solid #6a5a33;color:#e8d9b0;"
                "padding:5px 10px;border-radius:6px;font-weight:normal;}"
                "QPushButton:hover{background:#4a3c22;}"
                "QPushButton:disabled{background:#23262d;color:#666;border-color:#333;}")
            self.flag_btn.setEnabled(False)
            self.flag_btn.clicked.connect(self._flag_last)
            lay.addWidget(self.flag_btn)

            # Jump to the dashboard's Build (PoB) tab for the active character.
            # Surfaces automatically when the Orb suggests looking at PoB.
            self.build_btn = QPushButton("📊 Open my build (PoB) in the dashboard")
            self.build_btn.setStyleSheet(
                "QPushButton{background:#1a2a1f;border:1px solid #2f6a44;color:#bfe8cf;"
                "padding:5px 10px;border-radius:6px;font-weight:normal;}"
                "QPushButton:hover{background:#22402c;}")
            self.build_btn.clicked.connect(self._open_build)
            self.build_btn.setVisible(bool(self.open_build_fn))
            lay.addWidget(self.build_btn)

            row = QHBoxLayout()
            self.input = QLineEdit()
            self.input.setPlaceholderText("Ask about your build, gear, crafting…")
            self.input.returnPressed.connect(self._send)
            self.send_btn = QPushButton("Send")
            self.send_btn.clicked.connect(self._send)
            row.addWidget(self.input, 1)
            row.addWidget(self.send_btn)
            lay.addLayout(row)

            self._reply_ready.connect(self._append)
            self._append("Orb", "The mirror listens. What would you know, Exile?")

        def _append(self, role, text):
            if role == "__ready__":     # sentinel: reply cycle done, re-enable input
                self._set_busy(False)
                return
            if role == "Orb":
                self._last_a = text or ""
                if hasattr(self, "flag_btn"):
                    self.flag_btn.setEnabled(bool(self._last_a))
                # If the Orb pointed the user at Path of Building, make the
                # "open build" link stand out as the clickable next step.
                if hasattr(self, "build_btn") and self.open_build_fn:
                    low = (text or "").lower()
                    suggests = any(k in low for k in (
                        "path of building", "pob", "power report", "node power",
                        "passive tree", "tree tab", "your tree"))
                    if suggests:
                        self.build_btn.setText("↪ Open my build in the PoB tab (the Orb suggested it)")
                        self.build_btn.setStyleSheet(
                            "QPushButton{background:#244a31;border:1px solid #4fc77f;"
                            "color:#dffbe9;padding:6px 10px;border-radius:6px;font-weight:bold;}"
                            "QPushButton:hover{background:#2c5a3c;}")
                    else:
                        self.build_btn.setText("📊 Open my build (PoB) in the dashboard")
            color = "#d98a94" if role == "Orb" else "#7fb2ff"
            safe = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            self.transcript.append(
                f'<p style="margin:6px 0;"><b style="color:{color};">{role}:</b> '
                f'<span style="color:#e8e8ee;">{safe}</span></p>')
            sb = self.transcript.verticalScrollBar()
            sb.setValue(sb.maximum())

        def _set_busy(self, busy):
            self._busy = busy
            self.send_btn.setEnabled(not busy)
            self.input.setEnabled(not busy)
            self.status.setText("Thinking…" if busy else
                                "Same AI, same build & database context — just typed.")
            if not busy:
                self.input.setFocus()

        def _send(self):
            if self._busy:
                return
            text = self.input.text().strip()
            if not text:
                return
            self._last_q = text
            self.input.clear()
            self._append("You", text)
            self._set_busy(True)

            def on_reply(reply, error=None):
                # Called from a worker thread -> hop to UI thread via the signal.
                if error:
                    self._reply_ready.emit("Orb", f"(couldn't answer: {error})")
                else:
                    self._reply_ready.emit("Orb", reply or "(no response)")
                # _set_busy touches widgets, so it must also run on the UI thread;
                # emit a sentinel the slot below clears.
                self._reply_ready.emit("__ready__", "")

            try:
                self.ask_fn(text, on_reply)
            except Exception as e:
                self._reply_ready.emit("Orb", f"(error: {e})")
                self._reply_ready.emit("__ready__", "")

        def _open_build(self):
            if self.open_build_fn:
                try:
                    self.open_build_fn()
                except Exception as e:
                    self.status.setText(f"Could not open build: {e}")

        def _flag_last(self):
            if not (self.flag_fn and self._last_a):
                return
            try:
                note, ok = QInputDialog.getText(
                    self, "Flag this answer",
                    "What's wrong with it? (optional — e.g. 'Corrupted Blood isn't Bleed')")
            except Exception:
                note, ok = "", True
            if ok is False:
                return
            try:
                self.flag_fn(self._last_q, self._last_a, note or "")
                self.status.setText("Flagged — added to the issues log (Settings → Known issues).")
                self.flag_btn.setEnabled(False)
            except Exception as e:
                self.status.setText(f"Could not flag: {e}")

        def showEvent(self, e):
            super().showEvent(e)
            self.input.setFocus()


# ----------------------------------------------------
# 3. SETTINGS / ACCOUNTS DIALOG
# ----------------------------------------------------
if PYQT_AVAILABLE:
    class PricePopup(QWidget):
        """W3-20: the in-game price flyout. PoE2's own Ctrl+C puts the hovered
        item's text on the clipboard; Kalandra notices, parses it, and floats
        this card near the cursor — Exiled-Exchange style, but 100%% passive
        (we read the clipboard the game wrote; we never touch the game)."""

        def __init__(self, info, raw_text, league, on_dashboard=None,
                     estimate=None):
            super().__init__(None, Qt.WindowType.FramelessWindowHint
                             | Qt.WindowType.WindowStaysOnTopHint
                             | Qt.WindowType.Tool)
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            from gui_overlay import theme as _t
            rarity = (info.get("rarity") or "").lower()
            rare_col = {"unique": "#af6025", "rare": "#d9cf8a",
                        "magic": "#8888ff"}.get(rarity, _t.TEXT)
            self.setStyleSheet(
                f"QWidget{{background:{_t.BG1};color:{_t.TEXT};font-size:12px;}}"
                f"QLabel{{background:transparent;}}"
                f"QPushButton{{background:{_t.BG2};border:1px solid {_t.GOLD_DARK};"
                f"border-radius:4px;padding:4px 10px;color:{_t.TEXT};}}"
                f"QPushButton:hover{{border-color:{_t.GOLD};color:{_t.GOLD_LIGHT};}}")
            lay = QVBoxLayout(self)
            lay.setContentsMargins(12, 10, 12, 10)
            name = info.get("name") or info.get("base") or "Item"
            head = QLabel(f"<b>{name}</b>")
            head.setStyleSheet(f"color:{rare_col};font-size:14px;background:transparent;")
            lay.addWidget(head)
            sub_bits = [b for b in (info.get("base") if info.get("name") else None,
                                    info.get("item_class"),
                                    f"ilvl {info.get('ilvl')}" if info.get("ilvl") else None)
                        if b]
            if sub_bits:
                sub = QLabel(" · ".join(sub_bits))
                sub.setStyleSheet("color:#9aa4b2;background:transparent;")
                lay.addWidget(sub)
            for m in (info.get("mods") or [])[:4]:
                ml = QLabel("• " + m)
                ml.setStyleSheet("color:#8fa0c0;background:transparent;")
                lay.addWidget(ml)
            est = QLabel(estimate or
                         "No instant estimate — check live listings ↓")
            est.setStyleSheet(
                f"color:{_t.GOLD_LIGHT};font-weight:bold;background:transparent;"
                if estimate else "color:#7d8694;background:transparent;")
            lay.addWidget(est)
            row = QHBoxLayout()
            tb = QPushButton("Trade ↗")
            from core_engine.trade_tools import trade_search_url
            url = trade_search_url(info, league)
            tb.clicked.connect(lambda: (QDesktopServices.openUrl(QUrl(url)),
                                        self.close()))
            row.addWidget(tb)
            if on_dashboard:
                db = QPushButton("Price Check tab")
                db.clicked.connect(lambda: (on_dashboard(raw_text), self.close()))
                row.addWidget(db)
            xb = QPushButton("✕")
            xb.setFixedWidth(28)
            xb.clicked.connect(self.close)
            row.addWidget(xb)
            lay.addLayout(row)
            # place near the cursor, clamped to the screen
            try:
                from PyQt6.QtGui import QCursor
                pos = QCursor.pos()
                scr = QApplication.screenAt(pos) or QApplication.primaryScreen()
                g = scr.availableGeometry()
                self.adjustSize()
                x = min(max(pos.x() + 18, g.left()), g.right() - self.width() - 8)
                y = min(max(pos.y() + 18, g.top()), g.bottom() - self.height() - 8)
                self.move(x, y)
            except Exception:
                pass
            QTimer.singleShot(12000, self.close)   # auto-dismiss

        def keyPressEvent(self, ev):
            if ev.key() == Qt.Key.Key_Escape:
                self.close()
            else:
                super().keyPressEvent(ev)


    class SettingsDialog(KalandraFrameDialog):
        _voices_loaded = pyqtSignal(list)
        _conn_loaded = pyqtSignal(dict)

        def __init__(self, account_manager, config, parent=None, on_export_vault=None,
                     on_import_gamedata=None, on_open_dashboard=None, on_scan_gamedata=None,
                     on_open_deps=None, voices=None, issues=None,
                     orbs=None, current_orb="divine", on_orb_change=None,
                     usage_provider=None, on_dashboard_change=None):
            super().__init__(f"KALANDRA v{KALANDRA_VERSION} — SETTINGS & ACCOUNTS",
                             parent)
            self.am = account_manager
            self.config = config
            self.issues = issues
            self.orbs = orbs or []
            self.current_orb = current_orb
            self.on_orb_change = on_orb_change
            self.usage_provider = usage_provider
            self.on_dashboard_change = on_dashboard_change
            self._voices = voices               # pre-cached [(id, name)] or None
            self._voices_loaded.connect(self._fill_voice_combo)
            self._conn_loaded.connect(self._apply_connections)
            self._svc_headers = {}              # svc_id -> (QLabel, name, kind)
            self.on_export_vault = on_export_vault
            self.on_import_gamedata = on_import_gamedata
            self.on_open_dashboard = on_open_dashboard
            self.on_scan_gamedata = on_scan_gamedata
            self.on_open_deps = on_open_deps
            # The frame border eats ~110px of width, so open WIDE (close to
            # the dashboard) or the bottom button row clips. Bounded to the
            # screen; the service list scrolls for height.
            self.setMinimumSize(820, 460)
            self._build_ui()
            try:
                scr = QApplication.primaryScreen()
                avail = scr.availableGeometry() if scr else None
                w, h = 1100, 780
                if avail is not None:
                    w = min(w, max(820, avail.width() - 120))
                    h = min(h, max(460, avail.height() - 90))
                self.resize(w, h)
            except Exception:
                self.resize(1100, 720)

        def _build_ui(self):
            root = self.body

            title = QLabel("<b>Oracle Setup &amp; Account Linking</b>")
            title.setStyleSheet("font-size:16px;color:#d4a373;")
            root.addWidget(title)

            note = QLabel(self.am.storage_note() if self.am else "Account storage unavailable.")
            note.setWordWrap(True)
            note.setStyleSheet("color:#9aa4b2;font-size:11px;")
            root.addWidget(note)

            # --- AI brain selector (provider + model + live usage) ---
            try:
                from core_engine.voice_engine import PROVIDERS as _PROV
            except Exception:
                _PROV = {}
            self._providers = _PROV
            brain_row = QHBoxLayout()
            brain_row.addWidget(QLabel("AI brain:"))
            self.brain_combo = QComboBox()
            for pid, p in _PROV.items():
                self.brain_combo.addItem(p.get("label", pid), pid)
            cur = self.config.get("ai_brain", "openai")
            i = self.brain_combo.findData(cur)
            self.brain_combo.setCurrentIndex(i if i >= 0 else 0)
            self.brain_combo.currentIndexChanged.connect(self._on_brain_change)
            brain_row.addWidget(self.brain_combo, 1)
            brain_row.addWidget(QLabel("Model:"))
            self.model_combo = QComboBox()
            self.model_combo.setEditable(True)   # provider model IDs change; allow typing
            self.model_combo.setMinimumWidth(170)
            self.model_combo.currentTextChanged.connect(self._on_model_change)
            brain_row.addWidget(self.model_combo, 1)
            root.addLayout(brain_row)
            # Live usage (tokens this session vs your self-set budget).
            self.usage_lbl = QLabel("")
            self.usage_lbl.setStyleSheet("color:#9aa4b2;font-size:11px;")
            self.usage_lbl.setWordWrap(True)
            root.addWidget(self.usage_lbl)
            budget_row = QHBoxLayout()
            budget_row.addWidget(QLabel("Session token budget (0 = off):"))
            self.budget_edit = QLineEdit(str(self.config.get("token_budget", 0)))
            self.budget_edit.setFixedWidth(110)
            self.budget_edit.editingFinished.connect(self._on_budget_change)
            budget_row.addWidget(self.budget_edit)
            budget_row.addStretch()
            root.addLayout(budget_row)
            bhint = QLabel("Note: providers don't expose your real account balance, so this "
                           "is a self-set cap on tokens used this session — you'll get a "
                           "countdown warning as you approach it.")
            bhint.setStyleSheet("color:#7d8694;font-size:10px;")
            bhint.setWordWrap(True)
            root.addWidget(bhint)
            # ONE key row for whichever brain is selected above — no more
            # per-provider rows cluttering the account list.
            key_row = QHBoxLayout()
            key_row.addWidget(QLabel("API key:"))
            self.ai_key_edit = QLineEdit()
            self.ai_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            key_row.addWidget(self.ai_key_edit, 1)
            ksave = QPushButton("Save")
            ksave.setProperty("gem", "emerald")
            ksave.clicked.connect(self._save_ai_key)
            key_row.addWidget(ksave)
            kclear = QPushButton("Clear")
            kclear.setProperty("gem", "ruby")
            kclear.clicked.connect(self._clear_ai_key)
            key_row.addWidget(kclear)
            self.ai_key_btn = QPushButton("Get key ↗")
            self.ai_key_btn.clicked.connect(self._open_ai_key_page)
            key_row.addWidget(self.ai_key_btn)
            root.addLayout(key_row)
            self.ai_key_status = QLabel("")
            self.ai_key_status.setStyleSheet("color:#9aa4b2;font-size:10px;")
            root.addWidget(self.ai_key_status)
            self._reload_models(cur)
            self._refresh_usage_label()
            self._refresh_ai_key_row()

            # --- Crawl speed (parallel fetchers) ---
            speed_row = QHBoxLayout()
            speed_row.addWidget(QLabel("DB sync speed (parallel fetchers):"))
            self.speed_combo = QComboBox()
            self.speed_combo.addItems(["4 (gentle)", "10 (default)", "20 (fast)", "32 (max)"])
            cur = str(self.config.get("crawl_concurrency", 10))
            for i in range(self.speed_combo.count()):
                if self.speed_combo.itemText(i).startswith(cur + " "):
                    self.speed_combo.setCurrentIndex(i)
                    break
            self.speed_combo.currentTextChanged.connect(self._on_speed_change)
            speed_row.addWidget(self.speed_combo)
            speed_row.addStretch()
            # W3-20: toggle for the in-game Ctrl+C price flyout.
            self.popup_check = QCheckBox("Ctrl+C price popup (in game)")
            self.popup_check.setToolTip(
                "When you copy an item in game (Ctrl+C over its tooltip), a "
                "small card pops up with the parsed item, an instant currency "
                "estimate, and trade-search shortcuts. Purely passive — reads "
                "the clipboard the game wrote, never touches the game.")
            self.popup_check.setChecked(bool(self.config.get("price_popup", True)))
            self.popup_check.stateChanged.connect(self._on_popup_toggle)
            speed_row.addWidget(self.popup_check)
            root.addLayout(speed_row)
            # Which tool answers your in-game price checks. Picking an
            # external tool silences Kalandra's own Ctrl+C popup so the two
            # never fight over the clipboard.
            pc_row = QHBoxLayout()
            pc_row.addWidget(QLabel("Price checker:"))
            self.pc_combo = QComboBox()
            for label, pid in (("Kalandra (built-in popup)", "kalandra"),
                               ("PoE Overlay 2", "poe_overlay2"),
                               ("Exiled Exchange 2", "exiled_exchange2"),
                               ("Xiletrade", "xiletrade")):
                self.pc_combo.addItem(label, pid)
            i = self.pc_combo.findData(self.config.get("price_checker", "kalandra"))
            self.pc_combo.setCurrentIndex(i if i >= 0 else 0)
            self.pc_combo.currentIndexChanged.connect(self._on_pc_change)
            pc_row.addWidget(self.pc_combo, 1)
            root.addLayout(pc_row)

            # --- Divine Orb voice ---
            voice_row = QHBoxLayout()
            voice_row.addWidget(QLabel("Divine Orb voice:"))
            self.voice_combo = QComboBox()
            self.voice_combo.addItem("System default", "")
            # The rest of the voices are filled in asynchronously (see
            # _populate_voices) so opening Settings is instant.
            self.voice_combo.currentIndexChanged.connect(self._on_voice_change)
            voice_row.addWidget(self.voice_combo, 1)
            root.addLayout(voice_row)

            # --- Companion orb (which currency orb floats as your companion) ---
            if self.orbs:
                orb_row = QHBoxLayout()
                orb_row.addWidget(QLabel("Companion orb:"))
                self.orb_combo = QComboBox()
                for name, slug in self.orbs:
                    # Show at a glance which orbs actually have art installed —
                    # previously picking an art-less orb silently kept showing
                    # the Divine Orb, which looked like the selector was broken.
                    has_art = bool(find_orb_art(slug)) or slug == "divine"
                    self.orb_combo.addItem(name if has_art else f"{name}  (no art yet)", slug)
                i = self.orb_combo.findData((self.current_orb or "divine").lower())
                if i >= 0:
                    self.orb_combo.setCurrentIndex(i)
                self.orb_combo.currentIndexChanged.connect(self._on_orb_change)
                orb_row.addWidget(self.orb_combo, 1)
                root.addLayout(orb_row)
                self.orb_hint = QLabel("Drop art in gui_overlay/assets/orbs/2d/&lt;slug&gt;.png; "
                                       "missing art falls back to the Divine Orb.")
                self.orb_hint.setStyleSheet("color:#7d8694;font-size:10px;")
                self.orb_hint.setWordWrap(True)
                root.addWidget(self.orb_hint)

            # --- Scrollable service list ---
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            container = QWidget()
            grid = QVBoxLayout(container)

            # --- Dashboard tabs: pick which to show ---
            self._build_dashboard_tabs_section(grid)
            # --- Custom tabs: user-added website/program tabs ---
            try:
                self._build_custom_tabs_section(grid)
            except Exception:
                pass

            self.fields = {}
            if self.am:
                # Build rows WITHOUT hitting the keychain (each read can stall on
                # Windows; 15 of them froze the overlay and showed a black box).
                # Grouped: builds, tools, external. AI brains live up top.
                _AI_IDS = ("openai", "gemini", "anthropic", "deepseek",
                           "mistral", "xai")
                _SECTIONS = [
                    ("⚔ PoE2 Builds", ("pathofexile", "pathofbuilding",
                                       "maxroll", "mobalytics")),
                    ("🛠 PoE2 Tools", ("poeninja", "poe2_forums", "poe_overlay",
                                      "neversink", "exiled_exchange2",
                                      "craftofexile2", "poe2wiki")),
                    ("🌐 External accounts", ("email", "youtube", "github",
                                             "elevenlabs")),
                ]
                meta = {s["id"]: s for s in self.am.list_service_meta()
                        if s["id"] not in _AI_IDS}
                for title, ids in _SECTIONS:
                    got = [meta.pop(i) for i in ids if i in meta]
                    if not got:
                        continue
                    hdr = QLabel(f"<b>{title}</b>")
                    hdr.setStyleSheet("color:#d4a373;font-size:14px;"
                                      "margin-top:10px;letter-spacing:1px;")
                    grid.addWidget(hdr)
                    for svc in got:
                        grid.addWidget(self._service_row(svc))
                for svc in meta.values():   # anything new lands at the end
                    grid.addWidget(self._service_row(svc))
                # Check which accounts are actually connected off the UI thread.
                threading.Thread(target=self._load_connections, daemon=True).start()
            else:
                grid.addWidget(QLabel("AccountManager unavailable (pip install keyring)."))

            grid.addStretch()
            scroll.setWidget(container)
            root.addWidget(scroll, 1)

            # --- Obsidian export ---
            exp_row = QHBoxLayout()
            exp_row.addWidget(QLabel("Knowledge base:"))
            exp_btn = QPushButton("Export Obsidian vault")
            exp_btn.setToolTip("Write the scraped database to data_engine/vault as a "
                               "linked Obsidian vault you can open directly.")
            exp_btn.clicked.connect(self._do_export)
            exp_row.addWidget(exp_btn)
            dash_btn = QPushButton("Open Dashboard")
            dash_btn.setToolTip("Open the single-pane dashboard (tools, web views, build sim).")
            dash_btn.clicked.connect(self._do_open_dashboard)
            exp_row.addWidget(dash_btn)
            deps_btn = QPushButton("Setup & Dependencies")
            deps_btn.setToolTip("Install/enable features, point to tools, set output folders.")
            deps_btn.clicked.connect(self._do_open_deps)
            exp_row.addWidget(deps_btn)
            gd_btn = QPushButton("Import game data")
            gd_btn.setToolTip("Import pre-extracted PoE2 game files (JSON) from "
                              "data_engine/game_data into the knowledge base.")
            gd_btn.clicked.connect(self._do_import_gamedata)
            exp_row.addWidget(gd_btn)
            scan_btn = QPushButton("Scan game data")
            scan_btn.setToolTip("Show what game data is available and whether it's up to date.")
            scan_btn.clicked.connect(self._do_scan_gamedata)
            exp_row.addWidget(scan_btn)
            exp_row.addStretch()
            root.addLayout(exp_row)
            self.gd_status = QLabel("Game data: click 'Scan game data' for status.")
            self.gd_status.setWordWrap(True)
            self.gd_status.setStyleSheet("color:#9aa4b2;font-size:11px;")
            root.addWidget(self.gd_status)

            # Known issues / changelog notification.
            if self.issues is not None:
                try:
                    n = self.issues.open_count()
                except Exception:
                    n = 0
                irow = QHBoxLayout()
                ilbl = QLabel(f"Known issues: <b>{n}</b> open")
                ilbl.setStyleSheet("color:#d4a373;font-size:12px;" if n else "color:#9aa4b2;font-size:12px;")
                irow.addWidget(ilbl)
                iss_btn = QPushButton("Open issues log & changelog")
                iss_btn.setToolTip("View/triage logged bugs & ideas, and copy the changelog "
                                   "to hand to the dev/AI.")
                iss_btn.clicked.connect(self._do_open_dashboard)
                irow.addWidget(iss_btn)
                irow.addStretch()
                root.addLayout(irow)

            close_btn = QPushButton("Done")
            close_btn.setProperty("gem", "emerald")
            close_btn.clicked.connect(self.accept)
            root.addWidget(close_btn)

            # Voices are slow to enumerate (Windows SAPI init); fill the combo
            # AFTER the dialog is up so construction never blocks the overlay's
            # repaint (which otherwise shows a black square for a few seconds).
            QTimer.singleShot(0, self._populate_voices)

        def _populate_voices(self):
            voices = self._voices
            if voices is None:           # not pre-cached: load off the UI thread
                def _load():
                    try:
                        vs = VoiceEngine.list_voices() if VoiceEngine else []
                    except Exception:
                        vs = []
                    self._voices_loaded.emit(vs)
                threading.Thread(target=_load, daemon=True).start()
            else:
                self._fill_voice_combo(voices)

        def _fill_voice_combo(self, voices):
            cur_v = self.config.get("voice_id", "")
            self.voice_combo.blockSignals(True)
            for vid, vname in (voices or []):
                self.voice_combo.addItem(vname, vid)
            i = self.voice_combo.findData(cur_v)
            if i >= 0:
                self.voice_combo.setCurrentIndex(i)
            self.voice_combo.blockSignals(False)

        def _on_pc_change(self, _idx):
            self.config["price_checker"] = self.pc_combo.currentData() or "kalandra"
            save_config(self.config)

        def _on_popup_toggle(self, _state):
            self.config["price_popup"] = self.popup_check.isChecked()
            save_config(self.config)

        def _on_orb_change(self, _idx):
            slug = self.orb_combo.currentData()
            if slug and hasattr(self, "orb_hint"):
                if slug != "divine" and not find_orb_art(slug):
                    self.orb_hint.setText(
                        f"⚠ No art installed for this orb yet — the overlay will keep "
                        f"showing the Divine Orb. Add a PNG at "
                        f"gui_overlay/assets/orbs/2d/{slug}.png (any similar filename "
                        f"like 'Orb_of_{slug.title()}.png' also works), then re-select it.")
                    self.orb_hint.setStyleSheet("color:#e0b050;font-size:10px;")
                else:
                    self.orb_hint.setText("Art found — the overlay orb updates instantly.")
                    self.orb_hint.setStyleSheet("color:#7fd6a0;font-size:10px;")
            if self.on_orb_change and slug:
                try:
                    self.on_orb_change(slug)
                except Exception:
                    pass

        def _build_dashboard_tabs_section(self, grid):
            """Checkboxes to choose which dashboard tabs are shown."""
            try:
                from gui_overlay.dashboard import DASHBOARD_TABS
            except Exception:
                DASHBOARD_TABS = []
            if not DASHBOARD_TABS:
                return
            hdr = QLabel("<b>Dashboard tabs</b> — tick the ones you want to see")
            hdr.setStyleSheet("color:#d4a373;font-size:12px;margin-top:4px;")
            grid.addWidget(hdr)
            prefs = self.config.get("dashboard_tabs", {}) or {}
            box = QFrame(); box.setStyleSheet("QFrame{border:1px solid #262c36;border-radius:6px;}")
            from PyQt6.QtWidgets import QGridLayout
            gl = QGridLayout(box)
            self._tab_checks = {}
            for i, (label, default_on) in enumerate(DASHBOARD_TABS):
                cb = QCheckBox(label)
                cb.setChecked(bool(prefs.get(label, default_on)))
                cb.stateChanged.connect(lambda _s, l=label: self._on_tab_toggle(l))
                self._tab_checks[label] = cb
                gl.addWidget(cb, i // 2, i % 2)
            grid.addWidget(box)

        def _on_tab_toggle(self, label):
            prefs = dict(self.config.get("dashboard_tabs", {}) or {})
            cb = self._tab_checks.get(label)
            if cb is not None:
                prefs[label] = cb.isChecked()
            self.config["dashboard_tabs"] = prefs
            save_config(self.config)

        def _build_custom_tabs_section(self, grid):
            """Add your OWN dashboard tabs: a website in a contained browser
            (like poe.ninja / Craft of Exile) or a program folder + exe
            adopted into the tab (containerized like PoB)."""
            hdr = QLabel("<b>Custom tabs</b> — add your own website or "
                         "program tabs to the dashboard")
            hdr.setStyleSheet("color:#d4a373;font-size:12px;margin-top:8px;")
            grid.addWidget(hdr)
            box = QFrame()
            box.setStyleSheet("QFrame{border:1px solid #262c36;border-radius:6px;}")
            v = QVBoxLayout(box)
            self._custom_list_lay = QVBoxLayout()
            v.addLayout(self._custom_list_lay)
            self._refresh_custom_list()
            # -- add a website tab --
            wrow = QHBoxLayout()
            self.ct_name = QLineEdit(); self.ct_name.setPlaceholderText("Tab name")
            self.ct_name.setMaximumWidth(140)
            wrow.addWidget(self.ct_name)
            self.ct_url = QLineEdit()
            self.ct_url.setPlaceholderText("https://… (contained browser)")
            wrow.addWidget(self.ct_url, 1)
            addw = QPushButton("Add website tab")
            addw.setProperty("gem", "emerald")
            addw.clicked.connect(self._add_custom_web)
            wrow.addWidget(addw)
            v.addLayout(wrow)
            # -- add a program tab --
            arow = QHBoxLayout()
            self.ct_exe_lbl = QLabel("No program picked.")
            self.ct_exe_lbl.setStyleSheet("color:#7d8694;font-size:10px;")
            pick = QPushButton("Pick program .exe…")
            pick.clicked.connect(self._pick_custom_exe)
            arow.addWidget(pick)
            arow.addWidget(self.ct_exe_lbl, 1)
            adda = QPushButton("Add program tab")
            adda.setProperty("gem", "emerald")
            adda.clicked.connect(self._add_custom_app)
            arow.addWidget(adda)
            v.addLayout(arow)
            note = QLabel("Program tabs launch the exe and adopt its window "
                          "into the dashboard (same containment as PoB). "
                          "Changes apply when the dashboard reopens.")
            note.setWordWrap(True)
            note.setStyleSheet("color:#7d8694;font-size:10px;")
            v.addWidget(note)
            grid.addWidget(box)
            self._picked_exe = ""

        def _refresh_custom_list(self):
            while self._custom_list_lay.count():
                it = self._custom_list_lay.takeAt(0)
                w = it.widget()
                if w:
                    w.setParent(None); w.deleteLater()
            tabs = self.config.get("custom_tabs") or []
            for i, ct in enumerate(tabs):
                roww = QWidget(); row = QHBoxLayout(roww)
                row.setContentsMargins(0, 0, 0, 0)
                kind = "🌐" if ct.get("kind") == "web" else "🖥"
                tgt = ct.get("url") or ct.get("exe") or ""
                lab = QLabel(f"{kind} <b>{ct.get('name', '?')}</b> "
                             f"<span style='color:#7d8694;'>{tgt[:60]}</span>")
                row.addWidget(lab, 1)
                rm = QPushButton("Remove")
                rm.setProperty("gem", "ruby")
                rm.clicked.connect(lambda _, idx=i: self._remove_custom(idx))
                row.addWidget(rm)
                self._custom_list_lay.addWidget(roww)

        def _pick_custom_exe(self):
            exe, _ = QFileDialog.getOpenFileName(
                self, "Pick the program to contain", "", "Programs (*.exe)")
            if exe:
                self._picked_exe = exe
                self.ct_exe_lbl.setText(exe)

        def _add_custom_web(self):
            name = self.ct_name.text().strip()
            url = self.ct_url.text().strip()
            if not name or not url.lower().startswith(("http://", "https://")):
                self.ct_url.setPlaceholderText("Need a name + a full https:// URL")
                return
            tabs = list(self.config.get("custom_tabs") or [])
            tabs.append({"name": name, "kind": "web", "url": url})
            self.config["custom_tabs"] = tabs
            save_config(self.config)
            self.ct_name.clear(); self.ct_url.clear()
            self._refresh_custom_list()

        def _add_custom_app(self):
            name = self.ct_name.text().strip()
            if not name or not getattr(self, "_picked_exe", ""):
                self.ct_exe_lbl.setText("Pick an .exe and give the tab a name "
                                        "first.")
                return
            tabs = list(self.config.get("custom_tabs") or [])
            tabs.append({"name": name, "kind": "app", "exe": self._picked_exe})
            self.config["custom_tabs"] = tabs
            save_config(self.config)
            self.ct_name.clear(); self._picked_exe = ""
            self.ct_exe_lbl.setText("No program picked.")
            self._refresh_custom_list()

        def _remove_custom(self, idx):
            tabs = list(self.config.get("custom_tabs") or [])
            if 0 <= idx < len(tabs):
                tabs.pop(idx)
                self.config["custom_tabs"] = tabs
                save_config(self.config)
                self._refresh_custom_list()
            if self.on_dashboard_change:
                try:
                    self.on_dashboard_change()
                except Exception:
                    pass

        def _do_scan_gamedata(self):
            if self.on_scan_gamedata:
                try:
                    self.gd_status.setText(self.on_scan_gamedata())
                except Exception as e:
                    self.gd_status.setText(f"Scan failed: {e}")

        def _do_export(self):
            if self.on_export_vault:
                self.on_export_vault()
                QMessageBox.information(self, "Obsidian Export",
                                       "Exporting vault in the background — "
                                       "watch the console for the output path.")

        def _do_open_dashboard(self):
            if self.on_open_dashboard:
                self.on_open_dashboard()
            self.accept()  # close the (modal) settings menu so it doesn't sit on top

        def _do_open_deps(self):
            if self.on_open_deps:
                self.on_open_deps()

        def _do_import_gamedata(self):
            if self.on_import_gamedata:
                self.on_import_gamedata()
                QMessageBox.information(self, "Game Data Import",
                                       "Importing game data in the background. See "
                                       "data_engine/game_data and ROADMAP.md for how "
                                       "to produce the extracted files.")

        def _load_connections(self):
            """Check each service's saved-secret status off the UI thread."""
            res = {}
            for sid in list(self._svc_headers.keys()):
                try:
                    res[sid] = bool(self.am.is_connected(sid)) if self.am else False
                except Exception:
                    res[sid] = False
            self._conn_loaded.emit(res)

        def _apply_connections(self, res):
            for sid, connected in res.items():
                tup = self._svc_headers.get(sid)
                if not tup:
                    continue
                header, name, kind = tup
                status = "🟢 connected" if connected else "⚪ not linked"
                try:
                    header.setText(f"<b>{name}</b>  "
                                   f"<span style='color:#7d8694;'>[{kind}]</span>  {status}")
                except Exception:
                    pass

        def _service_row(self, svc):
            box = QFrame()
            box.setStyleSheet("QFrame{border:1px solid #262c36;border-radius:6px;}")
            lay = QVBoxLayout(box)

            connected = svc.get("connected")
            if connected is None:
                status = "<span style='color:#7d8694;'>checking...</span>"
            else:
                status = "🟢 connected" if connected else "⚪ not linked"
            header = QLabel(f"<b>{svc['name']}</b>  "
                            f"<span style='color:#7d8694;'>[{svc['kind']}]</span>  "
                            f"{status}")
            lay.addWidget(header)
            # Remember the header so the async connection check can update it.
            self._svc_headers[svc["id"]] = (header, svc["name"], svc["kind"])

            desc = QLabel(svc["note"])
            desc.setWordWrap(True)
            desc.setStyleSheet("color:#9aa4b2;font-size:11px;")
            lay.addWidget(desc)

            if svc["kind"] in ("api_key", "login"):
                row = QHBoxLayout()
                edit = QLineEdit()
                edit.setEchoMode(QLineEdit.EchoMode.Password)
                edit.setPlaceholderText("Paste API key / token" if svc["kind"] == "api_key"
                                        else "username:password or token")
                self.fields[svc["id"]] = edit
                row.addWidget(edit)
                save = QPushButton("Save")
                save.setProperty("gem", "emerald")
                save.clicked.connect(lambda _, s=svc["id"]: self._save_secret(s))
                clear = QPushButton("Clear")
                clear.setProperty("gem", "ruby")
                clear.clicked.connect(lambda _, s=svc["id"]: self._clear_secret(s))
                row.addWidget(save)
                row.addWidget(clear)
                lay.addLayout(row)
                helper = QHBoxLayout()
                # "Get a key" helper for services with a key page.
                if svc["id"] in API_KEY_URLS:
                    getkey = QPushButton("Get a key ↗")
                    getkey.clicked.connect(
                        lambda _, s=svc["id"]: QDesktopServices.openUrl(QUrl(API_KEY_URLS[s])))
                    helper.addWidget(getkey)
                # EVERY keyed/login service gets its sign-in/site button too —
                # "where do I even do this?" should never need a web search.
                surl = LINK_SIGNIN_URLS.get(svc["id"]) or \
                    SERVICE_URLS.get(svc["id"], "")
                if surl:
                    opensite = QPushButton("Open sign-in / site ↗")
                    opensite.setToolTip(surl)
                    opensite.clicked.connect(
                        lambda _, u=surl: QDesktopServices.openUrl(QUrl(u)))
                    helper.addWidget(opensite)
                if helper.count():
                    helper.addStretch()
                    lay.addLayout(helper)
            elif svc["kind"] == "oauth":
                if svc["id"] == "pathofexile":
                    self._build_ggg_oauth_row(lay)
                elif svc["id"] == "email":
                    self._build_email_row(lay)
                else:
                    # Generic OAuth service (e.g. YouTube): open its sign-in page.
                    row = QHBoxLayout()
                    connect = QPushButton("Open sign-in page")
                    url = SERVICE_URLS.get(svc["id"], "")
                    connect.clicked.connect(
                        lambda _, u=url: QDesktopServices.openUrl(QUrl(u)))
                    row.addWidget(connect)
                    row.addStretch()
                    lay.addLayout(row)
            elif svc["id"] == "pathofbuilding":
                # Bundled/installed PoB: point Kalandra at the actual program.
                row = QHBoxLayout()
                auto = QPushButton("Auto-detect (bundled)")
                auto.setProperty("gem", "emerald")
                auto.clicked.connect(self._pob_autodetect)
                row.addWidget(auto)
                pick = QPushButton("Pick PoB .exe…")
                pick.clicked.connect(self._pob_pick)
                row.addWidget(pick)
                site = QPushButton("Website ↗")
                site.clicked.connect(lambda: QDesktopServices.openUrl(
                    QUrl(SERVICE_URLS.get("pathofbuilding", ""))))
                row.addWidget(site)
                row.addStretch()
                lay.addLayout(row)
                self.pob_path_lbl = QLabel(
                    self.config.get("pob_exe") or "No PoB path set yet.")
                self.pob_path_lbl.setWordWrap(True)
                self.pob_path_lbl.setStyleSheet("color:#9aa4b2;font-size:10px;")
                lay.addWidget(self.pob_path_lbl)
            else:  # link
                row = QHBoxLayout()
                url = SERVICE_URLS.get(svc["id"], "")
                if url:
                    open_btn = QPushButton("Open site ↗")
                    open_btn.setToolTip(url)
                    open_btn.clicked.connect(
                        lambda _, u=url: QDesktopServices.openUrl(QUrl(u)))
                    row.addWidget(open_btn)
                # Sites with accounts (Maxroll, Mobalytics, FilterBlade, the
                # wiki) also get a direct sign-in button + a remembered
                # username so Kalandra can reference YOUR profiles/guides.
                if svc["id"] in LINK_SIGNIN_URLS:
                    li = QPushButton("Open sign-in ↗")
                    li.setToolTip(LINK_SIGNIN_URLS[svc["id"]])
                    li.clicked.connect(
                        lambda _, u=LINK_SIGNIN_URLS[svc["id"]]:
                        QDesktopServices.openUrl(QUrl(u)))
                    row.addWidget(li)
                    user_edit = QLineEdit(self.config.get(
                        f"{svc['id']}_username", ""))
                    user_edit.setPlaceholderText("your username there (optional)")

                    def _mk_saver(sid, w):
                        def _save():
                            self.config[f"{sid}_username"] = w.text().strip()
                            save_config(self.config)
                        return _save
                    user_edit.editingFinished.connect(
                        _mk_saver(svc["id"], user_edit))
                    row.addWidget(user_edit, 1)
                else:
                    lbl = QLabel("Data-source / tool integration (no login "
                                 "required).")
                    lbl.setStyleSheet("color:#7d8694;font-size:11px;")
                    row.addWidget(lbl, 1)
                lay.addLayout(row)
            return box

        # -- GGG (pathofexile.com) OAuth ---------------------------------------
        def _build_ggg_oauth_row(self, lay):
            row = QHBoxLayout()
            self.ggg_connect_btn = QPushButton("Connect GGG account (OAuth)")
            self.ggg_connect_btn.setProperty("gem", "sapphire")
            self.ggg_connect_btn.setToolTip(
                "Runs the official OAuth 2.1 PKCE sign-in in your browser.\n"
                "Needs the client_id GGG issues for Kalandra (see the field →).")
            self.ggg_connect_btn.clicked.connect(self._start_ggg_oauth)
            row.addWidget(self.ggg_connect_btn)
            test_btn = QPushButton("Test PoE2 API (no login)")
            test_btn.setToolTip("Fetches the public PoE2 league list to prove "
                                "the API is reachable from your machine.")
            test_btn.clicked.connect(self._test_ggg_api)
            row.addWidget(test_btn)
            row.addStretch()
            lay.addLayout(row)
            cid_row = QHBoxLayout()
            cid_row.addWidget(QLabel("client_id:"))
            self.ggg_cid_edit = QLineEdit(self.config.get("ggg_client_id", ""))
            self.ggg_cid_edit.setPlaceholderText(
                "paste the client_id GGG sends back (GGG_OAuth_Application_Letter.md)")
            self.ggg_cid_edit.editingFinished.connect(self._save_ggg_cid)
            cid_row.addWidget(self.ggg_cid_edit, 1)
            lay.addLayout(cid_row)
            self.ggg_status = QLabel("")
            self.ggg_status.setWordWrap(True)
            self.ggg_status.setStyleSheet("color:#9aa4b2;font-size:11px;")
            lay.addWidget(self.ggg_status)

        def _save_ggg_cid(self):
            self.config["ggg_client_id"] = self.ggg_cid_edit.text().strip()
            save_config(self.config)

        def _start_ggg_oauth(self):
            self._save_ggg_cid()
            cid = self.config.get("ggg_client_id", "")
            if not cid:
                # No misleading browser jump (the docs page there is the old
                # PoE1-era OAuth reference) — explain the real state instead.
                self.ggg_status.setText(
                    "⚠ Not connectable yet — GGG hasn't opened public PoE2 "
                    "OAuth. They issue client_ids per app: email "
                    "docs/GGG_OAuth_Application_Letter.md to "
                    "oauth@grindinggear.com, paste the client_id above when it "
                    "arrives, then click Connect. Until then, character import "
                    "works WITHOUT login via the Character Selector "
                    "(ladder/profile fetch) and PoB's own import.")
                return
            try:
                from core_engine.oauth_pkce import run_pkce_flow
            except Exception as e:
                self.ggg_status.setText(f"OAuth module failed to load: {e}")
                return
            self.ggg_connect_btn.setEnabled(False)
            self.ggg_status.setText("Waiting for you to approve the sign-in in "
                                    "your browser (3-minute window)...")

            def _open(url):
                QDesktopServices.openUrl(QUrl(url))

            def _work():
                res = run_pkce_flow(cid, _open)
                def _done():
                    self.ggg_connect_btn.setEnabled(True)
                    if res.get("ok"):
                        tok = res["token"]
                        if self.am:
                            self.am.set_secret("pathofexile", json.dumps(tok))
                        self.ggg_status.setText("🟢 GGG account linked! Token stored "
                                                "securely in your OS keychain.")
                    else:
                        self.ggg_status.setText(f"⚠ OAuth failed: {res.get('error')}")
                QTimer.singleShot(0, _done)
            threading.Thread(target=_work, daemon=True).start()

        def _test_ggg_api(self):
            self.ggg_status.setText("Contacting the PoE2 trade API...")
            def _work():
                try:
                    import requests as _rq
                    from core_engine.poe_account import TRADE2_LEAGUES_URL, HEADERS
                    r = _rq.get(TRADE2_LEAGUES_URL, headers=HEADERS, timeout=12)
                    if r.status_code == 200:
                        names = [e.get("id") or e.get("text")
                                 for e in r.json().get("result", [])]
                        names = [n for n in names if n][:5]
                        msg = (f"🟢 PoE2 API reachable — current leagues: "
                               f"{', '.join(names)}" if names else
                               "⚠ API responded but listed no leagues.")
                    else:
                        msg = (f"⚠ API returned HTTP {r.status_code} "
                               f"(rate-limited or blocked; try again in a minute).")
                except Exception as e:
                    msg = f"⚠ Test failed: {e}"
                QTimer.singleShot(0, lambda: self.ggg_status.setText(msg))
            threading.Thread(target=_work, daemon=True).start()

        # -- Email provider picker ----------------------------------------------
        def _build_email_row(self, lay):
            # ---- Modern path first: Gmail OAuth 2.0 + PKCE + XOAUTH2 ------
            # No app passwords: sign-in happens AT Google with your MFA;
            # Kalandra stores only revocable tokens, only in the OS keychain.
            hdr = QLabel("<b>Gmail (OAuth 2.0 — recommended)</b>")
            hdr.setStyleSheet("color:#8fd6a0;font-size:12px;")
            lay.addWidget(hdr)
            g_row = QHBoxLayout()
            self.gm_addr_edit = QLineEdit(self.config.get("email_address", ""))
            self.gm_addr_edit.setPlaceholderText("you@gmail.com")
            g_row.addWidget(self.gm_addr_edit, 1)
            self.gm_connect_btn = QPushButton("Connect Gmail (OAuth)")
            self.gm_connect_btn.setProperty("gem", "emerald")
            self.gm_connect_btn.setToolTip(
                "OAuth 2.0 installed-app flow with PKCE: your browser signs "
                "in at Google (MFA and all); Kalandra receives a revocable, "
                "mail-only token — never your password.")
            self.gm_connect_btn.clicked.connect(self._start_gmail_oauth)
            g_row.addWidget(self.gm_connect_btn)
            lay.addLayout(g_row)
            cid_row = QHBoxLayout()
            self.gm_cid_edit = QLineEdit(self.config.get("google_client_id", ""))
            self.gm_cid_edit.setPlaceholderText("Google OAuth client_id (Desktop app)")
            cid_row.addWidget(self.gm_cid_edit, 1)
            self.gm_csec_edit = QLineEdit(self.config.get("google_client_secret", ""))
            self.gm_csec_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.gm_csec_edit.setPlaceholderText("client_secret")
            cid_row.addWidget(self.gm_csec_edit, 1)
            mk_btn = QPushButton("Create one ↗")
            mk_btn.setToolTip("console.cloud.google.com → Credentials → "
                              "OAuth client ID → Desktop app (free, one-time).")
            mk_btn.clicked.connect(lambda: QDesktopServices.openUrl(
                QUrl("https://console.cloud.google.com/apis/credentials")))
            cid_row.addWidget(mk_btn)
            lay.addLayout(cid_row)
            self.gm_status = QLabel("")
            self.gm_status.setWordWrap(True)
            self.gm_status.setStyleSheet("color:#9aa4b2;font-size:11px;")
            lay.addWidget(self.gm_status)

            # ---- Legacy fallback (other providers / no OAuth client) ------
            row = QHBoxLayout()
            row.addWidget(QLabel("Other provider (legacy app password):"))
            self.email_combo = QComboBox()
            for label, signin, apppass in EMAIL_PROVIDERS:
                self.email_combo.addItem(label, (signin, apppass))
            saved = self.config.get("email_provider", "Gmail")
            i = self.email_combo.findText(saved)
            self.email_combo.setCurrentIndex(i if i >= 0 else 0)  # Gmail default
            self.email_combo.currentTextChanged.connect(self._on_email_provider)
            row.addWidget(self.email_combo, 1)
            signin_btn = QPushButton("Open sign-in")
            signin_btn.clicked.connect(lambda: self._open_email_url(0))
            row.addWidget(signin_btn)
            app_btn = QPushButton("Get app password")
            app_btn.setToolTip("Legacy: a static secret that bypasses MFA. "
                               "Use the OAuth connect above when you can.")
            app_btn.clicked.connect(lambda: self._open_email_url(1))
            row.addWidget(app_btn)
            lay.addLayout(row)
            tok_row = QHBoxLayout()
            self.email_token_edit = QLineEdit()
            self.email_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.email_token_edit.setPlaceholderText(
                "address:app-password (stored in your OS keychain)")
            tok_row.addWidget(self.email_token_edit, 1)
            save = QPushButton("Save")
            save.clicked.connect(self._save_email_token)
            tok_row.addWidget(save)
            lay.addLayout(tok_row)

        def _start_gmail_oauth(self):
            addr = self.gm_addr_edit.text().strip()
            cid = self.gm_cid_edit.text().strip()
            csec = self.gm_csec_edit.text().strip()
            self.config["email_address"] = addr
            self.config["google_client_id"] = cid
            # NOTE: desktop-app client_secret is not confidential (RFC 8252);
            # PKCE carries the security. Stored in config for convenience.
            self.config["google_client_secret"] = csec
            save_config(self.config)
            if not addr or not cid:
                self.gm_status.setText(
                    "⚠ Enter your Gmail address and a Google OAuth client_id "
                    "('Create one ↗' walks you there — Desktop app type).")
                return
            try:
                from core_engine.email_oauth import run_gmail_oauth, store_bundle
            except Exception as e:
                self.gm_status.setText(f"OAuth module failed to load: {e}")
                return
            self.gm_connect_btn.setEnabled(False)
            self.gm_status.setText("Waiting for the Google sign-in in your "
                                   "browser (3-minute window)…")

            def _work():
                res = run_gmail_oauth(
                    cid, csec,
                    lambda u: QDesktopServices.openUrl(QUrl(u)))

                def _done():
                    self.gm_connect_btn.setEnabled(True)
                    if res.get("ok"):
                        ok = store_bundle(self.am, addr, res["token"])
                        self.gm_status.setText(
                            "🟢 Gmail connected via OAuth — token in your OS "
                            "keychain, revocable at myaccount.google.com/"
                            "permissions." if ok else
                            "⚠ Connected, but keychain storage failed "
                            "(pip install keyring).")
                    else:
                        self.gm_status.setText(f"⚠ OAuth failed: {res.get('error')}")
                QTimer.singleShot(0, _done)
            threading.Thread(target=_work, daemon=True).start()

        def _on_email_provider(self, label):
            self.config["email_provider"] = label
            save_config(self.config)

        def _open_email_url(self, which):
            data = self.email_combo.currentData()
            if data:
                QDesktopServices.openUrl(QUrl(data[which]))

        def _save_email_token(self):
            if self.am:
                ok = self.am.set_secret("email", self.email_token_edit.text().strip())
                self.email_token_edit.clear()
                if ok:
                    QMessageBox.information(self, "Saved", "Email credentials stored.")
                else:
                    QMessageBox.warning(self, "Storage disabled",
                                        "Install keyring (pip install keyring) "
                                        "for secure storage.")

        def _pob_set(self, exe):
            self.config["pob_exe"] = exe
            self.config["pob_install_dir"] = os.path.dirname(exe)
            if not self.config.get("pob_builds_dir"):
                for c in (os.path.join(os.path.dirname(exe), "Builds"),
                          os.path.join(os.path.expanduser("~"), "Documents",
                                       "Path of Building", "Builds")):
                    if os.path.isdir(c):
                        self.config["pob_builds_dir"] = c
                        break
            save_config(self.config)
            self.pob_path_lbl.setText(
                f"✓ {exe}\nBuilds: {self.config.get('pob_builds_dir') or 'not found yet'}")

        def _pob_autodetect(self):
            """Find the PoB bundled inside the Kalandra folder (tools/…)."""
            roots = ["tools", "."]
            for root in roots:
                for dirpath, _dn, files in os.walk(root):
                    if dirpath.count(os.sep) > 4:
                        continue
                    for fn in files:
                        if fn.lower().endswith(".exe") and "building" in fn.lower():
                            self._pob_set(os.path.abspath(os.path.join(dirpath, fn)))
                            return
            self.pob_path_lbl.setText(
                "No PoB .exe found under tools/ — use 'Pick PoB .exe…' to "
                "point at it directly.")

        def _pob_pick(self):
            from PyQt6.QtWidgets import QFileDialog
            p, _ = QFileDialog.getOpenFileName(self, "Locate Path of Building",
                                               "", "Programs (*.exe)")
            if p:
                self._pob_set(p)

        def _save_secret(self, service_id):
            edit = self.fields.get(service_id)
            if edit and self.am:
                ok = self.am.set_secret(service_id, edit.text().strip())
                edit.clear()
                if ok:
                    QMessageBox.information(self, "Saved", f"Stored credentials for '{service_id}'.")
                else:
                    QMessageBox.warning(self, "Storage disabled",
                                        "Couldn't store the secret. Install keyring "
                                        "(pip install keyring) for secure storage.")

        def _clear_secret(self, service_id):
            if self.am:
                self.am.clear(service_id)
                QMessageBox.information(self, "Cleared", f"Removed credentials for '{service_id}'.")

        def _on_brain_change(self, _idx):
            pid = self.brain_combo.currentData() or "openai"
            self.config["ai_brain"] = pid
            save_config(self.config)
            self._reload_models(pid)
            self._refresh_usage_label()
            self._refresh_ai_key_row()

        def _refresh_ai_key_row(self):
            pid = self.brain_combo.currentData() or "openai"
            label = self.brain_combo.currentText() or pid
            self.ai_key_edit.clear()
            self.ai_key_edit.setPlaceholderText(f"Paste your {label} API key")
            self.ai_key_btn.setEnabled(bool(API_KEY_URLS.get(pid)))
            def _check():
                ok = bool(self.am and self.am.is_connected(pid))
                QTimer.singleShot(0, lambda: self.ai_key_status.setText(
                    f"🟢 {label}: key saved in your OS keychain." if ok
                    else f"⚪ {label}: no key saved yet."))
            threading.Thread(target=_check, daemon=True).start()

        def _save_ai_key(self):
            pid = self.brain_combo.currentData() or "openai"
            if self.am and self.am.set_secret(pid, self.ai_key_edit.text().strip()):
                self.ai_key_status.setText("🟢 Key saved.")
            else:
                self.ai_key_status.setText("⚠ Couldn't store the key "
                                           "(pip install keyring).")
            self.ai_key_edit.clear()

        def _clear_ai_key(self):
            pid = self.brain_combo.currentData() or "openai"
            if self.am:
                self.am.clear(pid)
            self.ai_key_status.setText("Key cleared.")

        def _open_ai_key_page(self):
            pid = self.brain_combo.currentData() or "openai"
            url = API_KEY_URLS.get(pid)
            if url:
                QDesktopServices.openUrl(QUrl(url))

        def _reload_models(self, pid):
            prov = (self._providers or {}).get(pid, {})
            models = prov.get("models", [])
            self.model_combo.blockSignals(True)
            self.model_combo.clear()
            self.model_combo.addItems(models)
            chosen = self.config.get(f"{pid}_model") or prov.get("default_model", "")
            if chosen:
                self.model_combo.setCurrentText(chosen)
            self.model_combo.blockSignals(False)
            # Persist the resolved default so the engine and UI agree.
            if chosen:
                self.config[f"{pid}_model"] = chosen
                save_config(self.config)

        def _on_model_change(self, text):
            pid = self.brain_combo.currentData() or "openai"
            text = (text or "").strip()
            if text:
                self.config[f"{pid}_model"] = text
                save_config(self.config)

        def _on_budget_change(self):
            try:
                self.config["token_budget"] = max(0, int(self.budget_edit.text().strip() or "0"))
            except Exception:
                self.config["token_budget"] = 0
            save_config(self.config)
            self._refresh_usage_label()

        def _refresh_usage_label(self):
            if not hasattr(self, "usage_lbl"):
                return
            txt = ""
            if self.usage_provider:
                try:
                    txt = self.usage_provider() or ""
                except Exception:
                    txt = ""
            self.usage_lbl.setText(txt or "No AI usage yet this session.")

        def _on_speed_change(self, val):
            try:
                self.config["crawl_concurrency"] = int(val.split()[0])
                save_config(self.config)
            except Exception:
                pass

        def _on_voice_change(self, _idx):
            self.config["voice_id"] = self.voice_combo.currentData() or ""
            save_config(self.config)


if PYQT_AVAILABLE:
    class CharacterDialog(KalandraFrameDialog):
        """Pull your PoE2 characters (no GGG OAuth) + pick the active league."""
        leagues_ready = pyqtSignal(list)
        chars_ready = pyqtSignal(dict)
        builds_ready = pyqtSignal(object)
        sess_known = pyqtSignal(bool)
        code_loaded = pyqtSignal(object)

        def __init__(self, poe_account, account_manager, config, parent=None,
                     on_select=None, pob_bridge=None, on_load_sim=None,
                     on_load_build_file=None):
            super().__init__(f"KALANDRA v{KALANDRA_VERSION} — CHARACTERS",
                             parent)
            self.acc = poe_account
            self.am = account_manager
            self.config = config
            self.on_select = on_select
            self.pob = pob_bridge
            self.on_load_sim = on_load_sim
            self.on_load_build_file = on_load_build_file
            # ~30% taller than the old default so the middle buttons breathe
            # (the frame border eats ~110px of height).
            self.setMinimumSize(520, 560)
            try:
                scr = QApplication.primaryScreen()
                avail = scr.availableGeometry() if scr else None
                h = 940
                if avail is not None:
                    h = min(h, max(560, avail.height() - 80))
                self.resize(820, h)
            except Exception:
                self.resize(820, 900)
            self.setStyleSheet(
                "QDialog{background:#14181f;color:#e8e8e8;}QLabel{color:#e8e8e8;}"
                "QLineEdit,QComboBox{background:#0c0f14;color:#fff;border:1px solid #3a4150;padding:4px;border-radius:4px;}"
                "QComboBox QAbstractItemView{background:#0c0f14;color:#ffffff;"
                "selection-background-color:#3a4658;selection-color:#ffffff;"
                "border:1px solid #4a5468;outline:none;}"
                "QListWidget{background:#0c0f14;color:#fff;border:1px solid #3a4150;}"
                "QPushButton{background:#2a3140;color:#fff;border:1px solid #444c5c;padding:5px 10px;border-radius:5px;}"
                "QPushButton:hover{background:#39424f;}")
            self.leagues_ready.connect(self._populate_leagues)
            self.chars_ready.connect(self._populate_chars)
            self.builds_ready.connect(self._populate_builds)
            self.sess_known.connect(self._on_sess_known)
            self.code_loaded.connect(self._on_code_loaded)
            self._scanning_builds = False
            self._loading_code = False
            self._build_ui()
            self._refresh_leagues()
            # Reading the OS keychain can stall for a second on first access, so
            # check whether a POESESSID is saved OFF the UI thread.
            threading.Thread(target=self._sess_worker, daemon=True).start()

        def _build_ui(self):
            root = self.body
            root.addWidget(QLabel("<b>Path of Exile 2 characters</b>"))
            hint = QLabel("Heads-up: GGG's API now <i>technically</i> supports PoE2 characters "
                          "(<b>GET /character</b> with <b>realm=poe2</b>), but it requires an "
                          "approved OAuth <b>client_id</b>, and GGG hasn't opened public app "
                          "registration — so personal roster sync isn't usable yet. The "
                          "recommended route is <b>Path of Building</b> (paste a code or load a "
                          "saved build below). The public <b>ladder</b> also works via "
                          "<b>Browse ladder</b>. The account sync is ready for when GGG grants "
                          "API clients.")
            hint.setWordWrap(True)
            hint.setStyleSheet("color:#9aa4b2;font-size:11px;")
            root.addWidget(hint)

            # --- Path of Building section (the recommended route) ---
            pob_box = QFrame()
            pob_box.setStyleSheet("QFrame{border:1px solid #2a3a2a;border-radius:6px;}")
            pl = QVBoxLayout(pob_box)
            pl.addWidget(QLabel("<b>Path of Building (recommended)</b>"))
            pl.addWidget(QLabel("Paste a PoB code, or a pobb.in / poe.ninja build link:"))
            self.pob_edit = QLineEdit()
            self.pob_edit.setPlaceholderText("PoB code or https://pobb.in/... / poe.ninja build link")
            pl.addWidget(self.pob_edit)
            prow = QHBoxLayout()
            load_btn = QPushButton("Load build")
            load_btn.setToolTip("Decode the code and load it into Kalandra (no PoB install needed).")
            load_btn.clicked.connect(self._load_pob_code)
            prow.addWidget(load_btn)
            open_pob = QPushButton("Open in PoB app")
            open_pob.setToolTip("Copy the code and launch the Path of Building app (if installed).")
            open_pob.clicked.connect(self._open_in_pob)
            prow.addWidget(open_pob)
            pl.addLayout(prow)
            load_builds = QPushButton("Load my saved PoB builds")
            load_builds.clicked.connect(self._load_pob_builds)
            pl.addWidget(load_builds)
            root.addWidget(pob_box)

            ladder_lbl = QLabel("— or browse the public ladder / wait for GGG's account API —")
            ladder_lbl.setStyleSheet("color:#7d8694;font-size:10px;")
            root.addWidget(ladder_lbl)

            row1 = QHBoxLayout()
            row1.addWidget(QLabel("Account name:"))
            self.account_edit = QLineEdit(self.config.get("account_name", ""))
            self.account_edit.setPlaceholderText("Your pathofexile.com account name")
            row1.addWidget(self.account_edit)
            root.addLayout(row1)

            row2 = QHBoxLayout()
            row2.addWidget(QLabel("POESESSID (optional):"))
            self.sess_edit = QLineEdit()
            self.sess_edit.setEchoMode(QLineEdit.EchoMode.Password)
            # Placeholder is set now; the real "saved?" check runs in a thread
            # (see _sess_worker) and updates this via the sess_known signal.
            self.sess_edit.setPlaceholderText("only needed for private profiles")
            row2.addWidget(self.sess_edit)
            root.addLayout(row2)

            row3 = QHBoxLayout()
            row3.addWidget(QLabel("League:"))
            self.league_combo = QComboBox()
            row3.addWidget(self.league_combo, 1)
            self.refresh_btn = QPushButton("Sync my account")
            self.refresh_btn.clicked.connect(self._refresh_chars)
            row3.addWidget(self.refresh_btn)
            self.ladder_btn = QPushButton("Browse ladder")
            self.ladder_btn.clicked.connect(self._browse_ladder)
            row3.addWidget(self.ladder_btn)
            root.addLayout(row3)

            self.list = QListWidget()
            self.list.currentItemChanged.connect(self._sync_orb_combo)
            root.addWidget(self.list, 1)

            # Per-character companion orb: SEE and SET which orb speaks for
            # each character. Saved in config['character_orbs'] by build
            # name; setting a character active applies its orb to the mirror.
            orow = QHBoxLayout()
            orow.addWidget(QLabel("Companion orb for selected:"))
            # ORDER MATTERS: the label must exist and the combo must be fully
            # populated BEFORE the signal is connected — addItem fires
            # currentIndexChanged, and a handler touching a not-yet-created
            # label crashed the whole dialog mid-__init__ (2026-07-04: the
            # selector "wouldn't open").
            self.orb_lbl = QLabel("")
            self.orb_lbl.setStyleSheet("color:#7d8694;font-size:10px;")
            self.orb_combo = QComboBox()
            try:
                from gui_overlay.mirror_window import KalandraOverlayApp as _K
                orbs = _K.COMPANION_ORBS
            except Exception:
                orbs = [("Divine Orb", "divine")]
            self.orb_combo.blockSignals(True)
            for label, slug in orbs:
                self.orb_combo.addItem(label, slug)
            self.orb_combo.blockSignals(False)
            self.orb_combo.currentIndexChanged.connect(self._assign_orb)
            orow.addWidget(self.orb_combo, 1)
            orow.addWidget(self.orb_lbl)
            root.addLayout(orow)

            btns = QHBoxLayout()
            self.select_btn = QPushButton("Set active character")
            self.select_btn.clicked.connect(self._select)
            pob_btn = QPushButton("How to load in PoB")
            pob_btn.clicked.connect(self._pob_hint)
            btns.addWidget(self.select_btn)
            btns.addWidget(pob_btn)
            root.addLayout(btns)

            self.status = QLabel("")
            self.status.setStyleSheet("color:#9aa4b2;font-size:11px;")
            self.status.setWordWrap(True)
            root.addWidget(self.status)

        # -- saved POESESSID check (off the UI thread) --
        def _sess_worker(self):
            saved = False
            try:
                saved = bool(self.am.get_secret("poesessid")) if self.am else False
            except Exception:
                saved = False
            self.sess_known.emit(saved)

        def _on_sess_known(self, saved):
            try:
                self.sess_edit.setPlaceholderText(
                    "saved" if saved else "only needed for private profiles")
            except Exception:
                pass

        # -- leagues --
        def _refresh_leagues(self):
            self.status.setText("Fetching current leagues...")
            threading.Thread(target=self._leagues_worker, daemon=True).start()

        def _leagues_worker(self):
            try:
                leagues = self.acc.get_leagues() if self.acc else ["Standard"]
            except Exception:
                leagues = ["Standard"]
            self.leagues_ready.emit(leagues)

        def _populate_leagues(self, leagues):
            self.league_combo.clear()
            self.league_combo.addItems(leagues)
            default = self.config.get("league") or (
                self.acc.default_softcore_league(leagues) if self.acc else "Standard")
            idx = self.league_combo.findText(default)
            if idx >= 0:
                self.league_combo.setCurrentIndex(idx)
            self.status.setText(f"Default league: {self.league_combo.currentText()}")

        # -- characters --
        def _refresh_chars(self):
            account = self.account_edit.text().strip()
            if not account:
                self.status.setText("Enter your account name first.")
                return
            # Persist account name + optional POESESSID.
            self.config["account_name"] = account
            self.config["league"] = self.league_combo.currentText()
            save_config(self.config)
            if self.am and self.sess_edit.text().strip():
                self.am.set_secret("poesessid", self.sess_edit.text().strip())
            self.status.setText("Syncing characters from your GGG account...")
            self.refresh_btn.setEnabled(False)
            threading.Thread(target=self._chars_worker,
                             args=(account, self.league_combo.currentText()), daemon=True).start()

        def _chars_worker(self, account, league):
            sess = self.am.get_secret("poesessid") if self.am else None
            try:
                result = self.acc.get_characters(account, league=league, poesessid=sess)
            except Exception as e:
                result = {"ok": False, "characters": [], "error": str(e)}
            self.chars_ready.emit(result)

        def _browse_ladder(self):
            league = self.league_combo.currentText() or "Standard"
            self.status.setText(f"Fetching public ladder for {league}...")
            self.ladder_btn.setEnabled(False)
            threading.Thread(target=self._ladder_worker, args=(league,), daemon=True).start()

        def _ladder_worker(self, league):
            try:
                result = self.acc.get_ladder(league)
            except Exception as e:
                result = {"ok": False, "characters": [], "error": str(e)}
            self.chars_ready.emit(result)

        def _populate_chars(self, result):
            self.refresh_btn.setEnabled(True)
            self.ladder_btn.setEnabled(True)
            self.list.clear()
            if not result.get("ok"):
                self.status.setText(result.get("error") or "Unknown error.")
                return
            chars = result.get("characters", [])
            if not chars:
                self.status.setText("No characters found.")
                return
            for c in chars:
                rank = f"#{c['rank']} " if c.get("rank") else ""
                acct = f" — {c['account']}" if c.get("account") else ""
                label = f"{rank}{c['name']} — {c['class']} (Lvl {c['level']}) [{c['league']}]{acct}"
                self.list.addItem(QListWidgetItem(label))
            self.status.setText(f"Loaded {len(chars)} characters.")

        def _select(self):
            item = self.list.currentItem()
            if not item:
                self.status.setText("Pick a character or build from the list first.")
                return
            # If this row is a saved PoB build (carries its .xml path), LOAD it so
            # the AI can actually see it — not just set a name label.
            data = item.data(Qt.ItemDataRole.UserRole)
            loaded = False
            if isinstance(data, dict) and data.get("path") and self.on_load_build_file:
                try:
                    loaded = bool(self.on_load_build_file(data["path"]))
                except Exception as e:
                    self.status.setText(f"Could not load that build: {e}")
            if self.on_select:
                self.on_select(item.text())
            if loaded:
                self.status.setText("Active build loaded — the Orb can now see it. "
                                    "Ask it about your build in the chat.")
            self.accept()

        # -- Path of Building --
        def _resolve_code(self):
            """Resolve the pasted text/link to a PoB code; show errors. Returns code|None."""
            if not self.pob:
                self.status.setText("PoB bridge not available.")
                return None
            raw = self.pob_edit.text().strip()
            if not raw:
                self.status.setText("Paste a PoB code or a pobb.in / poe.ninja link first.")
                return None
            code, msg = self.pob.resolve_link_to_code(raw)
            if not code:
                self.status.setText(msg)
            return code

        def _load_pob_code(self):
            """Decode the build and load it into Kalandra. No PoB install required.
            Resolving a pobb.in / poe.ninja link hits the network, so the whole
            resolve+decode runs OFF the UI thread."""
            if not self.pob:
                self.status.setText("PoB bridge not available.")
                return
            raw = self.pob_edit.text().strip()
            if not raw:
                self.status.setText("Paste a PoB code or a pobb.in / poe.ninja link first.")
                return
            if self._loading_code:
                return
            self._loading_code = True
            self.status.setText("Loading build...")
            threading.Thread(target=self._code_worker, args=(raw,), daemon=True).start()

        def _code_worker(self, raw):
            res = {"ok": False, "msg": "", "label": None, "code": None}
            try:
                code, msg = self.pob.resolve_link_to_code(raw)
                if not code:
                    res["msg"] = msg
                    self.code_loaded.emit(res)
                    return
                xml = self.pob.decode_pob_string(code)
                stats = self.pob.extract_character_data(xml)
                if not (isinstance(stats, dict) and "error" not in stats):
                    err = stats.get("error") if isinstance(stats, dict) else "unknown"
                    res["msg"] = ("Couldn't read that PoB code (" + str(err) + "). "
                                  "Make sure you copied the whole code.")
                    self.code_loaded.emit(res)
                    return
                res["label"] = (
                    f"{stats.get('class_name','?')} / {stats.get('ascendancy_name','None')} "
                    f"(Lvl {stats.get('level','?')}) — DPS {stats.get('total_dps','?')}, "
                    f"eHP {stats.get('ehp','?')}")
                res["code"] = code
                res["ok"] = True
            except Exception as e:
                res["msg"] = f"Load error: {e}"
            self.code_loaded.emit(res)

        def _on_code_loaded(self, res):
            self._loading_code = False
            if not res.get("ok"):
                self.status.setText(res.get("msg") or "Could not load build.")
                return
            label = res["label"]
            # Show it in the list AND set it active so it's clearly "loaded".
            item = QListWidgetItem("★ " + label)
            self.list.insertItem(0, item)
            self.list.setCurrentItem(item)
            if self.on_select:
                self.on_select(label)
            if self.on_load_sim:
                self.on_load_sim(res["code"])   # feed the headless sim (if set up)
            self.status.setText("Build loaded: " + label)

        def _open_in_pob(self):
            """Copy the code and launch the PoB app (separate from loading).

            NO modal dialog here: PoB steals the foreground the moment it
            launches, so an application-modal box pops up BEHIND it — the
            user can't see it, and every Kalandra window (including the
            always-on-top overlay) freezes until the invisible box is
            dismissed. The status line carries the message instead."""
            code = self._resolve_code()
            if not code:
                return
            try:
                QApplication.clipboard().setText(code)
            except Exception:
                pass
            ok, lmsg = self.pob.launch_path_of_building(self.config.get("pob_exe"))
            self.status.setText(("✓ " if ok else "⚠ ") + lmsg +
                                "  (build code is on your clipboard — paste "
                                "it into PoB's Import/Export)")

        def _load_pob_builds(self):
            if not self.pob:
                self.status.setText("PoB bridge not available.")
                return
            if self._scanning_builds:
                return                      # already running; ignore double-clicks
            self._scanning_builds = True
            self.status.setText("Scanning your Path of Building builds folder...")
            threading.Thread(target=self._builds_worker, daemon=True).start()

        def _builds_worker(self):
            """Scan for saved PoB builds OFF the UI thread (the scan walks the
            filesystem and parses XML, so it must never run on the UI thread)."""
            result = {"builds": [], "searched": [], "error": None,
                      "primary": None}
            try:
                try:
                    result["primary"] = self.pob.pob_settings_build_path(
                        self.config.get("pob_install_dir"))
                except Exception:
                    pass
                # Same truth as the dashboard's PoB (live) tab: prefer the
                # configured install dir, else derive it from the picked exe
                # (the tab's primary key), so both always scan ONE install.
                pob_install = self.config.get("pob_install_dir")
                if not pob_install and self.config.get("pob_exe"):
                    pob_install = os.path.dirname(self.config["pob_exe"])
                result["builds"] = self.pob.find_pob_builds(
                    self.config.get("pob_builds_dir"), pob_install_dir=pob_install)
                if not result["builds"]:
                    searched = list(self.pob._discovered_build_dirs())
                    if pob_install:
                        searched.insert(0, os.path.join(pob_install, "Builds"))
                    searched += self.pob.candidate_build_dirs()
                    result["searched"] = searched
            except Exception as e:
                result["error"] = str(e)
            self.builds_ready.emit(result)

        def _populate_builds(self, result):
            """Runs on the UI thread once the background scan finishes."""
            self._scanning_builds = False
            if result.get("error"):
                self.status.setText("Build scan error: " + result["error"])
                return
            builds = result.get("builds") or []
            self.list.clear()
            if not builds:
                scanned = "\n".join("  • " + d for d in result.get("searched", []))
                self.status.setText("No saved PoB builds found.")
                QMessageBox.information(
                    self, "No saved builds found",
                    "I looked for PoB build files (.xml) in:\n\n" + scanned +
                    "\n\nIf your builds are elsewhere, set \"pob_builds_dir\" in "
                    "data_engine/config.json to that folder. Or just paste a PoB "
                    "code above and click 'Load build'.")
                return
            for b in builds:
                cls = b.get("class_name", "?")
                lvl = b.get("level", "?")
                label = f"{b['name']} — {cls} (Lvl {lvl})"
                it = QListWidgetItem(label)
                # Carry the full build dict (incl. its .xml file path) on the item
                # so 'Set active character' can actually LOAD it into Kalandra.
                it.setData(Qt.ItemDataRole.UserRole, b)
                self.list.addItem(it)
            where = result.get("primary")
            self.status.setText(
                f"Found {len(builds)} saved PoB builds"
                + (f" (PoB's configured folder: {where})" if where else
                   " (PoB's Settings.xml not found — scanned the usual "
                   "folders)")
                + ". Select one and 'Set active'.")

        def _sel_char_name(self):
            it = self.list.currentItem()
            if not it:
                return None
            b = it.data(Qt.ItemDataRole.UserRole) or {}
            return b.get("name") or (it.text().split(" — ")[0] if it.text() else None)

        def _sync_orb_combo(self, *_a):
            """Show the selected character's assigned orb (or the global one)."""
            name = self._sel_char_name()
            if not name:
                return
            assigned = (self.config.get("character_orbs") or {}).get(name)
            slug = assigned or self.config.get("companion_orb", "divine")
            i = self.orb_combo.findData(slug)
            if i >= 0:
                self.orb_combo.blockSignals(True)
                self.orb_combo.setCurrentIndex(i)
                self.orb_combo.blockSignals(False)
            self.orb_lbl.setText("assigned" if assigned else "default")

        def _assign_orb(self, _i):
            if not hasattr(self, "orb_lbl") or not hasattr(self, "list"):
                return          # fired during construction — ignore
            name = self._sel_char_name()
            if not name:
                self.orb_lbl.setText("select a character first")
                return
            m = dict(self.config.get("character_orbs") or {})
            m[name] = self.orb_combo.currentData()
            self.config["character_orbs"] = m
            save_config(self.config)
            self.orb_lbl.setText("assigned ✓")

        def _pob_hint(self):
            account = self.account_edit.text().strip() or self.config.get("account_name", "")
            hint = self.acc.pob_import_hint(account) if self.acc else ""
            try:
                QApplication.clipboard().setText(account)
            except Exception:
                pass
            QMessageBox.information(self, "Load in Path of Building",
                                   hint + "\n\n(Your account name was copied to the clipboard.)")


# ----------------------------------------------------
# 4. INTERACTIVE OVERLAY APP
# ----------------------------------------------------
class KalandraOverlayApp(ParentClass):

    MEDALLION_LAYOUT = [
        {"id": "TopLeft",     "name": "Voice Toggle Button",            "fx": 0.280, "fy": 0.345, "fr": 0.052, "color": QColor(255, 60, 60),  "callback_name": "toggle_voice"},
        {"id": "TopCenter",   "name": "DB Sync / Refresh Button",       "fx": 0.499, "fy": 0.256, "fr": 0.055, "color": QColor(70, 120, 255), "callback_name": "trigger_database_scour_sync"},
        {"id": "TopRight",    "name": "Character Selector Button",      "fx": 0.722, "fy": 0.345, "fr": 0.052, "color": QColor(70, 255, 120), "callback_name": "select_active_character"},
        {"id": "BottomLeft",  "name": "Screen Capture / Recording Button", "fx": 0.206, "fy": 0.589, "fr": 0.064, "color": QColor(255, 40, 40),  "callback_name": None},
        {"id": "BottomRight", "name": "Configuration Settings Button",  "fx": 0.799, "fy": 0.589, "fr": 0.064, "color": QColor(70, 160, 255), "callback_name": "show_settings_alert"},
    ] if PYQT_AVAILABLE else []

    ORB_CENTER_FX = 0.500
    ORB_CENTER_FY = 0.490
    ORB_RADIUS_FR = 0.105

    # The currency orbs a player can pick as their floating companion. Each maps
    # to assets/orbs/2d/<slug>.png (and, later, 3d/<slug>.glb). Falls back to the
    # bundled divine_orb.png, then to a procedural orb, so a missing file is fine.
    COMPANION_ORBS = [
        ("Divine Orb", "divine"),
        ("Orb of Annulment", "annulment"),
        ("Chaos Orb", "chaos"),
        ("Regal Orb", "regal"),
        ("Orb of Augmentation", "augmentation"),
        ("Orb of Transmutation", "transmutation"),
        ("Orb of Chance", "chance"),
        ("Exalted Orb", "exalted"),
        ("Vaal Orb", "vaal"),
        ("Orb of Alchemy", "alchemy"),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Kalandra Overlay Core  v{KALANDRA_VERSION}")
        self.resize(460, 460)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            # .Window, NOT .Tool: Windows hides Tool windows from the
            # taskbar + Alt-Tab, which made Kalandra look "not running".
            Qt.WindowType.NoDropShadowWindowHint |
            Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("background: transparent; border: none;")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Interactive states
        self.voice_active = False
        self.sync_active = False
        self.recording_active = False
        self.menu_active = False
        self.active_character = "None"
        self.char_notify = False      # badge the char selector when a build is ready to view

        # Animation state
        self.time_counter = 0.0
        self.bobbing_amplitude = 10.0
        self.bobbing_speed = 0.05
        self.current_y_offset = 0.0
        self.flash_intensity = 0.0
        self.hovered_button = None
        self.buttons = []
        self.opacity_multiplier = 0.97
        # Cache of pre-scaled pixmaps, keyed (name, w, h). Smooth-rescaling the
        # mirror + orb art EVERY frame was the top CPU cost on weak hardware.
        self._px_cache = {}

        # Talking-orb lip-sync state + tunable mouth geometry (fractions of the orb).
        self.mouth_open = 0.0
        self.is_talking = False
        self.recording_consent_given = False
        # Subtitle (the orb's spoken reply, revealed like karaoke).
        self.subtitle_full = ""
        self.subtitle_shown = ""
        self.subtitle_start = 0.0
        self.subtitle_dur = 0.0
        self.current_build_summary = ""   # full PoB build text fed to the AI
        self.current_build_full = None    # structured parse, drives tag-based RAG
        self.current_build_xml = None     # decoded PoB XML (for the headless sim)
        self.current_sim_stats = None     # live numbers from the LuaJIT sim (if up)
        self.reserve = None               # Unique/BIS reserve store (lazy, optional)
        try:
            self.reserve = ReserveTracker() if ReserveTracker else None
        except Exception:
            self.reserve = None
        self.corrections = None           # verified-fact overrides for the AI
        try:
            self.corrections = KnowledgeCorrections() if KnowledgeCorrections else None
        except Exception:
            self.corrections = None
        self.issues = None                # bug/changelog tracker
        try:
            self.issues = IssueTracker() if IssueTracker else None
        except Exception:
            self.issues = None
        # AI usage tracking + recent chat history (for mid-conversation model
        # switching with no lapse in continuity).
        self.session_tokens = 0
        self.session_prompts = 0
        self._budget_warned_at = None
        self.chat_history = []            # list of (role, text), recent turns
        self.orb_mouth_fy = 0.72      # vertical line where the "jaw" splits
        self.orb_mouth_x0 = 0.32      # mouth band left
        self.orb_mouth_x1 = 0.68      # mouth band right
        self.orb_jaw_max = 0.07       # max jaw drop as fraction of orb height

        # Sync button state: blink while syncing (speed tracks pages/min) + a
        # notification badge when startup finds data is out of date.
        self.sync_rate = 0.0
        self.sync_needed = False
        self.blink_phase = 0.0

        # Config
        self.config = load_config()

        # Assets
        self.assets_dir = "gui_overlay/assets"
        self.mirror_path = os.path.join(self.assets_dir, "mirror_of_kalandra.png")
        self.orb_path = os.path.join(self.assets_dir, "divine_orb.png")
        os.makedirs(self.assets_dir, exist_ok=True)
        self.mirror_pixmap = QPixmap(self.mirror_path) if os.path.exists(self.mirror_path) else None
        self.orb_pixmap = None
        self._load_companion_orb()

        # Viseme sprite face (lip-sync): optional PNGs in gui_overlay/assets/visemes/
        # named mouth_A.png .. mouth_H.png and mouth_X.png (rest). If present, the
        # orb swaps these while talking instead of the procedural jaw-drop.
        self.viseme_dir = os.path.join(self.assets_dir, "visemes")
        self.viseme_pixmaps = {}
        for shape in ("A", "B", "C", "D", "E", "F", "G", "H", "X"):
            p = os.path.join(self.viseme_dir, f"mouth_{shape}.png")
            if os.path.exists(p):
                pm = QPixmap(p)
                if not pm.isNull():
                    self.viseme_pixmaps[shape] = pm
        self.has_visemes = len(self.viseme_pixmaps) >= 2
        self.current_viseme = "X"

        # Signal bridge for background threads
        self.signals = WorkerSignals()
        self.signals.log.connect(lambda c, m: logger.log_event(c, m))
        self.signals.sync_state.connect(self._set_sync_state)
        self.signals.sync_finished.connect(self._on_sync_finished)
        self.signals.voice_result.connect(self._on_voice_result)
        self.signals.record_finished.connect(self._on_record_finished)
        self.signals.export_finished.connect(self._on_export_finished)
        self.signals.chars_finished.connect(self._on_chars_finished)
        self.signals.death_captured.connect(self._on_death_captured)
        self.signals.mouth.connect(self._set_mouth)
        self.signals.viseme.connect(self._set_viseme)
        self.signals.speaking.connect(self._set_talking)
        self.signals.subtitle.connect(self._set_subtitle)
        self.signals.sync_progress.connect(self._set_sync_rate)
        self.signals.sync_needed.connect(self._set_sync_needed)
        self.signals.open_build.connect(self.open_dashboard_build)
        self.signals.char_notify.connect(self._set_char_notify)
        self.signals.sim_updated.connect(self._on_sim_updated)

        # Backends (guarded)
        self.db = None
        self.recorder = None
        self.voice = None
        self.accounts = None
        self.scraper = None
        self.poe_account = None
        self.poe_ninja = None
        self.pob_bridge = None
        self.pob_sim = None
        self._sync_stop = threading.Event()
        self._init_backends()

        self.rebuild_button_objects()

        # Mouse / drag
        self.drag_position = QPoint()
        self.press_pos = QPoint()
        self.is_dragging = False
        self.has_moved = False
        self.right_button_pressed = False
        self.left_button_pressed = False
        # No native right-click context menu (it used to pop up and trap the
        # cursor); closing is now left-click held + ESC.
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        # Click distinction timers (single vs double click on the medallions)
        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self.execute_delayed_snapshot)
        self.voice_click_timer = QTimer(self)        # mic: single=voice, double=chat
        self.voice_click_timer.setSingleShot(True)
        self.voice_click_timer.timeout.connect(self.execute_delayed_voice)
        self.char_click_timer = QTimer(self)         # char: single=picker, double=PoB tab
        self.char_click_timer.setSingleShot(True)
        self.char_click_timer.timeout.connect(self.execute_delayed_character)

        # W3-20: watch the clipboard for in-game Ctrl+C item copies. Windows
        # notifies Qt of ALL clipboard changes, so this works while you play
        # — purely passive, nothing is ever sent to the game.
        self._last_clip = ""
        self._clip_ts = 0.0
        self._price_popup = None
        self._econ_cache = {"rows": [], "ts": 0.0}
        try:
            QApplication.clipboard().dataChanged.connect(self._on_clipboard_item)
        except Exception:
            pass
        self._chat = None

        # Enumerate TTS voices in the background (slow on Windows SAPI) so the
        # Settings dialog opens instantly instead of freezing the overlay.
        self._voice_cache = None
        def _cache_voices():
            try:
                self._voice_cache = VoiceEngine.list_voices() if VoiceEngine else []
            except Exception:
                self._voice_cache = []
        threading.Thread(target=_cache_voices, daemon=True).start()

        # Animation loop. 30 FPS is visually identical for a gentle bob but
        # HALVES paint cost vs the old 16ms/60FPS tick; physics is wall-clock
        # based so motion speed doesn't depend on the frame rate. When idle
        # (nothing but the bob moving) we repaint at half rate again, and when
        # the overlay is hidden we skip repaints entirely — this was a large
        # constant CPU drain on minimal hardware.
        self._last_tick = time.time()
        self._idle_skip = 0
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update_physics_loop)
        self.animation_timer.start(33)

        # Ghost mode: when the game window has focus the mirror fades to a
        # whisper (only the orb stays clearly visible) and stops eating
        # clicks entirely — hold Ctrl to make it solid + clickable again.
        # Config: game_fade / game_click_through (both default on),
        # game_fade_frame (frame opacity while ghosted).
        self.game_mode = False            # game is foreground right now
        self._ctrl_override = False       # Ctrl held: temporarily solid
        self._click_through_on = False    # current WS_EX_TRANSPARENT state
        # 150ms: fast enough that holding Ctrl feels instant (the calls are
        # a few user32 reads — microseconds).
        self.game_watch_timer = QTimer(self)
        self.game_watch_timer.timeout.connect(self._poll_game_state)
        self.game_watch_timer.start(150)

        # W4-21 death review: tail Client.txt while the game runs; a death
        # line flushes OBS's replay buffer into a clip (core_engine/
        # death_review). 1s poll, near-zero cost when the game is closed.
        self._death_watcher = None
        self._death_log_retry = 0.0
        self.death_watch_timer = QTimer(self)
        self.death_watch_timer.timeout.connect(self._death_tick)
        self.death_watch_timer.start(1000)

        logger.log_event("SYSTEM", "PyQt6 Transparent QWidget window initialized.")

    # ------------------------------------------------
    # BACKEND INIT
    # ------------------------------------------------
    def _init_backends(self):
        if KalandraDBHandler:
            try:
                self.db = KalandraDBHandler()
            except Exception as e:
                logger.log_event("DATABASE", f"DB init failed: {e}")
        if ScreenRecorder:
            try:
                self.recorder = ScreenRecorder(
                    output_dir=self.config.get("dir_clips", "data_engine/clips"),
                    fps=self.config.get("clip_fps", 15),
                    max_width=self.config.get("clip_max_width", 1920))
            except Exception as e:
                logger.log_event("OCR", f"Recorder init failed: {e}")
        if AccountManager:
            try:
                self.accounts = AccountManager()
            except Exception as e:
                logger.log_event("SYSTEM", f"AccountManager init failed: {e}")
        if VoiceEngine:
            try:
                provider = self.accounts.get_secret if self.accounts else None
                self.voice = VoiceEngine(
                    whisper_model_size=self.config.get("whisper_model", "base"),
                    brain=self.config.get("ai_brain", "openai"),
                    api_key_provider=provider,
                    logger=lambda c, m: self.signals.log.emit(c, m),
                    openai_model=self.config.get("openai_model", "gpt-4o-mini"),
                    gemini_model=self.config.get("gemini_model", "gemini-2.5-flash"),
                    model=self._active_model(),
                    voice_id=self.config.get("voice_id") or None,
                    voice_rate=self.config.get("voice_rate") or None,
                )
            except Exception as e:
                logger.log_event("VOICE", f"VoiceEngine init failed: {e}")
        if KalandraScraper and self.db:
            try:
                self.scraper = KalandraScraper(
                    self.db, logger=lambda c, m: self.signals.log.emit(c, m))
            except Exception as e:
                logger.log_event("DATABASE", f"Scraper init failed: {e}")
        if PoEAccount:
            try:
                self.poe_account = PoEAccount(logger=lambda c, m: self.signals.log.emit(c, m))
            except Exception as e:
                logger.log_event("POB", f"PoEAccount init failed: {e}")
        if PoENinja:
            try:
                self.poe_ninja = PoENinja(logger=lambda c, m: self.signals.log.emit(c, m))
            except Exception as e:
                logger.log_event("DATABASE", f"PoENinja init failed: {e}")
        if KalandraPoBBridge:
            try:
                self.pob_bridge = KalandraPoBBridge()
            except Exception as e:
                logger.log_event("POB", f"PoB bridge init failed: {e}")
        if PoBSimulator:
            try:
                # Construct only; the heavy headless engine starts lazily on use.
                self.pob_sim = PoBSimulator(
                    install_dir=self.config.get("pob_install_dir"),
                    luajit=self.config.get("luajit_path"),
                    logger=lambda c, m: self.signals.log.emit(c, m))
            except Exception as e:
                logger.log_event("POB", f"PoB simulator init failed: {e}")

        if _BACKEND_ERRORS:
            for k, v in _BACKEND_ERRORS.items():
                logger.log_event("SYSTEM", f"Optional backend '{k}' unavailable: {v}")

    # ------------------------------------------------
    # GEOMETRY
    # ------------------------------------------------
    def mirror_rect(self):
        margin = 10
        side = min(self.width(), self.height()) - margin
        if side < 1:
            side = 1
        x = (self.width() - side) / 2.0
        y = (self.height() - side) / 2.0
        return QRectF(x, y, side, side)

    def rebuild_button_objects(self):
        rect = self.mirror_rect()
        ox, oy, side = rect.x(), rect.y(), rect.width()
        self.buttons = []
        for spec in self.MEDALLION_LAYOUT:
            cx = ox + spec["fx"] * side
            cy = oy + spec["fy"] * side
            radius = spec["fr"] * side
            cb_name = spec["callback_name"]
            self.buttons.append({
                "id": spec["id"], "name": spec["name"],
                "center": QPointF(cx, cy), "radius": radius,
                "color": spec["color"],
                "callback": getattr(self, cb_name) if cb_name else None,
            })

    def orb_geometry(self):
        rect = self.mirror_rect()
        side = rect.width()
        r = self.ORB_RADIUS_FR * side
        cx = rect.x() + self.ORB_CENTER_FX * side
        cy = rect.y() + self.ORB_CENTER_FY * side + self.current_y_offset
        return QRectF(cx - r, cy - r, 2 * r, 2 * r)

    def resizeEvent(self, event):
        self.rebuild_button_objects()
        self._px_cache = {}   # sizes changed — rebuild scaled art on next paint
        super().resizeEvent(event)

    def _scaled_px(self, key, pm, w, h):
        """Return `pm` scaled to (w, h), cached. Scale once, reuse every frame."""
        w, h = int(w), int(h)
        if pm is None or pm.isNull() or w <= 0 or h <= 0:
            return pm
        ck = (key, w, h)
        hit = self._px_cache.get(ck)
        if hit is None:
            hit = pm.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
            self._px_cache[ck] = hit
        return hit

    def update_physics_loop(self):
        now = time.time()
        dt = min(now - getattr(self, "_last_tick", now), 0.1)
        self._last_tick = now
        # 3.1 rad/s == the old 0.05 rad per 16ms tick, now framerate-independent.
        self.time_counter += 3.1 * dt
        self.current_y_offset = math.sin(self.time_counter) * self.bobbing_amplitude
        if self.flash_intensity > 0.0:
            self.flash_intensity -= 3.0 * dt
            if self.flash_intensity < 0.0:
                self.flash_intensity = 0.0
        # Reveal subtitle words over the estimated speak duration (karaoke).
        if self.subtitle_full:
            frac = 1.0 if self.subtitle_dur <= 0 else \
                min(1.0, (time.time() - self.subtitle_start) / self.subtitle_dur)
            words = self.subtitle_full.split()
            n = max(1, int(round(frac * len(words))))
            self.subtitle_shown = " ".join(words[:n])
            # Clear a couple seconds after speaking finished.
            if not self.is_talking and frac >= 1.0 and \
                    (time.time() - self.subtitle_start) > self.subtitle_dur + 2.5:
                self.subtitle_full = ""
                self.subtitle_shown = ""

        # Advance the sync-button blink. Blink frequency scales with crawl speed:
        # ~0.6 Hz when idle/slow up to ~5 Hz at high pages/min.
        if self.sync_active:
            hz = 0.6 + min(self.sync_rate, 2000.0) / 450.0
            self.blink_phase += hz * dt * 2.0 * math.pi
        else:
            self.blink_phase = 0.0
        # Repaint policy: skip entirely when hidden; halve the rate when idle
        # (only the gentle bob is moving). Keeps weak machines responsive.
        if not self.isVisible():
            return
        busy = (self.is_talking or bool(self.subtitle_full)
                or self.flash_intensity > 0.0 or self.sync_active
                or self.hovered_button is not None or self.recording_active)
        if not busy:
            self._idle_skip = (self._idle_skip + 1) % 2
            if self._idle_skip:
                return
        self.update()

    # ------------------------------------------------
    # GHOST MODE (game foreground -> fade + click-through; Ctrl -> solid)
    # ------------------------------------------------
    def _poll_game_state(self):
        """150ms poll: is the game foreground, is Ctrl held? Applies the
        click-through window style only on CHANGE (SetWindowLongPtr is not
        free) and repaints only on visible-state changes."""
        try:
            from gui_overlay import game_watch
            game = bool(self.config.get("game_fade", True)) and \
                game_watch.game_foreground()
            ctrl = game_watch.ctrl_down() if game else False
        except Exception:
            game, ctrl = False, False
        want_ct = (game and not ctrl and
                   bool(self.config.get("game_click_through", True)))
        if want_ct != self._click_through_on:
            try:
                from gui_overlay import game_watch
                if game_watch.set_click_through(int(self.winId()), want_ct):
                    self._click_through_on = want_ct
            except Exception:
                pass
        if (game, ctrl) != (self.game_mode, self._ctrl_override):
            entering = game and not self.game_mode
            leaving = self.game_mode and not game
            self.game_mode, self._ctrl_override = game, ctrl
            if entering:
                self.signals.log.emit(
                    "GUI", "Game detected — overlay ghosted (orb stays "
                           "visible; clicks pass through; hold Ctrl to "
                           "interact).")
            elif leaving:
                self.signals.log.emit("GUI", "Game left focus — overlay solid "
                                             "and clickable again.")
            self.update()

    def _ghost_opacities(self):
        """(frame_opacity, orb_opacity) for the current state. Ghosted: the
        frame is a whisper, the orb stays clearly visible. Ctrl override or
        no game: both follow the normal multiplier."""
        if self.game_mode and not self._ctrl_override:
            try:   # junk config must never kill paintEvent
                fade = float(self.config.get("game_fade_frame", 0.15))
            except Exception:
                fade = 0.15
            fade = min(max(fade, 0.0), 1.0)
            return (self.opacity_multiplier * fade,
                    self.opacity_multiplier * 0.92)
        return self.opacity_multiplier, self.opacity_multiplier

    def _death_tick(self):
        """1s poll (W4-21): while the game runs, tail Client.txt; the
        moment a death line lands, capture the OBS replay + context on a
        worker thread. Results come back via signals.death_captured."""
        if not self.game_mode:
            return
        try:
            from core_engine import death_review as dr
            if self._death_watcher is None:
                now = time.time()
                if now < self._death_log_retry:
                    return
                p = dr.find_client_log(self.config)
                if not p:
                    self._death_log_retry = now + 120  # retry quietly later
                    return
                self._death_watcher = dr.ClientLogWatcher(p)
                self.signals.log.emit("DEATH",
                                      f"Death watch armed — tailing {p}")
            for ev in self._death_watcher.poll():
                if ev.get("kind") == "death" and ev.get("who") == "you":
                    ctx = list(self._death_watcher.recent)
                    cfg = dict(self.config)

                    def _work(ev=ev, ctx=ctx, cfg=cfg):
                        rec = dr.capture_death(ev, ctx, cfg)
                        self.signals.death_captured.emit(rec)

                    threading.Thread(target=_work, daemon=True).start()
        except Exception:
            pass                     # the watcher must never hurt the overlay

    def _on_death_captured(self, rec):
        got = ("clip saved" if rec.get("clip")
               else f"no clip — {str(rec.get('clip_note', ''))[:90]}")
        self.signals.log.emit(
            "DEATH", f"Death in {rec.get('zone', '?')} captured ({got}). "
                     f"Open the dashboard's Death Review tab for the "
                     f"autopsy.")

    # ------------------------------------------------
    # PAINT
    # ------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.mirror_rect()
        frame_op, orb_op = self._ghost_opacities()
        painter.setOpacity(frame_op)

        if self.mirror_pixmap and not self.mirror_pixmap.isNull():
            r = rect.toRect()
            painter.drawPixmap(r.topLeft(), self._scaled_px(
                "mirror", self.mirror_pixmap, r.width(), r.height()))
        else:
            self._draw_vector_fallback(painter, rect)

        core_rect = self.orb_geometry()
        painter.setOpacity(orb_op)   # the orb stays visible even when ghosted
        aura = QRadialGradient(core_rect.center(), core_rect.width() * 0.8)
        aura.setColorAt(0.0, QColor(0, 255, 255, 120))
        aura.setColorAt(1.0, QColor(0, 255, 255, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(aura))
        painter.drawEllipse(core_rect.adjusted(-20, -20, 20, 20))

        if self.has_visemes:
            # Viseme sprite face: show the rest face when idle, the current mouth
            # shape while talking (driven by Rhubarb lip-sync).
            shape = self.current_viseme if self.is_talking else "X"
            pm = self.viseme_pixmaps.get(shape) or self.viseme_pixmaps.get("X") \
                or self.orb_pixmap
            if pm is not None and not pm.isNull():
                cr = core_rect.toRect()
                painter.drawPixmap(cr.topLeft(), self._scaled_px(
                    ("viseme", shape), pm, cr.width(), cr.height()))
        elif self.orb_pixmap and not self.orb_pixmap.isNull():
            cr = core_rect.toRect()
            painter.drawPixmap(cr.topLeft(), self._scaled_px(
                "orb", self.orb_pixmap, cr.width(), cr.height()))
            if self.is_talking and self.mouth_open > 0.02:
                self._draw_talking_mouth(painter, core_rect)
        else:
            painter.setPen(QPen(QColor(0, 255, 255), 3))
            painter.setBrush(QBrush(QColor(25, 28, 35, 245)))
            painter.drawEllipse(core_rect)
            if self.is_talking and self.mouth_open > 0.02:
                # Simple vector mouth that opens with the voice.
                mw = core_rect.width() * 0.32
                mh = core_rect.height() * (0.04 + 0.16 * self.mouth_open)
                mx = core_rect.center().x() - mw / 2
                my = core_rect.top() + core_rect.height() * self.orb_mouth_fy
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(10, 5, 5, 230)))
                painter.drawEllipse(QRectF(mx, my, mw, mh))

        painter.setOpacity(frame_op)   # medallions/badges fade with the frame
        for btn in self.buttons:
            is_active = (
                (btn["id"] == "TopLeft" and self.voice_active) or
                (btn["id"] == "TopCenter" and self.sync_active) or
                (btn["id"] == "TopRight" and self.active_character != "None") or
                (btn["id"] == "BottomLeft" and self.recording_active) or
                (btn["id"] == "BottomRight" and self.menu_active)
            )
            if is_active or self.hovered_button == btn["id"]:
                glow_rad = btn["radius"] + 6
                glow = QRadialGradient(btn["center"], glow_rad)
                alpha = 190 if is_active else 110
                # The sync medallion BLINKS while crawling; blink rate tracks speed.
                if btn["id"] == "TopCenter" and self.sync_active:
                    pulse = 0.5 + 0.5 * math.sin(self.blink_phase)
                    alpha = int(70 + 160 * pulse)
                    glow_rad = btn["radius"] + 6 + 4 * pulse
                c = btn["color"]
                glow.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), alpha))
                glow.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 0))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(glow))
                painter.drawEllipse(btn["center"], glow_rad, glow_rad)

        # Notification badge on the sync medallion when data is out of date.
        if self.sync_needed and not self.sync_active:
            for btn in self.buttons:
                if btn["id"] == "TopCenter":
                    bc = btn["center"]
                    br = btn["radius"]
                    badge = QRectF(bc.x() + br * 0.4, bc.y() - br * 1.1,
                                   br * 0.9, br * 0.9)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(QColor(255, 140, 0, 240)))
                    painter.drawEllipse(badge)
                    painter.setPen(QPen(QColor(20, 20, 20)))
                    f = QFont(); f.setBold(True); f.setPointSize(max(6, int(br * 0.5)))
                    painter.setFont(f)
                    painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, "!")
                    break

        # Notification badge on the character selector when a build is ready to
        # view in the dashboard PoB tab (double-click the selector to open it).
        if self.char_notify:
            for btn in self.buttons:
                if btn["id"] == "TopRight":
                    bc = btn["center"]; br = btn["radius"]
                    badge = QRectF(bc.x() + br * 0.4, bc.y() - br * 1.1, br * 0.9, br * 0.9)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(QColor(70, 220, 120, 240)))
                    painter.drawEllipse(badge)
                    painter.setPen(QPen(QColor(20, 20, 20)))
                    f = QFont(); f.setBold(True); f.setPointSize(max(6, int(br * 0.45)))
                    painter.setFont(f)
                    painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, "▣")
                    break

        if self.flash_intensity > 0.0:
            painter.save()
            painter.setOpacity(self.flash_intensity)
            painter.setPen(QPen(QColor(255, 215, 0, 220), 10))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            glass = QRectF(rect.x() + 0.09 * rect.width(), rect.y() + 0.20 * rect.width(),
                           0.82 * rect.width(), 0.50 * rect.width())
            painter.drawEllipse(glass)
            painter.restore()

        # Visible recording indicator (privacy: the user always sees when capturing).
        if self.recording_active:
            painter.save()
            painter.setOpacity(1.0)
            dot = QRectF(rect.x() + 14, rect.y() + 12, 12, 12)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(230, 30, 30)))
            painter.drawEllipse(dot)
            painter.setPen(QPen(QColor(255, 80, 80)))
            f = QFont(); f.setBold(True); f.setPointSize(9)
            painter.setFont(f)
            painter.drawText(QRectF(rect.x() + 30, rect.y() + 8, 80, 20),
                             Qt.AlignmentFlag.AlignVCenter, "REC")
            painter.restore()

        # Subtitle bubble (the orb's reply) near the bottom of the mirror.
        if self.subtitle_shown:
            painter.save()
            painter.setOpacity(1.0)
            f = QFont(); f.setPointSize(9)
            painter.setFont(f)
            margin = 14
            bw = self.width() - 2 * margin
            text_rect = QRectF(margin + 8, 0, bw - 16, 10000)
            flags = (Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
                     | Qt.TextFlag.TextWordWrap)
            bound = painter.boundingRect(text_rect, int(flags), self.subtitle_shown)
            bh = min(bound.height() + 16, 120)
            by = self.height() - bh - margin
            bubble = QRectF(margin, by, bw, bh)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(10, 12, 16, 220)))
            painter.drawRoundedRect(bubble, 10, 10)
            painter.setPen(QPen(QColor(200, 170, 110, 90)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(bubble, 10, 10)
            painter.setPen(QPen(QColor(232, 230, 223)))
            painter.drawText(QRectF(margin + 8, by + 8, bw - 16, bh - 16),
                             int(flags), self.subtitle_shown)
            painter.restore()

    def _draw_vector_fallback(self, painter, rect):
        side = rect.width()
        glass = QRectF(rect.x() + 0.09 * side, rect.y() + 0.20 * side,
                       0.82 * side, 0.50 * side)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(12, 16, 24, 220)))
        painter.drawEllipse(glass)
        grad = QLinearGradient(glass.topLeft(), glass.bottomRight())
        grad.setColorAt(0.0, QColor(255, 215, 0))
        grad.setColorAt(1.0, QColor(184, 134, 11))
        painter.setPen(QPen(QBrush(grad), max(6, side * 0.02)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(glass)
        for btn in self.buttons:
            painter.setPen(QPen(QColor(120, 90, 20), 3))
            painter.setBrush(QBrush(QColor(212, 175, 55)))
            painter.drawEllipse(btn["center"], btn["radius"], btn["radius"])
            gem_r = btn["radius"] * 0.45
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(btn["color"]))
            painter.drawEllipse(btn["center"], gem_r, gem_r)

    def _draw_talking_mouth(self, painter, core_rect):
        """Lip-sync from a single 2D face: drop the 'jaw' (lower-mouth band) by an
        amount proportional to the voice amplitude and reveal a dark mouth gap.
        Tunable via self.orb_mouth_* so the art can be matched precisely."""
        pm = self.orb_pixmap
        pw, ph = pm.width(), pm.height()
        if pw == 0 or ph == 0:
            return
        W, H = core_rect.width(), core_rect.height()
        sf = self.orb_mouth_fy
        x0, x1 = self.orb_mouth_x0, self.orb_mouth_x1
        drop = self.mouth_open * self.orb_jaw_max * H
        if drop < 0.5:
            return
        gx = core_rect.left() + x0 * W
        gw = (x1 - x0) * W
        gy = core_rect.top() + sf * H
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        # Dark mouth interior in the opened gap.
        painter.setBrush(QBrush(QColor(12, 6, 6, 235)))
        painter.drawRoundedRect(QRectF(gx, gy, gw, drop + 1), 5, 5)
        # Re-draw the lower mouth band shifted down so the chin/lower lip moves.
        src = QRectF(x0 * pw, sf * ph, (x1 - x0) * pw, (1 - sf) * ph)
        dst = QRectF(gx, gy + drop, gw, (1 - sf) * H)
        painter.drawPixmap(dst, pm, src)
        painter.restore()

    def _set_sync_rate(self, rate):
        self.sync_rate = max(0.0, float(rate))

    def _set_sync_needed(self, needed):
        self.sync_needed = bool(needed)
        self.update()

    def _set_mouth(self, level):
        self.mouth_open = max(0.0, min(1.0, float(level)))

    def _set_viseme(self, shape):
        self.current_viseme = shape or "X"

    def _set_subtitle(self, text):
        """Start showing the orb's reply as karaoke-style subtitles."""
        self.subtitle_full = text or ""
        self.subtitle_shown = ""
        self.subtitle_start = time.time()
        words = max(1, len(self.subtitle_full.split()))
        self.subtitle_dur = max(1.0, words / 2.6)   # ~matches TTS pace
        self.update()

    def _set_talking(self, talking):
        self.is_talking = bool(talking)
        if not talking:
            self.mouth_open = 0.0
            self.current_viseme = "X"
        self.update()

    # ------------------------------------------------
    # MOUSE / KEYBOARD
    # ------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.press_pos = event.globalPosition().toPoint()
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.has_moved = False
            self.is_dragging = True
            self.left_button_pressed = True
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            # Right-click no longer does anything (it used to open a context menu
            # that trapped the cursor). Close is left-click held + ESC.
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            bid = self.check_button_click(event.position().toPoint())
            if bid == "BottomLeft":
                self.click_timer.stop()
                self._double_click_fired = True
                self.toggle_screen_recording()
                event.accept()
            elif bid == "TopLeft":
                # Double-click the mic -> open the typed chat instead of listening.
                self.voice_click_timer.stop()
                self._double_click_fired = True
                self.open_chat_window()
                event.accept()
            elif bid == "TopRight":
                # Double-click the character selector -> open the dashboard PoB tab.
                self.char_click_timer.stop()
                self._double_click_fired = True
                self.open_dashboard_build()
                event.accept()

    def mouseMoveEvent(self, event):
        x = int(event.position().x())
        y = int(event.position().y())
        self.update_hover_states(x, y)
        if event.buttons() & Qt.MouseButton.LeftButton and self.is_dragging:
            current_pos = event.globalPosition().toPoint()
            if (current_pos - self.press_pos).manhattanLength() > 4:
                self.move(current_pos - self.drag_position)
                self.has_moved = True
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            self.left_button_pressed = False
            # Qt fires Press→Release→DblClick→Release: without this guard the
            # release AFTER a double-click restarts the single-click timer and
            # opens BOTH windows.
            if getattr(self, "_double_click_fired", False):
                self._double_click_fired = False
                event.accept()
                return
            if not self.has_moved:
                self.trigger_click_action(int(event.position().x()), int(event.position().y()))
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.right_button_pressed = False
            event.accept()

    def keyPressEvent(self, event):
        # Close = hold LEFT mouse button + press ESC (right-click was opening a
        # context menu that trapped the cursor).
        if event.key() == Qt.Key.Key_Escape and self.left_button_pressed:
            logger.log_event("SHUTDOWN", "Shutdown sequence triggered via hotkey (L-Click + ESC).")
            self.close()
        else:
            super().keyPressEvent(event)

    def leaveEvent(self, event):
        self.right_button_pressed = False
        self.hovered_button = None
        self.update()
        super().leaveEvent(event)

    def check_button_click(self, pos):
        for btn in self.buttons:
            if math.hypot(pos.x() - btn["center"].x(), pos.y() - btn["center"].y()) <= btn["radius"]:
                return btn["id"]
        return None

    def update_hover_states(self, x, y):
        old = self.hovered_button
        self.hovered_button = self.check_button_click(QPoint(x, y))
        if old != self.hovered_button:
            self.update()

    def trigger_click_action(self, x, y):
        bid = self.check_button_click(QPoint(x, y))
        if bid == "BottomLeft":
            logger.log_event("SYSTEM", "Snapshot clicked... awaiting potential double click verification.")
            self.click_timer.start(250)
        elif bid == "TopLeft":
            # Defer the voice toggle briefly so a double-click can open text chat.
            self.voice_click_timer.start(250)
        elif bid == "TopRight":
            # Defer the character picker so a double-click can open the PoB tab.
            self.char_click_timer.start(250)
        else:
            for btn in self.buttons:
                if btn["id"] == bid and btn["callback"]:
                    logger.log_event("SYSTEM", f"Activated medallion button: {btn['name']}")
                    btn["callback"]()
                    break

    def execute_delayed_snapshot(self):
        self.take_snapshot()

    def execute_delayed_voice(self):
        self.toggle_voice()

    def execute_delayed_character(self):
        self.select_active_character()

    # ------------------------------------------------
    # MENU MANAGER — one menu at a time; the overlay steps aside while a
    # menu is open and reappears when the last one closes.
    # ------------------------------------------------
    def _present_menu(self, win, modal=False):
        prev = getattr(self, "_open_menu", None)
        if prev is not None and prev is not win:
            try:
                prev.close()          # only one menu open at a time
            except Exception:
                pass
        self._open_menu = win
        try:
            win.installEventFilter(self)   # watch for it closing/hiding
        except Exception:
            pass
        if self.isVisible():
            logger.log_event("SYSTEM", "Overlay stepping aside while the menu is open.")
            self.hide()
        if modal:
            try:
                win.exec()
            finally:
                self._menu_done(win)
        else:
            win.show()
            win.raise_()
            win.activateWindow()

    def _menu_done(self, win):
        # Spurious Hide events fire when a tab spins up an embedded web view
        # (QtWebEngine briefly recreates native window handles) — if the menu
        # is actually still on screen, it is NOT done and the overlay must
        # not barge back in on top of it.
        try:
            if win is getattr(self, "_open_menu", None) and win.isVisible() \
                    and not win.isMinimized():
                return
        except Exception:
            pass
        if getattr(self, "_open_menu", None) is win:
            self._open_menu = None
        if getattr(self, "_open_menu", None) is None and not self.isVisible():
            self.show()
            self.raise_()

    def eventFilter(self, obj, ev):
        try:
            if obj is getattr(self, "_open_menu", None) and ev.type() in (
                    QEvent.Type.Close, QEvent.Type.Hide):
                # Defer: on Close the window is mid-teardown; on Hide another
                # menu may be about to claim the slot.
                QTimer.singleShot(150, lambda o=obj: self._menu_done(o))
        except Exception:
            pass
        return super().eventFilter(obj, ev)

    # ------------------------------------------------
    # W3-20: CLIPBOARD PRICE POPUP
    # ------------------------------------------------
    def _on_clipboard_item(self):
        if not bool(self.config.get("price_popup", True)):
            return
        # An external tool owns price checking? Then it owns Ctrl+C too.
        if self.config.get("price_checker", "kalandra") != "kalandra":
            return
        try:
            txt = QApplication.clipboard().text() or ""
        except Exception:
            return
        now = time.time()
        if (not txt or txt == self._last_clip or len(txt) > 4000
                or (now - self._clip_ts) < 0.8):
            return
        if "Rarity:" not in txt and "Item Class:" not in txt:
            return                      # not a PoE item copy
        self._last_clip = txt
        self._clip_ts = now
        try:
            from core_engine.trade_tools import parse_item_text
            info = parse_item_text(txt)
        except Exception:
            return
        if not (info.get("name") or info.get("base")):
            return
        logger.log_event("TRADE", f"Item copied in game: "
                         f"{info.get('name') or info.get('base')}")
        self._show_price_popup(info, txt)

    def _econ_rows(self):
        """Cached poe.ninja rows for instant currency estimates (6h TTL).
        Prefers whatever the Exchange tab already fetched."""
        try:
            from gui_overlay import dashboard as _dash
            if _dash.LAST_ECON_ROWS:
                return _dash.LAST_ECON_ROWS
        except Exception:
            pass
        if time.time() - self._econ_cache["ts"] < 6 * 3600:
            return self._econ_cache["rows"]
        return []   # fetched lazily by _refresh_econ_cache

    def _refresh_econ_cache(self):
        def _work():
            try:
                if self.poe_ninja and self.poe_ninja.available:
                    rows = self.poe_ninja.get_currency(
                        self.config.get("league", "Standard")) or []
                    if rows:
                        self._econ_cache = {"rows": rows, "ts": time.time()}
            except Exception:
                pass
        threading.Thread(target=_work, daemon=True).start()

    def _show_price_popup(self, info, raw_text):
        est_text = None
        rows = self._econ_rows()
        if not rows:
            self._refresh_econ_cache()   # ready for the NEXT copy
        else:
            try:
                from core_engine.trade_tools import estimate_value
                est = estimate_value(info, rows)
                if est:
                    est_text = est[1]
            except Exception:
                pass

        def _to_dashboard(text):
            d = self.open_dashboard()
            if d is not None:
                try:
                    d.prefill_price_check(text)
                except Exception:
                    pass
        try:
            if self._price_popup is not None:
                self._price_popup.close()
        except Exception:
            pass
        self._price_popup = PricePopup(
            info, raw_text, self.config.get("league", "Standard"),
            on_dashboard=_to_dashboard, estimate=est_text)
        self._price_popup.show()

    # ------------------------------------------------
    # SIGNAL SLOTS (run on UI thread)
    # ------------------------------------------------
    def _set_sync_state(self, active):
        self.sync_active = active
        if not active:
            logger.stop_heartbeat()
        self.update()

    def _on_sync_finished(self, stats):
        self.sync_active = False
        logger.stop_heartbeat()
        self.update()
        pending = stats.get("pending", 0)
        done_note = ("Whole site covered ✅" if pending == 0
                     else f"<b>{pending}</b> pages still pending — click sync again to continue.")
        speed = ""
        if stats.get("rate_per_min"):
            speed = (f"Crawl speed: <b>{stats['rate_per_min']}</b> pages/min "
                     f"over <b>{stats.get('elapsed_min', '?')}</b> min<br>")
        self._info("Kalandra Database Sync",
            "<b>Database sync finished.</b><br><br>"
            f"Total entries in knowledge base: <b>{stats.get('ledger_rows', '?')}</b><br>"
            f"Pages crawled (all time): <b>{stats.get('pages_done', '?')}</b><br>"
            f"New this run: <b>{stats.get('new_this_run', '?')}</b><br>"
            f"Refreshed (re-checked content): <b>{stats.get('updated_this_run', 0)}</b><br>"
            f"{speed}"
            f"{done_note}<br><br>"
            f"Database file: <i>data_engine/localized_knowledge.db</i>")

    def _on_voice_result(self, transcript, reply):
        self.voice_active = False
        self.update()
        if not transcript:
            logger.log_event("VOICE", "No speech detected.")
            return
        # Save transcript
        try:
            d = self.config.get("dir_transcripts", "data_engine/transcripts")
            os.makedirs(d, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            with open(os.path.join(d, f"voice_{ts}.txt"), "w", encoding="utf-8") as f:
                f.write(f"You: {transcript}\n")
                if reply:
                    f.write(f"Orb: {reply}\n")
        except Exception:
            pass

    def _on_record_finished(self, result):
        self.recording_active = False
        self.update()
        v = result.get("video")
        t = result.get("transcript")
        stats = result.get("stats") or {}
        perf = ""
        if stats.get("grabbed"):
            perf = (f"<br>Capture: <b>{stats.get('capture_fps', '?')}</b> fps real "
                    f"(target {stats.get('target_fps', '?')}), "
                    f"{stats.get('size', '?')}, {stats.get('seconds', '?')}s")
            self.signals.log.emit(
                "RECORD", f"Clip stats: {stats.get('capture_fps')} fps captured "
                          f"/ {stats.get('target_fps')} target, "
                          f"{stats.get('duplicated', 0)} duplicated frames, "
                          f"{stats.get('size')}.")
        self._info("Recording Saved",
                   "<b>Screen recording saved.</b><br><br>"
                   f"Video: <i>{v or 'failed'}</i><br>"
                   f"Transcription: {'saved' if t else 'no audio captured'}"
                   f"{perf}")

    # ------------------------------------------------
    # BUTTON CALLBACKS
    # ------------------------------------------------
    def toggle_voice(self):
        # If voice engine missing, explain.
        if not self.voice:
            self._info("Voice unavailable",
                       "Voice engine could not load.\n\n"
                       "Install: pip install faster-whisper sounddevice pyttsx3 numpy")
            return

        if not self.voice_active:
            from core_engine import voice_engine as _ve
            if not _ve.STT_AVAILABLE:
                self._info("Microphone/transcription unavailable",
                           self.voice.availability_message())
                return
            if self.voice.start_listening():
                self.voice_active = True
                self.update()
                logger.log_event("VOICE", "Listening... click the ruby again to stop.")
            else:
                self._info("Microphone error", "Could not open the microphone.")
        else:
            # Stop + process on a worker thread (Whisper + AI can be slow).
            self.voice_active = True  # keep glow until done
            self.update()
            threading.Thread(target=self._voice_worker, daemon=True).start()

    def _build_search_terms(self):
        """Pull the meaningful 'tags' out of the loaded build — main skill, every
        active skill gem, equipped item names/bases, ascendancy — so we can pull
        the matching poe2db entries from the knowledge base (true build-aware RAG,
        not just a search on whatever the user typed)."""
        full = self.current_build_full
        if not isinstance(full, dict):
            return []
        terms = []
        def add(v):
            v = (v or "").strip()
            if v and v not in ("?", "None") and v.lower() not in (t.lower() for t in terms):
                terms.append(v)
        # Main + active skills first (these are what the AI most needs grounded).
        add(full.get("main_skill"))
        for grp in full.get("skills", []) or []:
            for a in (grp.get("actives") or []):
                add(a)
        add(full.get("ascendancy"))
        # Equipped item names / bases.
        for it in full.get("items", []) or []:
            add(it.get("name"))
        return terms

    def _rag_for_terms(self, terms, per_term=2, cap=8, max_terms=6):
        """Search the knowledge base for the build's top terms and return deduped,
        labelled snippets. Uses a worker-local DB connection (thread-safe).

        IMPORTANT: each search is a LIKE scan over a large table, so we run AT
        MOST `max_terms` of them regardless of how many tags the build has. A
        loaded build can yield 50-90 tags; scanning all of them once made the
        chat appear to lock up for minutes. The terms are already priority-
        ordered (main skill, then other actives, ascendancy, items), so the
        first handful are the most useful anyway."""
        if not (terms and KalandraScraper and KalandraDBHandler):
            return []
        out, seen = [], set()
        sdb = None
        try:
            sdb = KalandraDBHandler()
            sc = KalandraScraper(sdb)
            for term in terms[:max_terms]:
                if len(out) >= cap:
                    break
                try:
                    hits = sc.search(term, limit=per_term)
                except Exception:
                    hits = []
                for h in hits:
                    key = h[:120]
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(f"[matches your build: {term}] {h}")
                    if len(out) >= cap:
                        break
        except Exception:
            pass
        finally:
            if sdb:
                try:
                    sdb.close()
                except Exception:
                    pass
        return out

    def _ai_context(self, text):
        """Build the SAME context the AI gets for both voice and text chat:
        RAG hits from the local knowledge base + the full parsed PoB build +
        live PoB sim numbers. Safe to call from any worker thread (uses a
        worker-local DB connection)."""
        context = []
        if KalandraScraper and KalandraDBHandler:
            sdb = None
            try:
                sdb = KalandraDBHandler()
                found = KalandraScraper(sdb).search(text)
                if found:
                    context.extend(found)
            except Exception:
                pass
            finally:
                if sdb:
                    try:
                        sdb.close()
                    except Exception:
                        pass
        # Build-aware RAG: pull DB entries that match the build's own skills/items/
        # ascendancy, so the answer is grounded in what the character actually uses.
        build_terms = self._build_search_terms()
        if build_terms:
            tag_hits = self._rag_for_terms(build_terms)
            for h in tag_hits:
                if h not in context:
                    context.append(h)
            if self.config.get("log_ai_context", True):
                self.signals.log.emit(
                    "AI-CONTEXT", "Build tags used for RAG: " + ", ".join(build_terms[:12])
                    + (f"  (+{len(build_terms) - 12} more)" if len(build_terms) > 12 else "")
                    + f"  -> {len(tag_hits)} matching DB entries.")
        # Feed the FULL parsed build (items, gems, stats) so the AI can
        # actually "see" the character, plus live sim numbers if available.
        if self.current_build_summary:
            context.insert(0, "CURRENT BUILD (from Path of Building):\n"
                           + self.current_build_summary)
            # Tree/repathing guidance: always add the short scaling profile; add
            # the full PoB Power Report walkthrough when the user is asking about
            # optimizing / passives / DPS / upgrades.
            if self.pob_bridge and isinstance(self.current_build_full, dict):
                try:
                    low = (text or "").lower()
                    wants_tree = any(k in low for k in (
                        "tree", "passive", "path", "repath", "point", "dps", "damage",
                        "optimi", "upgrade", "improve", "scal", "efficient", "squeeze",
                        "better", "node", "respec", "more out of"))
                    if wants_tree:
                        guide = self.pob_bridge.tree_guidance(self.current_build_full)
                        if guide:
                            context.insert(1, guide)
                    else:
                        prof = self.pob_bridge.analyze_scaling(self.current_build_full)
                        if prof.get("main_skill"):
                            dts = ", ".join(prof.get("damage_types", [])[:3]) or "n/a"
                            context.insert(1,
                                "BUILD SCALING PROFILE: scales via " + dts +
                                ("; crit-based" if prof.get("crit_based") else "; non-crit") +
                                ". (Ask about passives/DPS for a PoB tree-optimization walkthrough.)")
                except Exception:
                    pass
        else:
            # No build loaded — tell the AI to guide, not refuse.
            context.append(
                "NOTE TO ASSISTANT: No Path of Building build is currently loaded in "
                "Kalandra, so you cannot see the user's character yet. Do NOT say you "
                "'can't access links'. Instead, tell them how to load it: click the green "
                "medallion (Character Selector) and either 'Load my saved PoB builds' and "
                "Set active, or paste a PoB code / pobb.in link — they can also paste a PoB "
                "code or pobb.in link right here in the chat and you'll read it.")
        if self.pob_sim and self.pob_sim.has_build():
            try:
                summary = self.pob_sim.stats_summary()
                if summary:
                    context.insert(0, "LIVE PoB SIM: " + summary)
            except Exception:
                pass
        # Recent conversation, so switching AI models mid-chat keeps continuity.
        try:
            hist = self._history_context()
            if hist:
                context.insert(0, hist)
        except Exception:
            pass
        # SCALING SOURCES (from the DB): for a "what scales / affects X?" style
        # question, look X up, read its REAL poe2db tags, and pull every tagged
        # asset that shares them — so the Orb answers from the database, listing
        # actual uniques/gems/mods/passives, not generic guesses.
        if KalandraTagGraph and KalandraDBHandler:
            tdb = None
            try:
                low = (text or "").lower()
                wants_scaling = any(k in low for k in (
                    "scale", "scaling", "affect", "boost", "increase", "buff",
                    "more damage", "improve", "what works", "good for", "help my",
                    "support", "uniqu", "mod", "passive", "craft", "gear", "stack"))
                tdb = KalandraDBHandler()
                tgr = KalandraTagGraph(tdb)
                named = tgr.entities_in_text(text)
                cands = list(named)
                if wants_scaling and isinstance(self.current_build_full, dict):
                    for t in (self._build_search_terms() or [])[:3]:
                        if t not in cands:
                            cands.append(t)
                if named or (wants_scaling and cands):
                    for ent in cands:
                        blk = tgr.context_block(ent)
                        if blk:
                            context.insert(0, blk)
                            if self.config.get("log_ai_context", True):
                                self.signals.log.emit(
                                    "AI-CONTEXT", f"Scaling sources grounded on: {ent}")
                            break
            except Exception:
                pass
            finally:
                if tdb is not None:
                    try:
                        tdb.close()
                    except Exception:
                        pass
        # Verified corrections go FIRST (highest priority): authoritative facts
        # that override the DB and the model's own (often wrong) PoE2 knowledge.
        # Match against the user's message + the loaded build so the right facts
        # surface (e.g. Corrupted Blood is not Bleed).
        if self.corrections:
            try:
                probe = (text or "") + " " + (self.current_build_summary or "")
                block = self.corrections.context_block(probe)
                if block:
                    context.insert(0, block)
            except Exception:
                pass
        # Player profile from the owl's interview: calibrates tone and depth
        # (veteran vs new, solo-ground levels vs carried, budget, build taste).
        try:
            from core_engine.player_profile import PlayerProfile
            pblock = PlayerProfile.load().prompt_block()
            if pblock:
                context.insert(0, pblock)
        except Exception:
            pass
        # The user's Unique/BIS reserve stash, so the Orb can suggest using items
        # they're already holding for upgrades.
        if self.reserve:
            try:
                rsum = self.reserve.ai_summary()
                if rsum:
                    context.append(rsum)
            except Exception:
                pass
        # Transparency: show in the terminal EXACTLY what gets appended to the
        # prompt and sent to the cloud brain (build summary + DB/RAG snippets).
        if self.config.get("log_ai_context", True):
            self._log_ai_context(text, context)
        return context

    def _log_ai_context(self, text, context):
        """Print the full prompt context (what's sent to the AI) to the terminal."""
        sig = self.signals.log
        brain = self.config.get("ai_brain", "ai")
        sig.emit("AI-CONTEXT", "─" * 60)
        sig.emit("AI-CONTEXT", f"Your message: {text}")
        sent = context[:12]   # ai_respond() sends the first 12 snippets
        sig.emit("AI-CONTEXT", f"Appending {len(sent)} context block(s) to the prompt "
                 f"sent to {brain} (of {len(context)} gathered):")
        for i, snip in enumerate(sent, 1):
            s = snip if len(snip) <= 1200 else (snip[:1200] + " …(truncated)")
            label = "BUILD/SIM" if i <= 2 and ("BUILD" in snip[:40] or "SIM" in snip[:40]) \
                else "DATABASE"
            sig.emit("AI-CONTEXT", f"  [{i}] ({label})\n{s}")
        if len(context) > len(sent):
            sig.emit("AI-CONTEXT", f"  (+{len(context) - len(sent)} more gathered but not "
                     f"sent — only the top {len(sent)} are included to stay within limits)")
        sig.emit("AI-CONTEXT", "─" * 60)

    def _maybe_load_build_from_text(self, text):
        """If the user pasted a PoB import code or a pobb.in / poe.ninja build link
        into the chat, fetch + parse it and load it as the active build so the AI
        can analyze it right away. Returns a short note string if it loaded one,
        else None. Safe to call from a worker thread."""
        if not (self.pob_bridge and text):
            return None
        import re
        candidate = None
        # 1) A build link.
        m = re.search(r"https?://\S+", text)
        if m:
            url = m.group(0).rstrip(").,]\"'")
            if any(s in url.lower() for s in ("pobb.in", "poe.ninja", "pastebin",
                                              "pastebin.com", "poeskilltree")):
                candidate = url
        # 2) A raw PoB code: a long, base64-ish, space-free token.
        if not candidate:
            for tok in text.split():
                if len(tok) >= 60 and re.fullmatch(r"[A-Za-z0-9\-_=+/]+", tok):
                    candidate = tok
                    break
        if not candidate:
            return None
        try:
            code, msg = self.pob_bridge.resolve_link_to_code(candidate)
            if not code:
                self.signals.log.emit("POB", f"Tried to load pasted build but: {msg}")
                return None
            self.signals.log.emit("POB", "Detected a PoB build in your message — loading it...")
            self.load_build_into_sim(code)
            cls = "build"
            if isinstance(self.current_build_full, dict):
                cls = (f"{self.current_build_full.get('class_name','?')} / "
                       f"{self.current_build_full.get('ascendancy','None')} "
                       f"Lv{self.current_build_full.get('level','?')}")
            return f"(Loaded the build you pasted: {cls}.)"
        except Exception as e:
            self.signals.log.emit("POB", f"Could not load pasted build: {e}")
            return None

    def ask_ai_text(self, text, on_reply):
        """Text-chat entry point (double-click the mic medallion). Same brain and
        same context as voice, but no STT and no TTS. Runs on a worker thread and
        calls on_reply(reply, error=None) when done. Also logs to terminal + the
        transcript folder so typed chats are recorded just like voice ones."""
        if not self.voice:
            on_reply(None, "Voice/AI engine could not load.")
            return

        def _work():
            try:
                self._maybe_load_build_from_text(text)
                self._sync_voice_brain()
                context = self._ai_context(text)
                reply = self.voice.ai_respond(text, context_snippets=(context or None))
                self._track_ai_usage()
                self._remember_turn("you", text)
                self._remember_turn("orb", reply or "")
                self.signals.log.emit("CHAT", f"You: {text}")
                if reply:
                    self.signals.log.emit("CHAT", f"Orb: {reply}")
                self._save_chat_log(text, reply)
                on_reply(reply or "", None)
            except Exception as e:
                self.signals.log.emit("CHAT", f"Text chat error: {e}")
                on_reply(None, str(e))

        threading.Thread(target=_work, daemon=True).start()

    def _sync_voice_brain(self):
        """Make the voice engine reflect the currently-selected provider + model,
        so changing them in Settings switches mid-conversation with no restart."""
        if not self.voice:
            return
        try:
            self.voice.brain = self.config.get("ai_brain", "openai")
            self.voice.model = self._active_model()
        except Exception:
            pass

    def _active_model(self):
        brain = self.config.get("ai_brain", "openai")
        try:
            from core_engine.voice_engine import provider_model_default
            default = provider_model_default(brain)
        except Exception:
            default = ""
        return self.config.get(f"{brain}_model") or default

    def _track_ai_usage(self):
        """After each AI reply, fold its token usage into the session totals and
        warn (counting down) as the user approaches their self-set budget."""
        self.session_prompts += 1
        usage = getattr(self.voice, "last_usage", None) if self.voice else None
        if usage and usage.get("total_tokens"):
            self.session_tokens += int(usage["total_tokens"])
        budget = 0
        try:
            budget = int(self.config.get("token_budget", 0) or 0)
        except Exception:
            budget = 0
        if budget > 0:
            remaining = budget - self.session_tokens
            # Approx replies left, based on the average cost so far.
            avg = (self.session_tokens / self.session_prompts) if self.session_prompts else 0
            approx = int(remaining / avg) if avg > 0 else None
            if remaining <= 0:
                self.signals.log.emit("VOICE", f"AI token budget reached "
                    f"({self.session_tokens}/{budget}). Raise it in Settings to continue freely.")
            elif approx is not None and approx <= 10 and self._budget_warned_at != approx:
                self._budget_warned_at = approx
                self.signals.log.emit("VOICE",
                    f"Heads up: about {approx} AI replies left at this rate "
                    f"({self.session_tokens}/{budget} tokens used this session).")

    def ai_usage_summary(self):
        used = self.session_tokens
        budget = 0
        try:
            budget = int(self.config.get("token_budget", 0) or 0)
        except Exception:
            budget = 0
        model = self._active_model() or "?"
        base = f"This session: {self.session_prompts} replies, {used} tokens (model: {model})."
        if budget > 0:
            rem = max(0, budget - used)
            avg = (used / self.session_prompts) if self.session_prompts else 0
            approx = f", ~{int(rem/avg)} replies left" if avg > 0 else ""
            base += f"  Budget: {used}/{budget} ({rem} left{approx})."
        return base

    def _remember_turn(self, role, text):
        if not text:
            return
        self.chat_history.append((role, text))
        # Keep the last ~8 turns (4 exchanges) for continuity across model switches.
        if len(self.chat_history) > 8:
            self.chat_history = self.chat_history[-8:]

    def _history_context(self):
        if not self.chat_history:
            return None
        lines = ["CONVERSATION SO FAR (for continuity, including across any AI "
                 "model switch — keep answering as the same assistant):"]
        for role, text in self.chat_history[-6:]:
            who = "User" if role == "you" else "Orb"
            snippet = text if len(text) <= 400 else (text[:400] + " …")
            lines.append(f"{who}: {snippet}")
        return "\n".join(lines)

    def _flag_last_answer(self, question, answer, note=""):
        """Record a flagged chat answer as a tracked issue (default type:
        hallucination) so it shows up in the changelog you export to the dev."""
        if not self.issues:
            return
        title = (note.strip() or (question or "")[:80] or "Flagged Orb answer")
        ctx = f"You: {question}\nOrb: {answer}"
        self.issues.add(title=title, details=note.strip(),
                        type="hallucination", severity="medium",
                        context=ctx, source="chat-flag")
        logger.log_event("SYSTEM", f"Issue logged from chat: {title}")

    def _save_chat_log(self, text, reply):
        try:
            d = self.config.get("dir_transcripts", "data_engine/transcripts")
            os.makedirs(d, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            with open(os.path.join(d, f"chat_{ts}.txt"), "w", encoding="utf-8") as f:
                f.write(f"You: {text}\n")
                if reply:
                    f.write(f"Orb: {reply}\n")
        except Exception:
            pass

    def open_chat_window(self):
        if not self.voice:
            self._info("Chat unavailable",
                       "The AI engine could not load.\n\n"
                       "Install: pip install openai google-genai")
            return
        existing = getattr(self, "_chat", None)
        if existing is not None:
            try:
                self._present_menu(existing)
                return
            except Exception:
                self._chat = None
        self._chat = ChatDialog(self.ask_ai_text, parent=self,
                                flag_fn=self._flag_last_answer,
                                open_build_fn=self.open_dashboard_build)
        self._present_menu(self._chat)
        logger.log_event("CHAT", "Text chat window opened (double-click the ruby).")

    def _voice_worker(self):
        try:
            text = self.voice.stop_listening_and_transcribe()
            reply = ""
            if text and self.config.get("speak_replies", True):
                self._maybe_load_build_from_text(text)
                # Verbal "show me my build / open PoB" -> open the dashboard PoB
                # tab for the active character and badge the character selector.
                low = text.lower()
                if any(k in low for k in ("my build", "my pob", "path of building",
                        "open pob", "show me my build", "look at my build",
                        "pull up my build", "open my build", "my passive tree")):
                    if self.current_build_summary:
                        self.signals.open_build.emit()
                    else:
                        self.signals.char_notify.emit(True)
                        self.signals.log.emit("VOICE", "You don't have a build loaded yet — "
                            "load one via the green character selector, then ask again.")
                self._sync_voice_brain()
                context = self._ai_context(text)
                reply = self.voice.ai_respond(text, context_snippets=(context or None))
                self._track_ai_usage()
                self._remember_turn("you", text)
                self._remember_turn("orb", reply or "")
                if reply:
                    self.signals.log.emit("VOICE", f"Orb: {reply}")
                    self.signals.subtitle.emit(reply)
                    self.signals.speaking.emit(True)
                    self.voice.speak(
                        reply,
                        on_amplitude=lambda a: self.signals.mouth.emit(a),
                        on_viseme=lambda v: self.signals.viseme.emit(v),
                        on_done=lambda: self.signals.speaking.emit(False))
            self.signals.voice_result.emit(text or "", reply or "")
        except Exception as e:
            self.signals.log.emit("VOICE", f"Voice processing error: {e}")
            self.signals.voice_result.emit("", "")

    def trigger_database_scour_sync(self):
        if not self.scraper:
            self._info("Sync unavailable",
                       "Scraper could not load.\n\n"
                       "Install: pip install requests requests-cache beautifulsoup4 lxml")
            return
        if self.sync_active:
            # Second click cancels.
            self._sync_stop.set()
            logger.log_event("DATABASE", "Stopping crawl after current page...")
            return
        self._sync_stop.clear()
        self.sync_needed = False          # clear the out-of-date badge
        self.signals.sync_state.emit(True)
        logger.log_event("DATABASE", "Connecting to poe2db. Real crawl starting...")
        logger.start_heartbeat("syncing")
        threading.Thread(target=self._sync_worker, daemon=True).start()

    def _sync_worker(self):
        # Each background worker gets its OWN db connection (sqlite objects can't
        # cross threads). The shared self.db stays on the UI thread.
        wdb = None
        try:
            wdb = KalandraDBHandler() if KalandraDBHandler else None
            if wdb is None or not KalandraScraper:
                self.signals.sync_state.emit(False)
                return
            log = lambda c, m: self.signals.log.emit(c, m)
            scraper = KalandraScraper(wdb, logger=log)

            # Honor the user's preconfigured source toggles (set in the DB updater)
            # and proceed with NO prompts. poe2db is the primary (default on);
            # secondary sources run only if the user enabled them.
            enabled = self.config.get("sources_enabled", {})
            def _on(key, default):
                return bool(enabled.get(key, default))
            chosen = [k for k, d in (("poe2db", True), ("poe2wiki", False),
                                     ("poe_ninja", False)) if _on(k, d)]
            log("DATABASE", "Auto-sync sources (from your settings): "
                + (", ".join(chosen) if chosen else "none enabled"))

            # Feed the live crawl rate to the UI so the sync button blinks in time.
            import time as _t
            prog_state = {"t": _t.time(), "p": 0}
            def _progress(processed, _max, _url):
                now = _t.time()
                dt = now - prog_state["t"]
                if dt >= 1.0:
                    rate = (processed - prog_state["p"]) / dt * 60.0
                    self.signals.sync_progress.emit(rate)
                    prog_state["t"] = now
                    prog_state["p"] = processed
            scraper.progress = _progress

            # poe2db (primary) -- concurrent, resumable, cancelable.
            total_new = 0
            total_updated = 0
            if _on("poe2db", True):
                # Content-freshness pass: roll the oldest previously-crawled
                # pages back into the queue so every sync genuinely re-checks
                # poe2db (pages change after patches; without this, a "sync"
                # after full site coverage made zero HTTP requests).
                try:
                    scraper.requeue_stale(days=int(self.config.get("recheck_days", 7)),
                                          cap=int(self.config.get("recheck_cap", 2000)))
                except Exception:
                    pass
                concurrency = int(self.config.get("crawl_concurrency", 10))
                max_pages = int(self.config.get("crawl_max_pages", 80000))
                # Drain mode (default on): after the main pass, keep re-queuing
                # pages that were skipped due to timeouts/rate-limits and crawl
                # again until nothing retryable remains — bounded by a round cap
                # and a stall guard so it always terminates. Set config
                # "crawl_drain" to false for a single old-style pass.
                if bool(self.config.get("crawl_drain", True)) and \
                        hasattr(scraper, "crawl_until_drained"):
                    result = scraper.crawl_until_drained(
                        max_pages=max_pages, concurrency=concurrency,
                        stop_flag=self._sync_stop)
                else:
                    result = scraper.crawl(max_pages=max_pages,
                                           concurrency=concurrency,
                                           stop_flag=self._sync_stop)
                total_new = result["stored"]
                total_updated = result.get("updated", 0)
            else:
                log("DATABASE", "poe2db disabled in your source settings; skipping.")

            # poe2wiki (secondary; only if enabled).
            wiki_new = 0
            if _on("poe2wiki", False) and WikiScraper and not self._sync_stop.is_set():
                try:
                    ws = WikiScraper(wdb, logger=log, progress=_progress)
                    wiki_conc = int(self.config.get("wiki_concurrency", 3))
                    wiki_new = ws.crawl(max_pages=20000, concurrency=wiki_conc,
                                        stop_flag=self._sync_stop)
                except Exception as e:
                    log("DATABASE", f"Wiki crawl skipped: {e}")

            # poe.ninja economy (secondary; only if enabled).
            econ_new = 0
            if _on("poe_ninja", False) and self.poe_ninja and not self._sync_stop.is_set():
                try:
                    econ_new = self.poe_ninja.store_economy(wdb, self.config.get("league", "Standard"))
                except Exception as e:
                    log("DATABASE", f"Economy snapshot skipped: {e}")

            stats = scraper.stats()
            stats["new_this_run"] = total_new + wiki_new + econ_new
            stats["updated_this_run"] = total_updated
            # Count BOTH 'queued' (poe2db frontier) and 'error' (wiki pages that
            # failed, usually Cloudflare throttling) — previously only 'queued'
            # was counted, so the dialog said "whole site covered" while
            # thousands of wiki pages were still missing.
            try:
                wdb.cursor.execute(
                    "SELECT COUNT(*) FROM crawl_state WHERE status IN ('queued','error')")
                stats["pending"] = wdb.cursor.fetchone()[0]
            except Exception:
                stats["pending"] = scraper.pending_count()
            self.signals.sync_finished.emit(stats)
        except Exception as e:
            self.signals.log.emit("DATABASE", f"Crawl error: {e}")
            self.signals.sync_state.emit(False)
        finally:
            if wdb:
                try:
                    wdb.close()
                except Exception:
                    pass

    # -- Obsidian export --
    def export_obsidian_vault(self):
        if not (ObsidianExporter and self.db):
            self._info("Export unavailable", "Database/exporter not loaded.")
            return
        threading.Thread(target=self._export_worker, daemon=True).start()

    def _export_worker(self):
        """Run the vault export in a SEPARATE PROCESS and stream its progress
        into the terminal. The export is CPU-bound; in a mere thread the GIL
        lets it starve the UI (this froze the whole app). A subprocess has its
        own interpreter, so the overlay stays perfectly smooth."""
        out_dir = self.config.get("dir_vault", "data_engine/vault")
        result = None
        try:
            import sys as _sys
            import subprocess as _sp
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            script = os.path.join(root, "core_engine", "obsidian_export.py")
            flags = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW
            proc = _sp.Popen([_sys.executable, script, "--out", out_dir],
                             stdout=_sp.PIPE, stderr=_sp.STDOUT, text=True,
                             encoding="utf-8", errors="replace",
                             cwd=root, creationflags=flags)
            for line in proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                if line.startswith("RESULT "):
                    try:
                        result = json.loads(line[len("RESULT "):])
                    except Exception:
                        result = None
                else:
                    self.signals.log.emit("DATABASE", line)
            proc.wait(timeout=10)
        except Exception as e:
            self.signals.log.emit("DATABASE",
                                  f"Export subprocess failed ({e}); falling back to in-app export.")
            result = None

        if result is None:
            # Fallback: in-process (still off the UI thread; progress-logged).
            wdb = None
            try:
                wdb = KalandraDBHandler() if KalandraDBHandler else None
                if wdb is not None:
                    ex = ObsidianExporter(
                        wdb, out_dir=out_dir,
                        logger=lambda c, m: self.signals.log.emit(c, m),
                        progress=lambda done, total, phase: self.signals.log.emit(
                            "DATABASE", f"Export progress: {done}/{total} {phase}"))
                    result = ex.export()
            except Exception as e:
                self.signals.log.emit("DATABASE", f"Obsidian export error: {e}")
            finally:
                if wdb:
                    try:
                        wdb.close()
                    except Exception:
                        pass
        self.signals.export_finished.emit(result or {"notes": 0, "path": ""})

    def import_game_data(self):
        if not (PoE2DataExtractor and KalandraDBHandler):
            self._info("Game data unavailable", "Extractor/database not loaded.")
            return
        def _work():
            wdb = None
            try:
                wdb = KalandraDBHandler()
                log = lambda c, m: self.signals.log.emit(c, m)
                ex = PoE2DataExtractor(wdb, logger=log)
                # Primary: schema-driven .datc64 import (real game data, with
                # resolved relationships for the Obsidian graph).
                n = ex.import_datc64_dir()
                # Also ingest any pre-extracted JSON if present.
                try:
                    n += ex.import_extracted_dir()
                except Exception:
                    pass
                if n == 0:
                    log("DATABASE", "No game data imported. See EXTRACTOR_SETUP.md "
                        "(put extracted .datc64 in data_engine/game_data).")
                else:
                    # Rebuild the Obsidian vault so the new interactions show up.
                    if ObsidianExporter:
                        try:
                            ObsidianExporter(
                                wdb, out_dir=self.config.get("dir_vault", "data_engine/vault"),
                                logger=log,
                                progress=lambda done, total, phase: log(
                                    "DATABASE", f"Vault progress: {done}/{total} {phase}")
                            ).export()
                        except Exception as e:
                            log("DATABASE", f"Vault export skipped: {e}")
            except Exception as e:
                self.signals.log.emit("DATABASE", f"Game data import error: {e}")
            finally:
                if wdb:
                    try:
                        wdb.close()
                    except Exception:
                        pass
        threading.Thread(target=_work, daemon=True).start()

    def _on_export_finished(self, result):
        if result.get("notes"):
            self._info("Obsidian Vault Ready",
                       f"Exported {result['notes']} notes to:\n{result['path']}\n\n"
                       "In Obsidian: Open folder as vault → this folder, then use Graph view.")
        else:
            self._info("Obsidian Export",
                       "Nothing exported yet — run a DB sync first to fill the knowledge base.")

    def _on_chars_finished(self, result):
        # Reserved for startup prefetch logging.
        if result.get("ok"):
            logger.log_event("POB", f"Startup prefetch: {len(result.get('characters', []))} characters.")

    # -- game data: boot check + scan (reference, don't duplicate) --
    def startup_game_data_check(self):
        """On boot: do a CHEAP, read-only scan to note whether extracted game
        data exists, and log a one-line status. It deliberately does NOT extract,
        import, or export anything automatically.

        Game-file (Oodle) extraction is heavy — it reads and decompresses
        gigabytes of bundle data and can spike memory hard — and poe2db is the
        PRIMARY data source, so extraction is an OPTIONAL/backup path that the
        user triggers on demand from Settings -> Setup & Dependencies. Auto-
        running it at startup (the old behavior) could freeze or OOM-crash the
        app while it sat idle, so it is gated behind explicit opt-in config flags
        that default to OFF."""
        if not (PoE2DataExtractor and KalandraDBHandler):
            return
        auto_import = bool(self.config.get("auto_import_game_data", False))
        auto_extract = bool(self.config.get("auto_extract_game_data", False))

        def _work():
            wdb = None
            try:
                wdb = KalandraDBHandler()
                log = lambda c, m: self.signals.log.emit(c, m)
                ex = PoE2DataExtractor(wdb, logger=log)
                s = ex.scan()   # filesystem-only, cheap
                if s.get("extracted_files"):
                    log("STARTUP", f"Game data: {s['extracted_files']} extracted file(s) "
                        f"present ({s.get('extracted_mb', '?')} MB). "
                        + ("Importing (auto)..." if auto_import and s.get("needs_import")
                           else "Use Settings -> Import game data if you want it in the DB."))
                    # Importing already-extracted files is bounded; still opt-in.
                    if auto_import and s.get("needs_import"):
                        res = ex.auto_update()
                        if res.get("status") == "imported":
                            log("STARTUP", f"Game data updated: {res.get('rows')} entries imported.")
                else:
                    log("STARTUP", "Game data: none extracted (poe2db is the primary "
                        "source; extraction is optional via Settings).")
                    # Heavy Oodle extraction NEVER runs automatically unless the
                    # user has explicitly opted in.
                    if auto_extract:
                        log("STARTUP", "auto_extract_game_data is ON — extracting in-process...")
                        if self._extract_game_data_inprocess(log) and auto_import:
                            res = ex.auto_update()
                            if res.get("status") == "imported":
                                log("STARTUP", f"Game data updated: {res.get('rows')} entries imported.")
            except Exception as e:
                self.signals.log.emit("STARTUP", f"Game-data check skipped: {e}")
            finally:
                if wdb:
                    try:
                        wdb.close()
                    except Exception:
                        pass
        threading.Thread(target=_work, daemon=True).start()

    def _extract_game_data_inprocess(self, log):
        """Use the in-process Oodle extractor to pull the .datc64 tables straight
        from the game install into data_engine/game_data/. Returns True if any
        table was written. No external converter, nothing copied wholesale."""
        if not OodleExtractor:
            return False
        try:
            from core_engine.poe2_data_extract import DEFAULT_TABLES
        except Exception:
            DEFAULT_TABLES = ["BaseItemTypes", "Mods", "Stats", "SkillGems", "Tags"]
        try:
            ex = OodleExtractor(install_dir=self.config.get("game_install_dir"),
                                logger=lambda c, m: self.signals.log.emit(c, m))
            if not (ex.install and ex.dll_path):
                return False
            log("STARTUP", "Extracting game data in-process (game's own Oodle DLL)...")
            out_dir = self.config.get("dir_game_data", "data_engine/game_data")
            res = ex.extract_tables(DEFAULT_TABLES, out_dir)
            return bool(res.get("written"))
        except Exception as e:
            self.signals.log.emit("STARTUP", f"In-process extraction skipped: {e}")
            return False

    def scan_game_data_text(self):
        """Synchronous scan for the Settings panel (filesystem only, fast)."""
        if not (PoE2DataExtractor and KalandraDBHandler):
            return "Game-data extractor not available."
        wdb = None
        try:
            wdb = KalandraDBHandler()
            s = PoE2DataExtractor(wdb).scan()
        except Exception as e:
            return f"Scan failed: {e}"
        finally:
            if wdb:
                try:
                    wdb.close()
                except Exception:
                    pass
        if not s["install_found"]:
            return ("PoE2 install: NOT found.\nInstall PoE2, or run an extractor and drop "
                    ".datc64 files in data_engine/game_data/ (see EXTRACTOR_SETUP.md).")
        changed = " (CHANGED since last import)" if s["game_changed"] else ""
        tail = ("New data to import — click 'Import game data'." if s["needs_import"]
                else "Up to date.")
        return (f"Install: {s['install_path']}\n"
                f"Game version token: {s['game_version']}{changed}\n"
                f"Extracted files: {s['extracted_files']} ({s['extracted_mb']} MB)\n"
                f"Recognized tables: {', '.join(s['recognized_tables']) or 'none'}\n"
                f"Last imported rows: {s['last_imported_rows']}\n{tail}")

    # -- startup freshness check (badge the sync button if out of date) --
    def startup_freshness_check(self):
        """On launch, check our data sources and flag the sync button if the
        live game version has changed (or we've never synced)."""
        if not FreshnessChecker:
            return
        def _work():
            try:
                tm = KalandraTimeMatrix() if KalandraTimeMatrix else None
                wdb = KalandraDBHandler() if KalandraDBHandler else None
                fc = FreshnessChecker(db_handler=wdb, time_matrix=tm,
                                      logger=lambda c, m: self.signals.log.emit(c, m))
                report = fc.run_startup_check(online=True)
                if wdb:
                    wdb.close()
                if report.get("needs_sync"):
                    self.signals.log.emit("STARTUP",
                        "Data looks out of date vs the live sources — sync recommended.")
                    self.signals.sync_needed.emit(True)
                else:
                    self.signals.log.emit("STARTUP", "Local database is up to date.")
            except Exception as e:
                self.signals.log.emit("STARTUP", f"Freshness check skipped: {e}")
        threading.Thread(target=_work, daemon=True).start()

    # -- initial sync on launch --
    def initial_sync(self):
        """Light, non-blocking startup sync: economy + character prefetch if configured."""
        def _work():
            try:
                league = self.config.get("league", "Standard")
                account = self.config.get("account_name")
                if account and self.poe_account:
                    sess = self.accounts.get_secret("poesessid") if self.accounts else None
                    res = self.poe_account.get_characters(account, league=league, poesessid=sess)
                    self.signals.chars_finished.emit(res)
                else:
                    self.signals.log.emit("STARTUP",
                        "No PoE account saved yet — click the green medallion to sync characters.")
            except Exception as e:
                self.signals.log.emit("STARTUP", f"Initial sync skipped: {e}")
        threading.Thread(target=_work, daemon=True).start()

    def select_active_character(self):
        if not (self.poe_account or self.pob_bridge):
            self._info("Characters unavailable",
                       "Character features need core modules.\n\npip install requests")
            return
        try:
            dlg = CharacterDialog(self.poe_account, self.accounts, self.config, self,
                                  on_select=self._set_active_character,
                                  pob_bridge=self.pob_bridge,
                                  on_load_sim=self.load_build_into_sim,
                                  on_load_build_file=self.load_build_from_file)
            self._present_menu(dlg, modal=True)
        except Exception as e:
            self._info("Character dialog error", str(e))

    def _set_char_notify(self, on):
        self.char_notify = bool(on)
        self.update()

    def _on_sim_updated(self):
        """Live sim produced numbers — refresh the dashboard Build tab if it's open."""
        d = getattr(self, "_dashboard", None)
        if d is not None:
            try:
                bt = getattr(d, "_build_tab", None)
                if bt is not None:
                    bt.refresh()
            except Exception:
                pass

    def _load_companion_orb(self):
        """Load the sprite for the player's chosen companion orb. Tries
        assets/orbs/2d/<slug>.png, then the bundled divine_orb.png, then leaves
        it None (procedural orb)."""
        slug = (self.config.get("companion_orb", "divine") or "divine").lower()
        # Tolerant lookup first (accepts 'Orb_of_Chance.png' etc.), then the
        # bundled Divine Orb as the fallback.
        art = find_orb_art(slug)
        candidates = ([art] if art else []) + [
            os.path.join(self.assets_dir, "divine_orb.png"),
        ]
        self.orb_pixmap = None
        for p in candidates:
            if os.path.exists(p):
                pm = QPixmap(p)
                if not pm.isNull():
                    self.orb_pixmap = pm
                    if p != art and slug != "divine":
                        logger.log_event("SYSTEM",
                            f"No art found for companion orb '{slug}' "
                            f"(expected {ORB_ART_DIR}/{slug}.png) — showing Divine Orb.")
                    break
        # New art -> drop any cached scaled copies (guard: called before
        # __init__ finishes creating the cache on first run).
        if hasattr(self, "_px_cache"):
            self._px_cache = {}

    def _apply_companion_orb(self, slug):
        """Settings callback: switch the companion orb live."""
        self.config["companion_orb"] = (slug or "divine").lower()
        try:
            save_config(self.config)
        except Exception:
            pass
        self._load_companion_orb()
        self.update()

    def _set_active_character(self, label):
        self.active_character = label
        logger.log_event("POB", f"Active character: {label}")
        self.update()

    def current_build_view(self):
        """Snapshot of the loaded build for the dashboard Build (PoB) tab. Always
        works from the parse — no LuaJIT simulator needed."""
        full = self.current_build_full if isinstance(self.current_build_full, dict) else None
        view = {
            "loaded": bool(self.current_build_summary),
            "character": self.active_character if self.active_character != "None" else None,
            "summary": self.current_build_summary or "",
            "scaling": {}, "guidance": "", "jewels": [], "sim": "",
            # Structured parse for the dashboard's Container view (W3-10):
            # class/ascendancy/level, stats{}, items[], skills[], main skill.
            "full": full,
        }
        # Live LuaJIT-sim numbers, if the engine is up and a build is loaded.
        if self.current_sim_stats and self.pob_sim:
            try:
                view["sim"] = self.pob_sim.stats_summary(self.current_sim_stats)
            except Exception:
                view["sim"] = ""
        if full and self.pob_bridge:
            try:
                view["scaling"] = self.pob_bridge.analyze_scaling(full) or {}
            except Exception:
                pass
            try:
                view["guidance"] = self.pob_bridge.tree_guidance(full) or ""
            except Exception:
                pass
            view["jewels"] = full.get("jewels", []) or []
        return view

    def open_dashboard(self):
        """Open the single-pane dashboard window (kept referenced so it persists)."""
        try:
            from gui_overlay.dashboard import KalandraDashboard
            if getattr(self, "_dashboard", None) is None:
                self._dashboard = KalandraDashboard(
                    config=self.config, pob_sim=self.pob_sim, accounts=self.accounts,
                    issues=self.issues, build_provider=self.current_build_view,
                    ask_ai=self.ask_ai_text,
                    on_build_saved=self.load_build_from_file)
            self._present_menu(self._dashboard)
            return self._dashboard
        except Exception as e:
            self._info("Dashboard error", str(e))
            return None

    def _rebuild_dashboard_tabs(self):
        """The user changed which dashboard tabs are shown — rebuild it so the
        change takes effect (the dashboard is built once and cached)."""
        d = getattr(self, "_dashboard", None)
        if d is None:
            return
        try:
            d.removeEventFilter(self)
        except Exception:
            pass
        try:
            d.close()
            d.deleteLater()
        except Exception:
            pass
        if getattr(self, "_open_menu", None) is d:
            self._open_menu = None
        self._dashboard = None
        # Deliberately NOT reopened here: it rebuilds fresh (with the new tab
        # set) the next time it's summoned. Auto-reopening would close the
        # Settings menu mid-toggle under the one-menu-at-a-time rule.

    def open_dashboard_build(self):
        """Open the dashboard focused on the Build (PoB) tab for the active
        character. Clears the character-selector notification badge."""
        self.char_notify = False
        self.update()
        dash = self.open_dashboard()
        if dash is not None:
            try:
                dash.show_build_tab()
            except Exception:
                pass

    def open_dependencies(self):
        """Open the Setup & Dependencies manager."""
        try:
            from gui_overlay.dependencies import DependenciesDialog
            def _oodle_test():
                if not OodleExtractor:
                    return {"notes": ["Extractor module not available."]}
                return OodleExtractor(install_dir=self.config.get("game_install_dir"),
                                      logger=lambda c, m: self.signals.log.emit(c, m)).self_test()
            def _extract():
                try:
                    from core_engine.poe2_data_extract import DEFAULT_TABLES
                except Exception:
                    DEFAULT_TABLES = ["BaseItemTypes", "Mods", "Stats", "SkillGems", "Tags"]
                ex = OodleExtractor(install_dir=self.config.get("game_install_dir"),
                                    logger=lambda c, m: self.signals.log.emit(c, m))
                res = ex.extract_tables(DEFAULT_TABLES,
                                        self.config.get("dir_game_data", "data_engine/game_data"))
                # Import what we just extracted so the AI can use it immediately.
                if res.get("written") and PoE2DataExtractor and KalandraDBHandler:
                    wdb = None
                    try:
                        wdb = KalandraDBHandler()
                        PoE2DataExtractor(wdb, logger=lambda c, m: self.signals.log.emit(c, m)).auto_update(force=True)
                    except Exception as e:
                        self.signals.log.emit("DATABASE", f"Import after extract failed: {e}")
                    finally:
                        if wdb:
                            try:
                                wdb.close()
                            except Exception:
                                pass
                return res
            dlg = DependenciesDialog(self.config, save_config, self, oodle_self_test=_oodle_test,
                                     on_extract_gamedata=_extract)
            self._present_menu(dlg, modal=True)
        except Exception as e:
            self._info("Setup error", str(e))

    def load_build_into_sim(self, pob_code):
        """Make the AI 'see' the whole build: parse the full PoB (items, gems,
        stats) into the AI context, save it as a loadable .pob/.xml file, and (if
        set up) load it into the headless simulator for live math."""
        # Full-build parse for the AI + save a loadable file — works with no sim.
        if self.pob_bridge and pob_code:
            try:
                xml = self.pob_bridge.decode_pob_string(pob_code)
                full = self.pob_bridge.extract_full_build(xml)
                self.current_build_summary = self.pob_bridge.build_ai_summary(full)
                self.current_build_full = full if isinstance(full, dict) else None
                self.current_build_xml = xml if isinstance(xml, str) else None
                self.current_sim_stats = None
                if isinstance(xml, str):
                    d = self.config.get("dir_pob", "data_engine/pob")
                    os.makedirs(d, exist_ok=True)
                    cls = (full.get("class_name", "build") if isinstance(full, dict) else "build")
                    path = os.path.join(d, f"{cls}_{full.get('level','')}.xml")
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(xml)
                    self.signals.log.emit("POB", f"Build saved (importable in PoB): {path}")
            except Exception as e:
                self.signals.log.emit("POB", f"Build parse/save error: {e}")
        if not (self.pob_sim and pob_code):
            return
        def _work():
            try:
                if not self.pob_sim.available:
                    # Optional feature; log a single concise note (not the full
                    # multi-line setup message every time a build loads).
                    if not getattr(self, "_sim_warned", False):
                        self._sim_warned = True
                        self.signals.log.emit("POB", "Live PoB simulator not set up (optional) "
                                              "— see POB_SIM_SETUP.md. Build still loaded for reference.")
                    return
                self.signals.log.emit("POB", "Loading build into headless PoB simulator...")
                stats = (self.pob_sim.load_build_xml(self.current_build_xml)
                         if self.current_build_xml else self.pob_sim.load_build(pob_code))
                if stats:
                    self.current_sim_stats = stats
                    self.signals.log.emit("POB", "Live sim: " + self.pob_sim.stats_summary(stats))
                    self.signals.sim_updated.emit()
                else:
                    self.signals.log.emit("POB", "Simulator could not load that build — run the "
                                          "self-test (Dashboard > Build Sim) and send me the output.")
            except Exception as e:
                self.signals.log.emit("POB", f"Simulator load error: {e}")
        threading.Thread(target=_work, daemon=True).start()

    def load_build_from_file(self, path):
        """Load a saved PoB build .xml straight from disk so the AI can 'see' it.
        This is what the green Character Selector calls when you 'Set active
        character' on one of your saved builds. Returns True on success."""
        if not (self.pob_bridge and path):
            return False
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                xml = f.read()
            full = self.pob_bridge.extract_full_build(xml)
            if isinstance(full, dict) and "error" in full:
                self.signals.log.emit("POB", f"Could not parse build: {full['error']}")
                return False
            self.current_build_summary = self.pob_bridge.build_ai_summary(full)
            self.current_build_full = full   # keep structured build for RAG tag search
            self.current_build_xml = xml
            self.current_sim_stats = None
            cls = full.get("class_name", "build") if isinstance(full, dict) else "build"
            asc = full.get("ascendancy", "None") if isinstance(full, dict) else "None"
            lvl = full.get("level", "?") if isinstance(full, dict) else "?"
            main = full.get("main_skill") if isinstance(full, dict) else None
            extra = f", main skill {main}" if main else ""
            self.signals.log.emit(
                "POB", f"Active build loaded from {os.path.basename(path)}: "
                f"{cls} / {asc} Lv{lvl}{extra}. The Orb can now see it.")
            # Badge the character selector: double-click it to view in the PoB tab.
            self.char_notify = True
            self.update()
            # Remember WHICH file is active (and when it was saved) so the
            # owl can prompt a re-import when the build goes stale — your
            # real character outgrows the saved copy fast while leveling.
            try:
                self.config["active_build_path"] = os.path.abspath(path)
                save_config(self.config)
            except Exception:
                pass
            # W4-07: every loaded character gets a folio (folder of working
            # memory: scan, generated review, roadmap, watchlist) that the
            # Companion's per-character features build on.
            try:
                from core_engine.character_folio import CharacterFolio
                fname = os.path.splitext(os.path.basename(path))[0]
                folio = CharacterFolio(fname)
                folio.write_scan(full)
                self.signals.log.emit(
                    "POB", f"Character folio updated: data_engine/characters/"
                           f"{folio.slug}/")
            except Exception:
                pass
            # Per-character orb identity: if this character has an assigned
            # orb (Character Selector -> 'Companion orb for selected'), the
            # mirror switches to it on load.
            try:
                stem = os.path.splitext(os.path.basename(path))[0]
                orbs_map = self.config.get("character_orbs") or {}
                slug = orbs_map.get(stem) or orbs_map.get(
                    full.get("name") if isinstance(full, dict) else "")
                if slug:
                    self._apply_companion_orb(slug)
                    self.signals.log.emit(
                        "GUI", f"Companion orb for {stem}: {slug}.")
            except Exception:
                pass
            # Also feed the headless sim if it's set up (optional, non-blocking).
            if self.pob_sim and getattr(self.pob_sim, "available", False):
                def _sim():
                    try:
                        stats = self.pob_sim.load_build_xml(xml)
                        if stats:
                            self.current_sim_stats = stats
                            self.signals.log.emit("POB", "Live sim: "
                                                  + self.pob_sim.stats_summary(stats))
                            self.signals.sim_updated.emit()
                    except Exception:
                        pass
                threading.Thread(target=_sim, daemon=True).start()
            return True
        except Exception as e:
            self.signals.log.emit("POB", f"Could not load saved build: {e}")
            return False

    def take_snapshot(self):
        logger.log_event("OCR", "Capturing live tooltip screenshot.")
        self.hide()
        QTimer.singleShot(250, self.perform_screenshot_capture)

    def perform_screenshot_capture(self):
        screen = QApplication.primaryScreen()
        screenshot = screen.grabWindow(0)
        self.show()
        snapshots_dir = self.config.get("dir_snapshots", "data_engine/snapshots")
        os.makedirs(snapshots_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(snapshots_dir, f"snapshot_{ts}.png")
        screenshot.save(path, "png")
        logger.log_event("OCR", f"Saved timestamped tooltip: {path}")
        self.flash_intensity = 1.0
        self.update()

    def toggle_screen_recording(self):
        if not self.recorder:
            self._info("Recording unavailable",
                       "Screen recorder could not load.\n\n"
                       "Install: pip install mss opencv-python numpy")
            return
        from core_engine import media_recorder as _mr
        if not _mr.VIDEO_AVAILABLE:
            self._info("Recording unavailable", self.recorder.availability_message())
            return

        if not self.recording_active:
            # One-time, clear consent before we ever capture the screen/mic.
            if not self.recording_consent_given:
                agreed = False
                try:
                    agreed = kconfirm(
                        self, "SCREEN RECORDING — CONSENT",
                        "<b>Start recording your screen?</b><br><br>"
                        "This captures your primary monitor (and your microphone, "
                        "if available) to a local file in data_engine/clips. "
                        "Nothing is uploaded. A red “● REC” indicator shows while "
                        "recording.", "Start recording", "Cancel")
                except Exception:
                    box = QMessageBox(self)
                    box.setWindowTitle("Screen Recording — Consent")
                    box.setText("<b>Start recording your screen?</b>")
                    box.setStandardButtons(QMessageBox.StandardButton.Yes
                                           | QMessageBox.StandardButton.No)
                    box.setStyleSheet("background-color:#1a1e24;color:#fff;")
                    agreed = box.exec() == QMessageBox.StandardButton.Yes
                if not agreed:
                    return
                self.recording_consent_given = True
            if self.recorder.start():
                self.recording_active = True
                self.update()
                logger.log_event("OCR", "Screen recorder STARTED (double-click ruby again to stop).")
            else:
                self._info("Recording error", "Could not start the screen recorder.")
        else:
            logger.log_event("OCR", "Screen recorder STOPPING, finalizing file...")
            threading.Thread(target=self._record_stop_worker, daemon=True).start()

    def _record_stop_worker(self):
        try:
            out = self.recorder.stop()
            transcript_path = None
            audio = out.get("audio")
            if audio and self.voice:
                text = self.voice.transcribe_file(audio)
                if text:
                    transcript_path = os.path.splitext(out["video"])[0] + "_transcription.txt"
                    with open(transcript_path, "w", encoding="utf-8") as f:
                        f.write(f"Transcription for: {logger.active_project_tag}\n")
                        f.write(f"Timestamp: {datetime.now().isoformat()}\n\n{text}\n")
            out["transcript"] = transcript_path
            self.signals.record_finished.emit(out)
        except Exception as e:
            self.signals.log.emit("OCR", f"Recording finalize error: {e}")
            self.signals.record_finished.emit({"video": None, "audio": None, "transcript": None})

    def show_settings_alert(self):
        self.menu_active = True
        self.update()
        logger.log_event("SYSTEM", "Opening settings & accounts panel.")
        try:
            dlg = SettingsDialog(self.accounts, self.config, self,
                                 on_export_vault=self.export_obsidian_vault,
                                 on_import_gamedata=self.import_game_data,
                                 on_open_dashboard=self.open_dashboard,
                                 on_scan_gamedata=self.scan_game_data_text,
                                 on_open_deps=self.open_dependencies,
                                 voices=self._voice_cache, issues=self.issues,
                                 orbs=self.COMPANION_ORBS,
                                 current_orb=self.config.get("companion_orb", "divine"),
                                 on_orb_change=self._apply_companion_orb,
                                 usage_provider=self.ai_usage_summary,
                                 on_dashboard_change=self._rebuild_dashboard_tabs)
            self._present_menu(dlg, modal=True)
            # Re-init voice with possibly-changed brain/key/model.
            if VoiceEngine and self.accounts:
                self.voice = VoiceEngine(
                    whisper_model_size=self.config.get("whisper_model", "base"),
                    brain=self.config.get("ai_brain", "openai"),
                    api_key_provider=self.accounts.get_secret,
                    logger=lambda c, m: self.signals.log.emit(c, m),
                    openai_model=self.config.get("openai_model", "gpt-4o-mini"),
                    gemini_model=self.config.get("gemini_model", "gemini-2.5-flash"),
                    model=self._active_model(),
                    voice_id=self.config.get("voice_id") or None,
                    voice_rate=self.config.get("voice_rate") or None)
        except Exception as e:
            self._info("Settings error", str(e))
        self.menu_active = False
        self.update()

    # ------------------------------------------------
    def _info(self, title, text):
        try:
            kinfo(self, title.upper(), text)
        except Exception:
            msg = QMessageBox(self)
            msg.setWindowTitle(title)
            msg.setText(text)
            msg.setStyleSheet("background-color:#1a1e24;color:#fff;")
            msg.exec()

    def closeEvent(self, event):
        logger.log_event("SYSTEM", "Closing application. Bundling session log data.")
        try:
            if self.recording_active and self.recorder:
                self.recorder.stop()
        except Exception:
            pass
        try:
            if self.db:
                self.db.close()
        except Exception:
            pass
        logger.dump_transcript_on_exit()
        event.accept()
        # Auto-quit-on-last-window is disabled (so closing the dashboard doesn't
        # kill us), so the overlay must quit the app explicitly on exit.
        try:
            if getattr(self, "_dashboard", None) is not None:
                # Graceful goodbye to containerized programs: PoB/Overlay we
                # LAUNCHED get WM_CLOSE (terminate only as fallback); adopted
                # EXTERNAL instances are released back to the desktop intact.
                try:
                    self._dashboard.shutdown_embedded()
                except Exception:
                    pass
                self._dashboard.deleteLater()
        except Exception:
            pass
        app = QApplication.instance()
        if app is not None:
            app.quit()


def _install_crash_guard():
    """Record unhandled exceptions (main thread AND worker threads) to a crash
    log instead of letting them vanish or abort the app without a trace."""
    import sys as _sys

    def _log_crash(where, exc_type, exc, tb):
        try:
            os.makedirs("data_engine", exist_ok=True)
            with open(os.path.join("data_engine", "crash.log"), "a", encoding="utf-8") as f:
                f.write(f"\n===== {datetime.now().isoformat()} ({where}) =====\n")
                traceback.print_exception(exc_type, exc, tb, file=f)
        except Exception:
            pass
        try:
            traceback.print_exception(exc_type, exc, tb)
        except Exception:
            pass

    def _hook(exc_type, exc, tb):
        _log_crash("main", exc_type, exc, tb)
    _sys.excepthook = _hook

    # Worker-thread exceptions (Python 3.8+).
    try:
        def _thook(args):
            _log_crash(f"thread:{getattr(args, 'thread', None)}",
                       args.exc_type, args.exc_value, args.exc_traceback)
        threading.excepthook = _thook
    except Exception:
        pass


if __name__ == "__main__":
    if PYQT_AVAILABLE:
        try:
            _install_crash_guard()
            try:
                QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
            except Exception:
                pass
            app = QApplication(sys.argv)
            app.setQuitOnLastWindowClosed(False)  # overlay (a Tool window) owns exit
            overlay = KalandraOverlayApp()
            overlay.show()
            QTimer.singleShot(800, overlay.initial_sync)
            QTimer.singleShot(1200, overlay.startup_freshness_check)
            QTimer.singleShot(1600, overlay.startup_game_data_check)
            exit_code = app.exec()
            print("\n=========================================================")
            print(f"    KALANDRA OVERLAY v{KALANDRA_VERSION} TERMINATED SAFELY.")
            print("    Press Enter to close this diagnostic terminal window...")
            print("=========================================================")
            input()
            sys.exit(exit_code)
        except Exception:
            print("\n=========================================================")
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              