"""
CORE_ENGINE/NERF_INTEL.PY — did this item get gutted since that league? (W4-06)

The character-review pipeline (docs/DESIGN_COMPANION.md P2/P3) needs to know
whether a unique's old value intuition still holds: Hand of Wisdom and
Action or Astramentis after a nerf are different items; Headhunter was
famously cheap in Temple league WITHOUT a nerf (supply, not balance). So
this module gives two independent signals, clearly labeled:

  1. PATCH SIGNAL  — heuristic scan of patch-note text for an item (or its
     mods): nerf / buff / mixed / none, with the evidence lines.
  2. PRICE SIGNAL  — league-over-league (or date-series) price shift with
     cliff detection: how big, how sudden.

Both are SIGNALS for the AI + review to weigh, never verdicts. Pure Python,
no network — callers feed it patch text (wiki_scraper already ingests patch
notes) and price series (EconomyProvider / poe.ninja history).
"""

import re

# Direction keywords. Order matters: negations are checked first.
_NERF_WORDS = (
    "no longer", "reduced", "lowered", "decreased", "removed", "nerfed",
    "less ", "now caps", "capped at", "can no longer", "halved",
    "no more than",
)
_BUFF_WORDS = (
    "increased", "raised", "improved", "buffed", "now grants", "doubled",
    "now also", "additionally grants", "more ",
)
# "no longer deals reduced damage" — a nerf word preceded by a negating nerf
# phrase is actually a buff; handled by scanning "no longer" first.


def classify_line(line):
    """-> 'nerf' | 'buff' | 'neutral' for one patch-note line (heuristic)."""
    s = " " + str(line or "").lower().strip() + " "
    if not s.strip():
        return "neutral"
    # negated-nerf reads as buff: "no longer suffers reduced attack speed"
    if "no longer" in s:
        after = s.split("no longer", 1)[1]
        if any(w in after for w in _NERF_WORDS if w != "no longer"):
            return "buff"
        return "nerf"
    nerf = any(w in s for w in _NERF_WORDS)
    buff = any(w in s for w in _BUFF_WORDS)
    if nerf and buff:
        # e.g. "reduced from 30% to 20%" + "increased radius": call it mixed
        # at line level by preferring the FIRST direction word encountered.
        for token in re.split(r"[,;:]", s):
            if any(w in token for w in _NERF_WORDS):
                return "nerf"
            if any(w in token for w in _BUFF_WORDS):
                return "buff"
        return "neutral"
    if nerf:
        return "nerf"
    if buff:
        return "buff"
    return "neutral"


def assess_patch_impact(item_name, patch_text, aliases=()):
    """Scan patch text for lines mentioning the item (or aliases).
    -> {'verdict': 'nerf'|'buff'|'mixed'|'none', 'evidence': [(line, cls)]}
    Only lines that NAME the item count — no guilt by adjacency."""
    name = str(item_name or "").strip().lower()
    if not name:
        return {"verdict": "none", "evidence": []}
    needles = [name] + [str(a).strip().lower() for a in aliases if a]
    evidence = []
    for raw in str(patch_text or "").splitlines():
        low = raw.lower()
        if not any(n in low for n in needles):
            continue
        cls = classify_line(raw)
        if cls != "neutral":
            evidence.append((raw.strip(), cls))
    kinds = {c for _, c in evidence}
    if not kinds:
        verdict = "none"
    elif kinds == {"nerf"}:
        verdict = "nerf"
    elif kinds == {"buff"}:
        verdict = "buff"
    else:
        verdict = "mixed"
    return {"verdict": verdict, "evidence": evidence}


def assess_patches(item_name, patches, aliases=()):
    """patches = [(version_or_league, patch_text), ...] oldest->newest.
    -> {'verdict', 'by_patch': {ver: verdict}, 'evidence': [...]}, where the
    overall verdict is the latest non-'none' patch's verdict (recent balance
    is what matters for price intuition)."""
    by_patch, evidence, overall = {}, [], "none"
    for ver, text in patches or []:
        r = assess_patch_impact(item_name, text, aliases=aliases)
        by_patch[str(ver)] = r["verdict"]
        for line, cls in r["evidence"]:
            evidence.append((str(ver), line, cls))
        if r["verdict"] != "none":
            overall = r["verdict"]
    return {"verdict": overall, "by_patch": by_patch, "evidence": evidence}


def price_shift(series):
    """series = [(label, price), ...] chronological (league-over-league or a
    date series within a league).
    -> {'change_pct': float, 'cliff_pct': float|None, 'cliff_at': label|None,
        'direction': 'down'|'up'|'flat'} or None if <2 valid points.
    cliff = the largest single-step drop (sudden, not drift)."""
    pts = []
    for label, price in series or []:
        try:
            p = float(price)
            if p > 0:
                pts.append((str(label), p))
        except Exception:
            continue
    if len(pts) < 2:
        return None
    first, last = pts[0][1], pts[-1][1]
    change = (last - first) / first * 100.0
    cliff_pct, cliff_at = None, None
    for (la, pa), (lb, pb) in zip(pts, pts[1:]):
        step = (pb - pa) / pa * 100.0
        if step < 0 and (cliff_pct is None or step < cliff_pct):
            cliff_pct, cliff_at = step, lb
    direction = "flat"
    if change <= -10:
        direction = "down"
    elif change >= 10:
        direction = "up"
    return {"change_pct": round(change, 1),
            "cliff_pct": round(cliff_pct, 1) if cliff_pct is not None else None,
            "cliff_at": cliff_at, "direction": direction}


# ---------------------------------------------------------------------------
# W4-06 wiring: feed the signals from what Kalandra already has on disk —
# patch-note pages in the scraped knowledge base, and the poe.ninja daily
# snapshots the Exchange tab writes to economy_history. Read-only sqlite,
# still no network.
# ---------------------------------------------------------------------------

_VERSION_RE = re.compile(r"\b(\d+\.\d+(?:\.\d+)*[a-z]?)\b")


def _default_db_path():
    try:
        from core_engine.database_handler import KalandraDBHandler
        import os
        return os.path.join(KalandraDBHandler._configured_db_dir(),
                            "localized_knowledge.db")
    except Exception:
        return "data_engine/localized_knowledge.db"


def _version_key(label):
    """Sortable key for '0.2.1c'-style labels; unknown -> sorts first."""
    m = _VERSION_RE.search(str(label or ""))
    if not m:
        return (0,)
    parts = []
    for p in m.group(1).split("."):
        num = re.match(r"(\d+)([a-z]?)", p)
        parts.append(int(num.group(1)))
        if num.group(2):
            parts.append(ord(num.group(2)))
    return tuple(parts)


def patches_from_db(db_path=None, limit=40):
    """[(version_label, patch_text), ...] oldest->newest, mined from the
    knowledge base: any ledger page whose topic or URL says patch-notes /
    'Version X.Y.Z' (poe2wiki's version pages, poe2db patch pages). Empty
    list on any problem — the signal degrades to 'none', never crashes."""
    import sqlite3
    out = []
    path = db_path or _default_db_path()
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        try:
            rows = con.execute(
                "SELECT topic_tag, content_payload, source_url "
                "FROM knowledge_ledger WHERE "
                "  lower(topic_tag) LIKE '%patch note%'"
                "  OR lower(topic_tag) LIKE '%patch_note%'"
                "  OR lower(topic_tag) LIKE 'version %'"
                "  OR source_url LIKE '%Version_%'"
                "  OR source_url LIKE '%patch-notes%'"
                " LIMIT ?", (int(limit),)).fetchall()
        finally:
            con.close()
        for topic, text, url in rows:
            label = None
            for probe in (topic, url):
                m = _VERSION_RE.search(str(probe or ""))
                if m:
                    label = m.group(1)
                    break
            out.append((label or str(topic or "?"), str(text or "")))
        out.sort(key=lambda t: _version_key(t[0]))
    except Exception:
        return []
    return out


def price_series_from_db(item_name, league, db_path=None, days=90):
    """[(day, value), ...] chronological from economy_history (the daily
    snapshots the Exchange tab stores — currency/fragments only; uniques
    aren't in that feed, so they get the patch signal alone). Empty list on
    any problem."""
    import sqlite3
    path = db_path or _default_db_path()
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        try:
            rows = con.execute(
                "SELECT day, value FROM economy_history "
                "WHERE league=? AND lower(name)=lower(?) "
                "AND day >= date('now', ?) ORDER BY day",
                (str(league or "Standard"), str(item_name or ""),
                 f"-{int(days)} day")).fetchall()
        finally:
            con.close()
        return [(str(d), v) for d, v in rows]
    except Exception:
        return []


def nerf_watch(item_name, league=None, db_path=None, aliases=()):
    """One-call W4-06 signal for the Price Check tab and reviews:
    value_intuition fed straight from the local DB. Adds 'has_signals' so
    callers can stay silent when there's nothing to say."""
    patches = patches_from_db(db_path=db_path)
    series = price_series_from_db(item_name, league, db_path=db_path) \
        if league else []
    vi = value_intuition(item_name, patches=patches, series=series,
                         aliases=aliases)
    vi["has_signals"] = (vi["patch"]["verdict"] != "none"
                         or (vi["price"] or {}).get("direction")
                         in ("down", "up"))
    return vi


def value_intuition(item_name, patches=None, series=None, aliases=()):
    """The combined, honestly-worded signal for reviews and the AI.
    -> {'summary': str, 'patch': {...}, 'price': {...}|None}"""
    patch = assess_patches(item_name, patches or [], aliases=aliases)
    price = price_shift(series or [])
    bits = []
    if patch["verdict"] == "nerf":
        bits.append(f"{item_name} has nerf-flagged patch lines")
    elif patch["verdict"] == "buff":
        bits.append(f"{item_name} has buff-flagged patch lines")
    elif patch["verdict"] == "mixed":
        bits.append(f"{item_name} has mixed balance changes")
    if price:
        if price["direction"] == "down":
            s = f"price is down {abs(price['change_pct'])}%"
            if price["cliff_pct"] is not None and price["cliff_pct"] <= -25:
                s += (f" with a {abs(price['cliff_pct'])}% cliff at "
                      f"{price['cliff_at']}")
            bits.append(s)
        elif price["direction"] == "up":
            bits.append(f"price is up {price['change_pct']}%")
    if patch["verdict"] == "none" and price and price["direction"] == "down":
        bits.append("no balance change found — likely supply/league effects "
                    "(the Temple-league-Headhunter pattern)")
    summary = ("; ".join(bits) + ".") if bits else \
        f"No nerf or price signals found for {item_name}."
    return {"summary": summary, "patch": patch, "price": price}
