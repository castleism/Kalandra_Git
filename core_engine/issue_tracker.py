"""
CORE_ENGINE/ISSUE_TRACKER.PY
A lightweight issue / changelog log for Kalandra: a running list of bugs, data
errors, AI hallucinations, and feature requests found while using the app. It is
surfaced in Settings (open-issue count) and exported as clean Markdown the user
can hand to the developer/AI to action — then ship a new revision.

Backed by a plain JSON file (survives DB rebuilds, easy to commit/share).

Types:    bug | db-error | hallucination | feature | correction | other
Status:   open | in-progress | resolved | wont-fix

Public API:
    IssueTracker(path=None)
    .add(title, details="", type="bug", severity="medium", context="", source="user")
    .all(status=None)                 -> list (newest first)
    .open_count()                     -> int
    .set_status(id, status)           -> bool
    .delete(id)                       -> bool
    .export_markdown(only_open=True)  -> str   (paste this to the dev/AI)
"""

import json
import os
import threading
import time

_DEFAULT_NAME = "issues.json"

TYPES = ["bug", "db-error", "hallucination", "feature", "correction", "other"]
STATUSES = ["open", "in-progress", "resolved", "wont-fix"]
SEVERITIES = ["low", "medium", "high", "critical"]


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


class IssueTracker:
    def __init__(self, path=None):
        self.path = path or _default_path()
        self._lock = threading.Lock()
        self._items = []
        self._seq = 0
        self._load()

    def _new_id(self, prefix):
        self._seq += 1
        return "%s_%d_%d" % (prefix, int(time.time() * 1000), self._seq)

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

    def add(self, title, details="", type="bug", severity="medium",
            context="", source="user"):
        with self._lock:
            title = (title or "").strip() or "(untitled issue)"
            entry = {
                "id": self._new_id("iss"),
                "title": title,
                "details": (details or "").strip(),
                "type": type if type in TYPES else "other",
                "severity": severity if severity in SEVERITIES else "medium",
                "status": "open",
                "context": (context or "").strip(),
                "source": source,
                "created": time.strftime("%Y-%m-%d %H:%M"),
            }
            self._items.append(entry)
            self._save()
            return entry

    def all(self, status=None):
        with self._lock:
            items = list(reversed(self._items))
        if status:
            items = [e for e in items if e.get("status") == status]
        return items

    def open_count(self):
        with self._lock:
            return sum(1 for e in self._items
                       if e.get("status") not in ("resolved", "wont-fix"))

    def get(self, entry_id):
        with self._lock:
            for e in self._items:
                if e.get("id") == entry_id:
                    return dict(e)
        return None

    def set_status(self, entry_id, status):
        if status not in STATUSES:
            return False
        with self._lock:
            for e in self._items:
                if e.get("id") == entry_id:
                    e["status"] = status
                    self._save()
                    return True
        return False

    def update(self, entry_id, **fields):
        with self._lock:
            for e in self._items:
                if e.get("id") == entry_id:
                    for k, v in fields.items():
                        if k != "id":
                            e[k] = v
                    self._save()
                    return True
        return False

    def delete(self, entry_id):
        with self._lock:
            n = len(self._items)
            self._items = [e for e in self._items if e.get("id") != entry_id]
            changed = len(self._items) != n
            if changed:
                self._save()
            return changed

    def export_markdown(self, only_open=True):
        """Produce a Markdown changelog to hand to the developer/AI. Grouped by
        type, with everything needed to action each item."""
        items = self.all()
        if only_open:
            items = [e for e in items if e.get("status") not in ("resolved", "wont-fix")]
        try:
            from version import KALANDRA_VERSION as _v
        except Exception:
            _v = "?"
        lines = [f"# Kalandra issue log (rev {_v})",
                 f"_{len(items)} open item(s). Generated for processing by the dev/AI._",
                 ""]
        if not items:
            lines.append("_No open issues._")
            return "\n".join(lines)
        order = {t: i for i, t in enumerate(TYPES)}
        items.sort(key=lambda e: (order.get(e.get("type"), 99), e.get("severity")))
        cur = None
        for e in items:
            if e.get("type") != cur:
                cur = e.get("type")
                lines.append(f"\n## {cur.upper()}\n")
            lines.append(f"### [{e.get('severity','?')}] {e.get('title','(untitled)')}")
            lines.append(f"- **id:** {e.get('id')}  ")
            lines.append(f"- **status:** {e.get('status')}  ")
            lines.append(f"- **reported:** {e.get('created')} ({e.get('source')})  ")
            if e.get("details"):
                lines.append(f"- **details:** {e['details']}  ")
            if e.get("context"):
                ctx = e["context"].replace("\n", "\n  > ")
                lines.append(f"- **context:**\n  > {ctx}")
            lines.append("")
        return "\n".join(lines)


if __name__ == "__main__":
    it = IssueTracker()
    print("File:", it.path, "| open:", it.open_count())
    print(it.export_markdown())
