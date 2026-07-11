"""
SCRIPTS/MAKE_RELEASE_ZIP.PY — build a shareable Kalandra-Setup.zip.

Run on Windows (launchers\\"Make Release Zip.bat"). The zip is safe to
share: data_engine/ (config ids/secrets, profile, chats, ledgers), .env,
.git/, __pycache__/, tools/ and Additional Resources/ are excluded, and
the finished archive is re-scanned for key-shaped strings.

ZIP-INCEPTION GUARD (2026-07-04): *.zip files are NEVER packed — an old
release zip sitting anywhere in the tree used to get swallowed into the
new one, recursively, run after run. Output also never lands inside the
project folder (Desktop, else your user profile dir).
"""

import os
import re
import sys
import time
import zipfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT)

EXCLUDE_DIRS = {".git", "__pycache__", "data_engine", "tools",
                "Additional Resources", ".claude", "build"}
EXCLUDE_FILES = {".env"}
EXCLUDE_EXTS = (".pyc", ".db", ".log", ".zip", ".7z", ".rar",
                ".corrupt.bak", ".tmp")
KEY_PATTERNS = re.compile(
    rb"sk-[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{30,}|ghp_[A-Za-z0-9]{30,}"
    rb"|AKIA[A-Z0-9]{16}|xoxb-[A-Za-z0-9-]{20,}")

# BUNDLED DATABASE (2026-07-05): the scraped knowledge DB is public game
# data (poe2db/wiki/poe.ninja), no secrets - ship the freshest copy found so
# a new install already knows the game before its first scrape. The
# installer auto-imports it from Additional Resources\Database.
DB_SOURCES = (
    os.path.join("data_engine", "localized_knowledge.db"),
    os.path.join("Additional Resources", "Database", "localized_knowledge.db"),
    os.path.join(os.path.expanduser("~"), "Documents", "Kalandra-Data",
                 "localized_knowledge.db"),   # the uninstaller's keep-spot
)
DB_CACHES = ("poe2db_cache.sqlite", "poeninja_cache.sqlite")

# PYINSTALLER ONEDIR (2026-07-05): the setup wizard exe folder is packed
# VERBATIM. Its _internal\ holds a file literally named base_library.zip;
# the .zip exclusion used to strip it, and every unzipped package then died
# with "failed to start embedded python interpreter".
ONEDIR = "Kalandra-Setup"


def pack_onedir(z):
    """-> files packed from the exe folder (0 + note if it wasn't built)."""
    d = os.path.join(_ROOT, ONEDIR)
    if not os.path.isdir(d):
        print("  NOTE: no Kalandra-Setup\\ exe folder found - package ships "
              "without the wizard exe (Setup.bat still works).")
        return 0
    n = 0
    for root, dirs, files in os.walk(d):
        for f in files:
            q = os.path.join(root, f)
            z.write(q, os.path.join("Kalandra", os.path.relpath(q, _ROOT)))
            n += 1
    print(f"  setup wizard exe packed VERBATIM ({n} files, "
          f"base_library.zip included).")
    return n


def bundle_db(z):
    """Pack the newest localized_knowledge.db (+ its caches) into the zip at
    Kalandra/Additional Resources/Database/. -> files bundled (0 if none)."""
    best = None
    for cand in DB_SOURCES:
        if os.path.isfile(cand) and (
                best is None
                or os.path.getmtime(cand) > os.path.getmtime(best)):
            best = cand
    if not best:
        print("  NOTE: no localized_knowledge.db found anywhere - the package "
              "ships without a bundled database.")
        return 0
    arc = os.path.join("Kalandra", "Additional Resources", "Database")
    z.write(best, os.path.join(arc, "localized_knowledge.db"))
    age_h = (time.time() - os.path.getmtime(best)) / 3600.0
    print(f"  bundled DB: {best} ({os.path.getsize(best) / 1e6:.1f} MB, "
          f"~{age_h:.0f}h old)")
    n = 1
    for c in DB_CACHES:
        q = os.path.join(os.path.dirname(best), c)
        if os.path.isfile(q):
            z.write(q, os.path.join(arc, c))
            n += 1
    return n


def build(out_path):
    n = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(_ROOT):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS
                       and not (root == _ROOT and d == ONEDIR)]
            for f in files:
                if f in EXCLUDE_FILES or f.lower().endswith(EXCLUDE_EXTS):
                    continue
                p = os.path.join(root, f)
                if os.path.abspath(p) == os.path.abspath(out_path):
                    continue          # never swallow the archive being built
                z.write(p, os.path.join("Kalandra", os.path.relpath(p, _ROOT)))
                n += 1
        n += bundle_db(z)
        n += pack_onedir(z)
    return n


def scan(out_path):
    hits = []
    with zipfile.ZipFile(out_path) as z:
        for name in z.namelist():
            if name.lower().endswith((".db", ".sqlite")):
                continue   # bundled scraped-game-data DB: binary, ours-key-free
            if name.startswith("Kalandra/" + ONEDIR + "/"):
                continue   # our own exe's binaries: key-free, avoids false hits
            try:
                data = z.read(name)
            except Exception:
                continue
            if KEY_PATTERNS.search(data):
                hits.append(name)
    return hits


def main():
    env_out = os.environ.get("KALANDRA_RELEASE_OUT")
    if env_out:
        outdir = env_out
        os.makedirs(outdir, exist_ok=True)
    else:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        outdir = desktop if os.path.isdir(desktop) else os.path.expanduser("~")
    out = os.path.join(outdir, "Kalandra-Setup.zip")
    # Leftover zips INSIDE the project poison future builds — refuse them.
    strays = [f for f in os.listdir(_ROOT) if f.lower().endswith(".zip")]
    if strays:
        print("REFUSED: zip file(s) inside the project folder would nest "
              "into the release:")
        for s in strays:
            print("  -", s)
        print("Delete or move them out of the Kalandra folder, then rerun.")
        return 1
    print(f"Building {out} ...")
    n = build(out)
    print(f"  {n} files packed (data/tools/git/zips excluded).")
    print("Scanning the archive for key-shaped strings ...")
    hits = scan(out)
    if hits:
        os.remove(out)
        print("REFUSED: possible secrets found in:")
        for h in hits:
            print("  -", h)
        return 1
    print(f"OK — {out} ({os.path.getsize(out) / 1e6:.1f} MB). "
          "Unzip anywhere and run Kalandra\\Setup.bat.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
