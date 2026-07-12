"""
TESTS/SCRAPER_TAG_CHECKS.PY
Checks for the per-page-kind tag extraction + page-kind classifier in
core_engine/scraper.py (W4-30 P1.5), and for the knowledge_ledger.kind column
they feed. The HTML fixtures are modeled on the REAL poe2db markup, verified in
a live browser on 2026-07-12:

  * unique item page   — https://poe2db.tw/us/Astramentis
                         (newItemPopup UniquePopup; <a class="KeywordPopups"
                          data-keyword="..."> chips inside implicit/explicit
                          mods; popup printed twice)
  * keystone passive   — https://poe2db.tw/us/Avatar_of_Fire
                         (newItemPopup keystonePopup; plain Stats text; the
                          KeywordPopups anchors live in the page's keyword
                          card; an embedded related-gem GemPopup must NOT
                          contribute tags)
  * notable passive    — https://poe2db.tw/us/Crystalline_Resistance
                         (newItemPopup notablePopup; data-keyword anchors,
                          incl. camel-case ids like MaximumResistances)
  * mod-table page     — https://poe2db.tw/us/Amulets
                         (normalPopup FIRST + .mod-title rows whose tag chips
                          are <span class="badge" data-tag="...">)
  * base item page     — https://poe2db.tw/us/Stellar_Amulet
                         (newItemPopup NormalPopup — note the case difference
                          from the mod-table page's "normalPopup")
  * gem pages          — <a class="GemTags"> chips, unchanged behavior.

Run:  python tests/scraper_tag_checks.py     Exit code 0 = all green.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bs4 import BeautifulSoup  # noqa: E402

from core_engine.database_handler import KalandraDBHandler  # noqa: E402
from core_engine.scraper import KalandraScraper  # noqa: E402
from core_engine.tag_graph import KalandraTagGraph  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"  XX  {name}")


def soup(html):
    return BeautifulSoup(html, "html.parser")


# --------------------------------------------------------------------------
# Fixtures — shaped exactly like the live poe2db markup (see module docstring).
# --------------------------------------------------------------------------

UNIQUE_PAGE = """
<html><body>
<div class="d-flex flex-wrap">
 <div class="newItemPopup UniquePopup item-popup--poe2 ">
  <div class="itemHeader doubleLine">
   <div class="itemName"><span class="lc">Astramentis</span></div>
   <div class="itemName typeLine"><span class="lc">Stellar Amulet</span></div>
  </div>
  <div class="content"><div class="Stats">
   <div class="implicitMod">+(10-16) to all
     <a class="KeywordPopups" data-keyword="Attributes" href="Attributes">Attributes</a></div>
   <div class="explicitMod">Reduced
     <a class="KeywordPopups" data-keyword="Physical" href="Physical_Damage">Physical</a>
     <a class="KeywordPopups" data-keyword="Attack" href="Attacks">Attack</a> Damage taken</div>
  </div></div>
 </div>
 <div class="newItemPopup UniquePopup item-popup--poe2 ">
  <div class="content"><div class="Stats">
   <div class="implicitMod">+(10-16) to all
     <a class="KeywordPopups" data-keyword="Attributes" href="Attributes">Attributes</a></div>
  </div></div>
 </div>
</div>
</body></html>
"""

KEYSTONE_PAGE = """
<html><body>
<div class="newItemPopup keystonePopup item-popup--poe2 ">
 <div class="itemHeader singleLine">
  <div class="itemName typeLine"><span class="lc">Avatar of Fire</span></div>
 </div>
 <div class="content">
  <div class="Stats"><div class="implicitMod">75% of Damage Converted to Fire Damage<br>Deal no Non-Fire Damage</div></div>
  <div class="FlavourText">"In my dreams I see a great warrior."</div>
 </div>
</div>
<div class="newItemPopup GemPopup item-popup--poe2 ">
 <div class="content"><div class="Stats">
  <a class="GemTags" href="Fire">Fire</a>
  <a class="KeywordPopups" data-keyword="Projectile" href="Projectiles">Projectile</a>
 </div></div>
</div>
<div class="newItemPopup keywordPopups"><div class="card mb-2">
 <h5 class="card-header"><a href="Avatar_of_Fire">Avatar of Fire</a></h5>
 <div class="card-body"><div class="keyword-body">75% of Damage
  <a data-keyword="Conversion" href="Damage_Conversion" class="KeywordPopups">Converted</a> to
  <a data-keyword="Fire" href="Fire_Damage" class="KeywordPopups">Fire</a> Damage</div></div>
</div></div>
</body></html>
"""

NOTABLE_PAGE = """
<html><body>
<div class="newItemPopup notablePopup item-popup--poe2">
 <div class="itemName typeLine"><span class="lc">Crystalline Resistance</span></div>
 <div class="content"><div class="Stats"><div class="implicitMod">
  <a class="KeywordPopups" data-keyword="DistilledEmotion" href="Liquid_Emotions">Liquid Emotions</a>
  <a class="KeywordPopups" data-keyword="MaximumResistances" href="Maximum">Maximum Elemental Resistances</a>
 </div></div></div>
</div>
</body></html>
"""

MOD_TABLE_PAGE = """
<html><body>
<div class="newItemPopup normalPopup item-popup--poe2"><div class="content">
 <div class="Stats"><div class="implicitMod">Amulet</div></div>
</div></div>
<div class="tab-content">
 <div class="mod-title explicitMod" data-gengroup="1MaximumManaIncreasePercent">
  <span>#% increased maximum Mana
   <span><span class="badge bg-primary craftingmana" data-tag="mana">Mana</span></span></span>
 </div>
 <div class="mod-title explicitMod" data-gengroup="1MaximumLife">
  <span>+# to maximum Life
   <span><span class="badge bg-primary craftinglife" data-tag="life">Life</span></span></span>
 </div>
 <div class="mod-title explicitMod" data-gengroup="1FireRes">
  <span>+#% to Fire Resistance
   <span><span class="badge bg-primary craftingfire" data-tag="fire">Fire</span></span>
   <span><span class="badge bg-primary craftingres" data-tag="resistance"></span></span></span>
 </div>
</div>
</body></html>
"""

BASE_ITEM_PAGE = """
<html><body>
<div class="newItemPopup NormalPopup item-popup--poe2">
 <div class="itemName typeLine"><span class="lc">Stellar Amulet</span></div>
 <div class="content"><div class="Stats"><div class="implicitMod">+(10-16) to all
  <a class="KeywordPopups" data-keyword="Attributes" href="Attributes">Attributes</a></div>
 </div></div>
</div>
</body></html>
"""

SKILL_GEM_PAGE = """
<html><body>
<div class="newItemPopup GemPopup item-popup--poe2">
 <div class="itemName typeLine"><span class="lc">Lightning Arrow</span></div>
 <div class="content"><div class="Stats">
  <div class="TagLine">
   <a class="GemTags" href="Attack">Attack</a>, <a class="GemTags" href="AoE">AoE</a>,
   <a class="GemTags" href="Projectile">Projectile</a>, <a class="GemTags" href="Lightning">Lightning</a>
  </div>
  <div class="TagLine">
   <a class="GemTags" href="Attack">Attack</a>, <a class="GemTags" href="AoE">AoE</a>
  </div>
 </div></div>
</div>
</body></html>
"""

SUPPORT_GEM_PAGE = SKILL_GEM_PAGE.replace("Lightning Arrow", "Corrupting Cry") \
    .replace('<a class="GemTags" href="Attack">Attack</a>, <a class="GemTags" href="AoE">AoE</a>,',
             '<a class="GemTags" href="Support">Support</a>, <a class="GemTags" href="Warcry">Warcry</a>,')

UNTAGGED_PAGE = """
<html><body><h1>Quest Rewards</h1><p>Plain page, no popups, no chips.</p></body></html>
"""


def main():
    S = KalandraScraper.__new__(KalandraScraper)  # no DB needed for parsing bits
    S.host = "poe2db.tw"  # _parse -> _is_followable reads it

    # --- page-kind classification ---------------------------------------------
    check("unique page classified", KalandraScraper._page_kind(soup(UNIQUE_PAGE)) == "unique")
    check("keystone page classified as passive",
          KalandraScraper._page_kind(soup(KEYSTONE_PAGE)) == "passive")
    check("notable page classified as passive",
          KalandraScraper._page_kind(soup(NOTABLE_PAGE)) == "passive")
    check("mod-table page classified (before base-item fallback)",
          KalandraScraper._page_kind(soup(MOD_TABLE_PAGE)) == "mod")
    check("base item page classified", KalandraScraper._page_kind(soup(BASE_ITEM_PAGE)) == "item")
    check("gem page classified", KalandraScraper._page_kind(soup(SKILL_GEM_PAGE)) == "gem")
    check("unknown page -> ''", KalandraScraper._page_kind(soup(UNTAGGED_PAGE)) == "")

    # --- per-kind tag extraction ----------------------------------------------
    check("unique tags from KeywordPopups (deduped, popup printed twice)",
          KalandraScraper._extract_tags(soup(UNIQUE_PAGE), "unique")
          == "Attributes, Physical, Attack")
    kt = KalandraScraper._extract_tags(soup(KEYSTONE_PAGE), "passive")
    check("keystone tags from keyword card", "Conversion" in kt and "Fire" in kt)
    check("embedded GemPopup does NOT bleed into passive tags",
          "Projectile" not in kt)
    nt = KalandraScraper._extract_tags(soup(NOTABLE_PAGE), "passive")
    check("camel-case data-keyword split to words",
          "Distilled Emotion" in nt and "Maximum Resistances" in nt)
    mt = KalandraScraper._extract_tags(soup(MOD_TABLE_PAGE), "mod")
    check("mod tags from badge[data-tag] text", "Mana" in mt and "Life" in mt and "Fire" in mt)
    check("empty badge text falls back to data-tag", "Resistance" in mt)
    check("base item tags via KeywordPopups",
          KalandraScraper._extract_tags(soup(BASE_ITEM_PAGE), "item") == "Attributes")
    check("gem tags unchanged (GemTags, deduped)",
          KalandraScraper._extract_tags(soup(SKILL_GEM_PAGE), "gem")
          == "Attack, AoE, Projectile, Lightning")
    check("untagged page -> '' (never fabricate)",
          KalandraScraper._extract_tags(soup(UNTAGGED_PAGE)) == "")
    check("kind=None auto-classifies",
          KalandraScraper._extract_tags(soup(UNIQUE_PAGE))
          == "Attributes, Physical, Attack")

    # --- _parse end-to-end: kind refinement for gems ---------------------------
    t, x, v, links, tags, kind = S._parse(SKILL_GEM_PAGE, "https://poe2db.tw/us/Lightning_Arrow")
    check("_parse returns skill_gem kind", kind == "skill_gem")
    check("_parse returns gem tags", tags == "Attack, AoE, Projectile, Lightning")
    t, x, v, links, tags, kind = S._parse(SUPPORT_GEM_PAGE, "https://poe2db.tw/us/Corrupting_Cry")
    check("_parse refines Support-tagged gem to support_gem", kind == "support_gem")
    t, x, v, links, tags, kind = S._parse(UNIQUE_PAGE, "https://poe2db.tw/us/Astramentis")
    check("_parse returns unique kind + tags",
          kind == "unique" and tags == "Attributes, Physical, Attack")
    t, x, v, links, tags, kind = S._parse(UNTAGGED_PAGE, "https://poe2db.tw/us/Quest")
    check("_parse unknown page -> kind '' and no tags", kind == "" and tags == "")

    # --- DB: kind column + migration -------------------------------------------
    d = tempfile.mkdtemp(prefix="kindcheck_")
    import sqlite3
    old = sqlite3.connect(os.path.join(d, "old.db"))
    old.execute("""CREATE TABLE knowledge_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT, topic_tag TEXT NOT NULL,
        content_payload TEXT NOT NULL, source_url TEXT NOT NULL,
        scraped_at TEXT NOT NULL, game_version_tag TEXT DEFAULT 'Patch 0.5.4',
        tags TEXT DEFAULT '')""")
    old.execute("INSERT INTO knowledge_ledger (topic_tag, content_payload, "
                "source_url, scraped_at, tags) VALUES ('Old Row','x','u','t','Fire')")
    old.commit()
    old.close()
    db = KalandraDBHandler(db_dir=d, db_name="old.db")
    cols = [r[1] for r in db.cursor.execute(
        "PRAGMA table_info(knowledge_ledger)").fetchall()]
    check("migration adds kind column to pre-existing DB", "kind" in cols)
    db.cursor.execute("SELECT kind FROM knowledge_ledger WHERE topic_tag='Old Row'")
    check("migrated rows default to kind ''", db.cursor.fetchone()[0] == "")

    rid = db.insert_scoured_data(topic="Astramentis", content="c",
                                 url="https://poe2db.tw/us/Astramentis",
                                 tags="Attributes, Physical, Attack", kind="unique")
    db.cursor.execute("SELECT kind FROM knowledge_ledger WHERE id=?", (rid,))
    check("insert stores kind", db.cursor.fetchone()[0] == "unique")
    db.update_scoured_data(topic="Astramentis", content="c2",
                           url="https://poe2db.tw/us/Astramentis",
                           tags="Attributes, Physical, Attack", kind="unique")
    db.cursor.execute("SELECT kind, content_payload FROM knowledge_ledger WHERE id=?", (rid,))
    k, c = db.cursor.fetchone()
    check("update keeps kind + refreshes content", k == "unique" and c == "c2")
    check("insert without kind still works (back-compat)",
          db.insert_scoured_data(topic="Legacy", content="c", url="u2") > 0)

    # --- tag_graph honors the stored kind ---------------------------------------
    db.insert_scoured_data(topic="Widowhail", content="bow",
                           url="https://poe2db.tw/us/Widowhail",
                           tags="Attack, Physical", kind="unique")
    db.insert_scoured_data(topic="Amulets", content="mods",
                           url="https://poe2db.tw/us/Amulets",
                           tags="Physical, Life, Mana", kind="mod")
    db.insert_scoured_data(topic="Crystalline Resistance", content="node",
                           url="https://poe2db.tw/us/Crystalline_Resistance",
                           tags="Physical, Maximum Resistances", kind="passive")
    db.insert_scoured_data(topic="Old Sword", content="legacy row, no kind",
                           url="https://poe2db.tw/us/Old_Sword_Support",
                           tags="Physical, Support")
    tg = KalandraTagGraph(db)
    assets = tg.assets_with_tags(["Physical", "Attack"], exclude="Astramentis")
    by_title = {a["title"]: a for a in assets}
    check("stored kind wins: unique", by_title.get("Widowhail", {}).get("kind") == "unique")
    check("stored kind wins: mod", by_title.get("Amulets", {}).get("kind") == "mod")
    check("stored kind wins: passive",
          by_title.get("Crystalline Resistance", {}).get("kind") == "passive")
    check("legacy row falls back to inference",
          by_title.get("Old Sword", {}).get("kind") == "support_gem")
    src = tg.scaling_sources("Astramentis")
    check("scaling_sources groups real kinds",
          "unique" in src["groups"] and "passive" in src["groups"])
    block = tg.context_block("Astramentis")
    check("context block renders Uniques + Passives + Item mods groups",
          "Uniques:" in block and "Passives:" in block and "Item mods:" in block)

    db.close()
    print(f"\nscraper_tag: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
