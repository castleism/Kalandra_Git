"""
UPDATE_DB.PY  --  Kalandra standalone database updater.

Run this WITHOUT the overlay (double-click "launchers/Update Database.bat", or
`python update_db.py`). It:

  1. Shows, for every data source: whether it's enabled, its last successful
     sync, the current live revision, and what % of the currently-discovered
     revision you already hold locally.
  2. Lets you TUNE which sources are active (e.g. enable Craft of Exile, which
     has no language prohibiting scraping, or toggle game-file extraction).
  3. Lets you find/set folder locations (e.g. your Path of Exile 2 install for
     game-file extraction, and the extracted-data output folder).
  4. Asks you to confirm each enabled source before it updates that DB.

Nothing here needs the overlay open; it writes to the same
data_engine/localized_knowledge.db the overlay reads.
"""

import os
import sys
import json
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/ -> repo root
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

CONFIG_PATH = os.path.join("data_engine", "config.json")

# ---- guarded engine imports -----------------------------------------------
def _try(modpath, attr):
    try:
        mod = __import__(modpath, fromlist=[attr])
        return getattr(mod, attr)
    except Exception as e:
        print(f"  (module {modpath}.{attr} unavailable: {e})")
        return None

KalandraDBHandler = _try("core_engine.database_handler", "KalandraDBHandler")
KalandraScraper   = _try("core_engine.scraper", "KalandraScraper")
WikiScraper       = _try("core_engine.wiki_scraper", "WikiScraper")
PoENinja          = _try("core_engine.poe_ninja", "PoENinja")
PoE2DataExtractor = _try("core_engine.poe2_data_extract", "PoE2DataExtractor")
OodleExtractor    = _try("core_engine.oodle_extractor", "OodleExtractor")
FreshnessChecker  = _try("core_engine.data_sources", "FreshnessChecker")

try:
    import requests
except Exception:
    requests = None

UA = {"User-Agent": "KalandraUpdater/1.0"}


# ---- config ---------------------------------------------------------------
def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


# ---- source catalogue -----------------------------------------------------
# tier: "primary" (poe2db is THE database) | "secondary" (optional backups)
# kind: web_crawl | wiki_crawl | economy | game_extract | reference
SOURCES = [
    {"key": "poe2db",        "label": "poe2db.tw  (items, skills, mods, passives - the MAIN database)",
     "kind": "web_crawl",   "host": "poe2db.tw", "default": True, "tier": "primary",
     "note": "Primary source. Direct datamine of the game files, published cleanly as pages. "
             "Tracks every patch (currently 0.5.x, per-version pages) and is actively maintained. "
             "robots.txt allows crawling; fast + resumable. This alone covers items/mods/gems/passives."},
    {"key": "poe2wiki",      "label": "poe2wiki.net  (community wiki articles)",
     "kind": "wiki_crawl",  "host": "poe2wiki.net", "default": False, "tier": "secondary",
     "note": "BACKUP. Adds prose/lore/mechanics explanations. Much slower & finicky: sits behind "
             "Cloudflare and rate-limits hard, so we crawl only 3-wide with backoff (~10x slower "
             "than poe2db) and some pages need retries across runs."},
    {"key": "poe_ninja",     "label": "poe.ninja  (live economy / prices)",
     "kind": "economy",     "host": "poe.ninja", "default": False, "tier": "secondary",
     "note": "BACKUP/supplement. Economy ONLY (currency values), not game data. Snapshot per "
             "league via an undocumented PoE2 API; league name must match exactly."},
    {"key": "game_data",     "label": "In-process game-file extraction (.datc64 tables)",
     "kind": "game_extract", "host": None, "default": False, "tier": "secondary",
     "note": "BACKUP/advanced. The 'purist' direct route to structured tables, but needs the "
             "game's Oodle DLL via ctypes. Many builds (incl. cloud/Shadow installs) statically "
             "link Oodle so there's no DLL to use - and poe2db already gives you this data."},
    {"key": "craftofexile2", "label": "Craft of Exile  (crafting odds/data)",
     "kind": "reference",   "host": "craftofexile.com", "default": False, "tier": "secondary",
     "note": "BACKUP/experimental. No anti-scrape language found, but the data lives in JS so the "
             "importer is currently only a reference snapshot (a full odds importer is future work)."},
]


def enabled_map(cfg):
    saved = cfg.get("sources_enabled", {})
    return {s["key"]: bool(saved.get(s["key"], s["default"])) for s in SOURCES}


# ---- status helpers -------------------------------------------------------
def _ensure_crawl_state(db):
    try:
        db.cursor.execute("""CREATE TABLE IF NOT EXISTS crawl_state(
            url TEXT PRIMARY KEY, status TEXT NOT NULL, fetched_at TEXT)""")
        db.conn.commit()
    except Exception:
        pass


def host_status(db, host):
    """(done, queued, last_sync) for a crawl host, from the shared frontier."""
    _ensure_crawl_state(db)
    done = queued = 0
    last = None
    try:
        like = f"%{host}%"
        c = db.cursor
        c.execute("SELECT COUNT(*) FROM crawl_state WHERE url LIKE ? AND status='done'", (like,))
        done = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM crawl_state WHERE url LIKE ? AND status='queued'", (like,))
        queued = c.fetchone()[0]
        c.execute("SELECT MAX(fetched_at) FROM crawl_state WHERE url LIKE ? AND status='done'", (like,))
        last = c.fetchone()[0]
    except Exception:
        pass
    return done, queued, last


def ledger_count(db, like=None):
    try:
        if like:
            db.cursor.execute("SELECT COUNT(*) FROM knowledge_ledger WHERE source_url LIKE ? OR game_version_tag LIKE ?",
                              (f"%{like}%", f"%{like}%"))
        else:
            db.cursor.execute("SELECT COUNT(*) FROM knowledge_ledger")
        return db.cursor.fetchone()[0]
    except Exception:
        return 0


def live_patch_label():
    """Detect the current PoE2 patch label from poe2db (best-effort)."""
    if requests is None:
        return None
    try:
        import re
        r = requests.get("https://poe2db.tw/us/", headers=UA, timeout=8)
        if r.status_code == 200:
            m = re.search(r"\b0\.\d+(?:\.\d+)?\b", r.text)
            return m.group(0) if m else None
    except Exception:
        return None
    return None


def pct(done, total):
    if total <= 0:
        return 0.0
    return round(100.0 * done / total, 1)


def fmt_when(ts):
    if not ts:
        return "never"
    try:
        return datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


# ---- overview -------------------------------------------------------------
def print_overview(cfg, db):
    en = enabled_map(cfg)
    patch = live_patch_label()
    print("\n" + "=" * 70)
    print("  KALANDRA DATABASE STATUS")
    print("=" * 70)
    print(f"  Checked: {datetime.now().strftime('%A, %B %d, %Y - %I:%M %p')}")
    print(f"  Live PoE2 revision (poe2db): {('Patch ' + patch) if patch else 'unknown (offline?)'}")
    print(f"  Total entries in local knowledge base: {ledger_count(db)}")

    def _print_source(i, s):
        flag = "ON " if en[s["key"]] else "off"
        print(f"  [{i}] ({flag}) {s['label']}")
        if s["kind"] in ("web_crawl", "wiki_crawl"):
            done, queued, last = host_status(db, s["host"])
            total = done + queued
            print(f"        current as of: {fmt_when(last)}    "
                  f"pages: {done} crawled / {total} discovered    "
                  f"coverage: {pct(done, total)}%")
        elif s["kind"] == "economy":
            print(f"        economy entries stored: {ledger_count(db, 'poe.ninja')}    (snapshot)")
        elif s["kind"] == "game_extract":
            _game_status_line(cfg)
        elif s["kind"] == "reference":
            print(f"        entries stored: {ledger_count(db, s['host'])}")

    print("-" * 70)
    print("  PRIMARY DATABASE  (this is the one we rely on)")
    for i, s in enumerate(SOURCES, 1):
        if s.get("tier") == "primary":
            _print_source(i, s)
            print("        why: direct datamine, published cleanly, fast to crawl, tracks")
            print("             every patch. Covers items / mods / gems / passives on its own.")
    print("-" * 70)
    print("  SECONDARY / BACKUP SOURCES  (optional - poe2db already covers the core data)")
    for i, s in enumerate(SOURCES, 1):
        if s.get("tier") != "primary":
            _print_source(i, s)
    print("-" * 70)
    print("  Coverage % = of the pages DISCOVERED on a source, how many are crawled in.")
    print("  poe2db tracks each patch; Kalandra flags when the live patch is newer than")
    print("  your last sync, so you know when to re-run. The secondary sources are harder")
    print("  to scrape (see their notes via 'T') and are not needed for the core database.")
    print("=" * 70)


def _game_status_line(cfg):
    if not PoE2DataExtractor or not KalandraDBHandler:
        print("        game-data extractor unavailable.")
        return
    wdb = None
    try:
        wdb = KalandraDBHandler()
        ex = PoE2DataExtractor(wdb)
        s = ex.scan()
        if not s.get("install_found"):
            print("        PoE2 install NOT set — use menu option F to find/set it.")
            return
        changed = "CHANGED (re-import needed)" if s.get("game_changed") else "up to date"
        cov = 0.0 if s.get("needs_import") else 100.0
        print(f"        install: {s.get('install_path')}")
        print(f"        game rev token: {s.get('game_version')}  [{changed}]")
        print(f"        last imported rows: {s.get('last_imported_rows')}    "
              f"current-rev coverage: {cov}%")
    except Exception as e:
        print(f"        game-data status error: {e}")
    finally:
        if wdb:
            try:
                wdb.close()
            except Exception:
                pass


# ---- runners --------------------------------------------------------------
def _logger(cat, msg):
    print(f"    [{cat}] {msg}")


def run_poe2db(cfg, db):
    if not KalandraScraper:
        print("    poe2db scraper unavailable (pip install requests beautifulsoup4).")
        return
    sp = KalandraScraper(db, logger=_logger)
    conc = int(cfg.get("crawl_concurrency", 4))
    cap = int(cfg.get("crawl_max_pages", 80000))
    print(f"    Crawling poe2db (concurrency {conc}, cap {cap})... Ctrl+C to pause (progress saved).")
    res = sp.crawl(max_pages=cap, concurrency=conc)
    print(f"    poe2db done: stored {res.get('stored')}, processed {res.get('processed')}, "
          f"pending {res.get('pending')}.")


def run_wiki(cfg, db):
    if not WikiScraper:
        print("    wiki scraper unavailable.")
        return
    # WikiScraper logs with (category, message) -- pass a 2-arg logger so its
    # progress is actually shown (a 1-arg lambda silently swallowed everything).
    wp = WikiScraper(db, logger=lambda c, m: print(f"    [{c}] {m}"))
    conc = int(cfg.get("wiki_concurrency", 3))
    print(f"    Crawling poe2wiki (concurrency {conc}). Note: the wiki rate-limits,")
    print(f"    so this is intentionally slower than poe2db; it enumerates all pages")
    print(f"    first (can take a minute) before fetching. Progress will print below.")
    res = wp.crawl(max_pages=int(cfg.get("wiki_max_pages", 5000)), concurrency=conc)
    print(f"    poe2wiki done: {res}")


def run_ninja(cfg, db):
    if not PoENinja:
        print("    poe.ninja module unavailable.")
        return
    league = cfg.get("league", "Standard")
    nj = PoENinja(logger=lambda c, m: print(f"    [{c}] {m}"))
    print(f"    Pulling poe.ninja PoE2 economy for league '{league}'...")
    try:
        n = nj.store_economy(db, league)
        if n:
            print(f"    poe.ninja: stored {n} economy rows for '{league}'.")
        else:
            print(f"    poe.ninja: 0 rows stored. The league name may be wrong for PoE2 — "
                  f"valid examples: 'Standard', 'Rise of the Abyssal'. Set \"league\" in "
                  f"data_engine/config.json.")
    except Exception as e:
        print(f"    poe.ninja error: {e}")


def run_game(cfg, db):
    if not (PoE2DataExtractor and KalandraDBHandler):
        print("    game-data extractor unavailable.")
        return
    # First, try the in-process Oodle extractor to (re)write the .datc64 tables.
    if OodleExtractor:
        try:
            from core_engine.poe2_data_extract import DEFAULT_TABLES
        except Exception:
            DEFAULT_TABLES = ["BaseItemTypes", "Mods", "Stats", "SkillGems", "Tags"]
        ex = OodleExtractor(install_dir=cfg.get("game_install_dir"), logger=_logger)
        # Full diagnostic so we can see exactly what's found.
        try:
            rep = ex.self_test()
            print(f"    Self-test: install={rep.get('install')} dll={rep.get('dll')} "
                  f"dll_loaded={rep.get('dll_loaded')} "
                  f"index_decompressed={rep.get('index_decompressed')}")
            print(f"    Install path: {rep.get('install_path')}")
            for n in rep.get("notes", []):
                print(f"      - {n}")
            if rep.get("hash_scores"):
                print("    Hash candidate scores: "
                      + ", ".join(f"{k}={v}" for k, v in rep["hash_scores"].items()))
        except Exception as e:
            print(f"    Self-test error: {e}")

        if ex.install and ex.dll_path:
            print(f"    Extracting game data from: {ex.install}")
            res = ex.extract_tables(DEFAULT_TABLES,
                                    cfg.get("dir_game_data", "data_engine/game_data"))
            print(f"    Extracted tables: {', '.join(res.get('written', [])) or 'none'}")
            if res.get("missing"):
                print(f"    Missing tables: {', '.join(res['missing'])}")
        else:
            why = []
            if not ex.install:
                why.append("install folder not recognized (no Bundles2/Content.ggpk)")
            if not ex.dll_path:
                why.append("no Oodle DLL (this PoE2 build statically links it)")
            print("    In-process extractor unavailable: " + "; ".join(why) + ".")
            print("    This is OPTIONAL - your poe2db scrape already contains the same")
            print("    item/mod/gem/passive data, so the AI and vault are fully usable")
            print("    without it. (To enable direct extraction later, supply an "
                  "oo2core DLL via config 'oo2core_dll'.)")
    # Then import whatever .datc64 are present into the DB.
    try:
        ext = PoE2DataExtractor(db, logger=_logger)
        r = ext.auto_update(force=True)
        print(f"    Game-data import: {r.get('status')} "
              f"({r.get('rows', 0)} rows).")
    except Exception as e:
        print(f"    Game-data import error: {e}")


def run_craftofexile(cfg, db):
    print("    Craft of Exile: no language prohibiting scraping was found, so this")
    print("    source can be enabled. A full odds/data importer is not built yet;")
    print("    for now this records a reference snapshot of the site.")
    if requests is None:
        print("    (install 'requests' to fetch).")
        return
    try:
        r = requests.get("https://craftofexile.com/", headers=UA, timeout=15)
        if r.status_code == 200 and db:
            db.insert_scoured_data(topic="Craft of Exile (reference)",
                                   content=r.text[:20000],
                                   url="https://craftofexile.com/",
                                   version="craftofexile")
            print("    Stored a Craft of Exile reference snapshot.")
        else:
            print(f"    Fetch returned HTTP {r.status_code}.")
    except Exception as e:
        print(f"    Craft of Exile fetch error: {e}")


RUNNERS = {
    "poe2db": run_poe2db, "poe2wiki": run_wiki, "poe_ninja": run_ninja,
    "game_data": run_game, "craftofexile2": run_craftofexile,
}


# ---- folder finder --------------------------------------------------------
def find_and_set_game_folder(cfg):
    print("\n  -- Find / set the Path of Exile 2 install folder --")
    detected = None
    if OodleExtractor:
        try:
            ex = OodleExtractor(install_dir=cfg.get("game_install_dir"))
            detected = ex.install
        except Exception:
            pass
    if detected:
        print(f"  Auto-detected: {detected}")
    cur = cfg.get("game_install_dir") or "(not set)"
    print(f"  Currently set: {cur}")
    ans = input("  Enter the PoE2 folder path (blank = keep, 'auto' = use detected): ").strip()
    if ans.lower() == "auto" and detected:
        cfg["game_install_dir"] = detected
    elif ans:
        if os.path.isdir(ans):
            cfg["game_install_dir"] = ans
        else:
            print("  That folder doesn't exist; leaving unchanged.")
            return
    save_config(cfg)
    print(f"  game_install_dir = {cfg.get('game_install_dir')}")

    out = input(f"  Extracted-data output folder [{cfg.get('dir_game_data','data_engine/game_data')}]: ").strip()
    if out:
        cfg["dir_game_data"] = out
        save_config(cfg)
        print(f"  dir_game_data = {out}")


# ---- menu -----------------------------------------------------------------
def main():
    print("Kalandra Database Updater (standalone — the overlay does NOT need to be open).")
    if not KalandraDBHandler:
        print("FATAL: database handler unavailable. Run the installer (Setup.bat) first.")
        input("Press Enter to exit...")
        return
    cfg = load_config()
    db = KalandraDBHandler()

    while True:
        print_overview(cfg, db)
        print("\n  MENU:")
        print("    U   Update now (you'll confirm each enabled source)")
        print("    T   Toggle a source on/off")
        print("    F   Find / set folder locations (game install, output)")
        print("    R   Refresh status")
        print("    Q   Quit")
        choice = input("  > ").strip().lower()

        if choice == "q":
            break
        elif choice == "r":
            continue
        elif choice == "t":
            for i, s in enumerate(SOURCES, 1):
                print(f"    [{i}] {s['label']}  -  {s['note']}")
            sel = input("  Toggle which number? ").strip()
            if sel.isdigit() and 1 <= int(sel) <= len(SOURCES):
                key = SOURCES[int(sel) - 1]["key"]
                en = enabled_map(cfg)
                se = cfg.get("sources_enabled", {})
                se[key] = not en[key]
                cfg["sources_enabled"] = se
                save_config(cfg)
                print(f"    {key} is now {'ON' if se[key] else 'off'}.")
        elif choice == "f":
            find_and_set_game_folder(cfg)
        elif choice == "u":
            en = enabled_map(cfg)
            any_run = False
            for s in SOURCES:
                if not en[s["key"]]:
                    continue
                ans = input(f"  Update '{s['label']}'? [y/N] ").strip().lower()
                if ans.startswith("y"):
                    any_run = True
                    print(f"  >>> Updating {s['key']} ...")
                    try:
                        RUNNERS[s["key"]](cfg, db)
                    except KeyboardInterrupt:
                        print("    Paused by user (progress saved).")
                    except Exception as e:
                        print(f"    Error updating {s['key']}: {e}")
            if not any_run:
                print("  Nothing selected.")
            input("\n  Done. Press Enter to return to the status screen...")
        else:
            print("  Unknown option.")

    try:
        db.close()
    except Exception:
        pass
    print("Goodbye, Exile.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")
