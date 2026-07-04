# Changelog

All notable changes to Kalandra are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versions follow
the app's `version.py`. Process: every finished ROADMAP item gets an entry here
**and** a status flip in `ROADMAP.md`, in the same commit.

Repo: https://github.com/castleism/Kalandra_Git

## [Unreleased]

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
vault export, medallion overlay. See `ROADMAP.md` → "Shipped" for the full
feature table and `READ_ME_FIRST.md` for the narrative history.
