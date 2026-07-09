"""
MAKE_UPDATE_ZIP.PY
Build a code-only update zip that is SAFE to extract over an existing Kalandra
install. The hard rule: NEVER include user state — config, secrets, trackers,
databases, logs — because extracting the zip would clobber the user's copies.
(This script exists because a hand-built zip once shipped an empty config.json
and wiped a real install's settings. Codify the rule; don't repeat it.)

Usage:  python make_update_zip.py [out.zip]
"""
import os as _os, sys as _sys
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # scripts/ -> repo root
_os.chdir(_ROOT)
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)

import os
import sys
import zipfile

# Files worth shipping in a code update.
CODE_EXT = {".py", ".lua", ".md", ".bat", ".txt"}
CODE_NAMES = {".gitignore", ".gitattributes"}

# Never ship anything under these directories.
SKIP_DIRS = {"__pycache__", ".git", "tools", ".venv", "venv", "node_modules"}

# User state that must NEVER be in an update zip (would overwrite the user's).
FORBIDDEN = {
    os.path.join("data_engine", "config.json"),
    os.path.join("data_engine", ".secrets.json"),
    os.path.join("data_engine", "issues.json"),
    os.path.join("data_engine", "kalandra_issues.json"),
    os.path.join("data_engine", "reserve_items.json"),
    os.path.join("data_engine", "knowledge_corrections.json"),
    os.path.join("data_engine", "crash.log"),
}
# JSON policy: json files are DATA, not code — only explicitly whitelisted ones ship.
JSON_WHITELIST = {os.path.join("data_engine", "config.template.json")}


def want(rel):
    rel_norm = os.path.normpath(rel)
    parts = rel_norm.split(os.sep)
    if any(p in SKIP_DIRS for p in parts):
        return False
    if rel_norm in FORBIDDEN:
        return False
    name = os.path.basename(rel_norm)
    ext = os.path.splitext(name)[1].lower()
    if ext == ".json":
        return rel_norm in JSON_WHITELIST
    return ext in CODE_EXT or name in CODE_NAMES


def main():
    root = _ROOT   # repo root, not scripts/ (post-reorg)
    out = sys.argv[1] if len(sys.argv) > 1 else "Kalandra_update.zip"
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root)
                if want(rel):
                    z.write(full, rel)
                    n += 1
    print(f"{out}: {n} files (user state excluded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
