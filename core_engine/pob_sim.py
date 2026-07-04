"""
CORE_ENGINE/POB_SIM.PY
Purpose: A headless Path of Building 2 "sandbox" the AI orb can drive to answer
build / gear / mechanics questions with REAL numbers -- without the user building
anything by hand.

LICENSING NOTE: We do NOT bundle Path of Building. The user installs PoB2 (or the
portable build) themselves, and we drive *their* copy as a separate program over
stdio. Calling a separate, user-installed GPL program at arm's length is "mere
aggregation" and does not impose GPL on this app -- which keeps Kalandra's
licensing flexible. (This is not legal advice.)

How it works (same proven pattern as pob2-mcp):
  * PoB2 ships `HeadlessWrapper.lua`, which boots its calc engine with no GUI.
  * We run it under LuaJIT as a subprocess and talk over a tiny line-delimited
    JSON-RPC protocol (one JSON per line in, one per line out).

Requirements (the user provides these; nothing is redistributed by us):
  * LuaJIT on PATH.
  * An installed Path of Building 2 (we auto-detect common locations, or set
    `pob_install_dir` in data_engine/config.json).

Until both are present this class reports clear instructions and the rest of the
app runs normally.
"""

import os
import json
import shutil
import threading
import subprocess
import queue as _queue

HARNESS_NAME = "pob_headless.lua"

# Common install locations for Path of Building 2 (Windows). The folder must
# contain HeadlessWrapper.lua (the standalone install ships the Lua source).
INSTALL_CANDIDATES = [
    os.path.expandvars(r"%PROGRAMFILES(X86)%\Path of Building Community (PoE2)"),
    os.path.expandvars(r"%PROGRAMFILES%\Path of Building Community (PoE2)"),
    os.path.expandvars(r"%PROGRAMFILES(X86)%\Path of Building Community"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Path of Building Community (PoE2)"),
    os.path.expanduser(r"~\Path of Building (PoE2)"),
    os.path.expanduser(r"~\AppData\Roaming\Path of Building Community (PoE2)"),
]


def find_pob_install(explicit=None):
    """Return the folder that CONTAINS HeadlessWrapper.lua, or None.

    The Lua source can sit at the install root, or under src/ or lua/ depending
    on how PoB2 was installed (standalone vs source checkout), so we check all of
    those for each candidate."""
    cands = []
    if explicit:
        cands.append(explicit)
    cands.extend(INSTALL_CANDIDATES)
    subdirs = ("", "src", "lua", os.path.join("runtime", "lua"))
    for d in cands:
        if not d or not os.path.isdir(d):
            continue
        for sub in subdirs:
            cand = os.path.join(d, sub) if sub else d
            if os.path.exists(os.path.join(cand, "HeadlessWrapper.lua")):
                return cand
    return None


def _valid_luajit(path):
    """True only for a real luajit interpreter binary. Rejects the
    'LuaJIT-For-Windows.exe' SELF-EXTRACTING INSTALLER, which people (and the
    installer UI) naturally point config at — running it would pop an
    extraction GUI instead of executing our harness."""
    if not path or not os.path.exists(path):
        return False
    base = os.path.basename(str(path)).lower()
    if "for-windows" in base or "setup" in base or "install" in base:
        return False
    return base.startswith("luajit")


class PoBSimulator:
    def __init__(self, install_dir=None, luajit=None, harness=None, logger=None):
        self.install_dir = find_pob_install(install_dir)
        # Validate even an explicitly-passed path: config.json's luajit_path
        # frequently ends up pointing at the installer, not the interpreter.
        self.luajit = luajit if _valid_luajit(luajit) else self._find_luajit()
        self.harness = harness or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                               HARNESS_NAME)
        self.logger = logger

        self.proc = None
        self._lock = threading.Lock()
        self._out_q = _queue.Queue()
        self._reader = None
        self._next_id = 1
        self._loaded_code = None
        from collections import deque as _deque
        self._stderr = _deque(maxlen=200)   # recent engine stderr, for diagnostics

    # -- helpers ---------------------------------------------------------------
    def _log(self, msg):
        if self.logger:
            try:
                self.logger("POB", msg)
            except Exception:
                pass

    @staticmethod
    def _find_luajit():
        # config first (written by the installer's Check Location / install_dependencies)
        try:
            with open(os.path.join("data_engine", "config.json"), "r", encoding="utf-8") as f:
                cp = json.load(f).get("luajit_path")
            if _valid_luajit(cp):
                return cp
        except Exception:
            pass
        # NOTE: "LuaJIT-For-Windows.exe" is the self-extracting INSTALLER, not the
        # interpreter — running it would pop a GUI, not execute our script. We only
        # ever resolve to the real luajit(.exe) binary (it lands in .../bin/).
        for name in ("luajit", "luajit.exe", "luajit-2.1.exe"):
            p = shutil.which(name)
            if p:
                return p
        env = os.environ.get("LUAJIT_PATH")
        if _valid_luajit(env):
            return env
        # vendored under tools/ — find the actual interpreter (bin/luajit.exe),
        # never the installer.
        import glob as _glob
        for pat in ("luajit.exe", "luajit-2.1.exe", "luajit"):
            hits = [h for h in _glob.glob(os.path.join("tools", "**", pat), recursive=True)
                    if os.path.basename(h).lower() != "luajit-for-windows.exe"]
            if hits:
                return os.path.abspath(hits[0])
        return None

    @property
    def available(self):
        return bool(self.luajit and self.install_dir
                    and os.path.exists(os.path.join(self.install_dir, "HeadlessWrapper.lua"))
                    and os.path.exists(self.harness))

    def availability_message(self):
        if self.available:
            return "PoB simulator ready."
        bits = ["PoB sandbox simulator isn't ready. Run:  python setup_pob_sim.py", ""]
        if not self.luajit:
            bits.append("  - LuaJIT interpreter not found. Note: \"LuaJIT-For-Windows.exe\"")
            bits.append("    is the INSTALLER, not LuaJIT itself — point \"luajit_path\" at")
            bits.append("    the extracted ...\\bin\\luajit.exe instead.")
        if not self.install_dir:
            bits.append("  - Path of Building 2 install not found. Install it, or set")
            bits.append("    \"pob_install_dir\" in data_engine/config.json to its folder")
            bits.append("    (the folder that contains HeadlessWrapper.lua).")
        if not os.path.exists(self.harness):
            bits.append(f"  - Lua harness missing ({self.harness}).")
        return "\n".join(bits)

    # -- process management ----------------------------------------------------
    def start(self):
        if not self.available:
            self._log(self.availability_message())
            return False
        if self.proc and self.proc.poll() is None:
            return True
        try:
            # PoB's native modules (lua-utf8.dll, lzip.dll, socket.dll, lcurl.dll)
            # depend on lua51.dll, all in ../runtime. Put that on PATH so Windows
            # resolves those dependencies when the modules load.
            env = os.environ.copy()
            runtime = os.path.join(os.path.dirname(os.path.normpath(self.install_dir)),
                                   "runtime")
            if os.path.isdir(runtime):
                env["PATH"] = runtime + os.pathsep + env.get("PATH", "")
            # Hide the LuaJIT console window on Windows (it popped up empty before).
            creationflags = 0
            if os.name == "nt":
                creationflags = 0x08000000  # CREATE_NO_WINDOW
            # Run from the PoB source dir (where HeadlessWrapper.lua lives) so its
            # relative `require`s / loadfiles resolve.
            self.proc = subprocess.Popen(
                [self.luajit, os.path.abspath(self.harness)],
                cwd=self.install_dir, env=env, creationflags=creationflags,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1)
        except Exception as e:
            self._log(f"Could not start headless PoB: {e}")
            return False

        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        # Drain stderr too, or a chatty engine could block the pipe; keep the tail
        # for diagnostics.
        threading.Thread(target=self._stderr_loop, daemon=True).start()
        if self._rpc("ping", {}, timeout=30) is None:
            self._log("Headless PoB did not respond to ping. Run the self-test "
                      "(Dashboard > Build Sim > Run self-test) and send me the output.")
            return False
        self._log("Headless PoB engine ready.")
        return True

    def _read_loop(self):
        for line in self.proc.stdout:
            line = line.strip()
            if line:
                self._out_q.put(line)
        self._out_q.put(None)

    def _stderr_loop(self):
        try:
            for line in self.proc.stderr:
                line = line.rstrip("\n")
                if line:
                    self._stderr.append(line)
        except Exception:
            pass

    def _rpc(self, method, params, timeout=60):
        if not (self.proc and self.proc.poll() is None):
            if not self.start():
                return None
        import time
        with self._lock:
            rid = self._next_id
            self._next_id += 1
            req = json.dumps({"id": rid, "method": method, "params": params})
            try:
                self.proc.stdin.write(req + "\n")
                self.proc.stdin.flush()
            except Exception as e:
                self._log(f"PoB write failed: {e}")
                return None
            deadline = time.monotonic() + timeout
            while True:
                remaining = max(0.1, deadline - time.monotonic())
                try:
                    line = self._out_q.get(timeout=remaining)
                except _queue.Empty:
                    self._log(f"PoB RPC '{method}' timed out.")
                    return None
                if line is None:
                    self._log("PoB process ended unexpectedly.")
                    return None
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                if msg.get("id") == rid:
                    if msg.get("error"):
                        self._log(f"PoB error on {method}: {msg['error']}")
                        return None
                    return msg.get("result")

    def stop(self):
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass
            self.proc = None

    # -- public simulation API -------------------------------------------------
    def load_build_xml(self, xml):
        """Load a build from already-decoded PoB XML (the reliable path — Python
        decodes the import code, so we never depend on PoB's in-Lua decoder)."""
        if not xml:
            return None
        r = self._rpc("load_xml", {"xml": xml}, timeout=90)
        if r is not None:
            self._loaded_code = "xml"
        return r

    def load_build(self, pob_code):
        # Back-compat: callers that only have the code. Prefer load_build_xml.
        r = self._rpc("load_xml", {"xml": pob_code})
        if r is not None:
            self._loaded_code = pob_code
        return r

    def get_stats(self):
        return self._rpc("get_stats", {})

    def has_build(self):
        return self._loaded_code is not None

    def simulate(self, changes):
        return self._rpc("simulate", {"changes": changes}, timeout=120)

    def diag(self):
        """Ask the harness what THIS PoB install exposes (functions, the build
        object, real stat-output keys). Used by self_test()."""
        return self._rpc("diag", {}, timeout=45)

    def self_test(self):
        """One-call health check + diagnostic. Returns a dict that pinpoints any
        version mismatch — paste it back to the developer to fix in one round."""
        report = {
            "luajit": self.luajit,
            "src_dir": self.install_dir,
            "harness": self.harness,
            "available": self.available,
        }
        if not self.available:
            report["status"] = "not-ready"
            report["message"] = self.availability_message()
            return report
        started = self.start()
        report["started"] = started
        report["diag"] = self.diag() if started else None
        # Whatever build is currently loaded in the engine (default empty build =>
        # level 0; YOUR character once you've loaded it in the overlay).
        report["current_loaded_build"] = (
            "your character" if self.has_build() else "PoB default (empty) build")
        report["current_stats"] = self.get_stats() if started else None
        report["stderr_tail"] = list(self._stderr)[-25:]
        report["status"] = "ok" if (report.get("diag") and report["diag"].get("has_output")) \
            else "engine-running-but-no-output" if started else "failed-to-start"
        return report

    def stats_summary(self, stats=None):
        s = stats or self.get_stats()
        if not s:
            return ""
        def g(k):
            return s.get(k, "?")
        def i(k):
            v = s.get(k)
            try:
                return f"{int(round(float(v))):,}"
            except (TypeError, ValueError):
                return "?"
        spirit = i("spirit")
        sun = s.get("spirit_unreserved")
        spirit_str = spirit + (f" (unreserved {int(round(float(sun)))})"
                               if isinstance(sun, (int, float)) and sun else "")
        return (f"Class {g('class')}/{g('ascendancy')} Lv{g('level')} | "
                f"DPS {i('total_dps')} | Life {i('life')} | ES {i('energy_shield')} | "
                f"Mana {i('mana')} | Spirit {spirit_str} | EHP {i('ehp')} | "
                f"Res f/c/l {g('fire_res')}/{g('cold_res')}/{g('lightning_res')} "
                f"chaos {g('chaos_res')}")


if __name__ == "__main__":
    sim = PoBSimulator(logger=lambda c, m: print(f"[{c}] {m}"))
    print("install:", sim.install_dir, "| luajit:", sim.luajit)
    print("available:", sim.available)
    if not sim.available:
        print(sim.availability_message())
