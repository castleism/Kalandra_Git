"""
CORE_ENGINE/FILTER_EDITOR.PY
Read, summarize, and edit a Path of Exile 2 item filter (.filter) — locally, by
editing the file directly. This is fully ToS-clean: no API, no game interaction,
just text editing the same way the in-game filter editor would.

A .filter is a list of blocks, each starting with Show / Hide / Minimal at column
0, followed by indented condition + action lines. We parse into blocks while
preserving every byte so an untouched file round-trips exactly; edits (flip a
block's action, etc.) only change what you change.

Public API:
    default_filter_dirs()                  -> [folders PoE2 keeps filters in]
    find_filters(extra_dir=None)           -> [paths to .filter files]
    FilterDocument.load(path) / from_text(text)
      .blocks                              -> [FilterBlock]
      .set_action(index, "Show"/"Hide"/"Minimal")
      .text()                              -> serialized filter
      .save(path=None)                     -> writes (path defaults to source)
      .stats()                             -> {show, hide, minimal, total}
"""

import os
import re

HEADER_RE = re.compile(r'^(Show|Hide|Minimal)\b(.*)$')
ACTIONS = ("Show", "Hide", "Minimal")

# Condition keywords we surface in a block's one-line summary.
_KEY_CONDITIONS = (
    "Class", "BaseType", "Rarity", "ItemLevel", "AreaLevel", "Quality",
    "Sockets", "LinkedSockets", "StackSize", "WaystoneTier", "MapTier",
    "Width", "Height", "Corrupted", "Mirrored", "Identified", "GemLevel",
    "DropLevel", "HasInfluence", "AnyEnchantment",
)


def default_filter_dirs():
    """Folders PoE2 stores filters in (Documents\\My Games\\Path of Exile 2),
    including OneDrive-redirected Documents."""
    dirs = []
    home = os.path.expanduser("~")
    docs_candidates = [
        os.path.join(home, "Documents"),
        os.path.join(home, "OneDrive", "Documents"),
        os.environ.get("USERPROFILE", ""),
    ]
    # Also honor an explicit Documents path from the shell env.
    for base in docs_candidates:
        if not base:
            continue
        for game in ("Path of Exile 2", "Path of Exile"):
            d = os.path.join(base, "My Games", game)
            if d not in dirs:
                dirs.append(d)
    return dirs


def find_filters(extra_dir=None):
    """Return paths to every .filter file found in the known folders."""
    out = []
    seen = set()
    dirs = []
    if extra_dir:
        dirs.append(extra_dir)
    dirs.extend(default_filter_dirs())
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        try:
            for fn in os.listdir(d):
                if fn.lower().endswith(".filter"):
                    p = os.path.join(d, fn)
                    if p not in seen:
                        seen.add(p)
                        out.append(p)
        except Exception:
            pass
    return out


class FilterBlock:
    __slots__ = ("action", "header_rest", "body")

    def __init__(self, action, header_rest, body=None):
        self.action = action            # Show / Hide / Minimal
        self.header_rest = header_rest  # text after the keyword on the header line
        self.body = body if body is not None else []   # raw body lines

    def header_line(self):
        return self.action + self.header_rest

    def conditions(self):
        """Uncommented condition/action lines, stripped."""
        out = []
        for ln in self.body:
            s = ln.strip()
            if s and not s.startswith("#"):
                out.append(s)
        return out

    def summary(self, maxlen=90):
        """A short, human label for the block (its key conditions)."""
        keys = []
        for c in self.conditions():
            head = c.split()[0] if c.split() else ""
            if head in _KEY_CONDITIONS:
                keys.append(c)
        text = " | ".join(keys) if keys else "(no item conditions — styling/defaults)"
        # also surface a leading comment on the header (filter section name)
        note = self.header_rest.strip()
        if note.startswith("#"):
            text = note.lstrip("# ").strip() + "  —  " + text
        return text if len(text) <= maxlen else (text[:maxlen] + "…")


class FilterDocument:
    def __init__(self, pre=None, blocks=None, path=None):
        self.pre = pre or []        # lines before the first block (preamble/comments)
        self.blocks = blocks or []  # list[FilterBlock]
        self.path = path

    # -- construction ----------------------------------------------------------
    @classmethod
    def from_text(cls, text, path=None):
        lines = (text or "").split("\n")
        pre, blocks, cur = [], [], None
        for raw in lines:
            m = HEADER_RE.match(raw)
            if m:
                if cur is not None:
                    blocks.append(cur)
                cur = FilterBlock(m.group(1), m.group(2))
            elif cur is None:
                pre.append(raw)
            else:
                cur.body.append(raw)
        if cur is not None:
            blocks.append(cur)
        return cls(pre, blocks, path)

    @classmethod
    def load(cls, path):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return cls.from_text(f.read(), path)

    # -- editing ---------------------------------------------------------------
    def set_action(self, index, action):
        if action not in ACTIONS:
            raise ValueError("action must be Show/Hide/Minimal")
        if 0 <= index < len(self.blocks):
            self.blocks[index].action = action
            return True
        return False

    def stats(self):
        s = {"Show": 0, "Hide": 0, "Minimal": 0}
        for b in self.blocks:
            s[b.action] = s.get(b.action, 0) + 1
        s["total"] = len(self.blocks)
        return s

    # -- serialization ---------------------------------------------------------
    def text(self):
        out = list(self.pre)
        for b in self.blocks:
            out.append(b.header_line())
            out.extend(b.body)
        return "\n".join(out)

    def save(self, path=None):
        target = path or self.path
        if not target:
            raise ValueError("no path to save to")
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(self.text())
        os.replace(tmp, target)
        self.path = target
        return target


if __name__ == "__main__":
    sample = """# My Filter
# Section: Currency
Show # $type->currency
\tClass "Currency"
\tBaseType "Divine Orb" "Mirror of Kalandra"
\tSetTextColor 255 0 0

Hide
\tClass "Gems"
\tRarity Normal
"""
    doc = FilterDocument.from_text(sample)
    assert doc.text() == sample, "round-trip must be exact"
    print("blocks:", doc.stats())
    for i, b in enumerate(doc.blocks):
        print(f"  [{i}] {b.action}: {b.summary()}")
    doc.set_action(1, "Show")
    print("after flip:", doc.stats())
