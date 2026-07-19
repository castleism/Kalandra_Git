"""
CORE_ENGINE/PLAYER_PROFILE.PY — who is this exile, actually?

The owl's first-use interview stores its answers here, and every AI prompt
gets a compact profile block so explanations land at the right depth: a
PoE1 veteran who hit 100 solo doesn't need Flasks 101; someone whose 100
came from temple leeching may know endgame gearing but not the mechanics
that got them there — different coaching, zero judgment.

Pure Python (no PyQt): headless-importable, stress-testable.

    from core_engine.player_profile import PlayerProfile
    prof = PlayerProfile.load()
    prof.set("detail", "terse"); prof.save()
    block = prof.prompt_block()   # -> str for AI context, "" if empty
"""

import json
import os
import time

PROFILE_PATH = os.path.join("data_engine", "player_profile.json")
PROFILE_VERSION = 1

# ---------------------------------------------------------------------------
# The interview script. Each question: id, the owl's wording, and chips
# (label shown on the button, value stored). 'free_text' questions render an
# input box instead of chips. Order matters — it's the conversation.
# ---------------------------------------------------------------------------
QUESTIONS = [
    {
        "id": "background",
        "ask": "First things first — what's your Path of Exile story?",
        "chips": [
            ("PoE1 veteran", "poe1_veteran"),
            ("PoE2 only", "poe2_only"),
            ("Both games", "both"),
            ("Brand new to both", "new"),
        ],
    },
    {
        "id": "leagues",
        "ask": "How many leagues have you played through?",
        "chips": [
            ("This is my first", "first"),
            ("A few (2–5)", "few"),
            ("Lots of them", "many"),
        ],
    },
    {
        "id": "peak_level",
        "ask": "Highest level you've reached on a character?",
        "chips": [
            ("Under 90", "lt90"),
            ("90–99", "90s"),
            ("Hit 100", "100"),
        ],
    },
    {
        # The sensitive one — framed as calibration, not judgment. Someone
        # whose 100 came from carries/rotas/temple leeching has a different
        # mechanical vocabulary than a solo grinder at the same level.
        "id": "climb_style",
        "ask": "And those levels — mostly your own mapping, or with help "
               "(party carries, rotas, temple leeching)? No wrong answer; it "
               "just tells me which mechanics you've actually driven yourself.",
        "chips": [
            ("Ground it out myself", "solo_ground"),
            ("Mostly group play", "group"),
            ("Had carries / leeched a fair bit", "carried"),
            ("Prefer not to say", "skip"),
        ],
    },
    {
        "id": "group_style",
        "ask": "Day to day, are you…",
        "chips": [
            ("A solo grinder", "solo"),
            ("A party player", "party"),
            ("A mix of both", "mix"),
        ],
    },
    {
        "id": "build_taste",
        "ask": "Build taste: chase the strongest thing going, or brew "
               "something weird?",
        "chips": [
            ("Meta / most powerful", "meta"),
            ("Niche and unique", "niche"),
            ("Depends on the league", "mixed"),
        ],
    },
    {
        "id": "exploit_stance",
        "ask": "When a mechanic is clearly overtuned or bugged — and probably "
               "getting nerfed — do you ride it while it lasts, or steer clear?",
        "chips": [
            ("Ride it while it lasts", "ride"),
            ("Avoid it", "avoid"),
            ("Depends how fun it is", "depends"),
        ],
    },
    {
        "id": "budget",
        "ask": "Where does a character's budget usually land by endgame?",
        "chips": [
            ("Scrappy (under ~5 div)", "low"),
            ("Comfortable (5–50 div)", "mid"),
            ("Deep pockets (50+ div)", "high"),
            ("Mirror tier", "mirror"),
        ],
    },
    {
        "id": "detail",
        "ask": "Last one: when I explain things, how much detail do you want?",
        "chips": [
            ("Teach me like I'm new", "full"),
            ("Assume I know the basics", "medium"),
            ("Terse — I know this game", "terse"),
        ],
    },
    {
        "id": "build_history",
        "ask": "Any builds you've loved — and roughly which league? Type a "
               "note (e.g. 'stat-stack Gemling, Rise of the Abyssal'). Later "
               "I'll be able to import them from PoB and read the mechanics "
               "you already know.",
        "free_text": True,
    },
]

# Human-readable labels for the prompt block (value -> phrase).
_PHRASES = {
    "background": {
        "poe1_veteran": "PoE1 veteran, newer to PoE2",
        "poe2_only": "plays PoE2 only (no PoE1 background)",
        "both": "experienced in both PoE1 and PoE2",
        "new": "new to Path of Exile entirely",
    },
    "leagues": {
        "first": "first league", "few": "a few leagues played",
        "many": "many leagues played",
    },
    "peak_level": {
        "lt90": "peak level under 90", "90s": "peak level 90–99",
        "100": "has reached level 100",
    },
    "climb_style": {
        "solo_ground": "levels earned through their own mapping",
        "group": "levels mostly from group play",
        "carried": "levels partly from carries/leeching — may know endgame "
                   "gearing better than moment-to-moment mechanics",
        "skip": None,
    },
    "group_style": {
        "solo": "solo grinder", "party": "party player", "mix": "plays both solo and party",
    },
    "build_taste": {
        "meta": "prefers meta/powerful builds",
        "niche": "prefers niche/unique builds",
        "mixed": "build taste varies by league",
    },
    "exploit_stance": {
        "ride": "happy to use overtuned/bugged mechanics before nerfs",
        "avoid": "avoids exploit-adjacent mechanics",
        "depends": "situational about overtuned mechanics",
    },
    "budget": {
        "low": "typical budget under ~5 divine",
        "mid": "typical budget 5–50 divine",
        "high": "typical budget 50+ divine",
        "mirror": "mirror-tier budget",
    },
    "detail": {
        "full": "wants full beginner-level explanations",
        "medium": "wants moderate detail (assume basics)",
        "terse": "wants terse expert-level answers",
    },
}

_DETAIL_DIRECTIVE = {
    "full": "Explain mechanics from first principles; define jargon on first use.",
    "medium": "Skip the basics; explain intermediate/advanced interactions.",
    "terse": "Be terse and technical; no hand-holding, jargon is fine.",
}


class PlayerProfile:
    def __init__(self, data=None):
        self.data = data if isinstance(data, dict) else {}
        self.data.setdefault("version", PROFILE_VERSION)
        self.data.setdefault("answers", {})

    # ------------- persistence -------------
    @classmethod
    def load(cls, path=PROFILE_PATH):
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return cls(json.load(f))
        except Exception:
            pass
        return cls()

    def save(self, path=PROFILE_PATH):
        try:
            d = os.path.dirname(path)        # "" for a bare filename — skip makedirs
            if d:
                os.makedirs(d, exist_ok=True)
            self.data["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False

    # ------------- answers -------------
    def set(self, qid, value):
        self.data["answers"][qid] = value

    def get(self, qid, default=None):
        return self.data["answers"].get(qid, default)

    def answered(self, qid):
        return qid in self.data["answers"]

    def is_complete(self):
        """Complete enough = every chip question answered (free text optional)."""
        return all(self.answered(q["id"]) for q in QUESTIONS
                   if not q.get("free_text"))

    def interview_done(self):
        return bool(self.data.get("interview_done"))

    def mark_interview_done(self):
        self.data["interview_done"] = True

    # ------------- AI prompt injection -------------
    def prompt_block(self):
        """Compact one-block profile for the AI context. '' if nothing known."""
        bits = []
        for qid, table in _PHRASES.items():
            phrase = table.get(self.get(qid) or "")
            if phrase:
                bits.append(phrase)
        hist = (self.get("build_history") or "").strip()
        if hist:
            bits.append(f"past builds: {hist}")
        if not bits:
            return ""
        block = "PLAYER PROFILE (calibrate tone and depth to this): " + "; ".join(bits) + "."
        directive = _DETAIL_DIRECTIVE.get(self.get("detail") or "")
        if directive:
            block += " " + directive
        return block

    def summary_lines(self):
        """Short human-readable summary (settings / Companion tab)."""
        out = []
        for q in QUESTIONS:
            qid = q["id"]
            if not self.answered(qid):
                continue
            val = self.get(qid)
            if q.get("free_text"):
                out.append(f"Build history: {val}")
                continue
            label = next((lab for lab, v in q.get("chips", []) if v == val), val)
            out.append(f"{qid.replace('_', ' ').title()}: {label}")
        return out
