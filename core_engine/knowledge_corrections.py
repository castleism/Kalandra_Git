"""
CORE_ENGINE/KNOWLEDGE_CORRECTIONS.PY
A small layer of VERIFIED, authoritative facts that override or augment the
scraped database when grounding the AI. The cloud brain (Gemini/OpenAI) has weak
PoE2-specific knowledge and will confidently fabricate; a correction here is fed
into the prompt as ground truth the model must not contradict.

This is how "teaching" the Orb works without retraining: add a correction (in the
app or by editing the JSON), and from the next message on, the relevant fact is
injected into context with top priority.

Backed by a plain JSON file so it survives DB rebuilds and is easy to ship.

Public API:
    KnowledgeCorrections(path=None)
    .add(topic, correction, tags=None)        -> entry
    .all()                                     -> list (newest first)
    .delete(entry_id)                          -> bool
    .relevant(text, limit=6)                   -> corrections matching text/tags
    .context_block(text, limit=6)             -> prompt-ready string ('' if none)
"""

import json
import os
import threading
import time

_DEFAULT_NAME = "knowledge_corrections.json"

# Shipped defaults: known facts the model gets wrong. Seeded on first run only.
#
# NOTE on "tags" here: these are MATCH TERMS — the real names/aliases of the
# thing the fact is about, used to decide WHEN to inject the correction. They are
# NOT game tags, and must never be a taxonomy of our own invention. A PoE entity's
# actual tags (Physical, Damage Over Time, Bleeding, ...) come from poe2db and are
# stored on the knowledge-base entry itself; a correction just states the true tag
# relationship in its text. So match on the subject's real names ("Corrupted
# Blood", "Corrupting Cry"), not on damage-type keywords like "physical"/"bleed"
# (which mislabel the entry and make the correction fire on unrelated builds).
_SEED = [
    {
        "topic": "Corrupted Blood",
        "correction": (
            "Corrupted Blood (applied by the Corrupting Cry support) is a STACKING "
            "PHYSICAL damage-over-time debuff. Its real tags are Physical and Damage "
            "Over Time; it does NOT have the Bleeding tag. It is therefore NOT a Bleed "
            "and is NOT affected by Bleed-specific modifiers (e.g. 'increased Bleeding "
            "damage', faster bleeding, bleed on hit). It scales with modifiers to "
            "Physical damage, to Damage Over Time, to generic/area damage where "
            "applicable, with warcry effectiveness/exerted attacks that apply more "
            "stacks, and with the number of stacks applied. Never recommend "
            "Bleed-specific scaling for Corrupted Blood."),
        "tags": ["corrupted blood", "corrupting cry"],
    },
]


def _default_path():
    base = "data_engine"
    try:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg = os.path.join(here, "data_engine", "config.json")
        if os.path.exists(cfg):
            with open(cfg, "r", encoding="utf-8") as f:
                base = json.load(f).get("dir_database", "data_engine") or "data_engine"
        if not os.path.isabs(base):
            base = os.path.join(here, base)
    except Exception:
        pass
    return os.path.join(base, _DEFAULT_NAME)


class KnowledgeCorrections:
    def __init__(self, path=None):
        self.path = path or _default_path()
        self._lock = threading.Lock()
        self._items = []
        self._seq = 0
        self._load()

    def _load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self._items = data
                    return
        except Exception:
            self._items = []
        # First run: seed the known corrections and persist.
        self._items = []
        for s in _SEED:
            self._items.append(self._make(s["topic"], s["correction"], s.get("tags")))
        self._save()

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._items, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except Exception:
            pass

    @staticmethod
    def _norm_tags(tags):
        if tags is None:
            return []
        if isinstance(tags, str):
            tags = tags.replace(";", ",").split(",")
        return [t.strip().lower() for t in tags if t and t.strip()]

    def _make(self, topic, correction, tags=None):
        self._seq += 1
        return {
            "id": "cor_%d_%d" % (int(time.time() * 1000), self._seq),
            "topic": (topic or "").strip(),
            "correction": (correction or "").strip(),
            "tags": self._norm_tags(tags) or self._norm_tags(topic),
            "added": time.strftime("%Y-%m-%d %H:%M"),
        }

    def add(self, topic, correction, tags=None):
        with self._lock:
            e = self._make(topic, correction, tags)
            self._items.append(e)
            self._save()
            return e

    def all(self):
        with self._lock:
            return list(reversed(self._items))

    def delete(self, entry_id):
        with self._lock:
            n = len(self._items)
            self._items = [e for e in self._items if e.get("id") != entry_id]
            changed = len(self._items) != n
            if changed:
                self._save()
            return changed

    def relevant(self, text, limit=6):
        """Return corrections whose topic/tags appear in the given text."""
        hay = (text or "").lower()
        if not hay:
            return []
        out = []
        for e in self.all():
            topic = e.get("topic", "").lower()
            tags = e.get("tags", [])
            if (topic and topic in hay) or any(t and t in hay for t in tags):
                out.append(e)
            if len(out) >= limit:
                break
        return out

    def context_block(self, text, limit=6):
        hits = self.relevant(text, limit=limit)
        if not hits:
            return ""
        lines = ["VERIFIED CORRECTIONS (authoritative PoE2 facts — these OVERRIDE any "
                 "conflicting info, including the database and your own assumptions; "
                 "if a correction applies, follow it exactly):"]
        for e in hits:
            lines.append(f"- {e.get('topic','?')}: {e.get('correction','')}")
        return "\n".join(lines)


if __name__ == "__main__":
    kc = KnowledgeCorrections()
    print("File:", kc.path, "| entries:", len(kc.all()))
    print(kc.context_block("how do I scale my corrupted blood from corrupting cry"))
