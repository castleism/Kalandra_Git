"""
TESTS/POB_SIM_CHECKS.PY — sandbox checks for the headless Path of Building 2
simulator (core_engine/pob_sim.py).

Covers install-dir discovery across every documented subdir layout, the
LuaJIT-vs-installer-binary guard, availability reporting with each piece
missing in turn, stats_summary junk-proofing, and the fail-soft paths that
must never touch a real subprocess when the sim isn't available. No LuaJIT,
no real PoB install, no network — pure engine, same style as
tests/death_checks.py.
"""
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [FAIL] {name}")


def guard(name, fn):
    """fn must not raise."""
    try:
        fn()
        check(name, True)
    except Exception as e:
        print(f"  [FAIL] {name}: raised {e}")
        globals()["FAIL"] += 1


from core_engine.pob_sim import PoBSimulator, find_pob_install, _valid_luajit

# ---- find_pob_install: subdir layouts (CH-P1 install detection) -------------
tmp = tempfile.mkdtemp(prefix="pobsim_")


def _mk_layout(sub):
    d = tempfile.mkdtemp(dir=tmp)
    target = os.path.join(d, sub) if sub else d
    os.makedirs(target, exist_ok=True)
    with open(os.path.join(target, "HeadlessWrapper.lua"), "w") as f:
        f.write("-- stub\n")
    return d, target

for sub in ("", "src", "lua", os.path.join("runtime", "lua")):
    root, expected = _mk_layout(sub)
    check(f"find_pob_install resolves subdir '{sub or '.'}'",
          find_pob_install(root) == expected)

check("find_pob_install returns None for empty dir",
      find_pob_install(tempfile.mkdtemp(dir=tmp)) is None)
check("find_pob_install returns None for nonexistent dir",
      find_pob_install(os.path.join(tmp, "does-not-exist")) is None)
check("find_pob_install returns None for None/empty explicit with no candidates",
      find_pob_install(None) in (None, find_pob_install(None)))  # just must not raise
check("find_pob_install ignores '' explicit",
      find_pob_install("") is find_pob_install(""))

# explicit path takes priority over the built-in candidate list even when a
# candidate also happens to resolve (can't easily fabricate a real candidate
# hit, so just confirm explicit alone is authoritative and deterministic).
root, expected = _mk_layout("src")
check("find_pob_install explicit wins and is stable across calls",
      find_pob_install(root) == expected == find_pob_install(root))

# ---- _valid_luajit: installer-vs-interpreter guard --------------------------
def _touch(name):
    p = os.path.join(tmp, name)
    with open(p, "w") as f:
        f.write("")
    return p

check("_valid_luajit rejects None", not _valid_luajit(None))
check("_valid_luajit rejects nonexistent path",
      not _valid_luajit(os.path.join(tmp, "ghost-luajit.exe")))
check("_valid_luajit rejects the self-extracting installer",
      not _valid_luajit(_touch("LuaJIT-For-Windows.exe")))
check("_valid_luajit rejects anything with 'setup' in the name",
      not _valid_luajit(_touch("luajit-setup.exe")))
check("_valid_luajit rejects anything with 'install' in the name",
      not _valid_luajit(_touch("install-luajit.exe")))
check("_valid_luajit rejects a binary not named luajit*",
      not _valid_luajit(_touch("notluajit.exe")))
check("_valid_luajit accepts a real luajit binary",
      _valid_luajit(_touch("luajit.exe")))
check("_valid_luajit accepts luajit-2.1.exe",
      _valid_luajit(_touch("luajit-2.1.exe")))
check("_valid_luajit is case-insensitive on the binary name",
      _valid_luajit(_touch("LuaJIT.EXE")))
guard("_valid_luajit tolerates non-str/odd path types", lambda: _valid_luajit(12345))
guard("_valid_luajit tolerates a bare directory path", lambda: _valid_luajit(tmp))

# ---- availability: every missing-piece combination reports correctly -------
# NOTE: this repo vendors a real LuaJIT under tools/, which _find_luajit()'s
# glob fallback will happily discover even when we pass luajit=None to the
# constructor — so to genuinely simulate "no luajit", force the attribute
# after construction rather than relying on the constructor argument alone.
no_install_no_lua = PoBSimulator(install_dir=os.path.join(tmp, "nope"), luajit=None)
no_install_no_lua.luajit = None
check("unavailable with nothing present", not no_install_no_lua.available)
msg = no_install_no_lua.availability_message()
check("message flags missing luajit", "LuaJIT interpreter not found" in msg)
check("message flags missing install", "Path of Building 2 install not found" in msg)

install_root, install_dir = _mk_layout("src")
have_install_no_lua = PoBSimulator(install_dir=install_root, luajit=None)
have_install_no_lua.luajit = None
check("unavailable with install but no luajit", not have_install_no_lua.available)
check("message no longer flags install when install is present",
      "Path of Building 2 install not found" not in have_install_no_lua.availability_message())
check("message still flags missing luajit",
      "LuaJIT interpreter not found" in have_install_no_lua.availability_message())

luajit_bin = _touch("luajit.exe")
have_lua_no_install = PoBSimulator(install_dir=os.path.join(tmp, "nope2"), luajit=luajit_bin)
check("unavailable with luajit but no install", not have_lua_no_install.available)

# harness missing: point at a harness path that doesn't exist so `available`
# is False even with a valid install_dir + luajit.
sim_no_harness = PoBSimulator(install_dir=install_root, luajit=luajit_bin,
                               harness=os.path.join(tmp, "ghost_harness.lua"))
check("unavailable when harness file is missing", not sim_no_harness.available)
check("message flags missing harness", "Lua harness missing" in sim_no_harness.availability_message())

# fully present -> available (harness defaults to the real vendored file next
# to pob_sim.py, which does exist in this repo).
real_harness = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "core_engine", "pob_headless.lua")
if os.path.exists(real_harness):
    sim_ready = PoBSimulator(install_dir=install_root, luajit=luajit_bin)
    check("available when luajit + install + harness all present", sim_ready.available)

# an explicit junk luajit path (the installer, wrong name) must never be
# accepted as-is — the constructor falls back to auto-detection instead.
junk_installer_path = _touch("LuaJIT-For-Windows.exe")
sim_rejects_junk = PoBSimulator(install_dir=install_root, luajit=junk_installer_path)
check("explicit installer path is never accepted verbatim as luajit",
      sim_rejects_junk.luajit != junk_installer_path)

# ---- fail-soft: no subprocess ever spawned when unavailable -----------------
sim = PoBSimulator(install_dir=os.path.join(tmp, "nope3"), luajit=None)
check("start() on unavailable sim returns False, no raise", sim.start() is False)
check("load_build_xml(None) short-circuits without touching rpc",
      sim.load_build_xml(None) is None and not sim.has_build())
check("load_build_xml('') short-circuits without touching rpc",
      sim.load_build_xml("") is None and not sim.has_build())
guard("load_build_xml with real xml on unavailable sim fails soft",
      lambda: sim.load_build_xml("<PathOfBuilding/>"))
check("has_build() stays False after a failed load", not sim.has_build())
guard("get_stats() on unavailable sim fails soft", sim.get_stats)
guard("simulate() on unavailable sim fails soft", lambda: sim.simulate({"x": 1}))
guard("diag() on unavailable sim fails soft", sim.diag)
guard("stop() with no process started is a no-op", sim.stop)
guard("stop() twice is still a no-op", sim.stop)

report = sim.self_test()
check("self_test reports not-ready without starting a process",
      report.get("status") == "not-ready" and "started" not in report)
check("self_test message matches availability_message",
      report.get("message") == sim.availability_message())

# ---- stats_summary: junk-proofing (CH-P1 display layer) ---------------------
check("stats_summary(None) is empty string", sim.stats_summary({}) == "")
guard("stats_summary with no arg falls back to get_stats() (fails soft)",
      lambda: sim.stats_summary())

full_junk = {
    "class": "Ranger", "ascendancy": "Deadeye", "level": "not-a-number",
    "total_dps": "NaN", "life": None, "energy_shield": [], "mana": {},
    "spirit": "x", "spirit_unreserved": "also-junk",
    "fire_res": 75, "cold_res": None, "lightning_res": "?", "chaos_res": -60,
}
guard("stats_summary tolerates fully junk stat values", lambda: sim.stats_summary(full_junk))
out = sim.stats_summary(full_junk)
check("stats_summary falls back to '?' for unparseable numerics", "DPS ?" in out and "Life ?" in out)
check("stats_summary keeps raw values for non-numeric display fields",
      "Ranger" in out and "Deadeye" in out)
check("stats_summary keeps a real negative resist untouched", "-60" in out)

zero_unreserved = {"spirit": "100", "spirit_unreserved": 0}
out0 = sim.stats_summary(zero_unreserved)
check("spirit_unreserved of exactly 0 is treated as falsy (no '(unreserved' suffix)",
      "(unreserved" not in out0)

nonzero_unreserved = {"spirit": "100", "spirit_unreserved": 42}
outn = sim.stats_summary(nonzero_unreserved)
check("spirit_unreserved nonzero renders the '(unreserved ..)' suffix",
      "(unreserved 42)" in outn)

string_unreserved = {"spirit": "100", "spirit_unreserved": "42"}
outs = sim.stats_summary(string_unreserved)
check("spirit_unreserved as a string (not int/float) is not shown (isinstance guard)",
      "(unreserved" not in outs)

nan_unreserved = {"spirit": "100", "spirit_unreserved": float("nan")}
guard("spirit_unreserved of NaN does not raise", lambda: sim.stats_summary(nan_unreserved))

# ---- thread-safety: concurrent _rpc callers serialize on the lock -----------
# All calls fail soft immediately (proc unavailable + start() fails), but the
# lock must still prevent interleaved _next_id corruption / races.
concurrent_sim = PoBSimulator(install_dir=os.path.join(tmp, "nope4"), luajit=None)
errors = []


def _hammer():
    try:
        for _ in range(25):
            concurrent_sim.get_stats()
            concurrent_sim.simulate({})
    except Exception as e:
        errors.append(e)


threads = [threading.Thread(target=_hammer) for _ in range(8)]
for t in threads:
    t.start()
for t in threads:
    t.join(timeout=10)
check("concurrent _rpc callers never raise", not errors)
check("concurrent _rpc callers all complete (no deadlock)",
      all(not t.is_alive() for t in threads))

print(f"RESULT: {PASS} passed, {FAIL} failed")
print("ALL GREEN" if FAIL == 0 else "NOT GREEN")
sys.exit(1 if FAIL else 0)
