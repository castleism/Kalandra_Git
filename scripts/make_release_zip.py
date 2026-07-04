"""
SCRIPTS/MAKE_RELEASE_ZIP.PY — build a shareable Kalandra-Setup.zip.

Run on Windows (launchers\\"Make Release Zip.bat") so the archive is built
from the REAL files. The zip is safe to share:

  EXCLUDED — everything personal or machine-local:
    data_engine/            your config (client ids/secrets, account name,
                            email), player profile, chat threads, ledgers,
                            knowledge DB, snapshots, clips, crash logs
    .env, .git/, __pycache__/
    tools/, Additional Resources/   (multi-GB bundled add-ons; the offline
                            bundle has its own builder — installer/
                            Build-Offline-Bundle.ps1)

  GUARD — after building, the archive is re-scanned for key-shaped strings
  (sk-…, AIza…, ghp_…, AKIA…) and REFUSES to finish if any appear.

Output: Kalandra-Setup.zip on your Desktop.
"""

import os
import re
import sys
import zipfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT)

EXCLUDE_DIRS = {".git", "__pycache__", "data_engine", "tools",
                "Additional Resources", ".claude"}
EXCLUDE_FILES = {".env"}
KEY_PATTERNS = re.compile(
    rb"sk-[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{30,}|ghp_[A-Za-z0-9]{30,}"
    rb"|AKIA[A-Z0-9]{16}|xoxb-[A-Za-z0-9-]{20,}")


def build(out_path):
    n = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(_ROOT):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in files:
                if f in EXCLUDE_FILES or f.endswith((".pyc", ".db", ".log")):
                    continue
                p = os.path.join(root, f)
                rel = os.path.relpath(p, _ROOT)
                z.write(p, os.path.join("Kalandra", rel))
                n += 1
    return n


def scan(out_path):
    hits = []
    with zipfile.ZipFile(out_path) as z:
        for name in z.namelist():
            try:
                data = z.read(name)
            except Exception:
                continue
            if KEY_PATTERNS.search(data):
                hits.append(name)
    return hits


def main():
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    out = os.path.join(desktop if os.path.isdir(desktop) else _ROOT,
                       "Kalandra-Setup.zip")
    print(f"Building {out} ...")
    n = build(out)
    print(f"  {n} files packed (data_engine/tools/.git excluded).")
    print("Scanning the archive for key-shaped strings ...")
    hits = scan(out)
    if hits:
        os.remove(out)
        print("REFUSED: possible secrets found in:")
        for h in hits:
            print("  -", h)
        print("Archive deleted — clean those files and rerun.")
        return 1
    mb = os.path.getsize(out) / 1e6
    print(f"OK — no secrets detected. {out} ({mb:.1f} MB)")
    print("Unzip anywhere and run Kalandra\\Setup.bat.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
