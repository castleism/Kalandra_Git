"""
W4-06 nerf_intel adversarial checks.
Run: python3 tests/nerf_checks.py
"""
import os, sys, traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = 0
FAIL = 0
FAILURES = []

def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  FAIL: {name}")

def guard(name, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
    except Exception as e:
        FAIL += 1
        FAILURES.append(f"{name}: {e!r}")
        print(f"  CRASH: {name}: {e!r}")
        traceback.print_exc()

from core_engine.nerf_intel import (
    classify_line, assess_patch_impact, assess_patches, nerf_watch,
    patches_from_db, price_series_from_db, price_shift, value_intuition,
    _version_key,
)

print("=== classify_line ===")
check("plain nerf", classify_line(
    "Hand of Wisdom and Action: damage per Dexterity reduced to 6-8") == "nerf")
check("plain buff", classify_line(
    "Astramentis: implicit attributes increased to +100") == "buff")
check("no longer = nerf", classify_line(
    "Headhunter no longer steals aura effects") == "nerf")
check("negated nerf = buff", classify_line(
    "The helmet no longer suffers reduced attack speed") == "buff")
check("neutral", classify_line("Fixed a bug with sockets") == "neutral")
check("empty", classify_line("") == "neutral")
check("None", classify_line(None) == "neutral")
guard("unicode line", lambda: classify_line("уменьшено 增加 🦉 reduced"))

print("=== assess_patch_impact ===")
PATCH = """
Balance changes:
Hand of Wisdom and Action: Lightning Damage per Dexterity reduced from 1-15 to 1-10.
Astramentis: no changes.
Boss health increased by 20%.
Stormweaver's Cap: cooldown recovery increased by 25%.
"""
r = assess_patch_impact("Hand of Wisdom and Action", PATCH)
check("HoWA flagged nerf", r["verdict"] == "nerf" and len(r["evidence"]) == 1)
check("unmentioned item -> none",
      assess_patch_impact("Headhunter", PATCH)["verdict"] == "none")
check("no guilt by adjacency (boss line not attributed)",
      all("Boss health" not in ln for ln, _ in r["evidence"]))
check("buff detected", assess_patch_impact(
    "Stormweaver's Cap", PATCH)["verdict"] == "buff")
check("alias matching", assess_patch_impact(
    "HoWA", PATCH, aliases=["Hand of Wisdom and Action"])["verdict"] == "nerf")
check("empty name -> none", assess_patch_impact("", PATCH)["verdict"] == "none")
guard("garbage patch text", lambda: assess_patch_impact("X", b"\x00\xff"))

print("=== assess_patches (multi-league) ===")
seq = [("0.2", "Astramentis: implicit increased to +100."),
       ("0.3", "Astramentis: implicit reduced to +80.")]
agg = assess_patches("Astramentis", seq)
check("latest patch wins", agg["verdict"] == "nerf")
check("per-patch verdicts", agg["by_patch"] == {"0.2": "buff", "0.3": "nerf"})
check("empty patches", assess_patches("X", [])["verdict"] == "none")

print("=== price_shift ===")
ps = price_shift([("league1", 100), ("league2", 90), ("league3", 30)])
check("down detected", ps["direction"] == "down")
check("change pct", abs(ps["change_pct"] - (-70.0)) < 0.1)
check("cliff at league3", ps["cliff_at"] == "league3"
      and ps["cliff_pct"] < -60)
check("up detected", price_shift([("a", 10), ("b", 20)])["direction"] == "up")
check("flat", price_shift([("a", 100), ("b", 103)])["direction"] == "flat")
check("too few points", price_shift([("a", 5)]) is None)
check("junk prices skipped", price_shift(
    [("a", "x"), ("b", -5), ("c", 10), ("d", 8)]) is not None)
check("empty", price_shift([]) is None)

print("=== value_intuition ===")
vi = value_intuition("Headhunter", patches=[("0.3", "Nothing about it.")],
                     series=[("Dawn", 100), ("Temple", 20)])
check("temple-headhunter pattern named",
      "supply/league" in vi["summary"])
vi2 = value_intuition("Hand of Wisdom and Action",
                      patches=[("0.3", PATCH)],
                      series=[("A", 50), ("B", 10)])
check("nerf + price drop combined",
      "nerf-flagged" in vi2["summary"] and "down" in vi2["summary"])
check("no signals wording", "No nerf or price signals" in
      value_intuition("Unknown Item")["summary"])
guard("all-junk inputs", lambda: value_intuition(None, patches=[(None, None)],
                                                 series=[(None, None)]))

print("=== W4-06 wiring: DB feeds ===")
import sqlite3
import tempfile

check("version key orders point releases",
      _version_key("Version 0.2.1") > _version_key("0.2.0")
      and _version_key("0.2.0g") > _version_key("0.2.0"))
check("unversioned sorts first", _version_key("garbage") < _version_key("0.1"))

with tempfile.TemporaryDirectory() as td:
    dbp = os.path.join(td, "kb.db")
    con = sqlite3.connect(dbp)
    con.execute("""CREATE TABLE knowledge_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT, topic_tag TEXT,
        content_payload TEXT, source_url TEXT, scraped_at TEXT,
        game_version_tag TEXT)""")
    con.executemany(
        "INSERT INTO knowledge_ledger (topic_tag, content_payload, "
        "source_url, scraped_at) VALUES (?,?,?,?)", [
            ("Version 0.2.0",
             "Hand of Wisdom and Action: damage per Dexterity reduced.",
             "https://www.poe2wiki.net/wiki/Version_0.2.0", "t"),
            ("Patch Notes 0.1.0",
             "Astramentis: implicit attributes increased to +100.",
             "https://poe2db.tw/us/patch-notes-0.1.0", "t"),
            ("Widowhail", "a bow page, not patch notes",
             "https://poe2db.tw/us/Widowhail", "t"),
        ])
    con.execute("""CREATE TABLE economy_history(
        day TEXT NOT NULL, league TEXT NOT NULL, name TEXT NOT NULL,
        value REAL, volume REAL, PRIMARY KEY (day, league, name))""")
    con.executemany("INSERT INTO economy_history VALUES (?,?,?,?,?)", [
        ("2026-07-01", "Standard", "Divine Orb", 180.0, 10),
        ("2026-07-05", "Standard", "Divine Orb", 150.0, 10),
        ("2026-07-09", "Standard", "Divine Orb", 90.0, 10),
        ("2026-07-09", "Standard", "Chaos Orb", 1.0, 10),
        ("2026-07-09", "OtherLeague", "Divine Orb", 500.0, 10),
    ])
    con.commit()
    con.close()

    patches = patches_from_db(db_path=dbp)
    check("only patch pages mined", len(patches) == 2)
    check("oldest first", patches[0][0].startswith("0.1")
          and patches[1][0].startswith("0.2"))
    check("non-patch page excluded",
          all("bow page" not in text for _v, text in patches))

    series = price_series_from_db("divine orb", "Standard", db_path=dbp)
    check("series chronological + league-scoped + case-insensitive",
          [v for _d, v in series] == [180.0, 150.0, 90.0])
    check("unknown item empty series",
          price_series_from_db("Mirror", "Standard", db_path=dbp) == [])

    vi = nerf_watch("Hand of Wisdom and Action", db_path=dbp)
    check("nerf found end-to-end", vi["patch"]["verdict"] == "nerf"
          and vi["has_signals"])
    vi2 = nerf_watch("Divine Orb", league="Standard", db_path=dbp)
    check("price cliff found end-to-end",
          vi2["price"] and vi2["price"]["direction"] == "down"
          and vi2["has_signals"])
    check("supply-not-nerf wording end-to-end",
          "supply/league" in vi2["summary"])
    vi3 = nerf_watch("Widowhail", db_path=dbp)
    check("quiet when nothing to say", not vi3["has_signals"])

check("missing db fails soft", patches_from_db(db_path="/no/such.db") == []
      and price_series_from_db("x", "Standard", db_path="/no/such.db") == [])
guard("nerf_watch junk-safe",
      lambda: nerf_watch(None, league=123, db_path="/no/such.db"))

print(f"\n{'='*50}\nRESULT: {PASS} passed, {FAIL} failed")
if FAILURES:
    print("FAILURES:")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("ALL GREEN")
