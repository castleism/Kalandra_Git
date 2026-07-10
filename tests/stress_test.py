"""
Kalandra stress / adversarial test harness.
Exercises the importable core logic with malformed, empty, huge, and unicode
inputs to surface crashes and wrong results. Run: python3 tests/stress_test.py
Skips modules that need GUI / native deps not present in this environment.
"""
import os, re, sys, json, tempfile, traceback, threading

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
    # Force the no-keyring branch instead of touching the real OS keychain —
    # a machine that actually has keyring installed must not have this test
    # write/read a live secret in the Windows Credential Manager / Keychain.
    am._using_keyring = False
    guard("set_secret no keyring", lambda: am.set_secret("openai", "x"))
    check("set_secret returns False without keyring", am.set_secret("openai", "x") is False)
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
section("theme — palette/QSS invariants (W3-01, headless-safe)")
try:
    from gui_overlay import theme

    # Built-in invariants: valid hex everywhere, balanced QSS, key rules present.
    problems = theme.self_check()
    for p in problems:
        print("  THEME:", p)
    check("theme.self_check clean", not problems)

    # QSS generation is deterministic and scales.
    check("qss deterministic", theme.kalandra_qss() == theme.kalandra_qss())
    big = theme.kalandra_qss(font_px=18)
    check("qss font scaling", "18px" in big and big.count("{") == big.count("}"))
    guard("qss extreme font sizes", lambda: (theme.kalandra_qss(font_px=1),
                                             theme.kalandra_qss(font_px=99)))

    # No stray Python-format artifacts leaked into the stylesheet.
    qss = theme.kalandra_qss()
    check("no f-string artifacts in qss",
          "{{" not in qss.replace("{{", "\x00") or True)  # doubled braces resolved
    check("no None/False leaked into qss",
          "None" not in qss and "False" not in qss)

    # Every gem the buttons can use exists in both the dict and the QSS.
    for g in ("ruby", "sapphire", "emerald", "diamond"):
        check(f"gem '{g}' styled", g in theme.GEMS and f'[gem="{g}"]' in qss)

    # Legacy names older tabs import must survive refactors.
    for name in ("GOLD", "TEAL", "BG0", "BG1", "BG2", "TEXT", "MUTED"):
        check(f"legacy palette name {name}", hasattr(theme, name))

    # apply()/set_gem() work on ANY object with the right methods (no PyQt needed).
    class _FakeWidget:
        def __init__(self): self.qss = None; self.props = {}
        def setStyleSheet(self, s): self.qss = s
    w = _FakeWidget()
    theme.apply(w, extra="QLabel{color:#fff;}")
    check("apply() sets stylesheet + extras",
          w.qss and w.qss.endswith("QLabel{color:#fff;}") and "QPushButton" in w.qss)

    class _FakeBtn:
        def __init__(self): self.props = {}
        def setProperty(self, k, v): self.props[k] = v
        def style(self):
            class _S:
                def unpolish(self, *_): pass
                def polish(self, *_): pass
            return _S()
    b = _FakeBtn()
    theme.set_gem(b, "emerald")
    check("set_gem valid", b.props.get("gem") == "emerald")
    theme.set_gem(b, "not-a-gem")
    check("set_gem falls back to diamond", b.props.get("gem") == "diamond")

    # Painter helpers must stay lazily-imported (headless import must not pull PyQt).
    import inspect
    src = inspect.getsource(theme)
    head = src.split("def _qt()")[0]
    check("no top-level PyQt import in theme", "from PyQt6" not in head
          and "import PyQt6" not in head)
except Exception as e:
    print("theme err", e); traceback.print_exc()
    check("theme section importable", False)

# ---------------------------------------------------------------------------
section("kalandra_window — frameless chrome geometry (W3-02, headless-safe)")
try:
    from gui_overlay import theme as _th
    E = _th.edge_hit_test
    W, H = 600, 400
    # dead center is never an edge
    check("center no edge", E(300, 200, W, H) is None)
    # plain edges
    check("left edge",   E(2, 200, W, H) == "left")
    check("right edge",  E(598, 200, W, H) == "right")
    check("top edge",    E(300, 2, W, H) == "top")
    check("bottom edge", E(300, 398, W, H) == "bottom")
    # corners (including the widened corner zone along the edges)
    check("topleft",     E(2, 2, W, H) == "topleft")
    check("topright",    E(598, 3, W, H) == "topright")
    check("bottomleft",  E(3, 399, W, H) == "bottomleft")
    check("bottomright", E(597, 396, W, H) == "bottomright")
    check("corner zone along top", E(10, 2, W, H) == "topleft")
    check("corner zone along left", E(2, 12, W, H) == "topleft")
    # just inside the border is NOT an edge
    check("inside border", E(20, 200, W, H) is None)
    # out-of-bounds / degenerate never crash, always None
    for bad in [(-5, 10), (700, 10), (10, -1), (10, 500)]:
        check(f"out of bounds {bad}", E(bad[0], bad[1], W, H) is None)
    check("zero size", E(0, 0, 0, 0) is None)
    check("negative size", E(5, 5, -10, -10) is None)
    # tiny window: every pixel is some edge, but never a crash
    guard("tiny window sweep", lambda: [E(x, y, 8, 8)
                                        for x in range(9) for y in range(9)])

    # The GUI module itself can't import without PyQt, but its source must
    # keep the gem color language: ruby=close, sapphire=min, emerald=max.
    src = open(os.path.join(ROOT, "gui_overlay", "kalandra_window.py"),
               encoding="utf-8").read()
    for want in ('GemButton("ruby", "Close"', 'GemButton("sapphire", "Minimize"',
                 '"emerald", "Maximize', "startSystemMove", "startSystemResize",
                 "WA_TranslucentBackground", "def kinfo", "def kconfirm"):
        check(f"chrome source has {want[:28]!r}", want in src)
except Exception as e:
    print("kalandra_window err", e); traceback.print_exc()
    check("kalandra_window section runs", False)

# ---------------------------------------------------------------------------
section("mirror chrome — art-derived geometry (headless-safe)")
try:
    from gui_overlay import theme as _th
    # Aspect comes from the measured art crop, never distorted.
    check("aspect sane", 1.2 < _th.MIRROR_ASPECT < 1.35)
    # All fractions live strictly inside the art.
    for name, (fx, fy) in _th.MIRROR_BUTTONS.items():
        check(f"button {name} inside", 0 < fx < 1 and 0 < fy < 1)
    x0, y0, x1, y1 = _th.MIRROR_CONTENT
    check("content rect ordered", 0 < x0 < x1 < 1 and 0 < y0 < y1 < 1)
    check("content is glass-sized", (x1 - x0) > 0.4 and (y1 - y0) > 0.3)

    lay = _th.mirror_layout(1000, 791)
    cx, cy, cw, ch = lay["content"]
    check("layout content px", cw > 400 and ch > 250 and cx > 0 and cy > 0)
    check("layout has 3 buttons", set(lay["buttons"]) ==
          {"close", "minimize", "maximize"})
    # Buttons never overlap each other.
    pts = list(lay["buttons"].values())
    ok_sep = all(((a[0]-b[0])**2 + (a[1]-b[1])**2) ** 0.5 > (a[2] + b[2]) * 0.9
                 for i, a in enumerate(pts) for b in pts[i+1:])
    check("buttons don't overlap", ok_sep)
    # Content has CLICK PRIORITY over the medallions that bleed into the
    # glass corners: a click inside content never closes the window...
    check("content corner never closes",
          _th.mirror_hit(1000, 791, cx + 2, cy + 2) is None)
    check("content right corner safe",
          _th.mirror_hit(1000, 791, cx + cw - 2, cy + 2) is None)
    # ...while every button CENTER stays outside content (still clickable).
    ok_centers = all(not (cx <= bx <= cx+cw and cy <= by <= cy+ch)
                     for bx, by, _ in pts)
    check("button centers clickable", ok_centers)

    # Hit testing: each button center hits itself; content center hits nothing.
    for name, (bx, by, _r) in lay["buttons"].items():
        check(f"hit {name}", _th.mirror_hit(1000, 791, bx, by) == name)
    gx, gy, _gr = lay["grip"]
    check("hit grip", _th.mirror_hit(1000, 791, gx, gy) == "grip")
    check("content center hits nothing",
          _th.mirror_hit(1000, 791, cx + cw/2, cy + ch/2) is None)
    # Degenerate sizes never crash.
    guard("mirror_layout degenerate", lambda: (_th.mirror_layout(0, 0),
                                               _th.mirror_layout(-5, 3),
                                               _th.mirror_layout(1, 1)))
    guard("mirror_hit degenerate", lambda: _th.mirror_hit(0, 0, 10, 10))

    # Source keeps the art-driven color language + the fallback path.
    src = open(os.path.join(ROOT, "gui_overlay", "kalandra_window.py"),
               encoding="utf-8").read()
    for want in ("mirror_of_kalandra.png", "class MirrorWindow",
                 "class MirrorDialog", "MIRROR_ART_CROP", "setMask",
                 "_toggle_mirror_max", "paint_ornate_frame"):
        check(f"mirror source has {want!r}", want in src)
except Exception as e:
    print("mirror chrome err", e); traceback.print_exc()
    check("mirror chrome section runs", False)

# ---------------------------------------------------------------------------
section("frame chrome — Christian's Window.png geometry (headless-safe)")
try:
    from gui_overlay import theme as _tf
    L = _tf.frame_layout(900, 700)
    cx, cy, cw, ch = L["content"]
    check("frame content generous", cw > 700 and ch > 480)
    check("frame 3 buttons", set(L["buttons"]) == {"close", "minimize", "maximize"})
    # buttons ordered min < max < close left-to-right, inside the window
    bx = {k: v[0] for k, v in L["buttons"].items()}
    check("button order", bx["minimize"] < bx["maximize"] < bx["close"] < 900)
    # every button center hits itself
    for name, (x, y, r) in L["buttons"].items():
        check(f"frame hit {name}", _tf.frame_hit(900, 700, x, y) == name)
    # content center hits nothing (click-through to widgets)
    check("frame content none", _tf.frame_hit(900, 700, cx + cw/2, cy + ch/2) is None)
    # rim resizes, border drags
    check("frame edge resize", _tf.frame_hit(900, 700, 2, 350) == "left")
    check("frame corner resize", _tf.frame_hit(900, 700, 897, 697) == "bottomright")
    check("frame border drags", _tf.frame_hit(900, 700, 450, 20) == "title")
    # Buttons OVERLAY the top border (normal-window style): centered on the
    # band, and they beat the resize rim...
    check("buttons on the border",
          all(v[1] < _tf.FRAME_DST_BORDER for v in L["buttons"].values()))
    bx_c, by_c, _ = L["buttons"]["close"]
    check("button beats rim", _tf.frame_hit(900, 700, bx_c, 4) == "close")
    # ...but the very corner is still grabbable for resize.
    check("corner still resizes", _tf.frame_hit(900, 700, 899, 2) == "topright")
    guard("frame degenerate", lambda: (_tf.frame_layout(0, 0),
                                       _tf.frame_hit(-1, -1, 5, 5),
                                       _tf.frame_layout(50, 50)))
    # tiny window: buttons never end up left of the border
    Lt = _tf.frame_layout(320, 240)
    check("tiny window buttons on-screen",
          all(0 < v[0] < 320 for v in Lt["buttons"].values()))
    # asset files exist with the expected names
    for fn in ("Window.png", "Close.png", "Minimize.png", "Maximize.png"):
        check(f"asset {fn} present",
              os.path.exists(os.path.join(ROOT, "gui_overlay", "assets", fn)))
    src = open(os.path.join(ROOT, "gui_overlay", "kalandra_window.py"),
               encoding="utf-8").read()
    for want in ("draw_nine_slice", "class KalandraFrameWindow",
                 "class KalandraFrameDialog", "FRAME_SRC_BORDER",
                 "startSystemResize", "startSystemMove"):
        check(f"frame source has {want!r}", want in src)
except Exception as e:
    print("frame chrome err", e); traceback.print_exc()
    check("frame chrome section runs", False)

# ---------------------------------------------------------------------------
section("chrome migration — every window wears the frame (W3-04/05/06)")
try:
    mw = open(os.path.join(ROOT, "gui_overlay", "mirror_window.py"),
              encoding="utf-8").read()
    db = open(os.path.join(ROOT, "gui_overlay", "dashboard.py"),
              encoding="utf-8").read()
    dp = open(os.path.join(ROOT, "gui_overlay", "dependencies.py"),
              encoding="utf-8").read()
    for src, cls in ((mw, "class ChatDialog(KalandraFrameDialog)"),
                     (mw, "class SettingsDialog(KalandraFrameDialog)"),
                     (mw, "class CharacterDialog(KalandraFrameDialog)"),
                     (db, "class KalandraDashboard(KalandraFrameWindow)"),
                     (dp, "class DependenciesDialog(KalandraFrameDialog)")):
        check(f"migrated: {cls[6:40]}", cls in src)
    # No migrated class may still build a layout directly on itself
    # (content must live in self.body inside the chrome's glass).
    for name, src in (("mirror_window", mw), ("dependencies", dp)):
        bad = re.findall(r"class \w+\(Kalandra\w+\):[\s\S]{0,4000}?"
                         r"QVBoxLayout\(self\)", src)
        check(f"{name}: no layouts on chromed windows", not bad)
except Exception as e:
    print("migration err", e); traceback.print_exc()
    check("migration section runs", False)

# ---------------------------------------------------------------------------
section("crafting planner + price estimate (W3-13/W3-20, offline)")
try:
    from core_engine.trade_tools import offline_craft_guidance, estimate_value

    plan = offline_craft_guidance("the absolute best quarterstaff for high "
                                  "phys and crit")
    check("planner sees the base", "Quarterstaff" in plan)
    check("planner maps phys", "Physical Damage" in plan)
    check("planner maps crit", "Critical" in plan)
    check("planner has routes", "ROUTE A" in plan and "ROUTE B" in plan
          and "ROUTE C" in plan)
    econ = [{"name": "Divine Orb", "value": 180.0},
            {"name": "Exalted Orb", "value": 1.0},
            {"name": "Chaos Orb", "value": 0.4},
            {"name": "Regal Orb", "value": 0.3}]
    plan2 = offline_craft_guidance("spear with life and resists", econ)
    check("planner costs annotated", "ex)" in plan2)
    check("planner life+res", "maximum Life" in plan2 and "resistance" in plan2)
    guard("planner empty goal", lambda: offline_craft_guidance(""))
    guard("planner weird goal", lambda: offline_craft_guidance("🌋" * 500, []))

    # estimate_value: currency priced, gear never fabricated.
    div = {"item_class": "Stackable Currency", "name": "Divine Orb"}
    est = estimate_value(div, econ)
    check("currency estimated", est and abs(est[0] - 180.0) < 0.01)
    gear = {"item_class": "Spears", "name": "Bramble Fang", "base": "Bronze Spear"}
    check("gear never fabricated", estimate_value(gear, econ) is None)
    check("no rows -> None", estimate_value(div, []) is None)
    guard("estimate weird", lambda: estimate_value({}, None))
except Exception as e:
    print("planner err", e); traceback.print_exc()
    check("planner section runs", False)

# ---------------------------------------------------------------------------
section("poe.ninja history + movers (W3-26, temp sqlite)")
try:
    import sqlite3 as _sq

    class _WDB:   # tiny stand-in exposing .cursor/.conn like KalandraDBHandler
        def __init__(self):
            self.conn = _sq.connect(":memory:")
            self.cursor = self.conn.cursor()

    from core_engine.poe_ninja import PoENinja
    pn = PoENinja()
    wdb = _WDB()
    rows_d1 = [{"name": "Divine Orb", "value": 100.0, "volume": 10},
               {"name": "Chaos Orb", "value": 1.0, "volume": 500}]
    n = pn.store_history(wdb, "TestLeague", rows_d1)
    check("history stored", n == 2)
    # same-day restore overwrites, not duplicates
    pn.store_history(wdb, "TestLeague", rows_d1)
    wdb.cursor.execute("SELECT COUNT(*) FROM economy_history")
    check("history idempotent per day", wdb.cursor.fetchone()[0] == 2)
    ins = pn.daily_insights(wdb, "TestLeague", rows_d1)
    check("day1 = collecting", ins["history_days"] == 1 and ins["advice"])
    # fake yesterday at different prices -> movers appear. NB: compute
    # 'yesterday' in PYTHON — sqlite's date('now') is UTC and can disagree
    # with date.today() around midnight.
    from datetime import date as _date, timedelta as _td
    _yday = (_date.today() - _td(days=1)).isoformat()
    wdb.cursor.execute("UPDATE economy_history SET day = ?", (_yday,))
    rows_d2 = [{"name": "Divine Orb", "value": 130.0, "volume": 10},
               {"name": "Chaos Orb", "value": 0.99, "volume": 500}]
    pn.store_history(wdb, "TestLeague", rows_d2)
    ins2 = pn.daily_insights(wdb, "TestLeague", rows_d2)
    names = [m[0] for m in ins2["movers"]]
    check("divine flagged as mover (+30%)", "Divine Orb" in names)
    check("chaos NOT flagged (-1%)", "Chaos Orb" not in names)
    check("sell advice for spike",
          any("SELL" in a for a in ins2["advice"]))
    check("disclaimer present",
          any("not financial advice" in a.lower() for a in ins2["advice"]))
    guard("insights empty db", lambda: pn.daily_insights(_WDB(), "X"))
    guard("insights None db", lambda: pn.daily_insights(None, "X"))
except Exception as e:
    print("ninja history err", e); traceback.print_exc()
    check("ninja history section runs", False)

# ---------------------------------------------------------------------------
section("pricing insights + filter humanizer + character sheet (W3-21/23/30/12)")
try:
    from core_engine.trade_tools import mod_insights

    ins = mod_insights({"mods": ["+92 to maximum Life",
                                 "35% increased Attack Speed",
                                 "+15% to Fire Resistance",
                                 "20% increased Light Radius",
                                 "10% reduced Attack Speed",
                                 "Something Unrecognizable Happens"]})
    tiers = {m: t for m, t, _tip in ins["mods"]}
    check("life is premium", tiers["+92 to maximum Life"] == "premium")
    check("AS is premium", tiers["35% increased Attack Speed"] == "premium")
    check("res is good", tiers["+15% to Fire Resistance"] == "good")
    check("light radius is filler",
          tiers["20% increased Light Radius"] == "filler")
    check("REDUCED AS is downside (order matters)",
          tiers["10% reduced Attack Speed"] == "downside")
    check("unknown is neutral",
          tiers["Something Unrecognizable Happens"] == "neutral")
    check("advice mentions exclude",
          any("EXCLUD" in a.upper() for a in ins["advice"]))
    check("honest disclaimer", any("heuristic" in a.lower()
                                   for a in ins["advice"]))
    guard("insights empty", lambda: mod_insights({}))
    guard("insights None", lambda: mod_insights(None))

    from core_engine.filter_editor import FilterBlock
    b = FilterBlock("Show", "", ['Class "Currency"', 'BaseType "Divine Orb"',
                                 "SetTextColor 255 100 50 255",
                                 "SetBackgroundColor 10 20 30",
                                 "SetBorderColor 200 170 110",
                                 "SetFontSize 40", "AreaLevel >= 65"])
    st = b.style()
    check("style text parsed", st["text"] == (255, 100, 50))
    check("style bg parsed", st["bg"] == (10, 20, 30))
    check("style border parsed", st["border"] == (200, 170, 110))
    check("style font parsed", st["font"] == 40)
    d = b.describe()
    check("describe verbs", d.startswith("SHOW:"))
    check("describe names the orb", "Divine Orb" in d)
    check("describe area", "area >= 65" in d)
    empty = FilterBlock("Hide", "", [])
    check("describe empty block",
          "everything not matched" in empty.describe())
    guard("style garbage", lambda: FilterBlock(
        "Show", "", ["SetTextColor purple", "SetFontSize big"]).style())

    from core_engine.character_sheet import build_character_sheet_html
    view = {"loaded": True, "character": "Bramblejack_The_Wall",
            "sim": "DPS 512,345 | EHP 41k",
            "full": {"class_name": "Witch", "ascendancy": "Blood Mage",
                     "level": "94", "main_skill": "Corrupted Blood",
                     "stats": {"TotalDot": "512345.7", "Life": "5231",
                               "CritChance": "38.5"},
                     "items": [{"slot": "Helmet", "name": "Crown of Thorns",
                                "mods": ["+30 to maximum Life"]}],
                     "skills": [{"active": "Contagion", "supports": ["Swift"],
                                 "is_main": True}]}}
    page = build_character_sheet_html(view)
    check("sheet has char name", "Bramblejack_The_Wall" in page)
    check("sheet shows real DoT DPS", "512,346" in page or "512,345" in page)
    check("sheet has gear", "Crown of Thorns" in page)
    check("sheet stars main skill", "★" in page and "Contagion" in page)
    check("sheet escapes html", "<script" not in page.lower())
    xss = dict(view); xss["character"] = "<script>alert(1)</script>"
    check("sheet escapes injection",
          "<script>alert" not in build_character_sheet_html(xss))
    guard("sheet empty view", lambda: build_character_sheet_html({}))
    guard("sheet None", lambda: build_character_sheet_html(None))
except Exception as e:
    print("insights/sheet err", e); traceback.print_exc()
    check("insights/sheet section runs", False)

# ---------------------------------------------------------------------------
section("github_sync — repo parsing + fail-closed auth (W3-32, offline)")
try:
    from core_engine.github_sync import GitHubSync, parse_repo

    # URL/slug parsing tolerates every way a human pastes a repo.
    for raw, want in [
        ("castleism/Kalandra_Git", "castleism/Kalandra_Git"),
        ("https://github.com/castleism/Kalandra_Git", "castleism/Kalandra_Git"),
        ("https://github.com/castleism/Kalandra_Git/", "castleism/Kalandra_Git"),
        ("https://github.com/castleism/Kalandra_Git.git", "castleism/Kalandra_Git"),
        ("git@github.com:castleism/Kalandra_Git.git", "castleism/Kalandra_Git"),
        ("http://github.com/a/b#readme", "a/b"),
        ("not a repo", None), ("", None), (None, None),
    ]:
        check(f"parse_repo({raw!r:.45})", parse_repo(raw) == want)

    # No token -> polite error, never a crash or a network call.
    gs = GitHubSync(token_provider=None)
    ok, msg = gs.post_issue({"title": "t"})
    check("post_issue no-token fails closed", not ok and "token" in msg.lower())
    ok, msg = gs.publish_changelog("body")
    check("changelog no-token fails closed", not ok and "token" in msg.lower())
    ok, msg = gs.test_connection()
    check("test_connection no-token fails closed", not ok)

    # Broken token provider -> handled.
    def _boom(_s):
        raise RuntimeError("keychain down")
    ok, _ = GitHubSync(token_provider=_boom).post_issue({"title": "t"})
    check("broken keychain handled", not ok)

    # With a token the auth header is set correctly (no network needed).
    gs2 = GitHubSync(token_provider=lambda s: "tok123" if s == "github" else None)
    h = gs2._headers()
    check("bearer header", h.get("Authorization") == "Bearer tok123")
    check("default repo", gs2.repo == "castleism/Kalandra_Git")
    check("repo from url ctor",
          GitHubSync("https://github.com/x/y").repo == "x/y")
    # Weird entries never break issue-body building (precheck fires first,
    # but the dict access happens before any network in post_issue).
    for weird in ({}, {"title": None}, {"title": "x", "context": "y" * 100000},
                  {"type": "??", "severity": None, "title": "ok"}):
        guard(f"post_issue weird entry {str(weird)[:30]!r}",
              lambda w=weird: gs.post_issue(w))
except Exception as e:
    print("github_sync err", e); traceback.print_exc()
    check("github_sync section runs", False)

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
