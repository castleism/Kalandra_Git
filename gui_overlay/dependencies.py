"""
GUI_OVERLAY/DEPENDENCIES.PY
The Setup / Dependencies manager. One place to see everything Kalandra can use,
what each part enables, what's installed on this machine, install the missing
pip pieces, point at external tools, and choose where output files go.

Organized as: Core (required), Highly Recommended, Optional. Installed items are
detected and greyed/checked; missing pip items can be installed with a click;
external tools get a "Get it" link + "Set path"; output folders are editable.
"""

import os
import sys
import shutil
import importlib.util
import subprocess
import threading

import fnmatch

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QFrame,
    QScrollArea, QWidget, QPlainTextEdit, QLineEdit, QFileDialog, QMessageBox,
    QApplication
)
from PyQt6.QtCore import Qt, QUrl, QObject, pyqtSignal
from PyQt6.QtGui import QDesktopServices

GOLD = "#c8aa6e"; TEAL = "#3fb6b6"; BG0 = "#0c0e12"; BG1 = "#14181f"
BG2 = "#1b212b"; TEXT = "#e8e6df"; MUTED = "#9aa4b2"; OKC = "#5bd66f"


def _mod_installed(module):
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:
        return False


def _which(*names):
    for n in names:
        if shutil.which(n):
            return shutil.which(n)
    return None


def _find_file(folder, pattern):
    """Find a file matching `pattern` (supports wildcards) at/under `folder`.
    `folder` may itself be a direct path to the file."""
    if not folder:
        return None
    if os.path.isfile(folder) and fnmatch.fnmatch(os.path.basename(folder), pattern):
        return folder
    if os.path.isdir(folder):
        for root, _d, files in os.walk(folder):
            for fn in files:
                if fnmatch.fnmatch(fn, pattern):
                    return os.path.join(root, fn)
    return None


# Dependency registry. kind: "pip" | "external" | "internal".
# check() -> (installed: bool, detail: str)
def _build_registry(config):
    PF86 = os.environ.get("ProgramFiles(x86)", "")
    LAD = os.environ.get("LOCALAPPDATA", "")

    def pip_check(mod):
        return lambda: (_mod_installed(mod), "installed" if _mod_installed(mod) else "missing")

    def ext_check(path_keys, pattern, default_dirs=None):
        """Search the configured path key(s) and default locations for the exact
        file `pattern` the feature needs. Returns (found, path-or-message)."""
        def _c():
            cands = [config.get(k) for k in path_keys] + list(default_dirs or [])
            for c in cands:
                hit = _find_file(c, pattern)
                if hit:
                    return True, hit
            w = shutil.which(pattern)
            if w:
                return True, w
            return False, f"not found (need {pattern})"
        return _c

    return {
        "core": [
            {"id": "pyqt6", "name": "PyQt6", "kind": "pip", "pip": "PyQt6",
             "enables": "The overlay and dashboard UI itself.", "check": pip_check("PyQt6")},
            {"id": "requests", "name": "requests", "kind": "pip", "pip": "requests",
             "enables": "All web access: scrapers, price check, freshness.", "check": pip_check("requests")},
            {"id": "bs4", "name": "BeautifulSoup4", "kind": "pip", "pip": "beautifulsoup4",
             "enables": "Parsing poe2db / poe2wiki pages.", "check": pip_check("bs4")},
            {"id": "numpy", "name": "numpy", "kind": "pip", "pip": "numpy",
             "enables": "Audio/video buffers for recording & voice.", "check": pip_check("numpy")},
            {"id": "keyring", "name": "keyring", "kind": "pip", "pip": "keyring",
             "enables": "Secure storage of API keys/tokens in the OS keychain.", "check": pip_check("keyring")},
        ],
        "recommended": [
            {"id": "pob", "name": "Path of Building 2 (app)", "kind": "external",
             "enables": "The PoB2 build planner app. Lets the orb work with PoB-accurate "
                        "builds (codes + your saved builds). Highly recommended.",
             "file": "Path of Building-PoE2.exe",
             "url": "https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2/releases",
             "path_key": "pob_app_dir",
             "check": ext_check(["pob_exe", "pob_app_dir", "pob_install_dir"],
                                "Path of Building-PoE2.exe",
                                [os.path.join(PF86, "Path of Building Community (PoE2)"),
                                 os.path.join(LAD, "Programs", "Path of Building Community (PoE2)")])},
            {"id": "luajit", "name": "LuaJIT", "kind": "external",
             "enables": "Runs PoB's engine headlessly for the live build simulator.",
             "file": "LuaJIT-For-Windows.exe",
             "url": "https://github.com/ScriptTiger/LuaJIT-For-Windows/releases", "path_key": "luajit_path",
             "check": ext_check(["luajit_path"], "LuaJIT-For-Windows.exe",
                                [os.path.join("tools", "luajit")])},
            {"id": "webengine", "name": "PyQt6-WebEngine", "kind": "pip", "pip": "PyQt6-WebEngine",
             "enables": "Embedded dashboard tabs: Craft of Exile, FilterBlade, poe.ninja.",
             "check": pip_check("PyQt6.QtWebEngineWidgets")},
            {"id": "whisper", "name": "faster-whisper", "kind": "pip", "pip": "faster-whisper",
             "enables": "On-device speech-to-text (the orb hears you).", "check": pip_check("faster_whisper")},
            {"id": "sounddevice", "name": "sounddevice", "kind": "pip", "pip": "sounddevice",
             "enables": "Microphone capture for voice + recording audio.", "check": pip_check("sounddevice")},
            {"id": "pyttsx3", "name": "pyttsx3", "kind": "pip", "pip": "pyttsx3",
             "enables": "On-device text-to-speech (the orb speaks).", "check": pip_check("pyttsx3")},
        ],
        "optional": [
            {"id": "mss", "name": "mss", "kind": "pip", "pip": "mss",
             "enables": "Fast screen capture for recording.", "check": pip_check("mss")},
            {"id": "opencv", "name": "opencv-python", "kind": "pip", "pip": "opencv-python",
             "enables": "Writes the MP4 screen recordings.", "check": pip_check("cv2")},
            {"id": "openai", "name": "OpenAI (ChatGPT)", "kind": "pip", "pip": "openai",
             "enables": "Cloud AI brain option (needs an OpenAI key).", "check": pip_check("openai")},
            {"id": "genai", "name": "Google GenAI (Gemini)", "kind": "pip", "pip": "google-genai",
             "enables": "Cloud AI brain option (needs a Gemini key).", "check": pip_check("google.genai")},
            {"id": "rhubarb", "name": "Rhubarb Lip Sync", "kind": "external",
             "enables": "Phoneme-accurate mouth shapes for the talking face.",
             "file": "rhubarb.exe",
             "url": "https://github.com/DanielSWolf/rhubarb-lip-sync/releases", "path_key": "rhubarb_path",
             "check": ext_check(["rhubarb_path"], "rhubarb.exe",
                                [os.path.join("tools", "rhubarb")])},
            {"id": "reqcache", "name": "requests-cache", "kind": "pip", "pip": "requests-cache",
             "enables": "Caches web hits so re-syncs are faster.", "check": pip_check("requests_cache")},
        ],
    }


class _Sig(QObject):
    log = pyqtSignal(str)
    done = pyqtSignal()


class DependenciesDialog(QDialog):
    def __init__(self, config, save_config, parent=None, oodle_self_test=None,
                 on_extract_gamedata=None):
        super().__init__(parent)
        self.config = config
        self.save_config = save_config
        self.oodle_self_test = oodle_self_test
        self.on_extract_gamedata = on_extract_gamedata
        self.reg = _build_registry(config)
        self.checks = {}      # dep id -> QCheckBox (for pip installs)
        self.path_edits = {}  # config key -> QLineEdit
        self.ext_status = {}  # external dep id -> status QLabel (for live verify)
        self.sig = _Sig()
        self.sig.log.connect(self._append_log)
        self.sig.done.connect(self._refresh)

        try:
            from version import KALANDRA_VERSION as _KV
        except Exception:
            _KV = "0.0.0"
        self.setWindowTitle(f"Kalandra v{_KV} — Setup & Dependencies")
        # Keep the minimum small enough to fit modest screens; the scroll area
        # holds the content, so the window must be allowed to shrink below the
        # content height (otherwise the bottom buttons clip on shorter displays).
        self.setMinimumSize(700, 460)
        self.setStyleSheet(
            f"QDialog{{background:{BG0};color:{TEXT};}}QLabel{{color:{TEXT};}}"
            f"QCheckBox{{color:{TEXT};}}"
            f"QLineEdit{{background:#0c0f14;color:#fff;border:1px solid #3a4150;padding:4px;border-radius:4px;}}"
            f"QPlainTextEdit{{background:#0c0f14;color:#cfe;border:1px solid #2a313d;}}"
            f"QPushButton{{background:{BG2};color:{TEXT};border:1px solid #3a4350;padding:6px 12px;border-radius:6px;}}"
            f"QPushButton:hover{{background:#283040;border-color:{GOLD};}}"
            f"QFrame#card{{background:{BG1};border:1px solid #2a313d;border-radius:8px;}}")
        self._build()
        # Open at a height that fits the screen (leave room for taskbar/title bar);
        # the scroll area handles anything taller.
        try:
            scr = QApplication.primaryScreen()
            avail = scr.availableGeometry() if scr else None
            h = 880
            if avail is not None:
                h = min(h, max(460, avail.height() - 90))
            self.resize(760, h)
        except Exception:
            self.resize(760, 760)

    def _build(self):
        root = QVBoxLayout(self)
        title = QLabel("Setup & Dependencies"); title.setStyleSheet(f"color:{GOLD};font-size:18px;font-weight:bold;")
        root.addWidget(title)
        root.addWidget(self._muted("Installed pieces are checked & greyed. Tick missing pip "
                                   "items and click Install. External tools get a download link "
                                   "and a 'Set path'. Each line says what it enables."))

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        host = QWidget(); self.host_lay = QVBoxLayout(host)

        self._section("Core — required to run", self.reg["core"])
        self._section("Highly recommended", self.reg["recommended"])
        self._section("Optional features", self.reg["optional"])
        self._oodle_section()
        self._paths_section()

        self.host_lay.addStretch()
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

        row = QHBoxLayout()
        auto = QPushButton("Run automated installer (everything)")
        auto.setToolTip("Downloads LuaJIT, Rhubarb, the converter and PoB source into "
                        "tools/ and sets all paths for you.")
        auto.clicked.connect(self._run_auto_installer)
        row.addWidget(auto)
        self.install_btn = QPushButton("Install checked (pip)")
        self.install_btn.clicked.connect(self._install_checked)
        row.addWidget(self.install_btn)
        row.addStretch()
        close = QPushButton("Done"); close.clicked.connect(self.accept)
        row.addWidget(close)
        root.addLayout(row)

        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setFixedHeight(120)
        root.addWidget(self.log)

    def _muted(self, text):
        l = QLabel(text); l.setWordWrap(True); l.setStyleSheet(f"color:{MUTED};font-size:11px;")
        return l

    def _section(self, heading, items):
        h = QLabel(heading); h.setStyleSheet(f"color:{GOLD};font-size:14px;font-weight:bold;margin-top:8px;")
        self.host_lay.addWidget(h)
        for dep in items:
            self.host_lay.addWidget(self._dep_row(dep))

    def _dep_row(self, dep):
        card = QFrame(); card.setObjectName("card"); lay = QVBoxLayout(card)
        installed, detail = dep["check"]()
        top = QHBoxLayout()
        if dep["kind"] == "pip":
            cb = QCheckBox(dep["name"])
            cb.setChecked(False)
            cb.setEnabled(not installed)
            self.checks[dep["id"]] = cb
            top.addWidget(cb)
        else:
            top.addWidget(QLabel("• " + dep["name"]))
        if dep["kind"] == "external":
            status = QLabel(("✓ " + detail) if installed else detail)
        else:
            status = QLabel("✓ installed" if installed else "missing")
        status.setStyleSheet(f"color:{OKC};" if installed else f"color:{MUTED};")
        top.addStretch(); top.addWidget(status)
        lay.addLayout(top)
        if dep["kind"] == "external":
            self.ext_status[dep["id"]] = status

        desc_text = dep["enables"]
        if dep.get("file"):
            desc_text += f"   (looks for the file: {dep['file']})"
        desc = QLabel(desc_text); desc.setWordWrap(True); desc.setStyleSheet(f"color:{MUTED};font-size:11px;")
        lay.addWidget(desc)

        if dep["kind"] == "external":
            erow = QHBoxLayout()
            get = QPushButton("Get it")
            get.clicked.connect(lambda _, u=dep["url"]: QDesktopServices.openUrl(QUrl(u)))
            erow.addWidget(get)
            if dep.get("path_key"):
                setp = QPushButton("Set path…")
                setp.clicked.connect(lambda _, d=dep: self._set_path(d))
                erow.addWidget(setp)
            verify = QPushButton(f"Verify ({dep.get('file', 'file')})")
            verify.setToolTip("Re-check that the needed file can be found at the set location.")
            verify.clicked.connect(lambda _, d=dep: self._verify_dep(d))
            erow.addWidget(verify)
            erow.addStretch()
            lay.addLayout(erow)
        return card

    def _verify_dep(self, dep):
        installed, detail = dep["check"]()
        st = self.ext_status.get(dep["id"])
        if st:
            st.setText(("✓ " + detail) if installed else detail)
            st.setStyleSheet(f"color:{OKC};" if installed else f"color:{MUTED};")
        fname = dep.get("file", "the required file")
        if installed:
            QMessageBox.information(self, "Verify: SUCCESS",
                                    f"Found {fname}:\n\n{detail}")
            self._append_log(f"Verify {dep['name']}: OK — {detail}")
        else:
            QMessageBox.warning(self, "Verify: NOT FOUND",
                                f"Could not find '{fname}'.\n\n"
                                f"Use 'Get it' to install it, or 'Set path…' to point at the "
                                f"folder (or the {fname} file) where it lives, then Verify again.")
            self._append_log(f"Verify {dep['name']}: not found (need {fname})")

    def _oodle_section(self):
        h = QLabel("Game-file extraction (experimental)")
        h.setStyleSheet(f"color:{GOLD};font-size:14px;font-weight:bold;margin-top:8px;")
        self.host_lay.addWidget(h)
        card = QFrame(); card.setObjectName("card"); lay = QVBoxLayout(card)
        lay.addWidget(QLabel("In-process Oodle extractor"))
        lay.addWidget(self._muted("Pulls exact item/mod/gem data straight from your installed "
                                  "game using the game's own Oodle DLL — no external tool. "
                                  "Experimental: the button runs a self-test and reports what "
                                  "works so it can be finished against your machine."))
        b = QPushButton("Set up & test in-process extractor")
        b.clicked.connect(self._run_oodle_test)
        lay.addWidget(b)
        if self.on_extract_gamedata:
            eb = QPushButton("Extract game data now")
            eb.clicked.connect(self._run_extract_gamedata)
            lay.addWidget(eb)
        self.oodle_status = QLabel(""); self.oodle_status.setWordWrap(True)
        self.oodle_status.setStyleSheet(f"color:{MUTED};font-size:11px;")
        lay.addWidget(self.oodle_status)
        self.host_lay.addWidget(card)

    def _run_extract_gamedata(self):
        if not self.on_extract_gamedata:
            return
        self.oodle_status.setText("Extracting game data… (watch the terminal for progress)")
        def _work():
            try:
                res = self.on_extract_gamedata()
                w = ", ".join(res.get("written", [])) or "none"
                m = ", ".join(res.get("missing", [])) or "none"
                self.sig.log.emit(f"Game-data extraction complete. Wrote: {w}. Missing: {m}.")
            except Exception as e:
                self.sig.log.emit(f"Game-data extraction error: {e}")
        threading.Thread(target=_work, daemon=True).start()

    def _paths_section(self):
        h = QLabel("Where files are saved")
        h.setStyleSheet(f"color:{GOLD};font-size:14px;font-weight:bold;margin-top:8px;")
        self.host_lay.addWidget(h)
        card = QFrame(); card.setObjectName("card"); lay = QVBoxLayout(card)
        rows = [
            ("dir_snapshots", "Screenshots", "data_engine/snapshots"),
            ("dir_clips", "Screen recordings", "data_engine/clips"),
            ("dir_transcripts", "Transcripts", "data_engine/transcripts"),
            ("dir_vault", "Obsidian vault", "data_engine/vault"),
            ("dir_game_data", "Extracted game data", "data_engine/game_data"),
        ]
        for key, label, default in rows:
            r = QHBoxLayout()
            r.addWidget(QLabel(label + ":"))
            e = QLineEdit(self.config.get(key, default))
            self.path_edits[key] = e
            r.addWidget(e, 1)
            b = QPushButton("Browse")
            b.clicked.connect(lambda _, ed=e: self._browse_dir(ed))
            r.addWidget(b)
            lay.addLayout(r)
        save = QPushButton("Save folders")
        save.clicked.connect(self._save_paths)
        lay.addWidget(save)
        self.host_lay.addWidget(card)

    # -- actions --------------------------------------------------------------
    def _append_log(self, line):
        self.log.appendPlainText(line)

    def _refresh(self):
        self.install_btn.setEnabled(True)
        self._append_log("Done. Re-open this window to refresh statuses.")

    def _set_path(self, dep):
        fname = dep.get("file", "")
        # Let the user pick the exact file OR a folder to search.
        f, _ = QFileDialog.getOpenFileName(
            self, f"Select {dep['name']} file ({fname or 'executable'})")
        chosen = f
        if not chosen:
            chosen = QFileDialog.getExistingDirectory(
                self, f"...or select the folder that contains {fname or dep['name']}")
        if not chosen:
            return
        self.config[dep["path_key"]] = chosen
        self.save_config(self.config)
        self._append_log(f"Set {dep['name']} location: {chosen}")
        # Immediately verify that the needed file is actually found there.
        self._verify_dep(dep)

    def _browse_dir(self, edit):
        d = QFileDialog.getExistingDirectory(self, "Select folder")
        if d:
            edit.setText(d)

    def _save_paths(self):
        for key, edit in self.path_edits.items():
            self.config[key] = edit.text().strip()
        self.save_config(self.config)
        self._append_log("Saved folder locations.")

    def _run_oodle_test(self):
        if not self.oodle_self_test:
            self.oodle_status.setText("Extractor not available in this build.")
            return
        self.oodle_status.setText("Testing…")
        def _work():
            try:
                rep = self.oodle_self_test()
                lines = [f"install:{rep.get('install')} dll:{rep.get('dll')} "
                         f"index:{rep.get('index')} dll_loaded:{rep.get('dll_loaded')} "
                         f"index_decompressed:{rep.get('index_decompressed')}"]
                if rep.get("install_path"):
                    lines.append(f"install path: {rep.get('install_path')}")
                lines += rep.get("notes", [])
                self.sig.log.emit("Oodle self-test: " + " | ".join(lines))
            except Exception as e:
                self.sig.log.emit(f"Oodle self-test error: {e}")
        threading.Thread(target=_work, daemon=True).start()

    def _run_auto_installer(self):
        self._append_log("Running automated installer (downloads can take a few minutes)…")
        script = os.path.join(os.getcwd(), "install_dependencies.py")
        if not os.path.exists(script):
            self._append_log("install_dependencies.py not found in the project root.")
            return
        def _work():
            try:
                proc = subprocess.Popen([sys.executable, script],
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, bufsize=1)
                for line in proc.stdout:
                    self.sig.log.emit(line.rstrip())
                proc.wait()
            except Exception as e:
                self.sig.log.emit(f"Installer error: {e}")
            self.sig.log.emit("Automated installer finished. Re-open this window to refresh.")
        threading.Thread(target=_work, daemon=True).start()

    def _install_checked(self):
        pkgs = []
        for dep in (self.reg["core"] + self.reg["recommended"] + self.reg["optional"]):
            cb = self.checks.get(dep["id"])
            if cb and cb.isChecked() and cb.isEnabled():
                pkgs.append(dep["pip"])
        if not pkgs:
            self._append_log("Nothing checked to install.")
            return
        self.install_btn.setEnabled(False)
        self._append_log("Installing: " + ", ".join(pkgs))

        def _work():
            for pkg in pkgs:
                self.sig.log.emit(f"pip install {pkg} …")
                try:
                    proc = subprocess.run([sys.executable, "-m", "pip", "install", "--user", pkg],
                                          capture_output=True, text=True, timeout=600)
                    tail = (proc.stdout or "")[-300:] + (proc.stderr or "")[-300:]
                    self.sig.log.emit(tail.strip() or f"{pkg}: done")
                except Exception as e:
                    self.sig.log.emit(f"{pkg} failed: {e}")
            self.sig.done.emit()
        threading.Thread(target=_work, daemon=True).start()
