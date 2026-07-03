"""
SETUP_POB_SIM.PY  --  one-time setup for the headless Path of Building 2 simulator.

We do NOT download or bundle Path of Building (that keeps this project free of
PoB's GPL-3.0 obligations). Instead you install PoB2 yourself, and this script:
  1. Checks for LuaJIT on your PATH.
  2. Locates your installed Path of Building 2 (or uses pob_install_dir from
     data_engine/config.json).
  3. Copies the Lua harness into that install folder.
  4. Runs a quick smoke test.

Usage:   python setup_pob_sim.py
"""

import os
import sys
import json
import shutil

HARNESS_SRC = os.path.join("core_engine", "pob_headless.lua")
CONFIG_PATH = os.path.join("data_engine", "config.json")


def load_cfg():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    print("=== Kalandra :: PoB2 simulator setup (user-installed PoB) ===\n")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from core_engine.pob_sim import find_pob_install, PoBSimulator

    luajit = shutil.which("luajit") or shutil.which("luajit.exe")
    print(f"[{'OK' if luajit else 'MISS'}] LuaJIT: {luajit or 'not found on PATH'}")
    if not luajit:
        print("       Install LuaJIT and add luajit.exe to PATH, then re-run.")

    cfg = load_cfg()
    install = find_pob_install(cfg.get("pob_install_dir"))
    if install:
        print(f"[OK]   Path of Building 2 found: {install}")
    else:
        print("[MISS] Path of Building 2 install not found.")
        print("       Install PoB2 from https://pathofbuilding.community/ , or set")
        print('       "pob_install_dir" in data_engine/config.json to the folder that')
        print("       contains HeadlessWrapper.lua.")

    if install and os.path.exists(HARNESS_SRC):
        dst = os.path.join(install, "pob_headless.lua")
        try:
            shutil.copyfile(HARNESS_SRC, dst)
            print(f"[OK]   Harness copied to {dst}")
        except Exception as e:
            print(f"[WARN] Could not copy harness ({e}). You may need to run this")
            print("       terminal as administrator (Program Files is protected).")

    print("\n[..]   Smoke test (ping the engine)...")
    try:
        sim = PoBSimulator(logger=lambda c, m: print(f"   [{c}] {m}"))
        if sim.available and sim.start():
            print("[OK]   Headless PoB responded. Simulator is ready.")
            sim.stop()
        else:
            print("[INFO] Not ready yet:")
            print(sim.availability_message())
    except Exception as e:
        print(f"[INFO] Smoke test skipped: {e}")

    print("\nDone. See POB_SIM_SETUP.md if anything needs attention.")


if __name__ == "__main__":
    main()
