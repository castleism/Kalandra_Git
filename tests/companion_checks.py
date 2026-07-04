"""
Companion-wave (W4) adversarial checks: player_profile, providers,
price_ledger, grind_tracker, character_folio.
Run: python3 tests/companion_checks.py   (headless-safe, no PyQt needed)
Same conventions as stress_test.py; uses a temp dir so it never touches
the real data_engine.
"""
import os, sys, json, tempfile, traceback

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

def section(s):
    print(f"\n=== {s} ===")

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

TMP = tempfile.mkdtemp(prefix="kalandra_w4_")

# ---------------------------------------------------------------------------
section("player_profile — answers, persistence, prompt block")
from core_engine.player_profile import PlayerProfile, QUESTIONS

p = PlayerProfile()
check("fresh profile incomplete", not p.is_complete())
check("fresh prompt block empty", p.prompt_block() == "")
check("10 questions", len(QUESTIONS) == 10)
check("every chip question has 2+ chips",
      all(len(q.get("chips", [])) >= 2 for q in QUESTIONS
          if not q.get("free_text")))
check("exactly one free-text question",
      sum(1 for q in QUESTIONS if q.get("free_text")) == 1)
check("sensitive question includes decline option",
      any(v == "skip" for _, v in
          next(q for q in QUESTIONS if q["id"] == "climb_style")["chips"]))

for q in QUESTIONS:
    if q.get("free_text"):
        p.set(q["id"], "унікальний build 🦉 " + "x" * 500)   # unicode + long
    else:
        p.set(q["id"], q["chips"][0][1])
check("complete after answering all", p.is_complete())
blk = p.prompt_block()
check("prompt block nonempty", bool(blk))
check("prompt block single line-ish (<1200 chars)", len(blk) < 1200)
check("detail directive present", "Explain mechanics" in blk)

path = os.path.join(TMP, "prof.json")
check("save ok", p.save(path))
p2 = PlayerProfile.load(path)
check("round trip", p2.get("background") == p.get("background"))
guard("load from garbage path", lambda: PlayerProfile.load(
    os.path.join(TMP, "nope", "deep", "prof.json")))
with open(os.path.join(TMP, "bad.json"), "w") as f:
    f.write("{not json")
check("load malformed -> empty profile",
      not PlayerProfile.load(os.path.join(TMP, "bad.json")).is_complete())

# unknown answer values must not break the prompt block
p3 = PlayerProfile()
p3.set("background", "hacked_value_9000")
guard("prompt block with unknown value", p3.prompt_block)

# ---------------------------------------------------------------------------
section("providers — registry, degradation")
from core_engine.providers import get_provider, set_provider, capabilities

check("six capabilities", len(capabilities()) == 6)
check("unknown capability -> None", get_provider("time_machine") is None)
for cap in capabilities():
    prov = get_provider(cap)
    check(f"{cap} instantiates", prov is not None)
    check(f"{cap} singleton", get_provider(cap) is prov)
    guard(f"{cap}.available() never raises", prov.available)

ts = get_provider("trade_search")
guard("trade url on junk", lambda: ts.search_url({"name": None}, ""))
check("trade url junk -> str", isinstance(ts.search_url({}, "x"), str))
bc = get_provider("build_calculator")
r = bc.parse_build("<not-xml")
check("calc junk xml -> dict", isinstance(r, dict))
check("calc stats without sim -> ''", bc.stats_summary() == "")

class _Fake:
    def available(self): return True
    def currency_rates(self, league): return {"divine": 180.0}
set_provider("economy", _Fake())
check("set_provider swaps", get_provider("economy").currency_rates("x")
      == {"divine": 180.0})

# ---------------------------------------------------------------------------
section("price_ledger — templates, logging, estimates")
from core_engine.price_ledger import PriceLedger, mod_template

check("template basic", mod_template("+120 to maximum Life")
      == ("+# to maximum Life", [120.0]))
check("template two nums", mod_template("Adds 5 to 12 Fire Damage")[0]
      == "Adds # to # Fire Damage")
check("template decimals", mod_template("1.5% of Damage Leeched")[1] == [1.5])
check("template no nums", mod_template("Cannot be Frozen")
      == ("Cannot be Frozen", []))
check("template empty", mod_template("") == ("", []))
check("template None", mod_template(None) == ("", []))
check("keeps T1 letters intact", mod_template("Tier: 1")[0] == "Tier: #")

led = PriceLedger(os.path.join(TMP, "ledger.db"))
ITEM = """Item Class: Body Armours
Rarity: Rare
Behemoth Shell
Full Plate
--------
Item Level: 82
--------
+120 to maximum Life
+45% to Fire Resistance
"""
check("log without price ok", led.log_check(ITEM, league="L") is not None)
for price in (2.0, 3.0, 4.0, 5.0):
    check(f"log priced {price}", led.log_check(
        ITEM, price=price, currency="divine", league="L") is not None)
check("log junk -> None", led.log_check("", league="L") is None)
check("log None -> None", led.log_check(None) is None)
guard("log huge item", lambda: led.log_check(
    "Rarity: Rare\nBig\nBase\n" + "\n".join(f"+{i} to X" for i in range(500)),
    price=1, currency="chaos", league="L"))

mv = led.mod_value("+# to maximum Life", league="L")
check("mod value found", mv is not None)
if mv:
    check("mod value median 3.5", abs(mv[0] - 3.5) < 0.01)
    check("mod value n=4", mv[2] == 4)
check("mod value respects min_samples",
      led.mod_value("+# to maximum Life", league="L", min_samples=99) is None)
check("mod value unknown tpl -> None", led.mod_value("no such mod #") is None)
est = led.estimate_item(ITEM, league="L")
check("item estimate present", est is not None and est["known_mods"] >= 1)
st = led.stats()
check("stats counts", st["checks"] >= 5 and st["priced"] >= 4
      and st["mod_templates"] >= 2)

# mixed currency must refuse to answer rather than lie
led2 = PriceLedger(os.path.join(TMP, "ledger2.db"))
for cur in ("divine", "divine", "chaos"):
    led2.log_check(ITEM, price=1, currency=cur, league="L")
check("mixed currencies -> None",
      led2.mod_value("+# to maximum Life", league="L") is None)

# ---------------------------------------------------------------------------
section("grind_tracker — snapshots, runs, per-mod returns")
from core_engine.grind_tracker import GrindTracker

gt = GrindTracker(os.path.join(TMP, "grind.db"))
RATES = {"divine": 180.0, "chaos": 1.0}
lid = gt.snapshot("juiced breach", [
    {"name": "Breach Tablet", "qty": 4,
     "mods": ["23% increased Quantity of Items"]},
    {"name": "Waystone T15", "qty": 10, "mods": ["Area contains 2 Breaches"]},
], league="L")
check("snapshot id", lid is not None)
for div, mins in ((0.5, 10), (1.0, 12), (0.3, 9)):
    check("run recorded", gt.record_run(
        lid, income=[("divine", div), ("chaos", 20)], minutes=mins) is not None)
stats = gt.loadout_stats(lid, rates=RATES)
check("3 runs", stats["runs"] == 3)
check("total value right",
      abs(stats["total_chaos"] - (1.8 * 180 + 60)) < 0.01)
check("per-hour computed", stats["per_hour"] is not None and stats["per_hour"] > 0)
mr = gt.mod_returns(rates=RATES)
check("mod returns nonempty", len(mr) >= 2)
check("mod returns sorted desc",
      all(mr[i]["avg_per_run"] >= mr[i+1]["avg_per_run"]
          for i in range(len(mr) - 1)))
check("mod returns respects min_runs", gt.mod_returns(rates=RATES,
                                                      min_runs=99) == [])
check("stats on bogus loadout", gt.loadout_stats(999999)["runs"] == 0)
guard("record on bogus loadout", lambda: gt.record_run(999999, [("chaos", 1)]))
guard("snapshot junk items", lambda: gt.snapshot("x", [None, {}, {"mods": [None, ""]}]))
check("untimed run kills per_hour", (
    gt.record_run(lid, income=[("chaos", 5)]) is not None
    and gt.loadout_stats(lid, rates=RATES)["per_hour"] is None))

# ---------------------------------------------------------------------------
section("character_folio — scaffold, corpus budget")
from core_engine.character_folio import CharacterFolio, list_folios, slugify

check("slug basic", slugify("My Gemling! (v2)") == "My_Gemling_v2")
check("slug empty", slugify("") == "character")
check("slug unicode survives", slugify("Штормовик") != "character")

root = os.path.join(TMP, "chars")
f = CharacterFolio("Storm Weaver", root=root)
check("ensure", f.ensure())
check("scaffold files", all(os.path.exists(os.path.join(f.path, fn))
      for fn in ("profile.json", "review.md", "roadmap.md", "watchlist.json")))
check("corpus empty before content", f.prompt_corpus() == "")
check("write review", f.write_doc("review", "# Review\nA storm build. " * 50))
check("write bad doc refused", not f.write_doc("hack", "x"))
check("write scan", f.write_scan({"class": "Sorceress", "skills": ["Spark"]}))
check("watch item", f.add_watch_item("Astramentis", note="pivot to stat-stack"))
check("sim note", f.add_sim_note("what-if: swap ring", "dps +4%"))
corp = f.prompt_corpus(budget_chars=800)
check("corpus nonempty after content", bool(corp))
check("corpus respects budget", len(corp) <= 900)
check("corpus prioritizes review", "review.md" in corp)
check("list folios", "Storm_Weaver" in list_folios(root))
g = CharacterFolio("Storm Weaver", root=root)
check("same name -> same folio", g.path == f.path)
guard("corpus on missing folio", lambda: CharacterFolio(
    "Ghost", root=root).prompt_corpus())

# ---------------------------------------------------------------------------
print(f"\n{'='*50}\nRESULT: {PASS} passed, {FAIL} failed")
if FAILURES:
    print("FAILURES:")
    for fl in FAILURES:
        print("  -", fl)
    sys.exit(1)
print("ALL GREEN")
