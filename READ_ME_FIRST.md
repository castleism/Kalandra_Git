# Kalandra — Read Me First

Kalandra is a desktop overlay and companion app for **Path of Exile 2**. A floating
"mirror" with a talking Divine Orb sits on top of the game; behind it is an AI
assistant grounded in real PoE2 data, a live Path of Building engine, and a
single-pane dashboard of tools. This document is the complete breakdown: what it
is, what to have ready, how every button works, what's finished, what's a
placeholder, and where it's going.

> Pre-release. Version is shown in the title bars (e.g. `v0.1.0-pre.1`).

---

## 1. Before you begin — what to have ready

**An AI API key (required for the talking Orb).** The Orb's answers come from a
cloud LLM you choose. You only need **one** of these, and you paste the key into
Settings (it's stored in your OS keychain, never in a file):

- **OpenAI (GPT)** — https://platform.openai.com/api-keys
- **Anthropic (Claude)** — https://console.anthropic.com/settings/keys (needs `pip install anthropic`)
- **Google Gemini** — https://aistudio.google.com/app/apikey (default; free tier is generous)
- **DeepSeek** — https://platform.deepseek.com/api_keys (low cost)
- **Mistral** — https://console.mistral.ai/api-keys/
- **xAI (Grok)** — https://console.x.ai/

You pay the provider directly for usage. Kalandra tracks tokens used per session
and can warn you as you approach a budget you set, but it cannot read your actual
account balance (no provider exposes that).

**Optional but recommended:**
- **Path of Building 2 (source/standalone build)** — for the live simulator. Must
  include the Lua source (`HeadlessWrapper.lua`), not just the packaged `.exe`.
- **A PoE account name** — to browse the public ladder (your own PoE2 characters
  can't be pulled yet; GGG hasn't shipped that API).

---

## 2. Programs Kalandra uses (baked-in integrations)

Kalandra does not bundle or redistribute these — it drives your own installed
copies, or links you to them. The installer can help you fetch and locate each.

- **Path of Building 2 (PoB)** — the authority on build math. Kalandra reads your
  PoB builds and drives PoB's real calculation engine headlessly for live numbers.
- **LuaJIT** — runs PoB's engine outside the GUI.
- **poe2db.tw** — the primary database (game items, gems, mods, passives,
  ascendancies). This is Kalandra's source of truth for grounding the AI.
- **poe.ninja** — live economy/prices (used for currency/exchange features).
- **Exiled Exchange 2 / Xiletrade** — price-check tools (integration links).
- **PoE Overlay II Standalone** — companion overlay (integration planned).
- **NeverSink / FilterBlade** — loot filter management (embedded web tool).
- **Craft of Exile** — crafting simulator (embedded web tool).
- **Rhubarb Lip Sync** — drives the Orb's mouth movements when it speaks.
- **Obsidian** — optional viewer for the scraped knowledge base exported as a vault.

---

## 3. Installing

1. Run the installer (`Kalandra-Setup.ps1` via the provided launcher, or
   `launchers/Install Dependencies.bat`). It's a step-by-step hub: each dependency has its
   own row with **Install** (opens the download/repo), **Check Location** (point
   Kalandra at the file and verify it's found), and **Connect Account** where
   relevant. It doubles as a repair tool — re-run it any time to re-verify.
2. The installer lists, per dependency, which revision is verified to work.
3. Launch with **launchers/Kalandra.bat** (no console) or **launchers/Windows Diagnostic Launcher.bat**
   (keeps a console open — use this if something crashes; it captures the error).
4. A desktop shortcut can be created with **launchers/Create Desktop Shortcut.bat**.

If a crash ever happens, look for `data_engine\crash.log` — it records the error.

---

## 4. The overlay and its buttons

The overlay is a frameless, always-on-top, draggable mirror. Drag it anywhere by
holding the left mouse button and moving. **To close it: hold the left mouse
button and press ESC.** (Right-click does nothing — it used to open a stuck menu.)

The five medallions around the orb, and their single vs double click actions:

| Medallion (position) | Single click | Double click |
|---|---|---|
| **Voice / Mic** (top-left, red) | Start/stop voice — speak to the Orb | Open the **typed chat** window |
| **Database Sync** (top-center, blue) | Sync the poe2db database (honors your source toggles, no prompts) | **DB status window** *(planned)* |
| **Character Selector** (top-right, green) | Open the **character/build picker** | Open the dashboard on your **Build (PoB)** tab |
| **Screen Capture** (bottom-left, red) | Take a tooltip screenshot | Start/stop **screen recording** |
| **Settings** (bottom-right, blue) | Open **Settings & Accounts** | — |

A small badge appears on the green medallion when a build is loaded and ready to
view. Saying "show me my build" / "open my PoB" by voice also opens the Build tab.

---

## 5. Settings & Accounts

Opened with the bottom-right medallion. The whole panel wears the shared
Mirror-of-Kalandra theme (gold leaf + gem-accented buttons: emerald = save,
ruby = clear, sapphire = connect). Contains:

- **GGG account (OAuth).** "Connect GGG account" runs the official OAuth 2.1
  PKCE sign-in in your browser once GGG issues a client_id (send them
  `docs/GGG_OAuth_Application_Letter.md`; paste the id into the field). "Test PoE2
  API (no login)" proves the trade API is reachable right now.
- **GitHub (issue & changelog sync).** Paste a personal-access token
  (`repo` scope — the "Get a key" button opens the right page) and the
  dashboard's Issues tab can post entries straight to
  github.com/castleism/Kalandra_Git.
- **Email.** Pick your provider (Gmail / Outlook / Yahoo / Proton / iCloud);
  buttons open its sign-in and app-password pages; credentials go to the OS
  keychain only.
- **Every linked tool** (poe.ninja, FilterBlade, Exiled Exchange 2, Craft of
  Exile 2, Maxroll, Mobalytics, poe2wiki…) has an "Open site" button.

- **AI brain + model.** Pick your provider and model (the model field is editable
  because providers change model IDs often). Switching mid-conversation carries
  the conversation over with no lapse. A live line shows tokens used this session;
  set a **session token budget** to get a countdown warning as you approach it.
- **Companion orb.** Choose which currency orb floats as your companion (Divine,
  Chaos, Vaal, etc.). Drop art into `gui_overlay/assets/orbs/2d/<slug>.png`.
- **Divine Orb voice.** Pick a local system voice (TTS).
- **Account linking.** Each integration/provider has a row to paste its key (stored
  in the OS keychain) or open its sign-in page. Connection status loads in the
  background so the panel opens instantly.
- **Known issues.** Shows the open-issue count and opens the changelog log.

---

## 6. Loading a build (Character Selector)

The green medallion opens the build picker. You can:

- **Load my saved PoB builds** — scans your PoB Builds folder, pick one, "Set
  active." This loads it so the Orb can see it and (if set up) the live engine
  computes it.
- **Paste a PoB code or a pobb.in / poe.ninja link** — loads it directly, no PoB
  install required.
- You can also **paste a PoB code/link right into the chat** and the Orb loads it.
- **Browse the public ladder** (your own PoE2 characters aren't available via API
  yet).

Once loaded, the Orb "sees" your whole build — class, level, every skill group,
all gear, and tree-socketed jewels with their mods.

---

## 7. The Dashboard

A single window with tabs (open it from Settings, or double-click the green
medallion to land on the Build tab). Styled by the shared Kalandra theme
(`gui_overlay/theme.py`); the frameless golden chrome (`KalandraWindow`,
gem window buttons: ruby closes, sapphire minimizes, emerald maximizes) ships
behind a demo first — run `python -m gui_overlay.kalandra_window` to preview.

**Recent additions (2026-07-03):**
- **Build (PoB) view toggle** — switch between "Container" (stat chips, gear
  table, skill groups with the main one starred) and "Text" (the full
  breakdown). Your choice is remembered.
- **Live Search embedded** — the official trade site now loads *inside* the
  tab (with PyQt6-WebEngine installed; external-browser button still there).
- **Issues → GitHub** — "Post selected → GitHub" files a real GitHub Issue;
  "Publish changelog → GitHub" ships the open list as a pre-release note.
  Needs the GitHub token from Settings.

**Working now:**
- **Terminal** — total transparency: every backend event in real time (database,
  GUI actions, AI context, build loads), filterable by type.
- **Build (PoB)** — your loaded character rendered from the parse: class, scaling
  profile, skills, all gear, tree jewels, and a "LIVE PoB SIM" line with numbers
  recomputed by PoB's real engine when it's connected.
- **Build Sim** — the live LuaJIT engine view, with a **self-test** that diagnoses
  the engine and a copy button to send diagnostics.
- **Reserve / BIS** — snapshot uniques/items you're holding for future builds or
  upgrades, with tags, notes, and which build they're earmarked for. The Orb sees
  your reserve and can factor it into advice.
- **Issues / Changelog** — log bugs, AI mistakes, and ideas (the chat has a "Flag
  last answer" button). "Copy changelog for Claude" exports a clean list to hand
  to the developer.
- **Craft of Exile / FilterBlade / poe.ninja** — embedded web tools.

**Also working now (completed 2026-06-30):**
- **Price Check** — paste an item (Ctrl+C in-game → Ctrl+V); Kalandra parses it
  and opens the official trade search for your league. You buy manually.
- **Exchange** — live PoE2 economy from poe.ninja (league picker, filter,
  sortable value/volume table).
- **Crafting** — describe a goal in plain language; get a realistic craft path
  plus a Craft of Exile link (uses your AI brain if configured, offline
  heuristic otherwise).
- **Filter Editor** — lists every block in your `.filter`, flip Show/Hide and
  save; writes a `.bak` first and round-trips your file byte-exact.
- **Live Search** — opens the official trade site's live search for your league
  (manual whisper-and-buy; nothing automated).

---

## 8. The AI (the Orb) — how it stays accurate

- **Grounded in poe2db.** Your questions and your build's tags (skills, items,
  ascendancy) are used to pull matching entries from the local database, so answers
  are based on real PoE2 data, not generic guesses.
- **Verified corrections layer.** A set of authoritative facts overrides both the
  database and the model's own (sometimes wrong) knowledge — e.g. "Corrupted Blood
  is physical damage over time, not a Bleed." You can add your own.
- **Build-aware.** When a build is loaded, the Orb analyzes it directly and never
  claims it "can't see your build."
- **Passive-tree guidance.** Ask about DPS/repathing and the Orb guides you through
  PoB's Power Report with the right stat weights for your build — it does the
  strategy, PoB gives the exact node numbers.
- **Flag button.** Wrong answer? One click logs it to the changelog for fixing.

---

## 9. The live PoB simulator

When LuaJIT and a PoB source build are set up, Kalandra runs PoB's actual engine
in the background and recomputes your build's real numbers (DPS, EHP, resists,
spirit, etc.). Setup requirements:

- LuaJIT findable (on PATH or `luajit_path` in config — the installer's Check
  Location handles it). Note: this is the real `luajit.exe`, not the installer.
- A PoB2 install containing the Lua source (`HeadlessWrapper.lua`), with
  `pob_install_dir` pointing at the folder that contains it (usually `...\src`).
- If a build's numbers look off, it's almost always **mods PoB doesn't support
  yet** — fixable in PoB's own source (see the troubleshooting note on
  `unsupported.txt`).

---

## 10. Data & privacy

- **Secrets** (API keys, POESESSID) are stored only in the OS keychain — never in
  a file, never in the repo. If the keychain is unavailable, storage is refused
  rather than written in plaintext.
- **Transcript logging** of your chats will be an opt-in toggle. If you turn it on,
  you are choosing to store whatever you type — so never include personally
  identifiable or account information beyond what's already public (e.g. your
  account name).
- The git repo intentionally excludes your config, secrets, databases, transcripts,
  and personal data files.

---

## 11. Hard rules (account safety)

Kalandra will never automate gameplay. No auto-purchasing, no auto-teleporting, no
sending inputs to the game — those violate GGG's Terms and risk a ban. Everything
Kalandra does is **read-only and advisory**: it observes, analyzes, and tells you
what to do; you perform every in-game action yourself.

---

## 12. Roadmap

Ordered roughly by how close each is. ToS notes included where it matters.

**Next up (close):**
- **"Hey Kalandra" wake word** — hands-free voice using a lightweight always-on
  detector (low CPU) that only wakes transcription when it hears the phrase.
- **ElevenLabs voices** — premium cloud TTS as an option alongside the free local voice.
- **DB status window** — double-click the sync medallion: shows the active
  database, last sync, whether poe2db has a newer patch, and a primary-source picker.
- **PoE Overlay II Standalone** — add to the integrations list in setup/settings.

**Character threads + orb identity:**
- Each character gets a **manually-chosen orb** and its **own preserved chat
  thread**, so switching characters never mixes builds. Loading a build (your own
  or a build creator's) can create/save it in a tabbed PoB instance. Threads are
  kept so you can return to them later.

**Character Sheet (a flagship):**
- A beautiful, intuitive character sheet — the in-game sheet but better. Clean
  space, borders, your character + gear shown on the side, tree jewels listed,
  and a slot to import a screenshot. All of PoB's extra calculations surfaced.
  **Interactive highlighting:** mouse over "main skill damage" and it highlights
  every related thing on screen (weapon, rings with flat damage, etc.); things not
  on screen (passives, support/lineage gems) appear in a dropdown. Greyed-out
  unused passives/supports listed at the bottom.

**Tools:**
- **Dynamic FilterBlade filter** — auto-adjust your loot filter to currency
  exchange rates; set a threshold (e.g. "only pick up items worth ≥ 1 Divine").
  On boot it compares the last snapshot to current prices and asks you to confirm
  including newly-valuable or excluding now-cheap items.
- **Investment tracker** — track currency invested per craft, alongside the
  Reserve/BIS tracker; alert when you pick up items with the mods you want for
  expedition reforge.
- **Temple planner.**
- **Overlay transparency slider** (Settings).
- **Minimize-to-icon** when a menu opens, so two windows aren't fighting to stay
  on top.

**Under ToS review (need care):**
- **DPS calculator via screen recording** — watching boss health drop, buffs, and
  environmental factors (surrounded, shocked ground). *Reading and displaying what's
  on your screen is generally acceptable* (it's passive observation, like a damage
  meter overlay). The line you must not cross is automating any game input.
- **Training Dummy / combo builder** — building and timing skill combos. Building
  and reviewing combos offline is fine. **Highlighting "press this skill now" live
  while you play is a gray area:** as long as it only *displays a suggestion* and
  never sends the keypress for you, it's advisory like a guide — but it's closer to
  the line, so it should be clearly optional and never automate input. (None of
  this is legal advice; when unsure, keep it read-only and manual.)

**Deeper AI:**
- A true "simulate build changes to optimize" brain (today we guide you to PoB's
  Power Report; the next step is driving the live engine to compute what-if changes).

---

## 13. Troubleshooting

- **Crash with no obvious cause** → check `data_engine\crash.log`.
- **Live sim shows "not available"** → LuaJIT or PoB source not found; run the
  Build Sim self-test and check `luajit_path` / `pob_install_dir`.
- **A build's numbers look wrong in PoB and Kalandra** → unsupported mods. PoB's
  parser logs them to `unsupported.txt` (in the PoB repo root) when enabled; those
  mods then need patterns added to PoB's `ModParser.lua`.
- **Something froze** → it shouldn't; menu/scan/chat work runs off the UI thread.
  If it does, note what you clicked and check the Terminal tab.

---

*Kalandra is a personal, ToS-respecting companion: it thinks alongside you, it
never plays for you.*


## Folder map (reorganized 2026-07-04)

The root stays clean: this readme, `CHANGELOG.md`, and `Setup.bat` (plus `main.py`/`version.py`/`requirements.txt`/`LICENSE.md`, which the app itself needs at the root). Everything else lives in:

- `docs/` — every guide and spec (ROADMAP, INSTALL, DESIGN_COMPANION, security, testing, setup guides)
- `launchers/` — the double-click .bats: launch Kalandra, diagnostic launcher, update DB, build vault, shortcut, relocate PoB, **Uninstall / Repair**
- `scripts/` — maintenance Python (update_db, configure, install_dependencies, ...)
- `installer/` — Setup.bat's PowerShell machinery
- `core_engine/`, `gui_overlay/`, `tests/` — the app
- `data_engine/` — YOUR data (builds, ledgers, folios, knowledge DB)
- `tools/` — bundled add-ons (PoB, Obsidian, LuaJIT, ...)


## Status — 2026-07-04 (the Companion wave + live-testing round)

Everything shipped today is itemized in `CHANGELOG.md` (owl guide +
interview, Companion tab, ghost mode, grouped dashboard, Price Check
reorg, character sheet one-pager, Gmail OAuth, custom tabs, uninstaller/
repair, release-zip builder, and the truncation-bug recovery). This
section is the honest ledger of what's OPEN.

### Known issues (documented, not yet fixed)

1. **Remote-edit truncation (environment)** — file writes that GROW a file
   via the assistant's edit path can truncate on disk. Mitigated: all
   repairs now delivered as delete-and-recreate; config saves are atomic
   (temp + os.replace). If the app ever dies silently again, run
   `launchers\Windows Diagnostic Launcher.bat` and check for SyntaxError.
2. **config.json.corrupt.bak** — holds the pre-repair config tail; safe to
   delete once you've confirmed no settings are missing.
3. **PoB import-list characters** — characters visible in PoB's
   import-from-account screen but never saved have no .xml on disk; the
   Character Selector cannot list them until saved once in PoB.
4. **Old Kalandra-Setup.zip** (if still on your Desktop) predates the
   truncation repairs — delete and rebuild.

### Checks on Christian's side

- [ ] Death Review (new): `pip install websocket-client`; in OBS enable
      Tools ▸ WebSocket Server Settings and Settings ▸ Output ▸ Replay
      Buffer (start it); enter the websocket password in the Death Review
      tab and hit "Test + save" (expect 🟢). Then die once for science —
      the incident + clip should appear in the tab.
- [ ] Restart Kalandra; confirm: selector opens, its status line's folder
      matches PoB's Settings.xml buildPath, and the list matches PoB.
- [ ] "Open in PoB app" launches without freezing the overlay.
- [ ] Web tabs (Trade Site / Craft of Exile / poe.ninja) no longer summon
      the overlay over the dashboard.
- [ ] Ghost mode: fades in game, never in a browser; Ctrl restores.
- [ ] Build tab: sheet view renders; AI review returns text; scaling
      profile names the right damage type on your real characters.
- [ ] Run `python tests/stress_test.py` + the check files in tests/.
- [ ] Re-run `launchers\Make Release Zip.bat` for a clean shareable zip.
- [ ] Capture tab screenshots into installer/assets/tab_previews/ (W4-15).
- [ ] One-time: Google OAuth Desktop client for Gmail connect (Settings).

### Next up on the roadmap (docs/ROADMAP.md, W4 table)

1. **W4-04 PoB import + character deep-scan** — the unblocker for
   per-character orb threads, auto-reviews, and BIS sims.
2. **W4-05 remainder** — auto-review on import + standard-shuffle
   detection (nerf_intel is built and waiting for its DB/ninja feed,
   W4-06).
3. **W4-08** — BIS bank ↔ sims, live-search auto-creation from roadmap
   watchlists, notifications (the XOAUTH2 sender is ready).
4. **W4-20 install modes** — Local Copy / Contained / Browser-based per
   add-on; the uninstaller's Move-out is the migration path.
5. **W4-09/10** — researched auto-attendant, then the OBS streamer suite.
