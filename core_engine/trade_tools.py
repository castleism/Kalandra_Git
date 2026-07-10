"""
CORE_ENGINE/TRADE_TOOLS.PY
Pure, dependency-free helpers for the Price Check / Live Search / Crafting tabs.
No PyQt, no network — just text parsing and URL building, so they're unit-testable
and reusable. The GUI layer (gui_overlay/dashboard.py) imports these.

Everything here is ToS-clean: we parse the item text the game itself puts on the
clipboard (Ctrl+C in-game) and build a link to the OFFICIAL trade site. We never
automate buying, never fabricate prices, and never log in for the user.
"""

from urllib.parse import quote


def is_number(v):
    try:
        float(v)
        return True
    except Exception:
        return False


def parse_item_text(text):
    """Parse the clipboard text PoE2 produces on Ctrl+C over an item.

    Sections are separated by lines made only of dashes. The first section is the
    header (Item Class / Rarity / name / base); later sections hold requirements,
    item level, and the explicit/implicit mods. Returns a dict with keys:
    rarity, name, base, item_class, ilvl, mods(list). Always returns a dict.
    """
    info = {"rarity": "", "name": "", "base": "", "item_class": "", "ilvl": "",
            "mods": []}
    if not text or not str(text).strip():
        return info
    raw_lines = [ln.rstrip("\r") for ln in str(text).split("\n")]

    sections, cur = [], []
    for ln in raw_lines:
        stripped = ln.strip()
        if stripped and set(stripped) == {"-"}:
            sections.append(cur)
            cur = []
        else:
            cur.append(ln)
    if cur:
        sections.append(cur)

    header = sections[0] if sections else []
    for ln in header:
        s = ln.strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith("item class:"):
            info["item_class"] = s.split(":", 1)[1].strip()
        elif low.startswith("rarity:"):
            info["rarity"] = s.split(":", 1)[1].strip()
        elif not info["name"]:
            info["name"] = s
        elif not info["base"]:
            info["base"] = s

    # Normal / Magic items have no unique name — the "name" line is the base.
    if info["rarity"].lower() in ("normal", "magic") and not info["base"]:
        info["base"] = info["name"]
        info["name"] = ""

    for sec in sections[1:]:
        for ln in sec:
            s = ln.strip()
            if not s:
                continue
            low = s.lower()
            if low.startswith("item level:"):
                info["ilvl"] = s.split(":", 1)[1].strip()
                continue
            if (low.startswith("requirements") or low.startswith("level ")
                    or low.startswith("level:") or low.startswith("sockets:")
                    or low.startswith("str") or low.startswith("dex")
                    or low.startswith("int")):
                continue
            if (any(ch.isdigit() for ch in s) or low.startswith("+")
                    or "increased" in low or "reduced" in low
                    or " to " in low or "(implicit)" in low or "(rune)" in low):
                info["mods"].append(s)
    return info


def trade_search_url(info, league):
    """The official PoE2 trade search page for a league. The site needs a POST to
    prefill a query, so we open the search page for the right league; the parsed
    item name/base is shown to the user to type/confirm. Guarantees correct site
    and league with zero automation. (W3-21's ?q= prefill below upgrades this
    whenever the stat-id map is available.)"""
    league = (league or "Standard").strip() or "Standard"
    return f"https://www.pathofexile.com/trade2/search/poe2/{quote(league)}"


# ---------------------------------------------------------------------------
# W3-21 (remaining half): push the parsed item's filters INTO the trade site.
# The official site accepts ?q=<query JSON> on the search URL; the stat-id map
# comes from its /api/trade2/data/stats endpoint (fetched + cached by the GUI
# layer — this module stays pure: build/match only, no network).
# ---------------------------------------------------------------------------

_STAT_MARKUP = None      # compiled lazily (keeps import cost nil)
_NUMBER = None


def normalize_stat_text(text):
    """One canonical shape for a stat/mod line so the site's stat texts and
    the game's clipboard lines can meet in the middle:
    - trade-API markup `[Evasion|Evasion Rating]` -> the display half,
      `[Physical]` -> itself
    - every number (and the API's `#` placeholder) -> `#`
    - `+#` collapses to `#` (the sign is cosmetic), whitespace collapsed,
      lowercased."""
    import re
    global _STAT_MARKUP, _NUMBER
    if _STAT_MARKUP is None:
        _STAT_MARKUP = re.compile(r"\[([^\[\]|]+)\|([^\[\]]+)\]")
        _NUMBER = re.compile(r"[+-]?\d+(?:\.\d+)?|#")
    s = str(text or "")
    s = _STAT_MARKUP.sub(r"\2", s)
    s = s.replace("[", "").replace("]", "")
    s = _NUMBER.sub("#", s)
    s = s.replace("+#", "#").replace("+ #", "#")
    return " ".join(s.split()).strip().lower()


def mod_values(mod):
    """The numbers on a concrete mod line, in order (floats)."""
    import re
    return [float(x) for x in re.findall(r"[+-]?\d+(?:\.\d+)?",
                                         str(mod or ""))]


def build_stats_index(stats_json):
    """{normalized stat text -> stat id} from /api/trade2/data/stats.

    Explicit entries win collisions (they're what rare-item searches use);
    implicit/rune/enchant fill gaps. Returns {} for anything malformed —
    the caller falls back to the plain search URL."""
    index = {}
    try:
        groups = (stats_json or {}).get("result") or []
        ranked = {"explicit": 0, "implicit": 1, "rune": 2, "enchant": 3}
        best_rank = {}
        for g in groups:
            for e in (g.get("entries") or []):
                sid = e.get("id")
                text = normalize_stat_text(e.get("text"))
                etype = str(e.get("type") or g.get("id") or "").lower()
                rank = ranked.get(etype, 9)
                if sid and text and rank < best_rank.get(text, 99):
                    best_rank[text] = rank
                    index[text] = sid
    except Exception:
        return {}
    return index


def match_stat_id(index, mod, fuzz=0.92):
    """The stat id for one clipboard mod line: exact normalized match first,
    then a difflib pass over the index (>= fuzz). None if nothing fits."""
    if not index:
        return None
    key = normalize_stat_text(mod)
    if not key:
        return None
    hit = index.get(key)
    if hit:
        return hit
    import difflib
    cand = difflib.get_close_matches(key, list(index.keys()), n=1,
                                     cutoff=fuzz)
    return index[cand[0]] if cand else None


def build_trade_query(info, stats_index, online=True):
    """The trade-site query JSON for a parsed item (W3-21).

    - Uniques search by name + base; everything else by base type.
    - Every parsed mod that maps to a stat id becomes a filter with
      min = its rolled value ("at least as good as mine"); premium/good
      mods (mod_insights tiers) ship ENABLED, the rest disabled so they're
      one click away on the site instead of drowning the search.
    Returns (query_dict, matched, total, notes). Never raises."""
    info = info or {}
    notes = []
    q = {"query": {"status": {"option": "online" if online else "any"},
                   "stats": [{"type": "and", "filters": []}]},
         "sort": {"price": "asc"}}
    try:
        rarity = (info.get("rarity") or "").lower()
        name, base = info.get("name") or "", info.get("base") or ""
        if rarity == "unique" and name:
            q["query"]["name"] = name
            if base:
                q["query"]["type"] = base
        elif base:
            q["query"]["type"] = base
        elif name:
            q["query"]["type"] = name

        tiers = {}
        try:
            for m, tier, _tip in mod_insights(info)["mods"]:
                tiers[m] = tier
        except Exception:
            pass
        filters = []
        mods = info.get("mods") or []
        matched = 0
        for m in mods:
            sid = match_stat_id(stats_index, m)
            if not sid:
                continue
            matched += 1
            f = {"id": sid,
                 "disabled": tiers.get(m) not in ("premium", "good")}
            vals = mod_values(m)
            if len(vals) >= 2:
                # two-slot rolls ("Adds 12 to 24 ...") filter by their
                # AVERAGE on the trade site
                f["value"] = {"min": round((vals[0] + vals[1]) / 2.0, 1)}
            elif vals:
                f["value"] = {"min": vals[0]}
            filters.append(f)
        q["query"]["stats"][0]["filters"] = filters
        if matched < len(mods):
            notes.append(f"{len(mods) - matched} mod(s) had no stat-id "
                         "match — add them on the site if they matter.")
        return q, matched, len(mods), notes
    except Exception as e:
        return q, 0, len(info.get("mods") or []), [f"query build error: {e}"]


def trade_query_url(query, league):
    """Search URL with the query prefilled via ?q= (the site reads it)."""
    import json
    league = (league or "Standard").strip() or "Standard"
    return (f"https://www.pathofexile.com/trade2/search/poe2/{quote(league)}"
            f"?q={quote(json.dumps(query, separators=(',', ':')))}")


def live_search_url(league):
    league = (league or "Standard").strip() or "Standard"
    return f"https://www.pathofexile.com/trade2/search/poe2/{quote(league)}"


# ---------------------------------------------------------------------------
# Crafting planner (W3-13) — goal-aware, multi-route, cost-annotated
# ---------------------------------------------------------------------------

# What the player might ask for -> the mod groups that deliver it.
_GOAL_MODS = {
    "phys":      (("physical", "phys"), "flat 'Adds # to # Physical Damage' + '%increased Physical Damage' (both prefixes)"),
    "elemental": (("elemental", "fire", "cold", "lightning"), "flat elemental damage prefixes"),
    "chaos":     (("chaos",), "flat/over-time chaos damage"),
    "crit":      (("crit",), "'+#% Critical Hit Chance' and '+#% Critical Damage Bonus' (suffixes)"),
    "speed":     (("attack speed", "cast speed", "speed"), "'%increased Attack Speed' (suffix)"),
    "life":      (("life", "hp"), "'+# to maximum Life'"),
    "es":        (("energy shield", " es",), "'%increased Energy Shield' + flat ES"),
    "resist":    (("resist", "res "), "elemental resistance suffixes"),
    "spell":     (("spell", "caster"), "'%increased Spell Damage' + '+# to Level of all Spell Skills'"),
    "mana":      (("mana",), "mana / mana regeneration"),
}

_BASE_WORDS = ("quarterstaff", "staff", "bow", "crossbow", "spear", "mace",
               "sceptre", "wand", "dagger", "claw", "sword", "axe", "flail",
               "helmet", "body armour", "chest", "gloves", "boots", "shield",
               "buckler", "focus", "quiver", "ring", "amulet", "belt")


def _econ_price(econ_rows, name_fragment):
    """Value (in Exalted Orbs) of the first economy row matching the fragment."""
    for r in (econ_rows or []):
        if name_fragment.lower() in str(r.get("name", "")).lower():
            try:
                return float(r.get("value"))
            except (TypeError, ValueError):
                return None
    return None


def offline_craft_guidance(goal, econ_rows=None):
    """A concrete, route-based crafting plan built from the goal text.

    Pure logic (no AI, no network). If `econ_rows` (poe.ninja currency rows)
    are provided, each route gets a rough cost line in Exalted Orbs."""
    g = (goal or "").lower()
    wants = [key for key, (words, _d) in _GOAL_MODS.items()
             if any(w in g for w in words)]
    base = next((b for b in _BASE_WORDS if b in g), None)

    lines = [f"CRAFTING PLAN — {goal.strip() or 'unspecified goal'}", ""]
    lines.append(f"Target base: {base.title() if base else 'not stated — name the base type for tier advice'}")
    if wants:
        lines.append("Mods that deliver this goal:")
        for k in wants:
            lines.append(f"  • {_GOAL_MODS[k][1]}")
        if len(wants) > 4:
            lines.append("  ⚠ That's more mod groups than one rare can hold well — "
                         "prioritize 3-4.")
    else:
        lines.append("Goal keywords not recognized — say what stats matter "
                     "(phys, crit, life, resists, spell...).")
    lines.append("")
    lines.append("Base rules: item level 81+ unlocks the top tiers; white bases "
                 "from endgame maps or bought cheap on trade.")
    lines.append("")

    def cost(frag, n=1):
        v = _econ_price(econ_rows, frag)
        return f" (~{v * n:,.1f} ex)" if v else ""

    lines.append("ROUTE A — Essence-guaranteed (recommended for a defined goal):")
    lines.append("  1. Start with a WHITE base.")
    lines.append("  2. Use the Essence matching your key mod (guarantees it while "
                 "rolling the item to Magic/Rare).")
    lines.append(f"  3. Regal{cost('Regal Orb')} → Exalt{cost('Exalted Orb')} to "
                 "fill remaining affixes; stop when 4+ useful mods land.")
    lines.append(f"  4. Divine{cost('Divine Orb')} only when every mod is right "
                 "but numbers roll low.")
    lines.append("")
    lines.append("ROUTE B — Chaos-reroll (budget, higher variance):")
    lines.append(f"  1. Buy the cheapest RARE with 2 of your mods already on it.")
    lines.append(f"  2. Chaos Orb{cost('Chaos Orb')} rerolls ONE mod in PoE2 — "
                 "snipe the bad affix; walk away when the swap would risk a "
                 "good one.")
    lines.append("")
    lines.append("ROUTE C — Omen-biased (endgame, expensive):")
    lines.append("  1. Omens constrain outcomes (e.g. Omen of Sinistral Erasure "
                 "protects suffixes when annulling).")
    lines.append(f"  2. Pair with Exalts{cost('Exalted Orb')} for controlled "
                 "finishing; check current Omen prices before committing.")
    lines.append("")
    lines.append("Exact odds & expected cost: open the Craft of Exile tab and "
                 "simulate this base + mod set (it does the deterministic math).")
    if econ_rows is None:
        lines.append("(Refresh the Exchange tab once to annotate routes with "
                     "live prices.)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Clipboard price estimate (W3-20) — currency & fragments via poe.ninja rows
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Pricing insight engine (W3-23) — which mods carry the price tag
# ---------------------------------------------------------------------------
# Tiers: "premium" = drives the price, search for it; "good" = worth including;
# "filler" = safe to EXCLUDE from the search (widens results, rarely changes
# value); "downside" = actively lowers value on most items.

# Order matters: downsides are checked FIRST so "reduced attack speed" never
# reads as a premium "attack speed" roll. All plain substrings, lowercase.
_MOD_TIERS = [
    ("downside", ("thorns", "reflect", "reduced attack speed",
                  "reduced cast speed", "reduced movement speed",
                  "increased attribute requirements", "you take")),
    ("filler", ("light radius", "stun threshold", "mana on kill",
                "life on kill", "reduced flask", "flask charges",
                "stun buildup", "daze", "on low life")),
    ("premium", ("maximum life", "to level of", "critical damage",
                 "critical hit damage", "attack speed", "cast speed",
                 "movement speed", "increased physical damage",
                 "increased spell damage", "increased energy shield",
                 "all elemental resistances", "chaos resistance",
                 "increased rarity")),
    ("good", ("resistance", "adds", "accuracy", "increased damage",
              "critical hit chance", "maximum mana", "maximum energy shield",
              "armour", "evasion", "spirit", "projectile", "leech",
              "regenerate")),
]


def _tier_for(mod):
    low = mod.lower()
    for tier, frags in _MOD_TIERS:
        if any(f in low for f in frags):
            return tier
    return "neutral"


def mod_insights(info):
    """Per-mod value analysis for the parsed item (W3-23).

    Returns {'mods': [(mod_text, tier, advice), ...], 'advice': [str, ...]}.
    Tiers: premium / good / neutral / filler / downside. Pure heuristics —
    honest about being heuristics — and never invents a price."""
    out = {"mods": [], "advice": []}
    mods = (info or {}).get("mods") or []
    tips = {
        "premium": "search for this — it carries the price",
        "good": "include if you want close comparisons",
        "neutral": "judgment call — include only if it matters to the buyer",
        "filler": "EXCLUDE from the search — widens results, rarely adds value",
        "downside": "hurts the price on most items — expect lower offers",
    }
    counts = {}
    for m in mods:
        t = _tier_for(m)
        counts[t] = counts.get(t, 0) + 1
        out["mods"].append((m, t, tips[t]))
    if not mods:
        out["advice"].append("No explicit mods parsed — for uniques the name "
                             "itself is the price; for bases, ilvl matters most.")
        return out
    prem = counts.get("premium", 0)
    if prem >= 3:
        out["advice"].append(f"{prem} premium mods on one item — price it "
                             "AMBITIOUSLY and search with all of them included.")
    elif prem >= 1:
        out["advice"].append("Search with the premium mod(s) + one good mod; "
                             "leave the rest unchecked to see the real market.")
    else:
        out["advice"].append("No premium mods — this trades close to its base; "
                             "search by base type + ilvl only.")
    if counts.get("filler"):
        out["advice"].append(f"{counts['filler']} filler mod(s) — excluding "
                             "them from the search will surface far more "
                             "comparable listings without changing value.")
    if counts.get("downside"):
        out["advice"].append("Has value-LOWERING mod(s) — comparable clean "
                             "items will list higher than yours.")
    out["advice"].append("Heuristic tiers, not gospel — meta shifts; confirm "
                         "against live listings.")
    return out


def estimate_value(info, econ_rows):
    """Best-effort instant estimate for a parsed item.

    Only quotes things poe.ninja's currency feed actually prices (stackable
    currency); everything else returns None -> the popup links the trade
    search instead of fabricating a number. Returns (value_ex, note) or None."""
    if not info or not econ_rows:
        return None
    name = (info.get("name") or info.get("base") or "").strip()
    if not name:
        return None
    cls = (info.get("item_class") or "").lower()
    if "currency" not in cls and "fragment" not in cls and cls != "":
        return None
    for r in econ_rows:
        rname = str(r.get("name", ""))
        if rname.lower() == name.lower():
            try:
                v = float(r.get("value"))
            except (TypeError, ValueError):
                return None
            return v, f"{rname}: ~{v:,.2f} Exalted each (poe.ninja)"
    return None


if __name__ == "__main__":
    sample = """Item Class: Spears
Rarity: Rare
Bramble Fang
Bronze Spear
--------
Requirements:
Level: 45
Str: 80
--------
Item Level: 72
--------
Adds 12 to 24 Physical Damage
18% increased Attack Speed
+45 to maximum Life
"""
    info = parse_item_text(sample)
    assert info["rarity"] == "Rare", info
    assert info["name"] == "Bramble Fang", info
    assert info["base"] == "Bronze Spear", info
    assert info["ilvl"] == "72", info
    assert any("Attack Speed" in m for m in info["mods"]), info
    print("parse OK:", info)
    print("url:", trade_search_url(info, "Standard"))
