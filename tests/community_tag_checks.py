"""
TESTS/COMMUNITY_TAG_CHECKS.PY
Checks for core_engine/community_tags.py (Scaling Advisor P2.5 — player-
reported tags & interactions) and its merge into the tag graph. Run:
    python tests/community_tag_checks.py
Exit code 0 = all green.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core_engine.community_tags import CommunityTags  # noqa: E402
from core_engine.database_handler import KalandraDBHandler  # noqa: E402
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


def fresh(path=None):
    d = tempfile.mkdtemp(prefix="ctcheck_")
    return CommunityTags(path=path or os.path.join(d, "ct.json")), d


def main():
    ct, d = fresh()

    # --- suggestions + dedup-as-vote -------------------------------------------
    e = ct.suggest_tag("Widowhail", "Bow", note="it's a bow")
    check("suggest_tag returns entry", e and e["kind"] == "tag" and e["votes"] == 1)
    check("source is community, unverified by default",
          e["source"] == "community" and e["verified"] is False)
    e2 = ct.suggest_tag("widowhail", "bow")   # same, different case
    check("re-suggesting counts as a vote, not a duplicate",
          e2["id"] == e["id"] and e2["votes"] == 2 and len(ct.all()) == 1)
    check("empty proposal rejected", ct.suggest_tag("", "Bow") is None
          and ct.suggest_tag("X", "") is None)

    r = ct.suggest_relation("The Peacemaker's Draught", "applies", "Corrupted Blood")
    check("suggest_relation returns entry", r and r["kind"] == "relation")
    check("bad relation rejected",
          ct.suggest_relation("X", "causes", "Y") is None)
    r2 = ct.suggest_relation("the peacemaker's draught", "APPLIES", "corrupted blood")
    check("relation dedup-as-vote", r2["id"] == r["id"] and r2["votes"] == 2)

    # --- queries -----------------------------------------------------------------
    tags = ct.tags_for("Widowhail")
    check("tags_for finds proposal", tags and tags[0]["tag"] == "Bow"
          and tags[0]["votes"] == 2)
    check("tags_for unknown -> []", ct.tags_for("Nothing") == [])
    apps = ct.appliers_of("Corrupted Blood")
    check("appliers_of finds the applier", apps == ["The Peacemaker's Draught"])
    check("appliers_of unknown -> []", ct.appliers_of("Frostbite") == [])
    rels = ct.relations_for("The Peacemaker's Draught")
    check("relations_for finds relation",
          rels and rels[0]["relation"] == "applies"
          and rels[0]["target"] == "Corrupted Blood")

    # --- curation: vote / verify / delete ----------------------------------------
    check("vote bumps count", ct.vote(e["id"]) == 3)
    check("vote unknown -> None", ct.vote("nope") is None)
    check("verify promotes", ct.verify(e["id"]) and ct.tags_for("Widowhail")[0]["verified"])
    check("delete removes", ct.delete(r["id"]) and ct.appliers_of("Corrupted Blood") == [])
    check("delete unknown -> False", ct.delete("nope") is False)

    # --- persistence ---------------------------------------------------------------
    ct2 = CommunityTags(path=ct.path)
    check("reload keeps entries + votes + verified",
          ct2.tags_for("Widowhail") == ct.tags_for("Widowhail"))

    # --- tag_graph merge -------------------------------------------------------------
    dbd = tempfile.mkdtemp(prefix="ctdb_")
    db = KalandraDBHandler(db_dir=dbd, db_name="ct.db")
    rows = [
        ("Corrupted Blood", "phys dot", "https://poe2db.tw/us/Corrupted_Blood",
         "Physical, Damage Over Time, Area", ""),
        ("Bleed", "phys dot ailment", "https://poe2db.tw/us/Bleed",
         "Physical, Damage Over Time, Bleeding", ""),
        ("Sharpened Arrowheads", "bow node",
         "https://poe2db.tw/us/Sharpened_Arrowheads", "Bow, Physical", "passive"),
        ("Widowhail", "a unique bow", "https://poe2db.tw/us/Widowhail", "", "unique"),
    ]
    for t, c, u, tg, k in rows:
        db.insert_scoured_data(topic=t, content=c, url=u, tags=tg, kind=k)

    cte, _ = fresh()
    tg = KalandraTagGraph(db, community=cte)

    # With an EMPTY community overlay nothing changes.
    src = tg.scaling_sources("Corrupted Blood")
    check("empty overlay: no community tags in result",
          src["community_tags"] == [] and src["appliers"] == [])
    check("empty overlay: block renders without community lines",
          "player-reported" not in tg.context_block("Corrupted Blood"))

    # Widowhail is scraped but UNTAGGED — a community tag makes it findable.
    cte.suggest_tag("Widowhail", "Bow")
    src = tg.scaling_sources("Widowhail")
    check("community tag reported separately, not as subject tag",
          src["subject_tags"] == [] and
          [c["tag"] for c in src["community_tags"]] == ["Bow"])
    check("community tag widens the reverse lookup",
          any(a["title"] == "Sharpened Arrowheads"
              for g in src["groups"].values() for a in g))
    blk = tg.context_block("Widowhail")
    check("block renders for community-only subject", "Widowhail" in blk)
    check("unverified marked as hint, never fact",
          "UNVERIFIED" in blk and "never as fact" in blk)

    # Promotion: verified tags get their own, stronger label.
    wid = cte.tags_for("Widowhail")[0]["id"]
    cte.verify(wid)
    blk = tg.context_block("Widowhail")
    check("verified community tag labeled as maintainer-verified",
          "VERIFIED by the" in blk and "UNVERIFIED" not in blk)

    # Appliers: player-reported "X applies Y" surfaces on Y's block.
    cte.suggest_relation("The Peacemaker's Draught", "applies", "Corrupted Blood")
    blk = tg.context_block("Corrupted Blood")
    check("appliers line rendered",
          "Applied by (player-reported): The Peacemaker's Draught" in blk)

    # A community tag that DUPLICATES a scraped tag is filtered out.
    cte.suggest_tag("Corrupted Blood", "Physical")
    src = tg.scaling_sources("Corrupted Blood")
    check("community duplicate of scraped tag filtered",
          all(c["tag"].lower() != "physical" for c in src["community_tags"]))

    # community=False disables the overlay entirely.
    tg_off = KalandraTagGraph(db, community=False)
    check("community=False disables overlay",
          tg_off.community_tags_for("Widowhail") == []
          and tg_off.scaling_sources("Widowhail")["community_tags"] == [])

    db.close()
    print(f"\ncommunity_tags: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
