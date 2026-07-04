"""
BUILD_VAULT.PY  --  build (or refresh) Kalandra's Obsidian knowledge vault and
open it, WITHOUT needing the overlay.

It reads the local knowledge database, writes a browsable Obsidian vault (notes
sorted into category folders + keyword hubs that connect skills, uniques,
passives, supports and mechanics), then tries to open it in Obsidian.

Run via "launchers/Build Knowledge Vault.bat" or:  python build_vault.py
"""

import os
import sys
import json
import subprocess
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/ -> repo root
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def load_config():
    try:
        with open(os.path.join("data_engine", "config.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    print("Building the Kalandra Obsidian knowledge vault...")
    try:
        from core_engine.database_handler import KalandraDBHandler
        from core_engine.obsidian_export import ObsidianExporter
    except Exception as e:
        print(f"Cannot load modules: {e}\nRun Setup.bat first.")
        input("Press Enter to exit...")
        return

    cfg = load_config()
    vault = cfg.get("dir_vault", "KalandraVault")
    db = KalandraDBHandler()
    try:
        res = ObsidianExporter(db, out_dir=vault,
                               logger=lambda c, m: print(f"  [{c}] {m}")).export()
    finally:
        try:
            db.close()
        except Exception:
            pass

    notes = res.get("notes", 0)
    path = os.path.abspath(res.get("path", vault))
    print(f"\nDone: {notes} notes, {res.get('hubs', 0)} keyword hubs.")
    print(f"Vault folder: {path}")
    if notes == 0:
        print("\nThe database is empty - run 'launchers/Update Database.bat' first (poe2db sync")
        print("and/or game-file extraction), then build the vault again.")
        input("Press Enter to exit...")
        return

    # Try to open in Obsidian; fall back to opening the folder in Explorer.
    opened = False
    try:
        uri = "obsidian://open?path=" + urllib.parse.quote(path)
        os.startfile(uri)   # Windows: launches Obsidian if installed
        opened = True
        print("\nOpening in Obsidian... (first time: choose 'Open folder as vault')")
    except Exception:
        pass
    if not opened:
        try:
            os.startfile(path)  # open the folder
            print("\nOpened the vault folder. In Obsidian use 'Open folder as vault'.")
        except Exception:
            print("\nOpen this folder in Obsidian via 'Open folder as vault'.")
    input("Press Enter to exit...")


if __name__ == "__main__":
    main()
