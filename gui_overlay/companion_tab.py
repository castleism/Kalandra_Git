"""
GUI_OVERLAY/COMPANION_TAB.PY — the Companion: Kalandra's front room.

The main conversation tab (docs/DESIGN_COMPANION.md P0). Three ideas in one:

  1. THREADS — chats with different orbs are separate, labeled threads
     (left pane). Today: "The Orb" default thread. Later phases add one
     thread per imported character, auto-assigned its own orb.
  2. FRIENDLY LOG — the Terminal's LOG_BUS firehose, rendered gently:
     actions appear between chat messages as small color-coded notes
     (Database=sapphire, Build/PoB=emerald, Voice&AI=gold, Capture=amber,
     errors=ruby), so you SEE what the app did without reading a console.
  3. AUTO-ATTENDANT — if enabled in config ("companion_attendant"), an
     idle timer posts profile-aware conversation starters. With an AI brain
     connected (and "companion_attendant_ai" not disabled) it asks for one
     short starter built from the profile + character folios; otherwise it
     uses zero-token local templates. Web-researched suggestions
     (build sites / YouTube / Reddit) are W4-09 / P6 in DESIGN_COMPANION.

Threads persist as JSON under data_engine/chat_threads/.
"""

import json
import os
import random
import time
from collections import deque

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QSplitter, QTextBrowser, QVBoxLayout, QWidget,
)

from gui_overlay.log_bus import LOG_BUS, group_for
from gui_overlay.theme import (
    BG1, EMERALD, FAINT, GOLD, GOLD_LIGHT, MUTED, RUBY, SAPPHIRE, TEXT,
    COLOR_WARN,
)

THREADS_DIR = os.path.join("data_engine", "chat_threads")
DEFAULT_THREAD = "The Orb"

# LOG_BUS group -> note color in the friendly log.
_GROUP_COLORS = {
    "Database": SAPPHIRE,
    "Build / PoB": EMERALD,
    "Voice & AI": GOLD,
    "Capture": COLOR_WARN,
    "GUI / Actions": MUTED,
    "Other": FAINT,
}
_ERROR_WORDS = ("error", "fail", "exception", "crash", "unavailable")

# Auto-attendant conversation starters: (profile_condition, template).
# condition = (question_id, value) or (None, None) for always-eligible.
_ATTENDANT_LINES = [
    (("build_taste", "niche"),
     "Been thinking — with your taste for the weird ones, want me to dig for "
     "an off-meta skill that got quietly buffed this patch?"),
    (("build_taste", "meta"),
     "Want a rundown of what the ladder's top builds are doing differently "
     "since the last patch?"),
    (("budget", "low"),
     "I could hunt for the biggest damage-per-divine upgrades on your "
     "current character. Cheap wins are my favorite wins."),
    ((None, None),
     "If you tell me a unique you're hoarding, I can check whether any of "
     "your builds could actually use it."),
    ((None, None),
     "Want me to look at your passive tree for pathing that wastes points? "
     "There's usually two or three hiding."),
]


class _Bridge(QObject):
    reply = pyqtSignal(str, str)     # reply, error ('' if none)


class CompanionTab(QWidget):
    def __init__(self, ask_ai=None, config=None, parent=None):
        super().__init__(parent)
        self.ask_ai = ask_ai
        self.config = config or {}
        self.thread_name = DEFAULT_THREAD
        self._bridge = _Bridge()
        self._bridge.reply.connect(self._on_reply)
        # Live display list: persisted chats + in-memory action notes.
        # Actions are NEVER written to disk (LOG_BUS can emit thousands of
        # events during a sync) and rendering is debounced.
        self._display = []
        self._actions_pending = deque(maxlen=500)
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(250)
        self._render_timer.timeout.connect(self._render_thread)
        self._build_ui()
        self._load_threads()
        self._render_thread()
        try:
            LOG_BUS.emitted.connect(self._on_log_event)
        except Exception:
            pass
        # Auto-attendant: quiet unless enabled; never fires within 90s of use.
        self._last_activity = time.time()
        self._attendant = QTimer(self)
        self._attendant.setInterval(120_000)
        self._attendant.timeout.connect(self._attendant_tick)
        if self.config.get("companion_attendant", False):
            self._attendant.start()

    # ------------------------------------------------ UI
    def _build_ui(self):
        root = QVBoxLayout(self)
        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)

        # Left: threads
        left = QWidget(); ll = QVBoxLayout(left)
        hdr = QLabel("Threads"); hdr.setStyleSheet(
            f"color:{GOLD};font-weight:bold;font-size:12px;")
        ll.addWidget(hdr)
        self.thread_list = QListWidget()
        self.thread_list.currentTextChanged.connect(self._switch_thread)
        ll.addWidget(self.thread_list, 1)
        hint = QLabel("One thread per orb.\nCharacter orbs arrive with\n"
                      "PoB import (see roadmap).")
        hint.setStyleSheet(f"color:{FAINT};font-size:10px;")
        ll.addWidget(hint)
        split.addWidget(left)

        # Right: chat view + friendly action log + input
        right = QWidget(); rl = QVBoxLayout(right)
        controls = QHBoxLayout()
        self.show_actions = QCheckBox("Show app actions between messages")
        self.show_actions.setChecked(True)
        self.show_actions.toggled.connect(self._render_thread)
        controls.addWidget(self.show_actions)
        controls.addStretch()
        rl.addLayout(controls)

        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        self.view.setStyleSheet(
            f"QTextBrowser {{ background:{BG1}; color:{TEXT}; border:none;"
            f" font-size:12px; padding:8px; }}")
        rl.addWidget(self.view, 1)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Talk to the Orb — same brain as the voice channel…")
        self.input.returnPressed.connect(self._send)
        row.addWidget(self.input, 1)
        send = QPushButton("Send"); send.clicked.connect(self._send)
        row.addWidget(send)
        rl.addLayout(row)
        split.addWidget(right)
        split.setSizes([180, 720])

    # ------------------------------------------------ threads
    def _thread_path(self, name):
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name)
        return os.path.join(THREADS_DIR, f"{safe}.json")

    def _load_threads(self):
        os.makedirs(THREADS_DIR, exist_ok=True)
        names = []
        try:
            for fn in sorted(os.listdir(THREADS_DIR)):
                if fn.endswith(".json"):
                    names.append(fn[:-5].replace("_", " "))
        except Exception:
            pass
        if DEFAULT_THREAD not in names:
            names.insert(0, DEFAULT_THREAD)
        self.thread_list.clear()
        for n in names:
            QListWidgetItem(n, self.thread_list)
        self.thread_list.setCurrentRow(0)

    def _messages(self, name=None):
        path = self._thread_path(name or self.thread_name)
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def _append_message(self, role, text, kind="chat", color=None):
        entry = {"ts": time.strftime("%H:%M:%S"), "role": role,
                 "text": text, "kind": kind, "color": color}
        self._display.append(entry)
        self._display = self._display[-1200:]
        if kind == "chat":
            # Only real conversation persists; action notes are session-local.
            msgs = self._messages()
            msgs.append(entry)
            try:
                os.makedirs(THREADS_DIR, exist_ok=True)
                with open(self._thread_path(self.thread_name), "w",
                          encoding="utf-8") as f:
                    json.dump(msgs[-800:], f, indent=1, ensure_ascii=False)
            except Exception:
                pass
        if not self._render_timer.isActive():
            self._render_timer.start()

    def _switch_thread(self, name):
        if name:
            self.thread_name = name
            self._display = list(self._messages())
            self._render_thread()

    # ------------------------------------------------ rendering
    def _render_thread(self):
        show_actions = self.show_actions.isChecked()
        if not self._display:
            self._display = list(self._messages())
        parts = []
        for m in self._display:
            kind = m.get("kind", "chat")
            if kind == "action":
                if not show_actions:
                    continue
                c = m.get("color") or FAINT
                parts.append(
                    f"<div style='color:{c};font-size:10px;margin:2px 0 2px 14px;'>"
                    f"⚙ {m['ts']} — {_esc(m['text'])}</div>")
                continue
            if m["role"] == "you":
                parts.append(
                    f"<div style='margin:8px 0 2px 60px;padding:7px 10px;"
                    f"background:#232b38;border-radius:9px;color:{TEXT};'>"
                    f"{_esc(m['text'])}</div>")
            else:
                who = "🦉" if m.get("role") == "owl" else "🔮"
                parts.append(
                    f"<div style='margin:8px 60px 2px 0;padding:7px 10px;"
                    f"background:#1b212b;border:1px solid #3a2f1d;"
                    f"border-radius:9px;color:{GOLD_LIGHT};'>{who} "
                    f"{_esc(m['text'])}</div>")
        self.view.setHtml("<html><body>" + "".join(parts) + "</body></html>")
        self.view.verticalScrollBar().setValue(
            self.view.verticalScrollBar().maximum())

    # ------------------------------------------------ chat
    def start_build_finder(self):
        """New-player arc: the owl hands over here. The next few exchanges
        carry the build-finder directive (playstyle Q&A -> archetype
        suggestions -> roadmap offer; core_engine.build_seeker). When the
        player pastes a guide (URL/text with PoB links), the roadmap engine
        runs on it."""
        self._finder_turns = 6      # directive rides along for this many sends
        self._append_message(
            "owl",
            "Let's find your build. A good guide is training wheels that "
            "teach you which mechanics work together — so first: when you "
            "imagine your character, are you smashing things up close, "
            "shooting from a distance, casting big spells, or letting an "
            "army of minions do the work? Just answer here and we'll narrow "
            "it down. When we've picked one, I'll read the guide, load its "
            "variants into Path of Building, price the gear, and build your "
            "roadmap while you start playing.")
        self.input.setFocus()

    def _maybe_run_roadmap(self, text):
        """If a finder-mode message contains PoB links/codes (a pasted
        guide), run the roadmap engine on it and report."""
        if getattr(self, "_finder_turns", 0) <= 0:
            return False
        try:
            from core_engine.build_seeker import extract_pob_refs, build_roadmap
            refs = extract_pob_refs(text)
            if not (refs["codes"] or refs["links"]):
                return False
            name = "My First Build"
            res = build_roadmap(name, text,
                                league=self.config.get("league"))
            if res.get("error"):
                self._append_message("owl", f"I hit a snag reading that "
                                            f"guide: {res['error']}")
                return True
            msg = (f"Roadmap started! I parsed {res['variants']} build "
                   f"variant(s)")
            if res.get("failed"):
                msg += f" ({res['failed']} wouldn't parse — open those in PoB)"
            msg += (f", put {res['watchlist']} item(s) on your watchlist, and "
                    f"wrote the plan to your character folio. It's in "
                    f"data_engine/characters/ — and the Live Search tab can "
                    f"camp the watchlist items while you level.")
            if res.get("links_found") and not res.get("variants"):
                msg += (" The guide's PoB builds are behind links — open "
                        "them and paste the PoB codes here and I'll finish "
                        "the job.")
            self._append_message("owl", msg)
            return True
        except Exception:
            return False

    def _send(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self._last_activity = time.time()
        self._append_message("you", text)
        if self._maybe_run_roadmap(text):
            return
        if not self.ask_ai:
            self._append_message("orb", "(AI channel not connected — configure "
                                        "a brain in Settings.)")
            return
        prompt = text
        if getattr(self, "_finder_turns", 0) > 0:
            self._finder_turns -= 1
            try:
                from core_engine.build_seeker import finder_directive
                from core_engine.player_profile import PlayerProfile
                prompt = (finder_directive(PlayerProfile.load().prompt_block())
                          + "\n\nPLAYER SAYS: " + text)
            except Exception:
                pass

        def _cb(reply, error=None):
            self._bridge.reply.emit(reply or "", error or "")
        try:
            self.ask_ai(prompt, _cb)
        except Exception as e:
            self._append_message("orb", f"(AI unavailable: {e})")

    def _on_reply(self, reply, error):
        self._append_message("orb", reply if reply else f"(AI error: {error})")

    # ------------------------------------------------ friendly action log
    def _on_log_event(self, ts, category, message):
        grp = group_for(category)
        color = _GROUP_COLORS.get(grp, FAINT)
        if any(w in (message or "").lower() for w in _ERROR_WORDS):
            color = RUBY
        # Chats already render as bubbles; don't duplicate them as actions.
        if (category or "").upper() == "CHAT":
            return
        self._append_message("app", f"{category}: {message}",
                             kind="action", color=color)

    # ------------------------------------------------ auto-attendant
    def _attendant_tick(self):
        """Idle conversation, profile-aware. Two tiers:
        - AI brain connected: ask it for ONE conversation starter built from
          the player profile + loaded character folios (token cost: one
          short completion per idle interval — the interval IS the budget).
        - No brain / call fails: profile-gated local templates, zero tokens.
        Web-researched suggestions (build sites/YouTube/Reddit) are W4-09."""
        if time.time() - self._last_activity < 90 or not self.isVisible():
            return
        self._last_activity = time.time()
        if self.ask_ai and self.config.get("companion_attendant_ai", True):
            prompt = self._attendant_prompt()
            if prompt:
                def _cb(reply, error=None):
                    if reply and not error:
                        self._bridge.reply.emit(reply.strip(), "")
                    else:
                        self._local_starter()
                try:
                    self.ask_ai(prompt, _cb)
                    return
                except Exception:
                    pass
        self._local_starter()

    def _attendant_prompt(self):
        """Build the one-shot starter prompt from profile + folios."""
        bits = []
        try:
            from core_engine.player_profile import PlayerProfile
            blk = PlayerProfile.load().prompt_block()
            if blk:
                bits.append(blk)
        except Exception:
            pass
        try:
            from core_engine.character_folio import CharacterFolio, list_folios
            for slug in list_folios()[:3]:
                corp = CharacterFolio(slug).prompt_corpus(budget_chars=1200)
                if corp:
                    bits.append(corp)
        except Exception:
            pass
        if not bits:
            return None
        return ("\n\n".join(bits) +
                "\n\nYou are the owl companion sitting with the player while "
                "they idle. Using ONLY what you know above, offer ONE short, "
                "specific conversation starter (2-3 sentences max): a build "
                "idea matching their taste, an item on a watchlist worth "
                "hunting, or a question about a character. No greetings, no "
                "lists, no invented facts.")

    def _local_starter(self):
        try:
            from core_engine.player_profile import PlayerProfile
            prof = PlayerProfile.load()
        except Exception:
            prof = None
        eligible = []
        for cond, line in _ATTENDANT_LINES:
            qid, val = cond if cond else (None, None)
            if qid is None or (prof is not None and prof.get(qid) == val):
                eligible.append(line)
        if eligible:
            self._append_message("owl", random.choice(eligible))


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace("\n", "<br>"))
