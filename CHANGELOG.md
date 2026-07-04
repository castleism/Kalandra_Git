# Changelog

All notable changes to Kalandra are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versions follow
the app's `version.py`. Process: every finished ROADMAP item gets an entry here
**and** a status flip in `docs/ROADMAP.md`, in the same commit.

Repo: https://github.com/castleism/Kalandra_Git

## [Unreleased]

### Added — 2026-07-04 Companion wave (W4, spec: `docs/DESIGN_COMPANION.md`)
- **The owl guide** (W4-01) — the owl decoration from the Mirror's frame, cut
  out as its own face (`assets/owl_face.png`), perches in the dashboard
  corner and walks you through every tab in chat bubbles. The bubble pointer
  is the mirror's hanging arrow finial (`assets/owl_arrow.png`): it points up
  at the tab it's introducing, down at the owl when chatting. First visit to
  each tab auto-intros once; click the owl to step through that tab's tips.
- **First-use interview + player profile** (W4-02) — after its welcome tour
  the owl asks 10 questions (PoE background, leagues, peak level, how those
  levels happened — carries/rotas/temple-leech aware, with "prefer not to
  say" — solo/party, meta vs niche, stance on pre-nerf mechanics, budget,
  explanation depth, past builds). Answers persist to
  `data_engine/player_profile.json` and a compact profile block is injected
  into EVERY AI prompt so explanations land at the right depth. Right-click
  the owl to redo. (`core_engine/player_profile.py`,
  `gui_overlay/owl_interview.py`)
- **Companion tab** (W4-03) — new first dashboard tab: threaded orb chats
  (`data_engine/chat_threads/`), the Terminal firehose rendered as small
  color-coded action notes between messages (sync=sapphire, build=emerald,
  AI=gold, capture=amber, errors=ruby; toggleable), input wired to the same
  brain as voice. Auto-attendant stub included (profile-gated local
  templates, config `companion_attendant`, off by default).
- **Provider interfaces** (north star) — `core_engine/providers.py`: every
  third-party tool (PoB, poe.ninja, trade site, craft planning, game data,
  capture) now has a swappable interface + registry, so official APIs can
  replace any tool by changing one adapter.
- **Price ledger** (W4-12 local-first) — `core_engine/price_ledger.py`:
  every Price Check is parsed and logged to `data_engine/price_ledger.db`
  (mods templated: "+120 to maximum Life" → "+# to maximum Life" + value).
  Naive median mod-value + item estimates that improve all league. Local
  only; community upload stays opt-in P9.
- **Grind tracker** (W4-11) — `core_engine/grind_tracker.py`: snapshot a
  grind loadout (tablets/waystones with mods), record per-run income, get
  per-loadout chaos/hour and per-mod return correlations (honest min-sample
  gates; refuses mixed-currency lies).
- **Character folios** (W4-07 foundation) — `core_engine/character_folio.py`:
  `data_engine/characters/<slug>/` per character (profile.json, review.md,
  roadmap.md, watchlist.json, sim_notes/) + size-budgeted `prompt_corpus()`
  for token-cheap AI injection.
- **Companion test suite** — `tests/companion_checks.py`: 94 adversarial
  checks over the five new core modules (all green; caught and fixed a
  mod-template sign bug and a prompt-corpus leak before ship).
- **Nerf intelligence** (W4-06 core) — `core_engine/nerf_intel.py`: patch
  signal (heuristic nerf/buff/mixed scan of patch-note lines naming an item,
  negation-aware: "no longer suffers reduced…" reads as a buff) + price
  signal (league-over-league change with cliff detection) + combined
  `value_intuition()` that names the Temple-league-Headhunter pattern when
  price dropped WITHOUT a balance change. 30 adversarial checks green
  (`tests/nerf_checks.py`).
- **Grind Tracker tab** (W4-11 UI) — `gui_overlay/grind_tab.py`: snapshot
  loadouts ("Breach Tablet x4 | 23% increased Quantity; …"), live run timer,
  income logging ("divine 0.4, chaos 55"), per-loadout chaos/hour and
  per-mod returns tables, valued via live poe.ninja rates through the
  economy provider. Parse helpers covered by 9 checks.
- **Price Check ledger estimate** — after each check, if your own ledger
  knows enough of the item's mods it shows "~X divine (n/m mods known)" —
  explicitly labeled as your history, not a market quote.
- **Character folios auto-fill** — loading a build (green selector) now
  creates/updates `data_engine/characters/<slug>/` with the scan AND a
  generated first-pass review (facts straight from the parse; the AI review
  of P2 will replace it). Hand-written reviews are never overwritten.
- **Auto-attendant, real edition** — with an AI brain connected the
  Companion's idle chatter asks for one short starter built from the player
  profile + character folios (one small completion per idle interval);
  zero-token local templates remain the fallback. Config:
  `companion_attendant` (master, off by default), `companion_attendant_ai`.
- **Provider adapters verified against real APIs** — poe.ninja adapter uses
  `PoENinja.get_currency`, game-data adapter queries `knowledge_ledger`
  directly, capture adapter takes the overlay's live recorder via
  `attach_recorder()`.
- **Ghost mode** (W4-14) — when Path of Exile is the foreground window the
  mirror fades to a whisper (frame at 15% opacity; the ORB stays clearly
  visible, subtitles and the REC privacy dot stay full) and the overlay
  stops eating clicks entirely (WS_EX_TRANSPARENT — clicks land in the
  game). **Hold Ctrl** to make it solid + clickable while you interact.
  Detection is a passive 350ms foreground-title poll — nothing is ever sent
  to the game. Config: `game_fade`, `game_click_through` (both default on),
  `game_fade_frame` (0.15, clamped, junk-proof). New module
  `gui_overlay/game_watch.py`; 24 checks green (`tests/ghost_checks.py`) —
  the suite caught a paint-crash path from junk config values before ship.

### Fixed / Added — 2026-07-04 evening batch (Christian's live-testing round)
- **Ghost mode detection fixed** — a browser tab titled "…Path of Exile…"
  ghosted the overlay while browsing. Detection now reads the foreground
  window's PROCESS EXE (PathOfExile*.exe); exact-title match only as
  fallback; loose title matching forbidden. Ctrl response poll 350→150ms.
- **Menu windows minimize to the TASKBAR** with the Kalandra icon —
  `apply_window_identity()` gives top-level chrome windows real
  Window/minimize/system-menu hints (frameless windows otherwise park at
  the desktop's bottom-left), and main.py sets the Windows
  AppUserModelID + app icon (same kalandra.ico as the desktop shortcut).
- **Owl interview Q2 "no answers" fixed** — chips are now explicitly shown,
  the panel is force-resized after layout activation, old chips are fully
  reparented away, a fallback Continue chip guarantees no dead ends, and
  each question logs its chip count to the log bus.
- **Clip recording un-slideshowed** — the writer promised 15fps while the
  machine delivered ~4, so playback fast-forwarded. Now: honest timeline
  via frame duplication (`plan_writes`, unit-tested), SIMD cvtColor, and
  downscale-to-1080p before encode. Capture stats (real fps, duplicated
  frames) show in the save dialog and log. Config: clip_fps, clip_max_width.
- **"Load my saved PoB builds" unified with the dashboard PoB** — the tab's
  exe pick now also saves pob_install_dir; the selector derives the install
  from pob_exe when unset. One PoB, one truth.
- **PoB folder cleanup** — new `launchers/Relocate PoB Install.bat` (repo root):
  double-click to move the installed app out of the source clone to
  `tools/Path of Building Community (PoE2)/` and update config in one shot
  (native move — close PoB first). The source clone stays for the sim.
- **Per-character companion orbs** — Character Selector now shows a
  "Companion orb for selected" dropdown: see and set which orb speaks for
  each character (`character_orbs` in config); setting a character active
  switches the mirror to its orb automatically.
- **Price Check reorganized** — the cramped bottom browser is gone; the
  official trade site now lives in its own full-size **Trade Site** tab and
  'Open trade search' pushes the search there and switches tabs. The
  reclaimed space is a per-mod value board: search tier, why it matters,
  and YOUR ledger median per mod (sharpens as price-check history grows).
- **Build Sim: "Set PoB folder…" button** — picks the install, verifies
  HeadlessWrapper.lua (root or src/), saves pob_install_dir, tells you the
  next step. No more hand-editing config.json.
- **Build (PoB) tab: "AI review" button** (W4-05 v1) — the Orb writes a
  structured review from the full parse + live sim: damage-mechanism
  deduction (Corrupted Blood scaling and other unusual chains called out
  explicitly — the corrections layer rides along), gear/passives/supports
  analysis, sim-verifiable improvement suggestions (nearby nodes, support
  swaps, weakest slot), and defence gaps. Saved to the character's folio.
- **Exchange: currency-tab screenshot scan** — instruction + button: OCR a
  stash-tab screenshot into the holdings table for review before saving.
- **GGG connect button honesty** — no longer opens the PoE1-era OAuth docs;
  explains the real state (PoE2 public OAuth pending, letter ready) and the
  no-login import paths that work today.
- **Settings: every service row actionable** — sign-in/site buttons for all
  keyed & login services, dedicated sign-in URLs + optional remembered
  username for Maxroll/Mobalytics/FilterBlade/poe2wiki/forums, poe.ninja
  "key" row links to the site (its JSON needs no key).
- **Gmail: modern auth** — OAuth 2.0 installed-app flow with PKCE (RFC
  8252/7636), mail-only scope, tokens ONLY in the OS keychain,
  auto-refreshing XOAUTH2 over implicit-TLS SMTP (`core_engine/
  email_oauth.py`). App passwords demoted to a clearly-labeled legacy
  fallback; Gmail is the default provider.
- **Custom dashboard tabs** — Settings → Custom tabs: add any website as a
  contained-browser tab or any program (folder + exe) adopted into the
  dashboard exactly like PoB. Remove any time; applies on dashboard reopen.
- **Setup & Dependencies window widened** (760→980) — the "Installed ✓"
  status column was cut off.
- **New-player build finder + guide roadmaps** — brand-new players (from
  the interview) get offered the build finder: the owl hands off to a
  seeded Companion conversation (playstyle Q&A → archetype suggestions →
  roadmap offer; `core_engine/build_seeker.py`). Paste a guide (or its PoB
  codes) into the chat and the roadmap engine extracts every variant,
  parses them through pob_bridge, writes a priced roadmap.md (ledger
  medians where your history knows an item) + watchlist into a character
  folio, and points at Live Search for camping the watchlist while
  leveling. 10 engine checks green.
- **Own app icon** — new `kalandra.ico` generated from OUR art: the
  mirror's owl crest in gold on an obsidian disc with the double gold ring
  and a hint of the orb's aura (multi-resolution 16→256px). No more
  borrowed Divine Orb.
- **Graceful shutdown for containerized programs** — closing Kalandra now
  sends WM_CLOSE to any PoB/PoE Overlay/custom app the dashboard LAUNCHED
  (terminate only as a 4s fallback) and releases adopted EXTERNAL windows
  back to the desktop untouched — a separately-running PoB is never
  closed. No more mangled orphan windows after exit.

### Fixed — 2026-07-04 Build (PoB) tab round 2 (Christian's testing)
- **View toggle label** now names the view the click takes you TO
  ("View: Sheet ▣" while reading text, "View: Text ≡" while on the sheet) —
  it read backwards before.
- **AI review actually runs** — the reply callback fired on a worker thread
  where QTimer can't start, so the review silently vanished. Replies now
  arrive via a queued Qt signal (`review_ready`) on the UI thread.
- **Scaling profile accuracy** — damage-type scoring no longer counts
  resistance/regen/attribute rolls (a +35% Fire Res ring was flagging every
  build as "fire"); the main skill and its supports outweigh gear text 8:1;
  flat "adds X to Y damage" rolls weigh triple; minion builds are decided by
  their SKILLS, not a stray minion-damage gear roll. Verified: a Spark build
  wearing double fire-res now profiles pure lightning/crit; a skeleton build
  with a fire wand profiles minions-first.
- **Container view is now the one-page character sheet** — poe.ninja-style:
  headline DPS/Life/ES/attribute chips, resistances line, the computed
  scaling profile, full equipment table with every mod, and all skill links
  (main starred) on a single scrollable page, rendered from YOUR real PoB
  parse. The "Export sheet (HTML)" file version gains the same resistances
  + profile sections.

### Fixed — 2026-07-04 corrupt config: "Open in PoB app" + silent settings loss
- `data_engine/config.json` was truncated mid-string on disk, so
  `load_config()` silently fell back to DEFAULTS — pob_exe vanished
  ("Open in PoB app" launched nothing) and every saved setting was being
  ignored. Repaired: 29 settings salvaged from the corrupt file (only the
  owl's seen-tabs list was lost — it regenerates), PoB paths re-pointed at
  the relocated install (exe verified on disk), original preserved as
  `config.json.corrupt.bak`.
- **Root cause fixed**: `save_config` now writes ATOMICALLY — fresh temp
  file, parse-verified, then `os.replace()` over the old one. In-place
  rewrites of a growing config are what corrupted it; a rename of a
  complete new file cannot. `load_config` also preserves any corrupt file
  as `.corrupt.bak` instead of silently eating it.

### Fixed — 2026-07-04 "Open in PoB app" freeze + missing characters
- **Overlay frozen on top of PoB**: launching PoB popped an
  application-modal "code is on your clipboard" box that appeared BEHIND
  PoB (which had just stolen the foreground) — the invisible box blocked
  input to every Kalandra window, including the always-on-top overlay. The
  post-launch modal is gone; the message lives in the selector's status
  line. (If it ever happens again from an old build: Alt+Tab to the hidden
  dialog and press Enter.)
- **Selector missing characters that PoB shows**: Kalandra guessed at
  build folders but never asked PoB itself. It now parses PoB's own
  Settings.xml for its configured `buildPath` (checked first, outranking
  every guess) and adds the PoE2 community fork's default user dir
  (%APPDATA%\Path of Building Community (PoE2)\Builds) to the candidates.
  Verified headless: a synthetic Settings.xml buildPath is honored and its
  builds are found. Note: characters listed in PoB's import-from-account
  screen that were never SAVED as build files still won't appear — only
  saved .xml builds exist on disk to find.

### Fixed — 2026-07-04 character selector wouldn't open
- The per-character orb dropdown fired `currentIndexChanged` while the
  dialog was still under construction (addItem triggers it), hitting a
  not-yet-created label — the whole selector crashed mid-`__init__` and
  silently refused to open. Now: label built first, combo populated with
  signals blocked, handler guarded. The selector's status line also names
  PoB's configured build folder after each scan, so the list can be
  verified against what PoB itself shows. (The green medallion glow is
  unrelated — it simply means a character is active.)

### Changed — 2026-07-04 dashboard tabs grouped into categories
- The flat 18-tab strip is now two levels: category tabs on top, tools
  nested inside — 🦉 Companion (Companion, Terminal) · ⚔ Build Planning
  (Build (PoB), Build Sim, PoB (live), PoE Overlay 2) · 💰 Items & Trading
  (Price Check, Trade Site, Live Search, Exchange, Reserve/BIS, poe.ninja)
  · 🔨 Crafting (Crafting, Craft of Exile) · 📊 Loot & Filters (Filter
  Editor, FilterBlade, Grind Tracker) · 🛠 Other (Issues/Changelog + your
  custom tabs). Implemented as `GroupedTabs`, a wrapper that speaks the
  same flat-index QTabWidget dialect the rest of the code was written
  against — show_tab, lazy web loading, Price-Check→Trade-Site jumps,
  graceful shutdown and the owl all work unchanged, and the owl's arrow
  aims at the nested tab header (`current_tab_center_in`).

### Fixed — 2026-07-04 overlay barging in over the dashboard
- Opening a web-view tab (Trade Site, Craft of Exile, FilterBlade,
  poe.ninja, Live Search) made the overlay pop back up ON TOP of the
  dashboard: QtWebEngine's first view briefly recreates native window
  handles, which fired a spurious Hide on the dashboard, and the overlay's
  "menu closed" watcher believed it. `_menu_done` now verifies the menu is
  genuinely gone (still-visible = not done) and the check waits 150ms for
  the WebEngine transition to settle.

### Added — 2026-07-04 build freshness prompts
- **The owl now notices stale builds** — loading a character records its
  file path; when the dashboard opens and the active build file is older
  than `build_stale_days` (default 3), the owl walks you through pulling
  the current copy: PoB (live) tab → PoB's own 'Import from account' →
  save → Kalandra's file-watcher offers the fresh version as your active
  character. Prompts once per staleness (a new save resets the reminder);
  logic unit-tested (stale→walkthrough, no re-nag, fresh→quiet). Also adds
  a generic `walk_through(steps)` API on the owl for future guided flows.

### Changed — 2026-07-04 root declutter + uninstaller
- **Root folder reorganized** — a fresh visitor now sees `READ_ME_FIRST.md`,
  `CHANGELOG.md`, `Setup.bat` (plus the load-bearing `main.py`,
  `version.py`, `requirements.txt`, `LICENSE.md`). Everything else moved:
  all guides/specs → `docs/`, all launcher .bats → `launchers/` (each now
  `cd`s to the repo root), maintenance scripts → `scripts/` (path
  bootstraps updated: repo root resolved one level up). Every
  cross-reference patched (installer .ps1s, code hint strings, doc links —
  25 files); full test suite green from the new layout.
- **Clean uninstaller that doubles as a repair tool** —
  `launchers/Uninstall Kalandra.bat` → Repair mode: reinstall deps,
  validate/rescue a corrupt config.json, report configured tool paths that
  no longer exist, clear stale bytecode, recreate the shortcut, optional
  self-test. Uninstall mode: per-add-on Keep / Move-out (to
  %LOCALAPPDATA%\Programs, the standard per-user location) / Delete, your
  data preserved to Documents\Kalandra-Data by default, and only then the
  app itself. Nothing deleted without an explicit answer.

### Added — 2026-07-04 shareable release + install lifecycle
- **Setup.bat detects existing installs** — if a previous run's config or
  database exists it offers [R]epair / [U]ninstall / [I]nstall-anyway
  before doing anything, wiring straight into the Uninstall/Repair tool.
- **Release zip builder** — `launchers/Make Release Zip.bat` →
  `scripts/make_release_zip.py`: packs a shareable `Kalandra-Setup.zip`
  onto the Desktop, EXCLUDING everything personal (`data_engine/` with its
  config client-ids/secrets, player profile, chat threads, ledgers; `.env`;
  `.git`; multi-GB `tools/`), then re-scans the finished archive for
  key-shaped strings (sk-/AIza/ghp_/AKIA/xoxb-) and deletes it rather than
  finish if any are found. Real API keys never ship regardless — they live
  in Windows Credential Manager, not in files.

### Removed — 2026-07-04 cleanup
- `STRESS_TEST_AND_PLACEHOLDERS_REPORT.md` (session report, contents long
  since folded into ROADMAP/CHANGELOG; recoverable from git).
- `test_real_pob.py` (root-level dev scratch; `tests/stress_test.py` covers
  the parser; recoverable from git).
- All `__pycache__/` directories (regenerated automatically).

### Added
- **"PoE Overlay 2" containerized tab** (off by default — enable in Settings
  → Dashboard tabs): same window-adoption embed as PoB, with keyboard focus
  handling; asks for the .exe on first launch and remembers it.
- **Price Check: contained trade-site browser** — "Open trade search" now
  loads the official PoE2 trade site inside the tab (lazy, crash-safe
  WebEngine; external browser fallback). Filter push into the site is the
  next step (route documented in ROADMAP W3-21).
- **Price-checker selector** (Settings): choose Kalandra's built-in popup,
  PoE Overlay 2, Exiled Exchange 2, or Xiletrade. Picking an external tool
  silences Kalandra's Ctrl+C popup so the two never fight over the clipboard.
- **Price Check: "Scan screenshot…"** — OCR an item screenshot straight into
  the parse → tiers → official trade search pipeline (needs pytesseract +
  Tesseract; AI-vision no-install version is W3-33).
- **Repo de-inception**: `.git` promoted from `Kalandra_Git/` to the repo
  root; the duplicate mirror folder deleted. The live tree IS the repo now.
- **Settings: sectioned account list** — ⚔ PoE2 Builds (GGG account, Path of
  Building, Maxroll, Mobalytics), 🛠 PoE2 Tools (poe.ninja, forums, PoE
  Overlay, FilterBlade, Exiled Exchange 2, Craft of Exile 2, poe2wiki),
  🌐 External accounts (email, YouTube, GitHub, ElevenLabs) — each under a
  gold section header; future services land at the end automatically.
- **Settings: one AI section** — the six per-provider rows are gone. The AI
  brain dropdown now carries everything: pick the provider, the API-key
  field/Save/Clear and "Get key ↗" all re-bind to it, with a live saved/not
  indicator. ElevenLabs (voice) keeps its own row.
- **Settings: Path of Building buttons** — "Auto-detect (bundled)" finds the
  PoB .exe inside the Kalandra folder (tools/…) and wires exe/install/Builds
  paths in one click; "Pick PoB .exe…" as fallback; current path shown.
- **"PoB (live)" dashboard tab — the REAL Path of Building, containerized**:
  launches your own PoB install and adopts its window into the tab via
  Win32 re-parenting (QWindow.fromWinId). Use PoB's own GGG import inside
  it; a file-watcher on your PoB Builds folder hot-reloads any build you
  save there as Kalandra's active character automatically. "Launch
  external" fallback if embedding misbehaves.
- **Visual gear view (Build tab)**: the Container view is now a PoB-style
  paperdoll — gear slots laid out like the app (weapons/helmet top, body
  center, rings/belt, boots), rarity-colored frames, item art pulled from
  poe2db (cached forever in `data_engine/item_art/`), and poe.ninja-style
  hover tooltips with the full item description. Clear empty-state text when
  no build is loaded. Item parse now carries rarity + base type.
- **Menu manager**: only one menu opens at a time (opening a second closes
  the first), the overlay hides itself while any menu is open and returns
  when the last one closes. Character picker opens ~30% taller so the middle
  buttons stop scrunching.

### Fixed
- Embedded PoB now receives KEYBOARD input: reparented foreign windows don't
  get keystrokes by default, so clicking/entering the PoB container now
  attaches Kalandra's input thread to PoB's and hands it Win32 focus
  (AttachThreadInput + SetFocus). Typing, renaming, Delete all work.
- Companion orb art installed: Christian's nine orb PNGs (Transmutation →
  Chance) copied from the mirror into the live tree under their slug names —
  every orb in the selector now switches the overlay's art for real. The
  filename matcher also tolerates numbered/plural names now
  ("9_Chance_Orbs.png" → chance).
- Dashboard tab toggles: rebuilding no longer auto-reopens the dashboard
  (which fought the one-menu rule), and the dashboard re-reads saved toggles
  from disk if its config object ever misses them.
- Checkbox "on" state is now unmistakable: lighter square + real gold
  checkmark (`assets/theme/check.png`) instead of a solid gold fill.
- **W3-30 — Filter Editor for humans**: every block now reads in plain
  language ("SHOW: Divine Orb · area >= 65"), carries a color swatch chip
  painted with its actual label colors, and selecting one renders a live
  in-game-style label preview (text/background/border/font size from the
  block itself) above the raw filterese. Show/Hide/Minimal are gem buttons.
- **W3-21/23 — Pricing insight engine**: Price Check now tiers every mod —
  ★ premium (carries the price), good, neutral, — filler (EXCLUDE from the
  search to widen results), ▼ downside (lowers value) — plus a "Search
  strategy" verdict (what to include, when to price ambitiously, when the
  item trades as a base). Honest heuristics with a disclaimer, never a
  fabricated price.
- **W3-12 v1 — Character sheet export**: "Export sheet (HTML)" in the Build
  tab writes a themed, self-contained character page — poe.ninja-style
  layout but with the build's REAL PoB numbers (a Corrupted Blood character
  shows its actual DoT DPS chip, not zero) — and opens it in the browser.
  HTML-escaped against pasted-name injection.
- Stress suite grew to **285 checks** (mod-tier ordering traps like
  "reduced attack speed", filter style/describe parsing, character-sheet
  XSS escaping).
- **W3-20 — In-game Ctrl+C price popup**: copy any item in game and a themed
  card floats up by the cursor — parsed name/mods, an instant poe.ninja
  estimate for currency (never fabricated for gear), "Trade ↗", and a
  "Price Check tab" button that opens the dashboard pre-filled. Purely
  passive (reads the clipboard PoE2 itself writes). Toggle in Settings.
- **W3-13 — Crafting planner, real logic**: goal-aware plans (recognizes the
  base + phys/crit/life/res/spell/... keywords), three concrete routes
  (Essence-guaranteed / Chaos-reroll / Omen-biased) annotated with live
  prices once the Exchange tab has refreshed; the AI brain then refines the
  draft in place when connected (wired through the Orb's own ask path).
- **W3-25 — Currency tracker**: Exchange tab now has a "My currency" grid
  (all majors + Gold + your Mirror, obviously) with live portfolio value in
  Exalted and Divine equivalents; persists in config.
- **W3-26 — Daily movers + advice**: every price refresh snapshots the
  economy into the DB; after two days you get "Today's market" — currencies
  ±3% vs their 7-day average with buy/sell hints (clearly-labeled heuristics).
- **W3-22 — Saved searches**: Price Check can save any pasted item + league
  under a name and re-run it from a dropdown.
- **W3-11 — AI upgrade guide (v1)**: "Suggest upgrades (AI)" in Build Sim —
  the Orb reads your actual parsed build + live sim numbers and proposes
  3-5 concrete upgrades with reasons and cost brackets. (Sim-verified
  what-if diffs remain on the roadmap.)
- **W3-31 — Reserve snapshot strip (v1)**: the Reserve/BIS tab lists your
  ruby-medallion screenshots (newest first) with view/open-folder buttons
  and one-click "paste item from clipboard" filing. (OCR auto-read stays on
  the roadmap.)
- Stress suite grew to **258 checks** — planner goal-mapping, price-estimate
  fail-closed behavior, economy history idempotence, and mover/advice math
  on a temp database.
- **W3-04/05/06 — The whole app wears the frame**: Settings & Accounts, the
  Dashboard, Chat with the Orb, the Character picker, and Setup &
  Dependencies all migrated onto Christian's frame chrome
  (`KalandraFrameWindow`/`KalandraFrameDialog`) — celtic-gold border,
  medallion window buttons on the band, shared theme for tabs, text, combo
  menus, checkboxes, scrollbars, and submenus. Major message boxes
  (sync-finished, recording-saved, recording consent, issue delete, generic
  info) replaced with framed `kinfo`/`kconfirm` dialogs. Suite: 237 checks
  green, including a migration audit that fails if a chromed window ever
  builds a layout outside the glass.
- **W3-02/03 (final) — Christian's hand-made chrome assets**: window chrome
  now uses his Photoshop art — `assets/Window.png` (celtic-gold frame,
  nine-sliced so windows resize to ANY size with zero distortion) with
  `Close.png` / `Minimize.png` / `Maximize.png` face medallions top-right
  (red gem closes, green minimizes, blue maximizes; hover = gem glow ring).
  New `KalandraFrameWindow` / `KalandraFrameDialog`; message boxes use the
  frame; drag the gold to move, outer rim to resize, double-click title strip
  to maximize. The medallion buttons OVERLAY the top border band like a
  normal window's title-bar buttons (they take click priority over the
  resize rim; the corners stay grabbable), the title sits on the band with a
  dark shadow for readability, and the whole glass belongs to content. The
  mirror-shaped `MirrorWindow` remains available as an alternate skin.
  Border metrics measured from the art (150px nine-slice cut).
- **W3-02 (art v2) — Squared mirror frame** (`assets/mirror_frame_square.png`):
  the oval mirror warped into a squircle so the glass fits a window and the
  screen better, and the gothic bottom pendant shortened to 45% height — both
  per Christian's request. Done with an angular-radial superellipse warp that
  preserves the gold ring's shading; face medallions/rosettes survive intact;
  window-button and content geometry re-measured from the warp's forward map.
  The original mirror_of_kalandra.png is untouched (the overlay still uses it).
- **W3-02 (redesigned) — The window IS the Mirror**: per Christian's feedback
  the rectangular chrome was replaced by `MirrorWindow`/`MirrorDialog` — the
  window is a blown-up `mirror_of_kalandra.png`, alpha-masked to its exact
  shape, with content living inside the glass oval. The three face medallions
  on the top arc are the window buttons (their gems are already in the art:
  red = close, blue = minimize, green = maximize), the bottom-right star
  rosette is the resize grip, drag anywhere on the gold to move, and the
  aspect ratio is locked so the mirror never distorts. Geometry was measured
  from the art programmatically (gem pixels by color, glass by its dark
  core); content clicks always win over medallions that bleed into the glass.
  Message boxes (`kinfo`/`kconfirm`) are little mirrors too. Demo:
  `python -m gui_overlay.kalandra_window` from the repo root.
- **W3-02 (superseded) — Frameless golden chrome** (`gui_overlay/kalandra_window.py`):
  `KalandraWindow` / `KalandraDialog` with the painted ornate gold frame,
  corner gems, drag-anywhere title bar, native snap-friendly move/resize, and
  gem window buttons (ruby = close, sapphire = minimize, emerald = maximize).
  Plus themed message boxes `kinfo()` / `kconfirm()`. Preview before rollout:
  `python -m gui_overlay.kalandra_window`. Migration of Settings/dashboard
  onto the chrome (W3-04/05/06) waits on that visual check.
- **W3-10 — Build (PoB) tab view toggle**: Container view (stat chips, gear
  table, skill groups with the main skill starred) ⇄ Text breakdown (the
  classic full dump). Choice persists in config (`build_view_mode`).
- **W3-24 — Live Search inside the dashboard**: the official PoE2 trade site
  loads in an embedded web view in the tab (PyQt6-WebEngine optional; clean
  external-browser fallback). Manual whisper/buy flow unchanged (ToS-clean).
- **W3-32 — GitHub sync** (`core_engine/github_sync.py`): post issue-tracker
  entries as GitHub Issues and publish the open-items changelog as a
  pre-release on github.com/castleism/Kalandra_Git. Token (repo scope) lives
  in the OS keychain via the new Settings "GitHub" row.
- Stress suite grew to **179 checks** (chrome edge-geometry, gem-language
  source audit, GitHub repo parsing + fail-closed auth paths).
- **W3-01 — Kalandra theme module** (`gui_overlay/theme.py`): single source of
  truth for the app's look — gold-leaf palette, gem accents (ruby, sapphire,
  emerald, diamond), currency-orb iconography hooks, one shared Qt stylesheet
  builder (`kalandra_qss()`), and painter helpers for the ornate gold frame and
  cut-gem shapes. Settings and the dashboard now draw from it. Verified:
  stress suite extended 111 → 132 checks (all green), QSS structurally
  validated (62 rule blocks, all hex colors, gradients, gem selectors).
- GGG OAuth 2.1 PKCE sign-in flow (`core_engine/oauth_pkce.py`) with loopback
  redirect, client_id field, and a "Test PoE2 API (no login)" button.
- Email provider picker (Gmail / Outlook / Yahoo / Proton / iCloud) with
  sign-in and app-password shortcuts; credentials stored in the OS keychain.
- "Open site" buttons for every linked service: poe.ninja, PoE2 forums,
  YouTube, Path of Building, PoE Overlay, NeverSink FilterBlade, Exiled
  Exchange 2, Craft of Exile 2, Maxroll, Mobalytics, poe2wiki.net.
- Companion orb selector: tolerant art-file matching (accepts names like
  `Orb_of_Chance.png`), "(no art yet)" labels in the dropdown, and instant
  feedback showing exactly where to drop missing art.

### Fixed
- Settings now opens near dashboard width (1100px, bounded to the screen) —
  the frame border consumes ~110px, which was clipping the bottom button row
  at the old 580px width.
- Double-clicking a medallion (character selector, mic, snapshot) no longer
  ALSO fires the single-click action — Qt's Press→Release→DblClick→Release
  sequence restarted the single-click timer on the trailing release, opening
  both windows.
- Database sync no longer "stops partway": poe2wiki crawls now share a
  Cloudflare cooldown across workers, trip a circuit breaker after 30
  consecutive blocked requests (instead of burning hours marking thousands of
  pages failed), and retry previously failed pages next sync.
- Sync-finished dialog no longer claims "Whole site covered" while wiki pages
  are missing — pending now counts failed ('error') pages too.
- A single database write error during a crawl no longer aborts the whole sync.
- Settings → Dashboard tabs checkboxes were black-on-dark and unreadable; now
  themed (light text, gold check indicator).

## [0.1.0-pre.1] — 2026-07-02

Baseline for this changelog: five dashboard tool tabs (Filter Editor, Currency
Exchange, Price Check, Crafting Planner, Live Search), PoB live sim, talking
Divine Orb with AI brains, resumable poe2db/poe2wiki/poe.ninja sync, Obsidian
vault export, medallion overlay. See `docs/ROADMAP.md` → "Shipped" for the full
feature table and `READ_ME_FIRST.md` for the narrative history.
