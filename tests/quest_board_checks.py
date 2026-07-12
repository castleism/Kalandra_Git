"""
TESTS/QUEST_BOARD_CHECKS.PY
Checks for core_engine/quest_board.py (Community Quest Board P1 — the local
board). Covers the spec's contract: gap→quest generation, the lifecycle state
machine, verification thresholds vs maintainer sign-off, the structural
can't-close-without-verify rule, gap-must-be-gone closing, reopen-on-regap,
and the verified write-back into the community tag layer. Run:
    python tests/quest_board_checks.py
Exit code 0 = all green.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core_engine.community_tags import CommunityTags  # noqa: E402
from core_engine.database_handler import KalandraDBHandler  # noqa: E402
from core_engine.quest_board import QuestBoard  # noqa: E402

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


def fresh_board(**kw):
    d = tempfile.mkdtemp(prefix="qbcheck_")
    return QuestBoard(path=os.path.join(d, "q.json"), **kw)


def fresh_db():
    d = tempfile.mkdtemp(prefix="qbdb_")
    return KalandraDBHandler(db_dir=d, db_name="qb.db")


def main():
    # --- posting + dedup ---------------------------------------------------------
    qb = fresh_board(maintainers=["castleism"])
    q = qb.post("tag", "Widowhail")
    check("post creates an open quest", q and q["status"] == "open"
          and q["type"] == "tag")
    check("default title/criteria filled",
          q["title"] == "Tag Widowhail" and "poe2db" in q["criteria"])
    q2 = qb.post("tag", "widowhail")
    check("re-posting a live quest dedups", q2["id"] == q["id"]
          and len(qb.board()) == 1)
    check("bad type rejected", qb.post("nonsense", "X") is None)
    check("empty subject rejected", qb.post("tag", " ") is None)

    # --- claims (soft, non-exclusive, expiring) -----------------------------------
    check("claim works", qb.claim(q["id"], "exile1")
          and qb.get(q["id"])["status"] == "claimed")
    check("second claim allowed (non-exclusive)", qb.claim(q["id"], "exile2"))
    qb_ttl = fresh_board(claim_ttl_hours=0)   # everything expires immediately
    qt = qb_ttl.post("tag", "X")
    qb_ttl.claim(qt["id"], "ghost")
    check("claims expire by TTL",
          qb_ttl._active_claims(qb_ttl._get(qt["id"])) == [])

    # --- submissions + threshold verification --------------------------------------
    s = qb.submit(q["id"], "exile1", "poe2db link", "Bow, Physical")
    check("submit moves to submitted", s and s["status"] == "submitted")
    s = qb.submit(q["id"], "exile1", "again", "Bow, Physical")
    check("same player twice does NOT verify (needs independent)",
          s["status"] == "submitted")
    s = qb.submit(q["id"], "exile2", "in-game", "bow ,  physical")
    check("2nd independent agreeing proposal verifies (normalized match)",
          s["status"] == "verified")
    check("resolution recorded", s["resolution"].lower().startswith("bow"))
    check("agreeing contributors credited",
          set(s["contributor_credits"]) == {"exile1", "exile2"})
    check("credits query counts", qb.credits("exile1") == 1)

    # Disagreeing proposals never verify.
    qd = qb.post("tag", "Astramentis")
    qb.submit(qd["id"], "a", "x", "Attributes")
    r = qb.submit(qd["id"], "b", "y", "Fire")
    check("disagreeing proposals stay submitted", r["status"] == "submitted")

    # --- maintainer sign-off ----------------------------------------------------------
    check("non-maintainer sign-off refused", qb.signoff(qd["id"], "rando") is False)
    check("maintainer sign-off verifies",
          qb.signoff(qd["id"], "castleism", resolution="Attributes")
          and qb.get(qd["id"])["status"] == "verified")

    # --- can't close without verify (structural rule) ---------------------------------
    qn = qb.post("verify", "Patch 0.5.4 changed Temple mods")
    check("close refused while open", qb.close(qn["id"]) is False)
    qb.submit(qn["id"], "solo", "screenshot", "confirmed")
    check("close refused while submitted (unverified)", qb.close(qn["id"]) is False)
    qb.submit(qn["id"], "other", "video", "confirmed")
    check("close allowed once verified", qb.close(qn["id"]) is True
          and qb.get(qn["id"])["status"] == "closed")

    # --- generation from DB gaps --------------------------------------------------------
    db = fresh_db()
    db.insert_scoured_data(topic="Tagged Gem", content="c",
                           url="https://poe2db.tw/us/Tagged_Gem",
                           tags="Attack", kind="skill_gem")
    db.insert_scoured_data(topic="Mystery Unique", content="c",
                           url="https://poe2db.tw/us/Mystery_Unique",
                           tags="", kind="unique")
    db.insert_scoured_data(topic="Mystery Node", content="c",
                           url="https://poe2db.tw/us/Mystery_Node", tags="")
    qg = fresh_board()
    res = qg.generate_from_db(db)
    subs = {q["subject"] for q in res["created"]}
    check("untagged rows become TagQuests",
          subs == {"Mystery Unique", "Mystery Node"})
    check("tagged rows do NOT spawn quests", "Tagged Gem" not in subs)
    check("auto quests marked source=auto",
          all(q["source"] == "auto" for q in res["created"]))
    check("subject_url captured",
          all(q["subject_url"].startswith("https://poe2db.tw")
              for q in res["created"]))
    res2 = qg.generate_from_db(db)
    check("regeneration doesn't duplicate live quests", res2["created"] == [])

    # --- gap must be gone to close; reopen on regap --------------------------------------
    mq = next(q for q in qg.board(qtype="tag")
              if q["subject"] == "Mystery Unique")
    qg.submit(mq["id"], "p1", "e", "Bow")
    qg.submit(mq["id"], "p2", "e", "Bow")
    check("auto quest verified by agreement",
          qg.get(mq["id"])["status"] == "verified")
    check("close refused while the DB gap persists",
          qg.close(mq["id"], db_handler=db) is False)
    db.update_scoured_data(topic="Mystery Unique", content="c",
                           url="https://poe2db.tw/us/Mystery_Unique",
                           tags="Bow, Physical", kind="unique")
    check("close allowed once the entity is tagged",
          qg.close(mq["id"], db_handler=db) is True)
    # A later scrape wipes the tags -> the gap detector re-opens the quest.
    db.update_scoured_data(topic="Mystery Unique", content="c",
                           url="https://poe2db.tw/us/Mystery_Unique",
                           tags="", kind="unique")
    reopened = qg.recheck_gaps(db)
    check("closed quest reopens when its gap returns",
          [r["subject"] for r in reopened] == ["Mystery Unique"]
          and qg.get(mq["id"])["status"] == "reopened")

    # --- verified write-back into the community tag layer --------------------------------
    ctd = tempfile.mkdtemp(prefix="qbct_")
    ct = CommunityTags(path=os.path.join(ctd, "ct.json"))
    qc = fresh_board(community=ct, maintainers=["castleism"])
    tq = qc.post("tag", "New League Unique")
    qc.submit(tq["id"], "p1", "e", "Chaos, Damage Over Time")
    qc.submit(tq["id"], "p2", "e", "chaos, damage over time")
    tags = ct.tags_for("New League Unique")
    check("verified TagQuest writes VERIFIED community tags",
          {t["tag"].lower() for t in tags} == {"chaos", "damage over time"}
          and all(t["verified"] for t in tags))
    rq = qc.post("relationship", "The Peacemaker's Draught")
    qc.submit(rq["id"], "p1", "e", "applies: Corrupted Blood")
    qc.signoff(rq["id"], "castleism")
    check("verified RelationshipQuest writes the applier",
          ct.appliers_of("Corrupted Blood") == ["The Peacemaker's Draught"])
    # Community verified tags also satisfy the close gap-check without a scrape.
    check("community-verified tags count as gap-gone",
          qc.close(tq["id"], db_handler=db) is True)

    # --- persistence -------------------------------------------------------------------
    qb2 = QuestBoard(path=qb.path, maintainers=["castleism"])
    check("board reloads from disk with statuses intact",
          qb2.get(q["id"])["status"] == "verified"
          and qb2.get(qn["id"])["status"] == "closed")

    db.close()
    print(f"\nquest_board: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
