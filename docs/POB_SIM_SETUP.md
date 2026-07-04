# Path of Building 2 Sandbox Simulator — Setup

This lets the Divine Orb answer build / gear / mechanics questions with **real
Path of Building numbers**, by running PoB2's calculation engine headlessly and
driving it from the AI. You don't have to build anything by hand — load a build
code once, then ask "how much more DPS if I swap in X?" and it simulates.

## What it needs (you provide PoB — we don't bundle it)

1. **LuaJIT** on your PATH (`luajit` / `luajit.exe`). PoB's engine runs under it.
2. **Path of Building 2 installed** (https://pathofbuilding.community/). Its folder
   contains `HeadlessWrapper.lua`, which boots the engine without a GUI. We
   auto-detect common install locations, or you can set `pob_install_dir` in
   `data_engine/config.json`.
3. The Lua harness `core_engine/pob_headless.lua` (already in this project).

We deliberately do **not** download or bundle PoB (that avoids its GPL-3.0
copyleft and keeps Kalandra's licensing flexible). We just drive your installed
copy as a separate program.

## One-time setup

```
python scripts/setup_pob_sim.py
```

That checks LuaJIT, finds your PoB2 install, copies the harness into it, and pings
the engine. If LuaJIT or PoB2 is missing it tells you exactly what to do.
(If your PoB2 lives in Program Files, run the terminal as administrator so the
harness can be copied in — or set `pob_install_dir` to a writable portable copy.)

## How it works

`core_engine/pob_sim.py` launches `luajit pob_headless.lua` (working dir = the
PoB2 repo) and talks to it over a line-delimited JSON-RPC protocol on stdio:

- `load_build {code}` → decode a PoB import code, load it, return stats
- `get_stats {}` → current DPS / Life / ES / EHP / resistances
- `simulate {changes}` → apply a hypothetical change, recompute, return the delta

The orb loads whatever PoB code you paste in the Character panel, then your
spoken questions are answered using the live computed numbers as context.

## Honest status / where it may need a tweak

I could fully test the **Python** driver (process management + JSON-RPC) but I
cannot run PoB2's Lua engine in my build environment, so the harness is written
against PoB's documented headless entry points and may need a small adjustment to
match your installed PoB2 version. The spots to look at are marked `-- ADJUST:`
in `core_engine/pob_headless.lua`:

- the base64 + `Inflate` calls used to decode a build code,
- the `loadBuildFromXML` loader name,
- the output field names (`TotalDPS`, `Life`, …) and `build.spec` class fields.

If `scripts/setup_pob_sim.py`'s smoke test prints an error, copy it to me and I'll map
the exact names for the current PoB2 release. Run the harness directly to see
engine logs (they go to stderr):

```
cd "<your Path of Building 2 install folder>"
echo {"id":1,"method":"ping","params":{}} | luajit pob_headless.lua
```

## Licensing

Path of Building is **GPL-3.0**, but we do **not** bundle it — you install it and
we invoke your copy at arm's length (mere aggregation), so Kalandra itself is not
forced to be GPL. Still credit the Path of Building Community. See `LICENSE.md`.
