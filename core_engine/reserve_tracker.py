"""
CORE_ENGINE/RESERVE_TRACKER.PY
A small, dependency-free store for the "Unique / BIS Reserve" feature: items a
player is holding in reserve for future build ideas or upgrades.

Each snapshot records the raw item text (paste straight from the game tooltip),
a friendly name, a category (Unique / BIS / Reserve / Crafting base), free-form
tags, the build it's earmarked for, and a note. It's backed by a plain JSON file
so it survives database rebuilds and is trivial to back up, and it exposes the
reserve to the AI so the Orb can factor your stash into its advice.

Public API:
    ReserveTracker(path=None)
    .add(name, item_text="", category="Reserve", tags=None, note="", build_for="")
    .all()                         -> list of entries (newest first)
    .delete(entry_id)             -> bool
    .update(entry_id, **fields)   -> bool
    .search(term)                 -> matching entries
    .ai_summary(limit=30)         -> prompt-ready text block for the AI
"""

import json
import os
import threading
import time

_DEFAULT_NAME = "reserve_items.json"
CATEGORIES = ["Unique", "BIS", "Reserve", "Crafting base", "Other"]


def _default_path():
    # Mirror the rest of the app: data lives under the database dir if we can
    # read the config, else fall back to data_engine next to the project root.
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


class ReserveTracker:
    def __init__(self, path=None):
        self.path = path or _default_path()
        self._lock = threading.Lock()
        self._items = []
        self._seq = 0
        self._load()

    # ---- persistence ----
    def _load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self._items = data
        except Exception:
            self._items = []

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._items, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except Exception:
            pass

    # ---- helpers ----
    @staticmethod
    def _guess_name(item_text):
        """Best-effort: pull a display name out of a pasted item tooltip."""
        for line in (item_text or "").splitlines():
            line = line.strip()
            if not line or line.lower().startswith(("item class", "rarity", "--------")):
                continue
            return line
        return "Unnamed item"

    @staticmethod
    def _norm_tags(tags):
        if tags is None:
            return []
        if isinstance(tags, str):
            tags = tags.replace(";", ",").split(",")
        return [t.strip() for t in tags if t and t.strip()]

    # ---- CRUD ----
    def add(self, name="", item_text="", category="Reserve", tags=None,
            note="", build_for=""):
        with self._lock:
            name = (name or "").strip() or self._guess_name(item_text)
            self._seq += 1
            entry = {
                "id": "rsv_%d_%d" % (int(time.time() * 1000), self._seq),
                "name": name,
                "item_text": (item_text or "").strip(),
                "category": category if category in CATEGORIES else "Reserve",
                "tags": self._norm_tags(tags),
                "note": (note or "").strip(),
                "build_for": (build_for or "").strip(),
                "created": time.strftime("%Y-%m-%d %H:%M"),
            }
            self._items.append(entry)
            self._save()
            return entry

    def all(self):
        with self._lock:
            return list(reversed(self._items))

    def get(self, entry_id):
        with self._lock:
            for e in self._items:
                if e.get("id") == entry_id:
                    return dict(e)
        return None

    def delete(self, entry_id):
        with self._lock:
            n = len(self._items)
            self._items = [e for e in self._items if e.get("id") != entry_id]
            changed = len(self._items) != n
            if changed:
                self._save()
            return changed

    def update(self, entry_id, **fields):
        with self._lock:
            for e in self._items:
                if e.get("id") == entry_id:
                    if "tags" in fields:
                        fields["tags"] = self._norm_tags(fields["tags"])
                    e.update({k: v for k, v in fields.items() if k != "id"})
                    self._save()
                    return True
        return False

    def search(self, term):
        term = (term or "").strip().lower()
        if not term:
            return self.all()
        out = []
        for e in self.all():
            hay = " ".join([
                e.get("name", ""), e.get("note", ""), e.get("build_for", ""),
                e.get("category", ""), " ".join(e.get("tags", [])),
                e.get("item_text", ""),
            ]).lower()
            if term in hay:
                out.append(e)
        return out

    def ai_summary(self, limit=30):
        """A compact, prompt-ready block of the reserve for the AI context."""
        items = self.all()[:limit]
        if not items:
            return ""
        lines = ["RESERVE / BIS STASH (items the user is holding for future "
                 "builds or upgrades):"]
        for e in items:
            tags = (" [" + ", ".join(e["tags"]) + "]") if e.get("tags") else ""
            forb = (" -> for: " + e["build_for"]) if e.get("build_for") else ""
            note = (" -- " + e["note"]) if e.get("note") else ""
            lines.append(f"- ({e.get('category','Reserve')}) {e.get('name','?')}"
                         f"{tags}{forb}{note}")
        return "\n".join(lines)


if __name__ == "__main__":
    rt = ReserveTracker()
    print("Reserve file:", rt.path)
    print("Entries:", len(rt.all()))
    for e in rt.all():
        print(" -", e["category"], e["name"], e.get("tags"))
