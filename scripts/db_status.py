"""
DB_STATUS.PY  --  report how up-to-date each local database/source is.

Prints, per source, the date the local data was last updated and how many
entries it holds. The installer and the updater both use this so you can always
see "current as of <date>" for each database.

Usage:
    python db_status.py            # human-readable
    python db_status.py --json     # machine-readable (used by the installer)
"""

import os
import sys
import json
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/ -> repo root
os.chdir(ROOT)


def _db_path():
    db_dir = "data_engine"
    try:
        with open(os.path.join("data_engine", "config.json"), "r", encoding="utf-8") as f:
            db_dir = json.load(f).get("dir_database") or "data_engine"
    except Exception:
        pass
    return os.path.join(db_dir, "localized_knowledge.db")


def _date(ts):
    if not ts:
        return "never"
    return str(ts)[:10]      # YYYY-MM-DD


def gather():
    path = _db_path()
    out = {"db_path": path, "exists": os.path.exists(path), "sources": {}}
    if not out["exists"]:
        return out
    try:
        con = sqlite3.connect(path)
        c = con.cursor()
    except Exception as e:
        out["error"] = str(e)
        return out

    def host(h):
        last = cnt = None
        try:
            c.execute("SELECT MAX(fetched_at), COUNT(*) FROM crawl_state "
                      "WHERE url LIKE ? AND status='done'", (f"%{h}%",))
            r = c.fetchone(); last, cnt = r[0], r[1]
        except Exception:
            pass
        return {"as_of": _date(last), "entries": cnt or 0}

    def ledger(like):
        last = cnt = None
        try:
            c.execute("SELECT MAX(scraped_at), COUNT(*) FROM knowledge_ledger "
                      "WHERE source_url LIKE ? OR game_version_tag LIKE ?",
                      (f"%{like}%", f"%{like}%"))
            r = c.fetchone(); last, cnt = r[0], r[1]
        except Exception:
            pass
        return {"as_of": _date(last), "entries": cnt or 0}

    out["sources"]["poe2db"] = host("poe2db.tw")
    out["sources"]["poe2wiki"] = host("poe2wiki.net")
    out["sources"]["poe_ninja"] = ledger("poe.ninja")
    out["sources"]["game_data"] = ledger("game-data")
    out["sources"]["craftofexile2"] = ledger("craftofexile")
    try:
        c.execute("SELECT COUNT(*) FROM knowledge_ledger")
        out["total_entries"] = c.fetchone()[0]
    except Exception:
        out["total_entries"] = 0
    con.close()
    return out


def main():
    data = gather()
    if "--json" in sys.argv[1:]:
        print(json.dumps(data))
        return
    print("Kalandra database freshness")
    print("  DB file:", data["db_path"], "" if data["exists"] else "(not created yet)")
    if data.get("exists"):
        print("  Total entries:", data.get("total_entries", 0))
        labels = {"poe2db": "poe2db.tw", "poe2wiki": "poe2wiki.net",
                  "poe_ninja": "poe.ninja economy", "game_data": "game-file data",
                  "craftofexile2": "Craft of Exile"}
        for k, lbl in labels.items():
            s = data["sources"].get(k, {})
            print(f"  - {lbl:20s} current as of {s.get('as_of','never'):12s} "
                  f"({s.get('entries',0)} entries)")


if __name__ == "__main__":
    main()
