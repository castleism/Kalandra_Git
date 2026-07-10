"""
TESTS/TRADE_QUERY_CHECKS.PY — sandbox checks for the W3-21 trade-query
prefill (parsed item -> stat-id filters -> ?q= URL).

Pure trade_tools logic against a fixture stats map shaped exactly like the
site's /api/trade2/data/stats response (incl. its [A|B] text markup). The
live fetch/caching lives in the GUI layer and fails soft to the plain URL —
nothing here touches the network. Same style as tests/craft_checks.py.
"""

import json
import os
import sys
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [FAIL] {name}")


def guard(name, fn):
    try:
        fn()
        check(name, True)
    except Exception as e:
        print(f"  [FAIL] {name}: raised {e}")
        globals()["FAIL"] += 1


from core_engine.trade_tools import (
    build_stats_index, build_trade_query, match_stat_id, mod_values,
    normalize_stat_text, parse_item_text, trade_query_url,
)

# ---- fixture: the documented /api/trade2/data/stats shape --------------------
STATS_FIXTURE = {"result": [
    {"id": "explicit", "label": "Explicit", "entries": [
        {"id": "explicit.stat_life", "text": "+# to maximum Life",
         "type": "explicit"},
        {"id": "explicit.stat_spell", "text": "#% increased Spell Damage",
         "type": "explicit"},
        {"id": "explicit.stat_as",
         "text": "#% increased [Attacks|Attack] Speed", "type": "explicit"},
        {"id": "explicit.stat_fire", "text": "+#% to [Resistances|Fire "
         "Resistance]", "type": "explicit"},
        {"id": "explicit.stat_addphys",
         "text": "Adds # to # [Physical|Physical] Damage",
         "type": "explicit"},
        {"id": "explicit.stat_mana", "text": "+# to maximum Mana",
         "type": "explicit"},
        {"id": "explicit.stat_light", "text": "#% increased Light Radius",
         "type": "explicit"},
    ]},
    {"id": "implicit", "label": "Implicit", "entries": [
        {"id": "implicit.stat_life", "text": "+# to maximum Life",
         "type": "implicit"},
        {"id": "implicit.stat_ms",
         "text": "#% increased Movement Speed", "type": "implicit"},
    ]},
]}

# ---- normalize_stat_text ------------------------------------------------------
check("markup [A|B] -> B", normalize_stat_text(
    "+#% to [Resistances|Fire Resistance]") == "#% to fire resistance")
check("markup [A|B] mid-line", normalize_stat_text(
    "#% increased [Attacks|Attack] Speed") == "#% increased attack speed")
check("bare [A] keeps the word", normalize_stat_text(
    "#% increased [Evasion] Rating") == "#% increased evasion rating")
check("numbers -> #", normalize_stat_text("+45 to maximum Life")
      == "# to maximum life")
check("api # placeholder kept", normalize_stat_text("+# to maximum Life")
      == "# to maximum life")
check("clipboard and api meet in the middle",
      normalize_stat_text("104% increased Spell Damage")
      == normalize_stat_text("#% increased Spell Damage"))
check("junk-safe normalize", normalize_stat_text(None) == "")

# ---- mod_values ------------------------------------------------------------------
check("values in order", mod_values("Adds 12 to 24 Physical Damage")
      == [12.0, 24.0])
check("negative + decimal", mod_values("-30.5% thing") == [-30.5])
check("junk-safe values", mod_values(None) == [])

# ---- build_stats_index --------------------------------------------------------------
idx = build_stats_index(STATS_FIXTURE)
check("index built", len(idx) == 8)
check("explicit beats implicit on collisions",
      idx[normalize_stat_text("+# to maximum Life")] == "explicit.stat_life")
check("implicit-only stat still present",
      idx[normalize_stat_text("#% increased Movement Speed")]
      == "implicit.stat_ms")
check("malformed json -> empty index", build_stats_index({"result": "x"})
      in ({},))
check("none json -> empty index", build_stats_index(None) == {})

# ---- match_stat_id ---------------------------------------------------------------------
check("exact clipboard match",
      match_stat_id(idx, "+45 to maximum Life") == "explicit.stat_life")
check("markup stat matched from clipboard text",
      match_stat_id(idx, "+37% to Fire Resistance") == "explicit.stat_fire")
check("two-slot mod matched",
      match_stat_id(idx, "Adds 12 to 24 Physical Damage")
      == "explicit.stat_addphys")
check("unknown mod -> None",
      match_stat_id(idx, "Culling Strike") is None)
check("empty index -> None", match_stat_id({}, "+45 to maximum Life") is None)
check("near-typo fuzzy match",
      match_stat_id(idx, "+45 to maximum Lifee") == "explicit.stat_life")

# ---- build_trade_query -----------------------------------------------------------------
CLIP = """Item Class: Wands
Rarity: Rare
Storm Song
Attuned Wand
--------
Item Level: 81
--------
104% increased Spell Damage
+45 to maximum Life
Adds 12 to 24 Physical Damage
+38 to maximum Mana
14% increased Light Radius
12% increased Stun Threshold
"""
info = parse_item_text(CLIP)
q, matched, total, notes = build_trade_query(info, idx)
check("rare searches by base type", q["query"]["type"] == "Attuned Wand"
      and "name" not in q["query"])
check("online-only default", q["query"]["status"]["option"] == "online")
check("mods mapped", matched == 5 and total == 6)
check("unmapped mod reported", notes and "no stat-id" in notes[0])
filters = {f["id"]: f for f in q["query"]["stats"][0]["filters"]}
check("premium mod enabled at its roll",
      filters["explicit.stat_spell"]["disabled"] is False
      and filters["explicit.stat_spell"]["value"]["min"] == 104.0)
check("two-slot mod filters by average",
      filters["explicit.stat_addphys"]["value"]["min"] == 18.0)
check("filler mod ships disabled",
      filters["explicit.stat_light"]["disabled"] is True)
check("good mod enabled",
      filters["explicit.stat_mana"]["disabled"] is False)

UNIQ = ("Item Class: Bows\nRarity: Unique\nWidowhail\nCrude Bow\n--------\n"
        "150% increased bonuses gained from Equipped Quiver\n")
uq, _m, _t, _n = build_trade_query(parse_item_text(UNIQ), idx)
check("unique searches by name + base", uq["query"].get("name") == "Widowhail"
      and uq["query"].get("type") == "Crude Bow")

eq, m0, t0, _ = build_trade_query({}, idx)
check("empty item safe", m0 == 0 and t0 == 0
      and eq["query"]["stats"][0]["filters"] == [])
guard("junk inputs never crash", lambda: build_trade_query(
    {"mods": [None, 42]}, {"x": None}))

# ---- trade_query_url ----------------------------------------------------------------------
url = trade_query_url(q, "Rise of the Abyssal")
check("league path encoded",
      "/trade2/search/poe2/Rise%20of%20the%20Abyssal?q=" in url)
decoded = json.loads(unquote(url.split("?q=", 1)[1]))
check("q round-trips to the same query", decoded == q)
check("sort included", decoded["sort"] == {"price": "asc"})

print(f"RESULT: {PASS} passed, {FAIL} failed")
print("ALL GREEN" if FAIL == 0 else "NOT GREEN")
sys.exit(1 if FAIL else 0)
