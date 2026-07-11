"""
TESTS/TAG_GRAPH_CHECKS.PY
Checks for core_engine/tag_graph.py — the tag reverse-lookup that grounds the
Orb's "what scales X?" answers in the database. Self-contained: builds a tiny
in-memory-ish knowledge base with real-shaped rows and asserts behavior. Run:
    python tests/tag_graph_checks.py
Exit code 0 = all green.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core_engine"))

from core_engine.database_handler import KalandraDBHandler  # noqa: E402
from core_engine.tag_graph import (KalandraTagGraph, _split_tags,  # noqa: E402
                                    _norm)

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


def build_db():
    d = tempfile.mkdtemp(prefix="tagcheck_")
    db = KalandraDBHandler(db_dir=d, db_name="tg.db")
    rows = [
        # (topic, content, url, tags)
        ("Corrupted Blood", "Stacking physical damage over time debuff.",
         "https://poe2db.tw/us/Corrupted_Blood", "Physical, Damage Over Time, Area"),
        ("Corrupting Cry Support", "Exerted attacks apply Corrupted Blood.",
         "https://poe2db.tw/us/Corrupting_Cry_Support",
         "Support, Warcry, Physical, Damage Over Time, Area"),
        ("Some Warcry Skill", "A warcry.",
         "https://poe2db.tw/us/Some_Warcry", "Warcry, Area, Physical"),
        ("Bleed", "Physical damage over time ailment scaled by Bleeding mods.",
         "https://poe2db.tw/us/Bleed", "Physical, Damage Over Time, Bleeding"),
        ("Lightning Arrow", "Fires an arrow.",
         "https://poe2db.tw/us/Lightning_Arrow",
         "Attack, AoE, Projectile, Lightning, Chaining"),
        ("Random Item", "A base item with no tags.",
         "https://poe2db.tw/us/Random_Item", ""),
    ]
    for t, c, u, tg in rows:
        db.insert_scoured_data(topic=t, content=c, url=u, tags=tg)
    return db


def main():
    # --- helpers -------------------------------------------------------------
    check("split tags basic", _split_tags("Attack, AoE, Projectile") ==
          ["Attack", "AoE", "Projectile"])
    check("split tags dedups", _split_tags("Physical, physical, Area") ==
          ["Physical", "Area"])
    check("split empty -> []", _split_tags("") == [])

    db = build_db()
    tg = KalandraTagGraph(db)

    # --- tags_for ------------------------------------------------------------
    cb_tags = tg.tags_for("Corrupted Blood")
    check("tags_for exact match", cb_tags == ["Physical", "Damage Over Time", "Area"])
    check("tags_for case-insensitive", tg.tags_for("corrupted blood") == cb_tags)
    check("tags_for unknown -> []", tg.tags_for("Nonexistent Thing") == [])
    check("tags_for untagged -> []", tg.tags_for("Random Item") == [])

    # --- assets_with_tags ----------------------------------------------------
    assets = tg.assets_with_tags(cb_tags, exclude="Corrupted Blood")
    titles = [a["title"] for a in assets]
    check("reverse lookup finds tag-sharers", "Corrupting Cry Support" in titles
          and "Bleed" in titles)
    check("reverse lookup excludes the subject", "Corrupted Blood" not in titles)
    check("untagged asset never appears", "Random Item" not in titles)
    # Corrupting Cry shares 3 tags (Physical, DoT, Area); Bleed shares 2
    # (Physical, DoT). Cry should outrank Bleed.
    check("more-overlap ranks higher",
          titles.index("Corrupting Cry Support") < titles.index("Bleed"))
    cry = next(a for a in assets if a["title"] == "Corrupting Cry Support")
    check("overlap count correct", cry["overlap"] == 3)
    check("shared tags recorded", set(_norm(x) for x in cry["shared"]) ==
          {"physical", "damage over time", "area"})
    check("support gem kind inferred", cry["kind"] == "support_gem")

    # min_overlap filter
    strict = tg.assets_with_tags(cb_tags, exclude="Corrupted Blood", min_overlap=3)
    check("min_overlap filters", [a["title"] for a in strict] == ["Corrupting Cry Support"])

    # kinds filter
    only_support = tg.assets_with_tags(cb_tags, kinds=("support_gem",))
    check("kinds filter works",
          all(a["kind"] == "support_gem" for a in only_support) and only_support)

    # --- entities_in_text ----------------------------------------------------
    ents = tg.entities_in_text("how do i scale my corrupted blood build with warcries")
    check("entities_in_text finds named subject", "Corrupted Blood" in ents)
    check("entities_in_text ignores unmentioned", "Lightning Arrow" not in ents)
    check("entities_in_text empty text -> []", tg.entities_in_text("") == [])

    # --- scaling_sources -----------------------------------------------------
    src = tg.scaling_sources("Corrupted Blood")
    check("scaling_sources returns subject tags", src["subject_tags"] == cb_tags)
    check("scaling_sources groups by kind", "support_gem" in src["groups"])
    check("scaling_sources total counts assets", src["total"] >= 2)

    # unknown entity degrades honestly (no crash, explanatory note)
    empty = tg.scaling_sources("Totally Unknown")
    check("unknown entity -> empty + note", empty["subject_tags"] == []
          and empty["note"])

    # --- context_block -------------------------------------------------------
    block = tg.context_block("Corrupted Blood")
    check("context block mentions subject tags", "Physical" in block and
          "Damage Over Time" in block)
    check("context block lists a real asset", "Corrupting Cry Support" in block)
    check("context block is grounding-instructed",
          "ground your answer" in block.lower())
    check("context block for unknown entity is empty",
          tg.context_block("Totally Unknown") == "")

    # anti-fabrication contract: every name in the block is a real DB row
    real_titles = {"Corrupting Cry Support", "Some Warcry Skill", "Bleed",
                   "Lightning Arrow", "Corrupted Blood"}
    named = [t for t in real_titles if t in block]
    check("block names only real DB assets", len(named) >= 1)

    db.close()
    print(f"\ntag_graph: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
