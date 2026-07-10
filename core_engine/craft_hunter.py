"""
CORE_ENGINE/CRAFT_HUNTER.PY — the Craft Hunter engine (P1 of
docs/CRAFT_HUNTER_SPEC.md): alert-only crafting mod sniper.

Pure logic — no PyQt, no network, no OCR (that's P2) — so every rule here is
unit-testable in the sandbox (tests/craft_checks.py). Three jobs:

  1. TARGETS   — templated mod lines ("#% increased Spell Damage") with an
                 optional inclusive [min, max] range on the first # slot.
  2. MATCHING  — check parsed item mod lines (from trade_tools.parse_item_text,
                 i.e. the clipboard text the GAME wrote on Ctrl+C) against the
                 target list; 'any' or 'all' semantics. Tolerates OCR noise
                 (difflib fallback) so P2's tooltip reader reuses it unchanged.
  3. STASH REGEX — compile the target list into the in-game stash/vendor
                 search regex (PoE dialect, hard 50-char budget, numeric
                 ranges unrolled: 95+ -> `9[5-9]|\\d\\d\\d`). The game itself
                 highlights the hit — zero external detection, 100% ToS-safe.

Compliance line (same as trade_tools / mirror_window): we read what the game
shows/writes; we NEVER touch the game. No input interception, no hooks, no
sent clicks — the spec's §2 hard constraint. A hit produces a flash/sound/
banner for the HUMAN to act on, nothing more.
"""

import difflib
import re

# The in-game search box truncates at 50 characters — a hard budget, not a
# style preference (same limit poe.re generators build against).
STASH_REGEX_BUDGET = 50

# Words too common in mod text to anchor a search on (case-insensitive).
_STOPWORDS = {
    "to", "of", "the", "a", "an", "and", "with", "for", "per", "on", "you",
    "your", "increased", "reduced", "more", "less", "adds", "gain", "maximum",
    "additional", "level", "all", "damage", "chance", "while", "during",
    "from", "have", "has", "grants", "against", "hits", "hit", "second",
    "seconds", "skills", "skill",
}

# Curated fallback templates so the mod picker is useful on a fresh install
# (the scraped localized_knowledge.db grows richer suggestions over time).
BUILTIN_MOD_LINES = [
    "+# to maximum Life",
    "+# to maximum Mana",
    "+# to maximum Energy Shield",
    "#% increased maximum Life",
    "#% increased maximum Energy Shield",
    "#% increased Energy Shield",
    "+#% to Fire Resistance",
    "+#% to Cold Resistance",
    "+#% to Lightning Resistance",
    "+#% to Chaos Resistance",
    "+#% to all Elemental Resistances",
    "#% increased Spell Damage",
    "#% increased Physical Damage",
    "#% increased Attack Speed",
    "#% increased Cast Speed",
    "#% increased Movement Speed",
    "#% increased Critical Hit Chance",
    "#% increased Critical Damage Bonus",
    "+#% to Critical Damage Bonus",
    "Adds # to # Physical Damage",
    "Adds # to # Fire Damage",
    "Adds # to # Cold Damage",
    "Adds # to # Lightning Damage",
    "Adds # to # Chaos Damage",
    "+# to Level of all Spell Skills",
    "+# to Level of all Projectile Skills",
    "+# to Level of all Melee Skills",
    "+# to Level of all Minion Skills",
    "+# to Accuracy Rating",
    "#% increased Accuracy Rating",
    "+# to Spirit",
    "+# to Strength",
    "+# to Dexterity",
    "+# to Intelligence",
    "+# to all Attributes",
    "#% increased Rarity of Items found",
    "#% increased Armour",
    "#% increased Evasion Rating",
    "#% increased Armour and Evasion",
    "#% increased Mana Regeneration Rate",
    "Leech #% of Physical Attack Damage as Life",
    "Leech #% of Physical Attack Damage as Mana",
    "Regenerate # Life per second",
    "#% of Damage taken Recouped as Life",
    "#% increased Attack and Cast Speed",
    "#% increased Projectile Speed",
    "#% increased Area of Effect",
    "#% increased Elemental Damage with Attacks",
    "#% increased Damage over Time",
    "#% increased Skill Effect Duration",
    "#% increased Flask Charges gained",
    "#% increased Stun Threshold",
    "#% increased Block chance",
    "+#% to Block chance",
    "#% increased Light Radius",
    "+# to Level of all Skills",
]

# Tier / source tags PoE2 appends to mod lines; strip before comparing.
_TAG_RE = re.compile(
    r"\s*\((?:implicit|rune|enchant|crafted|fractured|desecrated|corrupted"
    r"|tier:? ?\d+|augmented)\)\s*$", re.IGNORECASE)
_NUM_RE = re.compile(r"[+-]?\d+(?:\.\d+)?")


# ---------------------------------------------------------------------------
# Normalization + template matching
# ---------------------------------------------------------------------------

def normalize_mod_line(line):
    """One canonical shape for a mod line: tags stripped, whitespace collapsed.
    Shared by the clipboard-confirm path today and the OCR path in P2 (which
    additionally fixes O->0 / l->1 BEFORE calling in here)."""
    s = str(line or "").strip()
    if not s:
        return ""
    # strip trailing tags, possibly stacked: "... (augmented) (Tier: 2)"
    while True:
        s2 = _TAG_RE.sub("", s)
        if s2 == s:
            break
        s = s2
    return re.sub(r"\s+", " ", s).strip()


def template_regex(template):
    """Compile a '#'-templated mod line to a regex. `#` = one number slot.
    Numbers in the template that AREN'T '#' are kept literal. Leading '+' in
    the template is optional in the item text (the game usually prints it,
    OCR sometimes eats it)."""
    t = normalize_mod_line(template)
    parts = []
    for chunk in t.split("#"):
        parts.append(re.escape(chunk))
    body = r"([+-]?\d+(?:\.\d+)?)".join(parts)
    body = body.replace(r"\+", r"\+?")     # printed '+' is cosmetic
    return re.compile(r"^\s*" + body + r"\s*$", re.IGNORECASE)


def match_line(template, line, fuzz=0.85):
    """Does ONE item line satisfy ONE template?

    Returns (matched: bool, values: [float, ...]) — values are the numbers
    captured at the template's # slots (empty if the template has no #).

    Exact regex first. If that fails, the OCR-noise fallback: compare the two
    lines with every number blanked out (difflib ratio >= fuzz); on a pass the
    numbers are pulled positionally from the item line."""
    t = normalize_mod_line(template)
    s = normalize_mod_line(line)
    if not t or not s:
        return False, []
    m = template_regex(t).match(s)
    if m:
        vals = []
        for g in m.groups():
            try:
                vals.append(float(g))
            except (TypeError, ValueError):
                return False, []
        return True, vals
    # fuzzy fallback (needed once OCR feeds this path; harmless on clipboard)
    if "#" in t:
        skel_t = _NUM_RE.sub("#", t.replace("#", "0"))
        skel_s = _NUM_RE.sub("#", s)
        ratio = difflib.SequenceMatcher(
            None, skel_t.lower(), skel_s.lower()).ratio()
        if ratio >= fuzz:
            vals = []
            for n in _NUM_RE.findall(s):
                try:
                    vals.append(float(n))
                except ValueError:
                    pass
            if vals:
                return True, vals
    return False, []


def value_in_range(values, lo=None, hi=None):
    """Inclusive range check on the FIRST captured # slot (documented UI
    behavior: for 'Adds # to #' lines the range applies to the first number).
    No # slots / no values -> only a no-range target can pass."""
    if lo is None and hi is None:
        return True
    if not values:
        return False
    v = values[0]
    if lo is not None and v < float(lo):
        return False
    if hi is not None and v > float(hi):
        return False
    return True


def match_target(target, mod_lines, fuzz=0.85):
    """One target vs an item's mod lines.

    Target dict: {"mod": template or [templates...], "min": x|None,
    "max": y|None}. A LIST of templates is the spec's hybrid case — every
    line must appear (the range applies to the first template's first slot).
    Returns (hit: bool, detail: str)."""
    templates = target.get("mod") or target.get("mod_line") or ""
    if isinstance(templates, str):
        templates = [templates]
    templates = [t for t in (normalize_mod_line(x) for x in templates) if t]
    if not templates:
        return False, "empty target"
    lines = [normalize_mod_line(x) for x in (mod_lines or [])]
    lines = [x for x in lines if x]
    lo, hi = target.get("min"), target.get("max")
    first_vals = None
    for i, tpl in enumerate(templates):
        found = False
        for ln in lines:
            ok, vals = match_line(tpl, ln, fuzz=fuzz)
            if ok:
                found = True
                if i == 0:
                    first_vals = vals
                break
        if not found:
            return False, f"missing: {tpl}"
    if not value_in_range(first_vals or [], lo, hi):
        got = first_vals[0] if first_vals else "?"
        want = f"{lo if lo is not None else ''}–{hi if hi is not None else ''}"
        return False, f"rolled {got}, want {want}"
    return True, "hit"


def evaluate_item(targets, mod_lines, mode="any", fuzz=0.85):
    """The clipboard-confirm verdict (authoritative layer, spec §3b).

    Returns {"checked": bool, "hit": bool, "mode": str,
             "results": [(target, hit, detail), ...]}.
    checked=False when there's nothing to do (no targets / junk input)."""
    out = {"checked": False, "hit": False,
           "mode": "all" if mode == "all" else "any", "results": []}
    tl = [t for t in (targets or []) if isinstance(t, dict)]
    if not tl:
        return out
    out["checked"] = True
    hits = []
    for t in tl:
        try:
            h, d = match_target(t, mod_lines, fuzz=fuzz)
        except Exception as e:            # a junk target must never crash a hunt
            h, d = False, f"target error: {e}"
        hits.append(h)
        out["results"].append((t, h, d))
    out["hit"] = all(hits) if out["mode"] == "all" else any(hits)
    return out


# ---------------------------------------------------------------------------
# Stash-search regex (spec §6) — the game does the highlighting
# ---------------------------------------------------------------------------

def _range_alternatives(lo=None, hi=None):
    """Unroll an inclusive integer range into PoE-search-safe regex
    alternatives (digits, `[x-y]` classes, `\\d` — no parens, no braces).
    Open-ended `lo` covers through three digits (95 -> 95..999 — the scale
    of the spec's own example `9[5-9]|1\\d\\d`), or lo's own digit count if
    that's bigger."""
    if lo is None and hi is None:
        return []
    try:
        # ceil the floor / floor the ceiling so fractional bounds never
        # light a roll that's actually outside the range
        import math
        lo = max(1, math.ceil(float(lo))) if lo is not None else 1
        if hi is None:
            hi = 10 ** max(3, len(str(max(lo, 1)))) - 1   # 999+ headroom
        hi = math.floor(float(hi))
    except (TypeError, ValueError):
        return []                       # junk bounds -> no numeric part
    if hi < lo:
        lo, hi = hi, lo

    def _digit(a, b):
        if a == b:
            return str(a)
        if a == 0 and b == 9:
            return r"\d"
        return f"[{a}-{b}]"

    def _span(sa, sb):
        """Regex alts for the integer range sa..sb, given as equal-length
        digit strings (sa <= sb). Standard range unroller."""
        if sa == sb:
            return [sa]
        if len(sa) == 1:
            return [_digit(int(sa), int(sb))]
        if sa[0] == sb[0]:
            return [sa[0] + alt for alt in _span(sa[1:], sb[1:])]
        nines = "9" * (len(sa) - 1)
        zeros = "0" * (len(sa) - 1)
        lo_head, hi_head = int(sa[0]), int(sb[0])
        alts, tail = [], []
        if sa[1:] != zeros:                    # partial low decade
            alts += [sa[0] + alt for alt in _span(sa[1:], nines)]
            lo_head += 1
        if sb[1:] != nines:                    # partial high decade
            tail = [sb[0] + alt for alt in _span(zeros, sb[1:])]
            hi_head -= 1
        if lo_head <= hi_head:                 # full decades in the middle
            alts.append(_digit(lo_head, hi_head) + r"\d" * (len(sa) - 1))
        return alts + tail

    alts = []
    for ndig in range(len(str(lo)), len(str(hi)) + 1):
        seg_lo = max(lo, 10 ** (ndig - 1) if ndig > 1 else 0)
        seg_hi = min(hi, 10 ** ndig - 1)
        if seg_lo <= seg_hi:
            alts.extend(_span(str(seg_lo).zfill(ndig), str(seg_hi).zfill(ndig)))
    return alts


def _anchor_for(template, max_len=12):
    """A short, distinctive lowercase fragment of the mod text for the
    in-game search to grab onto: the first non-stopword PLUS the word that
    follows it in the actual text ('spell damage' vs 'spell skills' — one
    keyword alone collides across mods). Falls back to the first word so
    SOMETHING is always produced. Substring search, so truncation is safe."""
    text = normalize_mod_line(template).replace("#", " ")
    words = re.findall(r"[a-zA-Z]+", text)
    if not words:
        return ""
    idx = next((i for i, w in enumerate(words)
                if w.lower() not in _STOPWORDS), 0)
    frag = words[idx].lower()
    if idx + 1 < len(words):
        frag = f"{frag} {words[idx + 1].lower()}"
    return frag[:max_len].rstrip()


def stash_regex(targets, budget=STASH_REGEX_BUDGET):
    """Compile the target list into ONE in-game search string (<= budget).

    Per target: `anchor.*num|anchor.*num...` when a min/max is set (anchor
    repeated per numeric alternative — the game's dialect has no groups),
    else `"anchor"` quoted when it contains a space. Targets are joined
    with `|`. When the budget forces cuts we degrade honestly: first drop
    numeric ranges (game highlights ANY roll), then shorten anchors, then
    drop trailing targets — every cut is reported in notes.

    Returns (regex: str, notes: [str, ...])."""
    notes = []
    tl = [t for t in (targets or []) if isinstance(t, dict)]
    if not tl:
        return "", []

    def term(t, with_range=True, anchor_len=12):
        tpls = t.get("mod") or t.get("mod_line") or ""
        tpl = tpls[0] if isinstance(tpls, list) else tpls
        anchor = _anchor_for(tpl, max_len=anchor_len)
        if not anchor:
            return None
        lo, hi = t.get("min"), t.get("max")
        if with_range and (lo is not None or hi is not None):
            alts = _range_alternatives(lo, hi)
            if alts:
                # the dialect has no groups, so the (shortened) anchor is
                # repeated per alternative: `spell dam.*9[5-9]|spell dam.*[1-9]\d\d`
                short = anchor[:9].rstrip()
                return "|".join(f"{short}.*{a}" for a in alts)
        return f'"{anchor}"' if " " in anchor else anchor

    def _join(terms):
        seen, out = set(), []
        for x in terms:
            if x and x not in seen:          # identical anchors collapse
                seen.add(x)
                out.append(x)
        return "|".join(out)

    # honest degradation ladder
    for with_range, alen in ((True, 12), (True, 8), (False, 12), (False, 8),
                             (False, 5)):
        rx = _join(term(t, with_range, alen) for t in tl)
        if rx and len(rx) <= budget:
            if not with_range and any(
                    t.get("min") is not None or t.get("max") is not None
                    for t in tl):
                notes.append("50-char budget: numeric ranges dropped — the "
                             "game will light ANY roll of these mods; "
                             "Ctrl+C confirm still checks the range.")
            return rx, notes
    # still over: drop targets from the end until it fits
    kept = list(tl)
    while len(kept) > 1:
        kept.pop()
        rx = _join(term(t, False, 5) for t in kept)
        if rx and len(rx) <= budget:
            notes.append(f"50-char budget: only the first {len(kept)} "
                         f"target(s) fit — {len(tl) - len(kept)} dropped "
                         "from the in-game search (clipboard confirm still "
                         "checks everything).")
            notes.append("Ranges dropped too (see above).")
            return rx, notes
    one = term(kept[0], False, 5) or ""
    return one[:budget], ["50-char budget: truncated to the first target's "
                          "anchor only."]


# ---------------------------------------------------------------------------
# Mod suggestions (autocomplete feed)
# ---------------------------------------------------------------------------

_MODISH_RE = re.compile(
    r"^[+-]?\d+(?:\.\d+)?%? (?:to|increased|reduced|more|less) .{3,60}$"
    r"|^Adds \d+ to \d+ .{3,40}$"
    r"|^\d+(?:\.\d+)?% (?:increased|reduced|of|to) .{3,60}$",
    re.IGNORECASE)


def _templatize(line):
    """Turn a concrete mod line into its '#' template."""
    return _NUM_RE.sub("#", normalize_mod_line(line)).replace("+#", "+#")


def mod_suggestions(db_path=None, limit=400):
    """Autocomplete feed: curated templates + mod-looking lines mined from
    the scraped localized_knowledge.db (knowledge_ledger.content_payload).
    Sorted, deduped, capped. Fails soft to the builtin list — a missing or
    empty DB must never take the tab down."""
    out = {t: None for t in BUILTIN_MOD_LINES}          # ordered set
    if db_path:
        try:
            import os
            import sqlite3
            if os.path.exists(db_path):
                con = sqlite3.connect(db_path)
                try:
                    rows = con.execute(
                        "SELECT content_payload FROM knowledge_ledger "
                        "WHERE content_payload LIKE '%increased%' "
                        "   OR content_payload LIKE '%Adds %' "
                        "   OR content_payload LIKE '%Resistance%' "
                        "LIMIT 4000").fetchall()
                finally:
                    con.close()
                found = 0
                for (payload,) in rows:
                    for ln in str(payload or "").splitlines():
                        ln = ln.strip()
                        if 8 <= len(ln) <= 80 and _MODISH_RE.match(ln):
                            tpl = _templatize(ln)
                            if tpl and "#" in tpl and tpl not in out:
                                out[tpl] = None
                                found += 1
                                if found >= limit:
                                    break
                    if found >= limit:
                        break
        except Exception:
            pass                                        # builtin list stands
    return list(out.keys())[:max(limit, len(BUILTIN_MOD_LINES))]


if __name__ == "__main__":
    # smoke run (the real suite is tests/craft_checks.py)
    tgt = [{"mod": "#% increased Spell Damage", "min": 95}]
    print(stash_regex(tgt))
    print(evaluate_item(tgt, ["104% increased Spell Damage"]))
