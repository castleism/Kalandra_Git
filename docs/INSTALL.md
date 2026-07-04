# Kalandra — Install Guide

Kalandra is a desktop companion/overlay for Path of Exile 2: a transparent
Mirror-of-Kalandra overlay with a talking Divine Orb you can speak or type to,
a local knowledge database, Path of Building integration, and (experimental)
in-process game-data extraction.

This is a development snapshot. It runs from source with Python — there is no
compiled .exe yet.

## 1. Requirements

- **Windows 10/11, 64-bit** (64-bit Python is required for the game's Oodle DLL).
- **Python 3.12** recommended. Install from <https://python.org> and tick
  "Add Python to PATH", or run:
  ```
  winget install -e --id Python.Python.3.12
  ```

## 2. Install

1. Unzip this folder somewhere permanent (e.g. `D:\GIT\Kalandra`).
2. Double-click **`launchers/Install Dependencies.bat`** (or run
   `py -3.12 scripts/install_dependencies.py`). You'll get a menu:

   - **REQUIRED** — Python packages (PyQt6, faster-whisper, etc.). Always installed.
   - **Engine extras (recommended)** — LuaJIT + Rhubarb + the PoB 2 source used by
     the live build simulator and the talking face.
   - **Companion apps (optional)** — pick any you want; each downloads the latest
     release automatically:
       - **Path of Building 2** — the build planner app
       - **Exiled Exchange 2** — PoE2 price-check overlay
       - **Xiletrade** — PoE1/2 overlay + price checker
       - **Lailloken Exile-UI** — PoE2 quality-of-life overlay

   App installers (`.exe`) are saved under `tools/installers/` and you choose
   whether to run them; portable apps (`.zip`) are unpacked under `tools/apps/`.

   Non-interactive options:
   ```
   py -3.12 scripts/install_dependencies.py --all       # everything, no prompts
   py -3.12 scripts/install_dependencies.py --minimal   # Python packages only
   py -3.12 scripts/install_dependencies.py --yes core extras   # named groups
   ```

3. Copy `data_engine/config.template.json` to `data_engine/config.json` and edit
   it (or just launch — Kalandra writes a default config on first run). Set
   `game_install_dir` to your Path of Exile 2 folder if you want game-data
   extraction, e.g.
   `"game_install_dir": "D:\\SteamLibrary\\steamapps\\common\\Path of Exile 2"`.

## 3. Run

```
python main.py
```
or double-click **`launchers/Windows Diagnostic Launcher.bat`** (keeps the console open so
you can read the logs).

Drag the mirror anywhere. The five medallions:

| Medallion | Single click | Double click |
|-----------|--------------|--------------|
| Top-left (ruby) | Voice channel (speak to the Orb) | Open the text-chat window |
| Top-middle | Database sync / scour | — |
| Top-right | Character / build selector | — |
| Bottom-left | Screenshot | Screen recording |
| Bottom-right | Settings & accounts | — |

Right-click + `Esc` exits.

## 4. API keys (for the AI brain)

The Orb's spoken/typed answers use a cloud model. In **Settings → AI brain**,
pick OpenAI or Gemini, then paste an API key (there's a "Get a key" button).
Keys are stored only in the OS keychain (via `keyring`) — never in plaintext.

## 5. Notes

- The overlay launches even if optional dependencies are missing; each feature
  reports an install hint if its libraries aren't present.
- Game-data extraction is experimental. Settings → Setup & Dependencies →
  "Set up & test in-process extractor" reports exactly what works on your machine.
- Path of Building is **user-installed**, not bundled, by design.
- See `docs/SECURITY_AND_PRIVACY.md`, `docs/ROADMAP.md`, and the other `*_SETUP.md` docs
  for details.

## 6. What's NOT in this snapshot

If this zip was produced without access to the original machine, two local
items may be missing and should be copied from your working install:

- `gui_overlay/assets/` — the mirror graphic (`mirror_of_kalandra.png`), the
  orb (`divine_orb.png`), and optional viseme sprites. See the README in that
  folder for exact filenames. The app still launches without them (it draws a
  procedural mirror/orb).
- `data_engine/schema.min.json` — the table schema used by the game-data
  extractor.

Everything else (all code + the installer) is included.
