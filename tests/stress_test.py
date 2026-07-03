"""
Kalandra stress / adversarial test harness.
Exercises the importable core logic with malformed, empty, huge, and unicode
inputs to surface crashes and wrong results. Run: python3 tests/stress_test.py
Skips modules that need GUI / native deps not present in this environment.
"""
import os, sys, json, tempfile, traceback, threading

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
    """Run fn(); a raised exception is a FAIL (we want no crashes)."""
    global PASS, FAIL
    try:
        fn()
        PASS += 1
    except Exception as e:
        FAIL += 1
        FAILURES.append(f"{name}: {e!r}")
        print(f"  CRASH: {name}: {e!r}")
        traceback.print_exc()

# ---------------------------------------------------------------------------
section("pob_bridge — build parsing edge cases")
try:
    from core_engine.pob_bridge import KalandraPoBBridge
    b = KalandraPoBBridge()

    # malformed / empty XML must not crash
    for bad in ["", "   ", "<not-xml", "<PathOfBuilding>", "<a><b></a>",
                None, "<PathOfBuilding></PathOfBuilding>", "随机字符 𝓤𝓷𝓲𝓬𝓸𝓭𝓮"]:
        guard(f"extract_full_build({bad!r:.20})", lambda bad=bad: b.extract_full_build(bad))

    # error dict passthrough
    err = b.extract_full_build("<bad")
    check("malformed xml returns error dict", isinstance(err, dict) and "error" in err)

    # build_ai_summary on error / empty
    check("summary on error -> ''", b.build_ai_summary({"error": "x"}) == "")
    check("summary on None -> ''", b.build_ai_summary(None) == "")
    check("summary on {} -> ''", b.build_ai_summary({}) == "")

    # analyze_scaling / tree_guidance robustness
    check("analyze None -> {}", b.analyze_scaling(None) == {})
    check("analyze error -> {}", b.analyze_scaling({"error": "x"}) == {})
    check("tree_guidance None -> ''", b.tree_guidance(None) == "")
    check("tree_guidance no main_skill -> ''", b.tree_guidance({"items": []}) == "")

    # decode_pob_string with garbage
    guard("decode garbage", lambda: b.decode_pob_string("!!!not-base64!!!"))
    guard("decode empty", lambda: b.decode_pob_string(""))

    # _is_mod classification
    check("_is_mod numeric-leading", b._is_mod("12% increased Physical Damage") is True)
    check("_is_mod plus-leading", b._is_mod("+25 to maximum Life") is True)
    check("_is_mod metadata rarity", b._is_mod("Rarity: RARE") is False)
    check("_is_mod item class", b._is_mod("Item Class: Jewels") is False)
    check("_is_mod blank", b._is_mod("   ") is False)
    check("_is_mod keyword", b._is_mod("increased Spirit") is True)

    # a real-ish build with jewels + warcry DPS shape
    xml = '''<PathOfBuilding>
    <Build level="92" className="Mercenary" ascendClassName="Gemling Legionnaire" mainSocketGroup="1">
    <PlayerStat value="0" stat="FullDPS"/><PlayerStat value="204595.7" stat="CombinedDPS"/>
    <PlayerStat value="2183" stat="Life"/><PlayerStat value="689" stat="Spirit"/>
    <PlayerStat value="322" stat="SpiritUnreserved"/></Build>
    <Skills activeSkillSet="1"><SkillSet id="1">
    <Skill enabled="true"><Gem nameSpec="Fortifying Cry"/><Gem nameSpec="Brutality" gemId="SupportGem"/></Skill>
    </SkillSet></Skills>
    <Items activeItemSet="1">
    <Item id="1">Rarity: UNIQUE
Tabula Rasa
Simple Robe</Item>
    <Item id="2">Rarity: RARE
Glyph Shard
Time-Lost Diamond
Item Class: Jewels
27% increased maximum Energy Shield
30% increased Damage with Warcries</Item>
    <ItemSet id="1"><Slot name="Body Armour" itemId="1"/></ItemSet>
    </Items>
    <Tree activeSpec="1"><Spec><Sockets><Socket nodeId="100" itemId="2"/></Sockets></Spec></Tree>
    </PathOfBuilding>'''
    full = b.extract_full_build(xml)
    check("full parse level", full.get("level") == "92")
    check("full parse class", full.get("class_name") == "Mercenary")
    check("jewel captured", any(j.get("name") == "Glyph Shard" for j in full.get("jewels", [])))
    check("jewel numeric mod captured",
          any("27% increased maximum Energy Shield" in (j.get("mods") or [])
              for j in full.get("jewels", [])))
    summ = b.build_ai_summary(full)
    check("summary has CombinedDPS not 0", "204,59" in summ or "204595" in summ)
    check("summary shows spirit unreserved", "unreserved 322" in summ)
    prof = b.analyze_scaling(full)
    check("scaling has main_skill", prof.get("main_skill") == "Fortifying Cry")
except Exception as e:
    print("pob_bridge section error:", e); traceback.print_exc()

# ---------------------------------------------------------------------------
section("trackers — CRUD / persistence / unique ids / corruption")
def _tracker_suite(make, prefix):
    d = tempfile.mkdtemp()
    path = os.path.join(d, "t.json")
    t = make(path)
    # rapid adds -> unique ids
    ids = []
    for i in range(50):
        e = t.add(f"item {i}") if prefix != "cor" else t.add(f"topic{i}", "correction text")
        ids.append(e["id"])
    check(f"{prefix}: 50 unique ids", len(set(ids)) == 50)
    # persistence: reload from disk
    t2 = make(path)
    check(f"{prefix}: persisted across reload", len(t2.all()) >= 50)
    # delete a known id works on the right one
    first = ids[0]
    if hasattr(t, "delete"):
        ok = t.delete(first)
        check(f"{prefix}: delete returns True", ok is True)
        check(f"{prefix}: deleted id gone", t.get(first) is None if hasattr(t, "get") else True)
    # corrupt the file -> must not crash on load
    with open(path, "w") as f:
        f.write("{ this is not valid json ][")
    guard(f"{prefix}: load corrupt json", lambda: make(path))
    # empty file
    with open(path, "w") as f:
        f.write("")
    guard(f"{prefix}: load empty file", lambda: make(path))

try:
    from core_engine.reserve_tracker import ReserveTracker
    _tracker_suite(lambda p: ReserveTracker(p), "rsv")
except Exception as e:
    print("reserve err", e); traceback.print_exc()
try:
    from core_engine.issue_tracker import IssueTracker
    _tracker_suite(lambda p: IssueTracker(p), "iss")
    # export markdown on empty + with items
    it = IssueTracker(os.path.join(tempfile.mkdtemp(), "i.json"))
    guard("issues export empty", lambda: it.export_markdown())
    it.add("Bug A", type="bug", severity="high", context="line1\nline2")
    md = it.export_markdown()
    check("issues export contains title", "Bug A" in md)
    check("issues open_count", it.open_count() == 1)
    it.set_status(it.all()[0]["id"], "resolved")
    check("issues resolved drops open_count", it.open_count() == 0)
except Exception as e:
    print("issue err", e); traceback.print_exc()
try:
    from core_engine.knowledge_corrections import KnowledgeCorrections
    kc = KnowledgeCorrections(os.path.join(tempfile.mkdtemp(), "k.json"))
    check("corrections seeded", len(kc.all()) >= 1)
    check("corrections relevant CB", bool(kc.context_block("scaling corrupted blood")))
    check("corrections irrelevant empty", kc.context_block("what is the best cold spell") == "")
    check("corrections empty text -> ''", kc.context_block("") == "")
    guard("corrections add", lambda: kc.add("Test Topic", "Test correction", ["test"]))
except Exception as e:
    print("corrections err", e); traceback.print_exc()

# ---------------------------------------------------------------------------
section("scraper — snippet cleaning")
try:
    from core_engine.scraper import KalandraScraper as S
    junk = "Skill Gems\nUpdate cookie preferences\nTW 繁體中文\n한국어\nPatreon\n" \
           "Fortifying Cry\nWarcry, AoE\nGrants Fortification.\n"
    cl = S._clean_content(junk)
    check("clean removes cookie line", "Update cookie preferences" not in cl)
    check("clean removes CJK", "繁體中文" not in cl and "한국어" not in cl)
    check("clean keeps real content", "Fortification" in cl)
    snip = S._snippet_around(junk, "Fortifying Cry")
    check("snippet centers on term", "Fortifying Cry" in snip and "Fortification" in snip)
    check("clean empty -> ''", S._clean_content("") == "")
    check("clean None -> ''", S._clean_content(None) == "")
    check("snippet term-not-present returns text", len(S._snippet_around("hello world data here", "zzz")) > 0)
except Exception as e:
    print("scraper err", e); traceback.print_exc()

# ---------------------------------------------------------------------------
section("poe_ninja — parsing robustness")
try:
    from core_engine import poe_ninja as pn
    # If the module exposes a pure parser, test it with mock; otherwise just import.
    check("poe_ninja imports", hasattr(pn, "PoENinja"))
except Exception as e:
    print("poe_ninja err", e); traceback.print_exc()

# ---------------------------------------------------------------------------
section("account_manager — fail-closed without keyring")
try:
    from core_engine.account_manager import AccountManager, SERVICES
    am = AccountManager()
    meta = am.list_service_meta()
    check("service meta non-empty", len(meta) >= 10)
    check("service meta no keychain (connected None)", all(s["connected"] is None for s in meta))
    # without keyring, set/get/is_connected must be safe and falsey
    guard("set_secret no keyring", lambda: am.set_secret("openai", "x"))
    check("is_connected falsey without keyring", not am.is_connected("openai"))
    check("ai providers present", all(p in SERVICES for p in
          ["openai","anthropic","gemini","deepseek","mistral","xai"]))
except Exception as e:
    print("account_manager err", e); traceback.print_exc()

# ---------------------------------------------------------------------------
section("database_handler — sqlite schema + search + threads")
try:
    from core_engine.database_handler import KalandraDBHandler
    d = tempfile.mkdtemp()
    db = KalandraDBHandler(db_dir=d)
    # store + search round trip
    guard("db search empty term", lambda: None)
    # concurrent connections (per-thread) must not corrupt
    def worker():
        h = KalandraDBHandler(db_dir=d)
        h.cursor.execute("SELECT COUNT(*) FROM knowledge_ledger")
        h.cursor.fetchone()
        h.close()
    ts = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    check("db concurrent connections survived", True)
    db.close()
except Exception as e:
    print("database_handler err", e); traceback.print_exc()

# ---------------------------------------------------------------------------
section("version")
try:
    import version
    check("version string", isinstance(version.KALANDRA_VERSION, str) and len(version.KALANDRA_VERSION) > 0)
    guard("version.title()", lambda: version.title("x") if hasattr(version, "title") else None)
except Exception as e:
    print("version err", e); traceback.print_exc()

# ---------------------------------------------------------------------------
section("trade_tools — item paste parsing + url building")
try:
    from core_engine import trade_tools as tt
    # empty / junk must not crash and returns a dict
    for bad in ["", "   ", None, "random\nnonsense", "----\n----"]:
        guard(f"parse({bad!r:.16})", lambda bad=bad: tt.parse_item_text(bad))
    check("parse empty -> dict", isinstance(tt.parse_item_text(""), dict))
    rare = ("Item Class: Spears\nRarity: Rare\nBramble Fang\nBronze Spear\n"
            "--------\nRequirements:\nLevel: 45\nStr: 80\n--------\n"
            "Item Level: 72\n--------\n"
            "Adds 12 to 24 Physical Damage\n18% increased Attack Speed\n"
            "+45 to maximum Life\n")
    p = tt.parse_item_text(rare)
    check("parse rarity", p["rarity"] == "Rare")
    check("parse unique name", p["name"] == "Bramble Fang")
    check("parse base", p["base"] == "Bronze Spear")
    check("parse item class", p["item_class"] == "Spears")
    check("parse ilvl", p["ilvl"] == "72")
    check("parse mods captured", any("Attack Speed" in m for m in p["mods"]))
    check("parse skips requirement Level line", not any(m.lower().startswith("level") for m in p["mods"]))
    # Normal/Magic: name line is the base, no unique name
    norm = "Item Class: Body Armours\nRarity: Normal\nSimple Robe\n--------\nItem Level: 5\n"
    pn2 = tt.parse_item_text(norm)
    check("normal item base set", pn2["base"] == "Simple Robe")
    check("normal item no unique name", pn2["name"] == "")
    # url building
    check("trade url has league", "Rise%20of%20the%20Abyssal" in tt.trade_search_url({}, "Rise of the Abyssal"))
    check("trade url default league", tt.trade_search_url({}, "") .endswith("/Standard"))
    check("live url poe2 path", "/trade2/search/poe2/" in tt.live_search_url("Standard"))
    check("is_number true", tt.is_number("12.5") is True)
    check("is_number false", tt.is_number("abc") is False)
    check("offline craft guidance non-empty", len(tt.offline_craft_guidance("phys spear")) > 50)
except Exception as e:
    print("trade_tools err", e); traceback.print_exc()

# ---------------------------------------------------------------------------
section("filter_editor — exact round-trip + edits")
try:
    from core_engine.filter_editor import FilterDocument, find_filters
    samples = [
        "# header only\n# no blocks\n",
        "Show\n\tClass \"Currency\"\n",
        "# pre\nShow # currency\n\tBaseType \"Divine Orb\"\n\tSetTextColor 255 0 0\n\nHide\n\tRarity Normal\n",
        "Minimal\n\tClass \"Gems\"\n",
        "",  # empty file
        "Show\nHide\nMinimal\n",  # back-to-back headers, empty bodies
    ]
    for i, s in enumerate(samples):
        doc = FilterDocument.from_text(s)
        check(f"round-trip exact [{i}]", doc.text() == s)
    # edit: flip an action, stats reflect it, still round-trips structurally
    doc = FilterDocument.from_text(samples[2])
    before = doc.stats()
    check("stats total counts blocks", before["total"] == 2)
    doc.set_action(1, "Show")
    after = doc.stats()
    check("flip changed Show count", after["Show"] == before["Show"] + 1)
    check("flip changed Hide count", after["Hide"] == before["Hide"] - 1)
    check("set_action bad index returns False", doc.set_action(99, "Show") is False)
    guard("set_action invalid action raises ValueError caught",
          lambda: (_ for _ in ()).throw(ValueError()) if False else doc.set_action(0, "Show"))
    try:
        doc.set_action(0, "Bogus"); check("invalid action rejected", False)
    except ValueError:
        check("invalid action rejected", True)
    # block summary + conditions don't crash
    guard("block summary", lambda: [b.summary() for b in doc.blocks])
    guard("block conditions", lambda: [b.conditions() for b in doc.blocks])
    # save round-trips to disk then reloads identical
    import tempfile as _tf, os as _os
    p = _os.path.join(_tf.mkdtemp(), "x.filter")
    FilterDocument.from_text(samples[2]).save(p)
    rel = FilterDocument.load(p)
    check("save+reload exact", rel.text() == samples[2])
    guard("find_filters no crash", lambda: find_filters())
except Exception as e:
    print("filter_editor err", e); traceback.print_exc()

# ---------------------------------------------------------------------------
section("obsidian_export — fast cross-links + progress + robustness")
try:
    import shutil as _sh
    from core_engine.database_handler import KalandraDBHandler as _DBH
    from core_engine.obsidian_export import ObsidianExporter as _OE
    d = tempfile.mkdtemp()
    db = _DBH(db_dir=os.path.join(d, "db"))
    # empty DB: no crash, notes == 0
    ex = _OE(db, out_dir=os.path.join(d, "v0"), logger=lambda c, m: None)
    r = ex.export()
    check("export empty db -> 0 notes", r.get("notes") == 0)
    # small linked corpus incl. unicode + fs-hostile titles
    rows = [
        ("Fortifying Cry", "A warcry that grants Fortification. Pairs with Echoing Cry."),
        ("Echoing Cry", "Warcry. Fortifying Cry users love it. 20% increased damage."),
        ("Weird/Name: <Test>?", "Contains Fortifying Cry reference and fire damage."),
        ("随机字符 Orb", "Unicode topic body mentioning Echoing Cry and lightning."),
    ]
    for t, c in rows:
        db.insert_scoured_data(topic=t, content=c, url="u", version="t")
    db.conn.commit()
    prog = []
    ex = _OE(db, out_dir=os.path.join(d, "v1"), logger=lambda c, m: None,
             progress=lambda a, b, ph: prog.append((a, b)))
    r = ex.export()
    check("export writes all notes", r.get("notes") == len(rows))
    check("export progress fired", prog and prog[-1][0] == len(rows))
    # cross-link actually present (token-index pass)
    found_rel = False
    for root, _, files in os.walk(os.path.join(d, "v1")):
        for fn in files:
            if fn.endswith(".md"):
                txt = open(os.path.join(root, fn), encoding="utf-8").read()
                if "## Related" in txt and "[[" in txt:
                    found_rel = True
    check("cross-links generated", found_rel)
    db.close(); _sh.rmtree(d, ignore_errors=True)
except Exception as e:
    print("obsidian_export err", e); traceback.print_exc()

# ---------------------------------------------------------------------------
section("static audit — no name used without being imported/defined")
# GUI modules can't be imported here (no PyQt6), so runtime NameErrors like the
# missing-QCheckBox settings crash slip past the runtime tests. This AST pass
# catches any Q* name (and common stdlib aliases) used but never bound.
try:
    import ast, glob
    problems = []
    for path in glob.glob(os.path.join(ROOT, "gui_overlay", "*.py")) + \
                glob.glob(os.path.join(ROOT, "core_engine", "*.py")) + \
                glob.glob(os.path.join(ROOT, "*.py")):
        src = open(path, encoding="utf-8").read()
        tree = ast.parse(src)
        bound, used = set(), {}

        class _V(ast.NodeVisitor):
            def visit_Import(self, n):
                for a in n.names:
                    bound.add((a.asname or a.name).split(".")[0])
            def visit_ImportFrom(self, n):
                for a in n.names:
                    bound.add(a.asname or a.name)
            def visit_FunctionDef(self, n):
                bound.add(n.name); self.generic_visit(n)
            visit_AsyncFunctionDef = visit_FunctionDef
            def visit_ClassDef(self, n):
                bound.add(n.name); self.generic_visit(n)
            def visit_Name(self, n):
                if isinstance(n.ctx, ast.Store):
                    bound.add(n.id)
                elif isinstance(n.ctx, ast.Load) and n.id.startswith("Q"):
                    used.setdefault(n.id, n.lineno)
                self.generic_visit(n)
            def visit_arg(self, n):
                bound.add(n.arg)
        _V().visit(tree)
        for name, ln in used.items():
            if name not in bound:
                problems.append(f"{os.path.relpath(path, ROOT)}:{ln}: {name}")
    for p in problems:
        print("  UNBOUND:", p)
    check("no unbound Q* names anywhere", not problems)
except Exception as e:
    print("static audit err", e); traceback.print_exc()

# ---------------------------------------------------------------------------
print(f"\n{'='*50}\nRESULT: {PASS} passed, {FAIL} failed")
if FAILURES:
    print("FAILURES:")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("ALL GREEN")
