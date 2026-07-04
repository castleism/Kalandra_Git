"""
CORE_ENGINE/BUILD_SEEKER.PY — from "I just started" to a followed build with
a priced roadmap (docs/DESIGN_COMPANION.md: the new-player arc).

Two halves:

1. THE CONVERSATION — `finder_directive()` seeds the Companion chat when a
   brand-new player asks for help picking a build: the AI runs a short
   back-and-forth (playstyle, pace, fantasy, melee/ranged/minions/spells),
   then suggests 2-3 popular, league-current archetypes and offers to build
   a roadmap for the chosen one.

2. THE ROADMAP ENGINE — given a build guide (pasted text or its PoB links):
     extract_pob_refs()    -> pobb.in / pastebin / poe.ninja links + raw
                              PoB codes found in guide text
     summarize_variants()  -> parse each variant through pob_bridge
                              (class, skill, notable uniques per variant)
     roadmap_markdown()    -> the character-folio roadmap.md: variants with
                              gear lists, price notes (ledger medians when
                              your history knows them), leveling waypoints,
                              and the watchlist
     watchlist_entries()   -> items to hunt -> feed the folio watchlist and
                              the Live Search tab ("set up a live search"
                              suggestions as you level / bank currency)

Pure Python; parsing fails soft per-variant. The AI/owl narrates on top.
"""

import re

# ---------------------------------------------------------------------------
# 1. The conversation seed
# ---------------------------------------------------------------------------

def finder_directive(profile_block=""):
    """The system-style directive prepended to a new player's first
    build-finder message in the Companion chat."""
    return (
        (profile_block + "\n\n" if profile_block else "") +
        "You are helping a NEW Path of Exile 2 player find their first build "
        "to follow. Run a short, friendly back-and-forth — ONE question per "
        "reply, four questions max: (1) do they like hitting things up close, "
        "shooting from range, casting spells, or commanding minions; (2) fast "
        "and fragile or slow and unkillable; (3) a power fantasy that excites "
        "them; (4) how much time they expect to play. THEN suggest 2-3 "
        "popular, currently-viable archetypes in plain words — one sentence "
        "each on how the build actually kills things — and ask which one "
        "sounds fun. When they pick, tell them you'll assemble a roadmap: "
        "the guide's gear by level bracket, what it costs, and what to "
        "watch the market for. Explain any game term you use — assume zero "
        "prior knowledge.")


# ---------------------------------------------------------------------------
# 2. Guide -> variants
# ---------------------------------------------------------------------------

_POB_LINK = re.compile(
    r"https?://(?:pobb\.in|pastebin\.com)/[\w/]+", re.I)
_POB_CODE = re.compile(       # raw PoB export: long base64ish blob
    r"(?<![\w/+=])[A-Za-z0-9+/_-]{200,}={0,2}(?![\w/+=])")


def extract_pob_refs(guide_text):
    """-> {'links': [...], 'codes': [...]} found in guide text/HTML.
    Links keep document order, deduped; codes are raw PoB export blobs."""
    text = str(guide_text or "")
    links, seen = [], set()
    for m in _POB_LINK.finditer(text):
        u = m.group(0).rstrip(".,)>\"'")
        if u not in seen:
            seen.add(u)
            links.append(u)
    codes = []
    for m in _POB_CODE.finditer(text):
        blob = m.group(0)
        # PoB exports are zlib-deflate: they start 'eN' after base64.
        if blob.startswith("eN"):
            codes.append(blob)
    return {"links": links, "codes": codes}


def summarize_variants(codes, bridge=None):
    """Parse each PoB code -> [{'idx', 'class', 'ascendancy', 'level',
    'main_skill', 'uniques': [names]}]; unparseable variants are skipped
    with an 'error' record so the roadmap can say so honestly."""
    if bridge is None:
        try:
            from core_engine.pob_bridge import KalandraPoBBridge
            bridge = KalandraPoBBridge()
        except Exception:
            return []
    out = []
    for i, code in enumerate(codes or []):
        try:
            full = bridge.extract_full_build(code)
            if not isinstance(full, dict) or full.get("error"):
                out.append({"idx": i, "error": str((full or {}).get("error",
                                                   "unparseable"))})
                continue
            uniques = []
            for it in full.get("items") or []:
                if isinstance(it, dict) and \
                        str(it.get("rarity", "")).lower() == "unique":
                    n = it.get("name")
                    if n and n not in uniques:
                        uniques.append(n)
            out.append({
                "idx": i,
                "class": full.get("class_name"),
                "ascendancy": full.get("ascendancy"),
                "level": full.get("level"),
                "main_skill": full.get("main_skill"),
                "uniques": uniques,
            })
        except Exception as e:
            out.append({"idx": i, "error": str(e)})
    return out


# ---------------------------------------------------------------------------
# 3. Variants -> priced roadmap + watchlist
# ---------------------------------------------------------------------------

def _price_note(item_name, league=None, ledger=None):
    """Ledger median if your history knows this item's name, else ''."""
    try:
        if ledger is None:
            from core_engine.price_ledger import PriceLedger
            ledger = PriceLedger()
        with ledger._conn() as c:
            q = ("SELECT price, currency FROM checks WHERE name = ? AND "
                 "price IS NOT NULL")
            args = [item_name]
            if league:
                q += " AND league = ?"
                args.append(league)
            rows = c.execute(q, args).fetchall()
        if len(rows) >= 2 and len({r[1] for r in rows}) == 1:
            prices = sorted(r[0] for r in rows)
            mid = prices[len(prices) // 2]
            return f"~{mid:g} {rows[0][1]} (your checks)"
    except Exception:
        pass
    return ""


def watchlist_entries(variants):
    """Uniques across variants -> [{'name', 'note'}] for the folio watchlist
    (and the Live Search tab's 'set up a live search' suggestions)."""
    seen, out = set(), []
    for v in variants or []:
        for u in v.get("uniques") or []:
            if u in seen:
                continue
            seen.add(u)
            which = f"variant {v['idx'] + 1}"
            out.append({"name": u,
                        "note": f"from the guide's {which} — set up a live "
                                f"search and grab it when one's cheap"})
    return out


def roadmap_markdown(build_name, variants, league=None, ledger=None):
    """The roadmap.md body: per-variant summary + gear + price notes +
    leveling waypoints + the watchlist. Honest about parse failures."""
    lines = [f"# Roadmap: {build_name}", "",
             "_Generated by the build seeker — variants parsed straight from "
             "the guide's PoB exports. Prices marked '(your checks)' come "
             "from your own price-check history and firm up as it grows._",
             ""]
    ok = [v for v in variants or [] if not v.get("error")]
    bad = [v for v in variants or [] if v.get("error")]
    for v in ok:
        head = " / ".join(str(x) for x in
                          (v.get("class"), v.get("ascendancy")) if x)
        lines.append(f"## Variant {v['idx'] + 1} — {head or 'build'} "
                     f"(guide level {v.get('level', '?')})")
        if v.get("main_skill"):
            lines.append(f"- **Main skill:** {v['main_skill']}")
        uniques = v.get("uniques") or []
        if uniques:
            lines.append("- **Key uniques:**")
            for u in uniques:
                note = _price_note(u, league=league, ledger=ledger)
                lines.append(f"  - {u}" + (f" — {note}" if note else
                                           " — price-check this in the "
                                           "Price Check tab"))
        else:
            lines.append("- No uniques in this variant — rare-gear based; "
                         "use the Price Check mod board to value candidates.")
        lines.append("")
    if bad:
        lines.append(f"_({len(bad)} variant(s) in the guide couldn't be "
                     "parsed — open them in PoB directly.)_")
        lines.append("")
    lines += [
        "## While leveling",
        "",
        "- Follow the guide's leveling section; don't buy endgame gear yet.",
        "- Bank currency; when a watchlist item goes cheap, that's the buy.",
        "- Load each variant in the PoB (live) tab and compare in Build Sim "
        "before committing currency.",
        "",
        "## Watchlist",
        "",
    ]
    wl = watchlist_entries(variants)
    if wl:
        lines += [f"- {w['name']} — {w['note']}" for w in wl]
    else:
        lines.append("- (no uniques found — nothing to camp on trade yet)")
    return "\n".join(lines)


def build_roadmap(build_name, guide_text, league=None, bridge=None):
    """One call: guide text -> folio with roadmap.md + watchlist filled.
    -> {'variants': n_ok, 'failed': n_bad, 'watchlist': n_items,
        'folio': path} or {'error': ...}."""
    try:
        refs = extract_pob_refs(guide_text)
        variants = summarize_variants(refs["codes"], bridge=bridge)
        md = roadmap_markdown(build_name, variants, league=league)
        from core_engine.character_folio import CharacterFolio
        folio = CharacterFolio(build_name)
        folio.ensure()
        folio.write_doc("roadmap", md)
        wl = watchlist_entries(variants)
        for w in wl:
            folio.add_watch_item(w["name"], note=w["note"])
        return {"variants": sum(1 for v in variants if not v.get("error")),
                "failed": sum(1 for v in variants if v.get("error")),
                "links_found": len(refs["links"]),
                "watchlist": len(wl), "folio": folio.path}
    except Exception as e:
        return {"error": str(e)}
