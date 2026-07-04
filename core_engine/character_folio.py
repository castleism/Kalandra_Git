"""
CORE_ENGINE/CHARACTER_FOLIO.PY — a folder per character (W4-07 foundation).

Each character the player loads gets `data_engine/characters/<slug>/`:

    profile.json     - the parsed build scan (class, skills, items, tree)
    review.md        - the written character review (P2 generates this)
    roadmap.md       - leveling -> endgame gear ladder (P4 fills this)
    watchlist.json   - items to hunt (feeds live-search suggestions, P5)
    sim_notes/       - what-if simulation results (P4)

These files are the character's working memory: `prompt_corpus()` returns a
size-budgeted concatenation for injecting into any AI prompt about that
character — small, curated, cheap in tokens (docs/DESIGN_COMPANION.md P4).

Pure Python, fails soft, headless-testable.
"""

import json
import os
import re
import time

CHAR_ROOT = os.path.join("data_engine", "characters")
_CORPUS_ORDER = ("review.md", "roadmap.md", "watchlist.json", "profile.json")


def slugify(name):
    s = re.sub(r"[^\w\- ]+", "", str(name or "").strip())
    s = re.sub(r"\s+", "_", s).strip("_")
    return s[:60] or "character"


class CharacterFolio:
    def __init__(self, name, root=CHAR_ROOT):
        self.name = str(name or "character")
        self.slug = slugify(name)
        self.path = os.path.join(root, self.slug)

    # ------------------------------------------------ scaffold
    def ensure(self):
        """Create the folder + skeleton files. Returns True on success."""
        try:
            os.makedirs(os.path.join(self.path, "sim_notes"), exist_ok=True)
            self._touch_json("profile.json", {"name": self.name,
                                              "created": _now()})
            self._touch_json("watchlist.json", {"items": []})
            for fn, title in (("review.md", "Review"),
                              ("roadmap.md", "Roadmap")):
                p = os.path.join(self.path, fn)
                if not os.path.exists(p):
                    with open(p, "w", encoding="utf-8") as f:
                        f.write(f"# {title}: {self.name}\n\n_(not written yet)_\n")
            return True
        except Exception:
            return False

    def _touch_json(self, fn, default):
        p = os.path.join(self.path, fn)
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8") as f:
                json.dump(default, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------ writing
    def write_scan(self, build_dict):
        """Store the parsed build (from pob_bridge.extract_full_build) and,
        if no review exists yet, write a basic generated one so the folio is
        never a placeholder (the AI review of P2 then overwrites it)."""
        try:
            self.ensure()
            data = {"name": self.name, "updated": _now(),
                    "build": build_dict if isinstance(build_dict, dict) else {}}
            with open(os.path.join(self.path, "profile.json"), "w",
                      encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            rp = os.path.join(self.path, "review.md")
            try:
                with open(rp, "r", encoding="utf-8") as f:
                    existing = f.read()
            except Exception:
                existing = ""
            if not existing.strip() or "_(not written yet)_" in existing:
                self.write_doc("review",
                               generate_basic_review(self.name, build_dict))
            return True
        except Exception:
            return False

    def write_doc(self, which, text):
        """which in {'review', 'roadmap'} -> overwrite that .md file."""
        if which not in ("review", "roadmap"):
            return False
        try:
            self.ensure()
            with open(os.path.join(self.path, f"{which}.md"), "w",
                      encoding="utf-8") as f:
                f.write(str(text or ""))
            return True
        except Exception:
            return False

    def add_watch_item(self, item_name, note=""):
        try:
            self.ensure()
            p = os.path.join(self.path, "watchlist.json")
            data = _read_json(p) or {"items": []}
            data.setdefault("items", []).append(
                {"name": str(item_name)[:160], "note": str(note)[:300],
                 "added": _now()})
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False

    def add_sim_note(self, title, text):
        try:
            self.ensure()
            fn = time.strftime("%Y%m%d_%H%M%S_") + slugify(title)[:40] + ".md"
            with open(os.path.join(self.path, "sim_notes", fn), "w",
                      encoding="utf-8") as f:
                f.write(f"# {title}\n\n{text}\n")
            return True
        except Exception:
            return False

    # ------------------------------------------------ prompt injection
    def prompt_corpus(self, budget_chars=6000):
        """Curated, size-budgeted text block about this character for AI
        prompts. Priority: review > roadmap > watchlist > profile. '' if
        the folio doesn't exist yet."""
        if not os.path.isdir(self.path):
            return ""
        parts = [f"CHARACTER FOLIO: {self.name}"]
        used = len(parts[0])
        for fn in _CORPUS_ORDER:
            p = os.path.join(self.path, fn)
            if not os.path.exists(p):
                continue
            try:
                with open(p, "r", encoding="utf-8") as f:
                    body = f.read().strip()
            except Exception:
                continue
            if not body or "_(not written yet)_" in body:
                continue
            # Skip skeleton JSON that carries no real content yet.
            if fn == "watchlist.json" and not (_read_json(p) or {}).get("items"):
                continue
            if fn == "profile.json" and not (_read_json(p) or {}).get("build"):
                continue
            room = budget_chars - used
            if room <= 80:
                break
            chunk = f"\n--- {fn} ---\n{body[:room]}"
            parts.append(chunk)
            used += len(chunk)
        return "\n".join(parts) if len(parts) > 1 else ""


def generate_basic_review(name, build):
    """Deterministic first-pass review straight from the scan — no AI, no
    network, never wrong about facts it states because it only states what
    the parse contains. P2's AI review replaces it with analysis."""
    b = build if isinstance(build, dict) else {}
    lines = [f"# Review: {name}", "",
             f"_Generated from the build scan on {_now()} — the AI-written "
             "review will replace this once character analysis runs._", ""]

    def _first(*keys):
        for k in keys:
            v = b.get(k)
            if v:
                return v
        return None

    ident = []
    for label, val in (("Class", _first("class", "className", "class_name")),
                       ("Ascendancy", _first("ascendancy", "ascendClassName")),
                       ("Level", _first("level", "char_level")),
                       ("Main skill", _first("main_skill", "mainSkill"))):
        if val:
            ident.append(f"- **{label}:** {val}")
    if ident:
        lines += ["## Identity", ""] + ident + [""]

    skills = b.get("skills") or b.get("skill_groups") or []
    names = []
    for s in skills if isinstance(skills, list) else []:
        if isinstance(s, dict):
            n = s.get("name") or s.get("skill") or s.get("label")
        else:
            n = str(s)
        if n:
            names.append(str(n))
    if names:
        lines += ["## Skills seen in the scan", ""]
        lines += [f"- {n}" for n in names[:20]] + [""]

    items = b.get("items") or []
    inames = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict):
            n = it.get("name") or it.get("base") or it.get("baseName")
        else:
            n = str(it)
        if n:
            inames.append(str(n))
    if inames:
        lines += ["## Notable gear", ""]
        lines += [f"- {n}" for n in inames[:20]] + [""]

    if len(lines) <= 4:
        lines += ["The scan parsed, but carried no class/skill/item details ",
                  "this generator recognizes — load the build again once the ",
                  "PoB parse succeeds and this review will fill in."]
    return "\n".join(lines)


def list_folios(root=CHAR_ROOT):
    try:
        return sorted(d for d in os.listdir(root)
                      if os.path.isdir(os.path.join(root, d)))
    except Exception:
        return []


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
