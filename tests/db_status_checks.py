"""
TESTS/DB_STATUS_CHECKS.PY — sandbox checks for the DB status window's data
layer (`database_handler.db_status`): the read-only one-pass summary behind
double-clicking the sync medallion. Pure sqlite on temp files — no Qt.
"""

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [FAIL] {name}")


from core_engine.database_handler import db_status

with tempfile.TemporaryDirectory() as td:
    db = os.path.join(td, "localized_knowledge.db")

    # -- missing DB is a complete, honest answer -----------------------------
    st = db_status(db)
    check("missing db: exists False", st["exists"] is False)
    check("missing db: all fields present",
          st["pages"] == 0 and st["versions"] == {} and st["sources"] == {}
          and st["pending"] == {"queued": 0, "error": 0, "done": 0})

    # -- populated DB ----------------------------------------------------------
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE knowledge_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT, topic_tag TEXT NOT NULL,
        content_payload TEXT NOT NULL, source_url TEXT NOT NULL,
        scraped_at TEXT NOT NULL, game_version_tag TEXT DEFAULT 'Patch 0.5.4')""")
    con.execute("""CREATE TABLE crawl_state (
        url TEXT PRIMARY KEY, status TEXT NOT NULL, fetched_at TEXT)""")
    rows = [
        ("mods", "x", "https://poe2db.tw/us/a", "2026-07-01T10:00:00", "Patch 0.5.4"),
        ("mods", "y", "https://poe2db.tw/us/b", "2026-07-09T09:00:00", "Patch 0.5.4"),
        ("wiki", "z", "https://www.poe2wiki.net/wiki/c", "2026-07-05T08:00:00",
         "Patch 0.5.3"),
    ]
    con.executemany("INSERT INTO knowledge_ledger (topic_tag, content_payload,"
                    " source_url, scraped_at, game_version_tag) VALUES "
                    "(?,?,?,?,?)", rows)
    con.executemany("INSERT INTO crawl_state VALUES (?,?,?)", [
        ("u1", "queued", None), ("u2", "queued", None),
        ("u3", "error", None), ("u4", "done", "t")])
    con.commit()
    con.close()

    st = db_status(db)
    check("pages counted", st["pages"] == 3)
    check("size read", st["size_bytes"] > 0)
    check("last sync is the max", st["last_scraped"] == "2026-07-09T09:00:00")
    check("versions histogram", st["versions"] == {"Patch 0.5.4": 2,
                                                   "Patch 0.5.3": 1})
    check("source domains", st["sources"] == {"poe2db.tw": 2,
                                              "www.poe2wiki.net": 1})
    check("pending split", st["pending"] == {"queued": 2, "error": 1,
                                             "done": 1})

    # -- ledger without crawl_state (old seed DBs) ------------------------------
    db2 = os.path.join(td, "seed.db")
    con = sqlite3.connect(db2)
    con.execute("CREATE TABLE knowledge_ledger (id INTEGER PRIMARY KEY, "
                "topic_tag TEXT, content_payload TEXT, source_url TEXT, "
                "scraped_at TEXT, game_version_tag TEXT)")
    con.commit()
    con.close()
    st2 = db_status(db2)
    check("no crawl_state fails soft",
          st2["pages"] == 0 and st2["pending"]["queued"] == 0)

    # -- junk file isn't a crash --------------------------------------------------
    db3 = os.path.join(td, "junk.db")
    with open(db3, "wb") as f:
        f.write(b"this is not sqlite")
    st3 = db_status(db3)
    check("corrupt file fails soft", st3["exists"] and st3["pages"] == 0)

    # -- read-only promise: status must not create/modify files -------------------
    before = os.path.getmtime(db)
    db_status(db)
    check("read-only access", os.path.getmtime(db) == before)

print(f"RESULT: {PASS} passed, {FAIL} failed")
print("ALL GREEN" if FAIL == 0 else "NOT GREEN")
sys.exit(1 if FAIL else 0)
