"""
INSTALL_VOICE.PY  --  the free "Kalandra Voice" (offline neural TTS, no account).

Downloads Piper (a fast, MIT-licensed neural text-to-speech engine that runs
entirely on your own PC) plus one curated voice model, into  tools/piper/ .
Nothing needs an account, an API key, or the internet after this one download.

    py -3.12 scripts/install_voice.py                # install the default voice
    py -3.12 scripts/install_voice.py --voice ryan   # pick a different voice
    py -3.12 scripts/install_voice.py --list         # show the voice menu
    py -3.12 scripts/install_voice.py --say "text"   # test the installed voice

After installing, Kalandra's Settings -> "Divine Orb voice" gains a
"Kalandra Voice — free offline neural voice" entry (selected automatically the
first time). The old system voices and the graceful pyttsx3 fallback remain.

Sizes: the Piper engine is ~25 MB; a 'medium' voice is ~60 MB, 'high' ~110 MB.
Voices come from the Piper voices collection on Hugging Face (MIT/CC licenses;
see https://huggingface.co/rhasspy/piper-voices for per-voice details).
"""
import os as _os, sys as _sys
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))   # scripts/ -> repo root
_os.chdir(_ROOT)
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)

import os
import re
import sys
import json
import shutil
import zipfile
import tarfile
import platform
import subprocess
import urllib.request

ROOT = _ROOT
TOOLS = os.path.join(ROOT, "tools")
PIPER_DIR = os.path.join(TOOLS, "piper")
VOICES_DIR = os.path.join(PIPER_DIR, "voices")
CONFIG_PATH = os.path.join(ROOT, "data_engine", "config.json")
UA = {"User-Agent": "Kalandra-Installer"}

# Pinned fallback in case the GitHub "latest release" lookup fails. This is the
# stable Piper release whose CLI (-m model, -f out.wav, text on stdin) the
# voice engine drives.
PIPER_FALLBACK = {
    "windows": ("piper_windows_amd64.zip",
                "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip"),
    "linux":   ("piper_linux_x86_64.tar.gz",
                "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz"),
    "darwin":  ("piper_macos_x64.tar.gz",
                "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_macos_x64.tar.gz"),
}

# Curated voice menu. Every entry is a single-speaker English voice from the
# official Piper voices collection; 'hf' is its folder inside that collection.
# Swap the default by running:  py scripts/install_voice.py --voice <id>
VOICES = {
    "alan":     ("Alan — male, British, warm (medium, ~63 MB)",
                 "en/en_GB/alan/medium/en_GB-alan-medium"),
    "northern": ("Northern English male — male, UK, distinctive (medium, ~63 MB)",
                 "en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium"),
    "cori":     ("Cori — female, Irish lilt, rich (high, ~110 MB)",
                 "en/en_GB/cori/high/en_GB-cori-high"),
    "alba":     ("Alba — female, Scottish, clear (medium, ~63 MB)",
                 "en/en_GB/alba/medium/en_GB-alba-medium"),
    "ryan":     ("Ryan — male, American, deep (high, ~110 MB)",
                 "en/en_US/ryan/high/en_US-ryan-high"),
    "lessac":   ("Lessac — female, American, crisp (high, ~110 MB)",
                 "en/en_US/lessac/high/en_US-lessac-high"),
}
DEFAULT_VOICE = "alan"
HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/"

TEST_LINE = "The mirror remembers its friends, exile."


def log(msg):
    print(msg, flush=True)


# --------------------------------------------------------------------------- #
# small self-contained helpers (mirrors install_dependencies.py)
# --------------------------------------------------------------------------- #
def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_PATH)          # atomic — never truncates on failure


def _download(url, dest, timeout=900):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    return dest


def _extract(archive, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    if archive.lower().endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest_dir)
    else:
        with tarfile.open(archive) as t:
            t.extractall(dest_dir)


def _find(root, *names):
    names = tuple(n.lower() for n in names)
    for r, _d, files in os.walk(root):
        for fn in files:
            if fn.lower() in names:
                return os.path.join(r, fn)
    return None


def _gh_latest_asset(owner, repo, patterns):
    urls = [f"https://api.github.com/repos/{owner}/{repo}/releases/latest",
            f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=10"]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception:
            continue
        releases = data if isinstance(data, list) else [data]
        for pat in patterns:
            rx = re.compile(pat, re.I)
            for rel in releases:
                for a in rel.get("assets", []):
                    if rx.search(a["name"]):
                        return a["name"], a["browser_download_url"]
    return None, None


# --------------------------------------------------------------------------- #
# the install steps
# --------------------------------------------------------------------------- #
def _platform_key():
    s = platform.system().lower()
    if "windows" in s:
        return "windows"
    if "darwin" in s:
        return "darwin"
    return "linux"


def find_piper_exe():
    """Locate an already-installed Piper executable under tools/piper/ or PATH."""
    exe = _find(PIPER_DIR, "piper.exe", "piper") if os.path.isdir(PIPER_DIR) else None
    return exe or shutil.which("piper") or shutil.which("piper.exe")


def install_engine(log=log):
    """Download + unpack the Piper engine. Returns the exe path."""
    exe = find_piper_exe()
    if exe:
        log(f"  Piper engine already present: {exe}")
        return exe
    plat = _platform_key()
    pat = {"windows": r"windows.*amd64.*\.zip$",
           "linux": r"linux.*x86_64.*\.tar\.gz$",
           "darwin": r"macos.*\.tar\.gz$"}[plat]
    name, url = _gh_latest_asset("rhasspy", "piper", [pat])
    if not url:
        name, url = PIPER_FALLBACK[plat]
        log("  (GitHub release lookup failed — using the pinned known-good build)")
    dest = os.path.join(PIPER_DIR, name)
    log(f"  downloading {name} (~25 MB) ...")
    _download(url, dest)
    _extract(dest, PIPER_DIR)
    try:
        os.remove(dest)
    except Exception:
        pass
    exe = _find(PIPER_DIR, "piper.exe", "piper")
    if not exe:
        raise RuntimeError(f"downloaded, but piper executable not found under {PIPER_DIR}")
    if os.name != "nt":
        try:
            os.chmod(exe, 0o755)
        except Exception:
            pass
    log(f"  Piper engine ready: {exe}")
    return exe


def install_voice_model(voice=DEFAULT_VOICE, log=log):
    """Download the .onnx + .onnx.json for a curated voice. Returns model path."""
    if voice not in VOICES:
        raise ValueError(f"unknown voice '{voice}' — choices: {', '.join(VOICES)}")
    _label, hf_path = VOICES[voice]
    fname = hf_path.rsplit("/", 1)[-1]                 # e.g. en_GB-alan-medium
    model = os.path.join(VOICES_DIR, fname + ".onnx")
    if os.path.exists(model) and os.path.getsize(model) > 1_000_000 \
            and os.path.exists(model + ".json"):
        log(f"  Voice already present: {model}")
        return model
    base = HF_BASE + hf_path.rsplit("/", 1)[0] + "/" + fname
    log(f"  downloading voice '{voice}' ({_label.split(' (')[0]}) ...")
    _download(base + ".onnx", model)
    _download(base + ".onnx.json", model + ".json")
    if os.path.getsize(model) < 1_000_000:
        raise RuntimeError("voice model download looks truncated — try again")
    log(f"  Voice ready: {model}")
    return model


def smoke_test(exe, model, log=log):
    """Synthesize one line to prove the voice actually speaks. Returns True/False."""
    out = os.path.join(PIPER_DIR, "voice_test.wav")
    try:
        os.remove(out)      # a stale wav from a previous run must never count
    except OSError:
        pass
    try:
        proc = subprocess.run(
            [exe, "-m", model, "-f", out],
            input=TEST_LINE.encode("utf-8"),
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            cwd=os.path.dirname(exe), timeout=120)
        ok = (proc.returncode == 0 and os.path.exists(out)
              and os.path.getsize(out) > 10_000)
        if ok:
            log(f"  Voice test OK — listen to it: {out}")
        else:
            tail = (proc.stderr or b"")[-300:].decode("utf-8", "replace")
            log(f"  Voice test produced no audio. Piper said: {tail}")
        return ok
    except Exception as e:
        log(f"  Voice test failed: {e}")
        return False


def install(cfg=None, voice=DEFAULT_VOICE, log=log, write_config=None):
    """Full install: engine + voice + smoke test + config keys.

    cfg: a config dict to update IN PLACE. If None, the config file is loaded
    and saved here (write_config defaults accordingly). Callers that own the
    config (the GUI, install_dependencies) pass their dict and save it
    themselves, so nobody's in-memory copy clobbers anyone else's keys.

    Returns (ok: bool, message: str).
    """
    own_cfg = cfg is None
    if own_cfg:
        cfg = load_config()
    if write_config is None:
        write_config = own_cfg
    try:
        exe = install_engine(log=log)
        model = install_voice_model(voice=voice, log=log)
    except Exception as e:
        return False, f"Download failed: {e}"

    # Prove the voice actually speaks BEFORE selecting it, so a corrupt
    # download can never leave a broken voice active in the config.
    ok = smoke_test(exe, model, log=log)

    cfg["piper_path"] = exe        # recorded either way so Setup&Deps can Verify
    cfg["piper_voice"] = model
    # First successful install selects the Kalandra Voice automatically; a
    # voice the user explicitly picked before is respected, and a failed smoke
    # test never auto-selects.
    if ok and not cfg.get("voice_id"):
        cfg["voice_id"] = "piper"
    if write_config:
        save_config(cfg)
    msg = ("Kalandra Voice installed — the Orb speaks with it now "
           "(Settings → Divine Orb voice)." if ok else
           "Installed, but the test synth failed — check tools/piper/ and re-run "
           "scripts/install_voice.py")
    return ok, msg


def main():
    args = [a.lower() for a in sys.argv[1:]]
    if "--list" in args:
        log("Available voices (install with --voice <id>):\n")
        for vid, (label, _p) in VOICES.items():
            mark = "  (default)" if vid == DEFAULT_VOICE else ""
            log(f"  {vid:<9} {label}{mark}")
        log("\nPreview any voice in your browser first: https://rhasspy.github.io/piper-samples/")
        return
    if "--say" in args:
        i = args.index("--say")
        text = sys.argv[1:][i + 1] if len(sys.argv[1:]) > i + 1 else TEST_LINE
        cfg = load_config()
        exe = cfg.get("piper_path")
        if not (exe and os.path.exists(exe)):        # stale config path -> re-find
            exe = find_piper_exe()
        model = cfg.get("piper_voice")
        if not (exe and os.path.exists(exe) and model and os.path.exists(model)):
            log("Kalandra Voice isn't installed yet (or moved) — run this script "
                "without --say to install/repair it first.")
            return
        out = os.path.join(PIPER_DIR, "voice_test.wav")
        try:
            os.remove(out)          # never report a stale wav as fresh output
        except OSError:
            pass
        proc = subprocess.run([exe, "-m", model, "-f", out], input=text.encode("utf-8"),
                              cwd=os.path.dirname(exe), timeout=120)
        if proc.returncode != 0 or not os.path.exists(out):
            log("Synthesis failed — run scripts/install_voice.py (no flags) to repair.")
            return
        log(f"Wrote {out}")
        if os.name == "nt":
            os.startfile(out)  # noqa — Windows only
        return

    voice = DEFAULT_VOICE
    if "--voice" in args:
        i = args.index("--voice")
        if len(args) > i + 1:
            voice = args[i + 1]
    log("=== Kalandra Voice — free offline neural voice (no account needed) ===")
    ok, msg = install(voice=voice)
    log("\n" + msg)


if __name__ == "__main__":
    main()
