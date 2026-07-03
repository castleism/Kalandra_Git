"""
INSTALL_DEPENDENCIES.PY  --  guided setup for Kalandra.

Run this once (double-click "Install Dependencies.bat", or
`py -3.12 install_dependencies.py`) and pick what you want. It can:

  1. Install the Python requirements (REQUIRED for Kalandra to run).
  2. Fetch the engine extras Kalandra uses internally:
        - LuaJIT            (runs Path of Building's engine for the live sim)
        - Rhubarb Lip Sync  (phoneme-accurate mouth shapes for the talking face)
        - PoB 2 source      (the headless build simulator)
  3. Download companion APPS you may want alongside Kalandra:
        - Path of Building 2   (the build planner app)
        - Exiled Exchange 2    (PoE2 price-check overlay)
        - Xiletrade            (PoE1/2 overlay + price checker)
        - Lailloken Exile-UI   (PoE2 QoL overlay)

Every GitHub download resolves the LATEST release at run time, so links never
go stale. Everything is best-effort and logged; one item failing doesn't stop
the rest. App installers (.exe) are downloaded into  tools/installers/  and you
choose whether to run them; portable apps (.zip) are unpacked into  tools/apps/ .

Usage:
    py -3.12 install_dependencies.py            # interactive menu
    py -3.12 install_dependencies.py --all      # install everything, no prompts
    py -3.12 install_dependencies.py --minimal  # just the Python requirements
    py -3.12 install_dependencies.py --yes core extras   # named groups, no prompts
"""

import os
import re
import sys
import json
import shutil
import zipfile
import subprocess
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(ROOT, "tools")
APPS = os.path.join(TOOLS, "apps")
INSTALLERS = os.path.join(TOOLS, "installers")
CONFIG_PATH = os.path.join(ROOT, "data_engine", "config.json")
UA = {"User-Agent": "Kalandra-Installer"}

AUTO_YES = False


def log(msg):
    print(msg, flush=True)


# --------------------------------------------------------------------------- #
# config + download helpers
# --------------------------------------------------------------------------- #
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


def _get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _download(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=900) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    return dest


def _extract_zip(zip_path, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dest_dir)


def _find(root, filename):
    for r, _d, files in os.walk(root):
        for fn in files:
            if fn.lower() == filename.lower():
                return os.path.join(r, fn)
    return None


def _download_repo_zip(owner, repo, dest_dir):
    """Download a GitHub repo's default-branch source zip (no git required)."""
    url = f"https://api.github.com/repos/{owner}/{repo}/zipball"
    zp = os.path.join(dest_dir, f"{repo}.zip")
    _download(url, zp)
    _extract_zip(zp, dest_dir)
    try:
        os.remove(zp)
    except Exception:
        pass
    return dest_dir


def gh_latest_asset(owner, repo, patterns):
    """Return (asset_name, download_url) for the first asset matching any regex,
    searching the latest release and then recent releases (handles repos whose
    'latest' is a pre-release)."""
    urls = [f"https://api.github.com/repos/{owner}/{repo}/releases/latest",
            f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=10"]
    seen = []
    for url in urls:
        try:
            data = _get_json(url)
        except Exception:
            continue
        releases = data if isinstance(data, list) else [data]
        for rel in releases:
            for a in rel.get("assets", []):
                seen.append(a["name"])
            for pat in patterns:
                rx = re.compile(pat, re.I)
                for a in rel.get("assets", []):
                    if rx.search(a["name"]):
                        return a["name"], a["browser_download_url"]
    raise RuntimeError(f"No asset matched {patterns} in {owner}/{repo}. Saw: {seen[:12]}")


def _ask_yes(prompt, default=True):
    if AUTO_YES:
        return True
    d = "Y/n" if default else "y/N"
    try:
        ans = input(f"{prompt} [{d}] ").strip().lower()
    except EOFError:
        return default
    if not ans:
        return default
    return ans.startswith("y")


# --------------------------------------------------------------------------- #
# component installers
# --------------------------------------------------------------------------- #
def step_pip(cfg):
    log("\n=== Python requirements (pip) ===")
    req = os.path.join(ROOT, "requirements.txt")
    if not os.path.exists(req):
        log("  requirements.txt not found, skipping.")
        return
    # Install into THIS python's own site-packages (no --user) so the same
    # interpreter the launchers use always sees them. Upgrade pip first.
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
                       check=False)
    except Exception:
        pass
    # Offline support: install from bundled wheels if present.
    wheel_dirs = [os.path.join(ROOT, "Additional Resources", "Python Packages (wheels)"),
                  os.path.join(ROOT, "installer", "bundled", "wheels")]
    wheels = next((w for w in wheel_dirs if os.path.isdir(w) and os.listdir(w)), None)
    cmd = [sys.executable, "-m", "pip", "install", "-r", req]
    if wheels:
        log(f"  using bundled wheels (offline): {wheels}")
        cmd = [sys.executable, "-m", "pip", "install",
               "--no-index", "--find-links", wheels, "-r", req]
    try:
        subprocess.run(cmd, check=False)
        log("  Python requirements installed (or already present).")
    except Exception as e:
        log(f"  pip failed: {e}")


def step_luajit(cfg):
    log("\n=== LuaJIT (Path of Building simulator engine) ===")
    try:
        name, url = gh_latest_asset("ScriptTiger", "LuaJIT-For-Windows",
                                    [r"\.zip$", r"\.7z$", r"luajit.*\.exe$"])
        ldir = os.path.join(TOOLS, "luajit")
        dest = os.path.join(ldir, name)
        log(f"  downloading {name} ...")
        _download(url, dest)
        if name.lower().endswith(".zip"):
            _extract_zip(dest, ldir)
        # The executable ScriptTiger ships is LuaJIT-For-Windows.exe (a
        # self-extractor that also serves as the entry point). Prefer it,
        # fall back to a plain luajit.exe if a zip provided one.
        exe = _find(ldir, "LuaJIT-For-Windows.exe") or _find(ldir, "luajit.exe")
        if exe:
            cfg["luajit_path"] = exe
            log(f"  LuaJIT ready: {exe}")
            if exe.lower().endswith("luajit-for-windows.exe"):
                log("  Note: this is ScriptTiger's self-extracting build. Run it once to")
                log("  unpack, then 'Check Location for: \"LuaJIT-For-Windows.exe\"' if needed.")
                try:
                    os.startfile(exe)
                except Exception:
                    pass
        else:
            log(f"  Downloaded, but the LuaJIT exe wasn't located - check {ldir}.")
    except Exception as e:
        log(f"  LuaJIT auto-install failed ({e}). Get it from "
            "https://github.com/ScriptTiger/LuaJIT-For-Windows/releases")


def step_rhubarb(cfg):
    log("\n=== Rhubarb Lip Sync (talking-face visemes) ===")
    try:
        name, url = gh_latest_asset("DanielSWolf", "rhubarb-lip-sync",
                                    [r"Windows.*\.zip$", r"win.*\.zip$", r"\.zip$"])
        dest = os.path.join(TOOLS, "rhubarb", name)
        log(f"  downloading {name} ...")
        _download(url, dest)
        _extract_zip(dest, os.path.join(TOOLS, "rhubarb"))
        exe = _find(os.path.join(TOOLS, "rhubarb"), "rhubarb.exe")
        if exe:
            cfg["rhubarb_path"] = exe
            log(f"  Rhubarb ready: {exe}")
        else:
            log("  Downloaded, but rhubarb.exe not located — check tools/rhubarb/.")
    except Exception as e:
        log(f"  Rhubarb auto-install failed ({e}). Get it from "
            "https://github.com/DanielSWolf/rhubarb-lip-sync/releases")


def step_pob_source(cfg):
    log("\n=== Path of Building 2 SOURCE (headless build simulator) ===")
    existing = _find(TOOLS, "HeadlessWrapper.lua")
    if existing:
        cfg["pob_install_dir"] = os.path.dirname(existing)
        log(f"  Already present: {cfg['pob_install_dir']}")
        return
    try:
        if shutil.which("git"):
            log("  cloning via git (a few hundred MB) ...")
            subprocess.run(["git", "clone", "--depth", "1",
                            "https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2.git",
                            os.path.join(TOOLS, "PathOfBuilding-PoE2")], check=False)
        else:
            log("  git not found — downloading the source zip instead "
                "(a few hundred MB, please wait) ...")
            _download_repo_zip("PathOfBuildingCommunity", "PathOfBuilding-PoE2", TOOLS)
        hw = _find(TOOLS, "HeadlessWrapper.lua")
        if hw:
            cfg["pob_install_dir"] = os.path.dirname(hw)
            log(f"  PoB 2 source ready: {cfg['pob_install_dir']}")
        else:
            log("  Downloaded, but HeadlessWrapper.lua wasn't found — check tools/.")
    except Exception as e:
        log(f"  PoB source download failed: {e}.")


def _install_github_app(title, owner, repo, patterns, cfg, cfg_key=None, run_default=False):
    """Download the latest Windows release asset of a companion app.
       .exe -> saved to tools/installers/<repo>/ and optionally launched.
       .zip -> unpacked to tools/apps/<repo>/ (portable)."""
    log(f"\n=== {title}  ({owner}/{repo}) ===")
    try:
        name, url = gh_latest_asset(owner, repo, patterns)
    except Exception as e:
        log(f"  Could not find a downloadable release asset ({e}).")
        log(f"  Get it manually: https://github.com/{owner}/{repo}/releases")
        return
    lname = name.lower()
    if lname.endswith(".zip"):
        dest_dir = os.path.join(APPS, repo)
        zp = os.path.join(dest_dir, name)
        log(f"  downloading portable app {name} ...")
        _download(url, zp)
        _extract_zip(zp, dest_dir)
        try:
            os.remove(zp)
        except Exception:
            pass
        if cfg_key:
            cfg[cfg_key] = dest_dir
        log(f"  Installed (portable) to: {dest_dir}")
    else:  # installer (.exe / .msi)
        dest = os.path.join(INSTALLERS, repo, name)
        log(f"  downloading installer {name} ...")
        _download(url, dest)
        if cfg_key:
            cfg[cfg_key] = dest
        log(f"  Installer saved to: {dest}")
        if _ask_yes("  Run the installer now?", default=run_default):
            try:
                os.startfile(dest)  # hands off to Windows
                log("  Launched the installer — follow its prompts.")
            except Exception as e:
                log(f"  Could not auto-launch ({e}); run it yourself: {dest}")


def step_pob2_app(cfg):
    _install_github_app("Path of Building 2 (build planner app)",
                        "PathOfBuildingCommunity", "PathOfBuilding-PoE2",
                        [r"setup.*\.exe$", r"PathOfBuilding.*\.exe$",
                         r"win.*\.zip$", r"\.exe$", r"\.zip$"],
                        cfg, cfg_key="pob_app_installer")


def step_exiled_exchange2(cfg):
    _install_github_app("Exiled Exchange 2 (PoE2 price-check overlay)",
                        "Kvan7", "Exiled-Exchange-2",
                        [r"Setup.*\.exe$", r"win.*\.exe$", r"\.exe$", r"win.*\.zip$"],
                        cfg, cfg_key="exiled_exchange2")


def step_xiletrade(cfg):
    _install_github_app("Xiletrade (PoE1/2 overlay + price checker)",
                        "maxensas", "xiletrade",
                        [r"win.*Setup.*\.exe$", r"Setup.*\.exe$",
                         r"win.*\.zip$", r"\.exe$", r"\.zip$"],
                        cfg, cfg_key="xiletrade")


def step_lailloken(cfg):
    _install_github_app("Lailloken Exile-UI (PoE2 QoL overlay)",
                        "Lailloken", "Exile-UI",
                        [r"win.*\.zip$", r"\.zip$", r"setup.*\.exe$", r"\.exe$"],
                        cfg, cfg_key="lailloken_ui")


def step_obsidian(cfg):
    # Obsidian is the app used to OPEN and explore Kalandra's knowledge vault.
    log("\n=== Obsidian (used to view Kalandra's knowledge database) ===")
    log("  Obsidian opens the exported vault so you can browse all game data and")
    log("  see how skills, uniques, passives and supports interact.")
    if shutil.which("winget"):
        log("  installing via winget...")
        try:
            subprocess.run(["winget", "install", "-e", "--id", "Obsidian.Obsidian",
                            "--silent", "--accept-package-agreements",
                            "--accept-source-agreements"], check=False)
            cfg["obsidian_installed"] = True
            return
        except Exception as e:
            log(f"  winget failed ({e}); falling back to GitHub download.")
    _install_github_app("Obsidian (knowledge-vault viewer)",
                        "obsidianmd", "obsidian-releases",
                        [r"Obsidian.*\.exe$", r"\.exe$"],
                        cfg, cfg_key="obsidian_installer", run_default=True)


# --------------------------------------------------------------------------- #
# component registry + menu
# --------------------------------------------------------------------------- #
COMPONENTS = [
    # id            group     default  installer            label
    ("pip",         "core",   True,  step_pip,
     "Python requirements (REQUIRED — Kalandra won't run without these)"),
    ("luajit",      "extras", True,  step_luajit,
     "LuaJIT engine (for the live Path of Building simulator)"),
    ("rhubarb",     "extras", True,  step_rhubarb,
     "Rhubarb Lip Sync (accurate talking-face mouth shapes)"),
    ("pob_source",  "extras", True,  step_pob_source,
     "PoB 2 source (headless build simulator) — a few hundred MB"),
    ("pob2_app",    "apps",   False, step_pob2_app,
     "Path of Building 2 — the build planner application"),
    ("exiled2",     "apps",   False, step_exiled_exchange2,
     "Exiled Exchange 2 — PoE2 price-check overlay"),
    ("xiletrade",   "apps",   False, step_xiletrade,
     "Xiletrade — PoE1/2 overlay + price checker"),
    ("lailloken",   "apps",   False, step_lailloken,
     "Lailloken Exile-UI — PoE2 quality-of-life overlay"),
    ("obsidian",    "apps",   True,  step_obsidian,
     "Obsidian — views Kalandra's knowledge database (recommended)"),
]
GROUP_TITLES = {"core": "REQUIRED", "extras": "Kalandra engine extras (recommended)",
                "apps": "Companion apps (optional)"}


def choose_components(argv):
    """Decide which components to install from CLI args or an interactive menu."""
    args = [a.lower() for a in argv]
    if "--minimal" in args:
        return ["pip"]
    if "--all" in args:
        return [c[0] for c in COMPONENTS]
    named = [a for a in args if not a.startswith("-")]
    if named:  # explicit groups/ids: e.g. "core extras" or "pip exiled2"
        chosen = []
        for cid, group, *_ in COMPONENTS:
            if cid in named or group in named:
                chosen.append(cid)
        return chosen or ["pip"]

    # Interactive menu.
    log("\nChoose what to install (Enter = accept the [recommended] defaults):\n")
    last_group = None
    for cid, group, default, _fn, label in COMPONENTS:
        if group != last_group:
            log(f"\n  -- {GROUP_TITLES.get(group, group)} --")
            last_group = group
        tag = "[recommended]" if default else "[optional]"
        log(f"    {cid:<11} {tag}  {label}")
    log("")
    chosen = []
    for cid, group, default, _fn, label in COMPONENTS:
        if cid == "pip":
            chosen.append(cid)  # always
            continue
        short = label.split(" — ")[0].split(" (")[0]
        if _ask_yes(f"  Install {cid} ({short})?", default=default):
            chosen.append(cid)
    return chosen


def main():
    global AUTO_YES
    argv = sys.argv[1:]
    low = [a.lower() for a in argv]
    AUTO_YES = ("--all" in low) or ("--yes" in low)

    if sys.maxsize <= 2 ** 32:
        log("WARNING: 64-bit Python is recommended (needed for the game's Oodle DLL).")
    log("Kalandra setup — tools install into: " + TOOLS)
    os.makedirs(TOOLS, exist_ok=True)
    os.makedirs(APPS, exist_ok=True)
    os.makedirs(INSTALLERS, exist_ok=True)

    chosen = choose_components(argv)
    log("\nWill install: " + ", ".join(chosen))

    cfg = load_config()
    by_id = {c[0]: c for c in COMPONENTS}
    for cid in chosen:
        comp = by_id.get(cid)
        if not comp:
            continue
        try:
            comp[3](cfg)        # call the installer fn
        except Exception as e:
            log(f"  [{cid}] failed: {e}")
        save_config(cfg)        # save progress after each step

    log("\n-------------------------------------------------------------")
    log("Setup finished. Paths saved to data_engine/config.json:")
    for k in ("luajit_path", "rhubarb_path", "pob_install_dir", "pob_app_installer",
              "exiled_exchange2", "xiletrade", "lailloken_ui",
              "obsidian_installer", "obsidian_installed"):
        if cfg.get(k):
            log(f"  {k} = {cfg[k]}")
    log("\nLaunch Kalandra with:  python main.py")
    log("Re-open Settings -> Setup & Dependencies to verify everything.")


if __name__ == "__main__":
    main()
