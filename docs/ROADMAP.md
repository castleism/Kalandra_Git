# Kalandra Overlay — Roadmap

Status of the security/compliance "gating work" identified in
`docs/SECURITY_AND_PRIVACY.md`, the feature roadmap, and the routes we considered
and deliberately did not take.

> **Verified 2026-07-03** (Linux sandbox): all source files pass `py_compile`;
> `tests/stress_test.py` passes **285/285** adversarial checks (was 111 on
> 07-02 — theme/chrome geometry, GitHub sync, crafting planner, pricing
> insights, economy history, filter humanizer, character sheet added).
> Original 2026-07-02 note: all 38 source files pass `py_compile`;
> `tests/stress_test.py` passes 111/111 adversarial checks (pob_bridge parsing, trackers, scraper,
> poe.ninja, account_manager fail-closed, sqlite under 8 threads, trade_tools,
> filter_editor round-trip, obsidian_export, and the AST audit that catches
> unbound Q* names in the GUI files). Medallion callbacks and signal handlers
> all resolve. Live tree and `Kalandra_Git` mirror are content-identical
> (line endings only). No `crash.log` present. Full PyQt6 render can only be
> confirmed on Windows (the sandbox has no GPU/EGL libraries) — the AST audit
> exists precisely to cover that gap.

## Gating work (must-haves before selling)

| Item | Status | Effort | Notes |
|---|---|---|---|
| Remove plaintext secrets fallback (fail closed) | ✅ DONE | — | `account_manager` now stores only in the OS keychain; if keyring is missing, saving is disabled (no plaintext file). |
| Visible recording indicator + consent | ✅ DONE | — | Red “● REC” while recording; one-time consent dialog before first capture. |
| Pin & audit dependencies | ◑ PARTIAL | low | Add a committed `requirements-lock.txt` (exact versions) and run `pip-audit` in CI. Floors are set; full lock pending so 3.13 wheels keep resolving. **Audited 2026-07-10** (`pip-audit -r requirements.txt`, Linux sandbox, resolves floors to current releases): **no known vulnerabilities**. The lock file itself must be generated on Windows (`pip freeze`) so it captures the wheels you actually run. |
| Code-sign the Windows build | ☐ TODO | med ($) | Requires an Authenticode cert (~$100–400/yr) + signing in the build pipeline. Removes SmartScreen warnings. |
| Per-site ToS / licensing review | ☐ TODO | med (legal) | Especially: poe2wiki is **CC BY-NC** (non-commercial) — redistributing it in a paid product needs review/relicensing. Confirm poe2db, poe.ninja, Craft of Exile commercial terms. |
| Privacy policy | ✅ DONE 2026-07-10 | — | `docs/PRIVACY.md`: plain-words policy — local-first tables (incl. Craft Hunter's in-memory-only OCR crops), the exact when-and-what of AI-provider sends, fixed outbound host list, user controls/deletion. Still wants the pre-commercial legal review (tracked with the ToS row). |
| Sandboxed file writes | ◑ PARTIAL | low | All writes already go under `data_engine/`; formalize + document. |

### How to do the dependency audit now (low-hanging)
```
pip install pip-audit
pip-audit -r requirements.txt
pip freeze > requirements-lock.txt   # commit this for reproducible installs
```

## Shipped

| Feature | Status |
|---|---|
| Five medallion buttons aligned (single/double-click, drag, L-click+ESC close) | ✅ |
| Real MP4 screen recording (+ consent/indicator) | ✅ |
| Local voice transcription (Whisper) + typed chat | ✅ |
| poe2db crawler with persistent, resumable frontier | ✅ |
| poe2wiki (MediaWiki API) scraping | ✅ |
| poe.ninja economy snapshots | ✅ |
| Obsidian vault export with relationship links | ✅ |
| AI brain (OpenAI/Gemini/…) + key helpers + budget tracking | ✅ |
| Talking orb lip-sync (jaw-drop + optional viseme sprites) | ✅ |
| Characters via PoB code/link + saved-builds folder + ladder browse | ✅ |
| Live PoB engine (LuaJIT headless) + Build Sim self-test | ✅ |
| Reserve / BIS tracker | ✅ |
| Issues / Changelog tracker + “Flag last answer” | ✅ |
| Verified-corrections layer over the AI | ✅ |
| **Filter Editor tab** (exact round-trip `.filter` edits, `.bak` backup) | ✅ 2026-06-30 |
| **Currency Exchange tab** (poe.ninja live economy, off-thread) | ✅ 2026-06-30 |
| **Price Check tab** (item paste → official trade search) | ✅ 2026-06-30 |
| **Crafting Planner tab** (NL goal → craft path; AI or offline heuristic) | ✅ 2026-06-30 |
| **Live Search tab** (official trade live search, manual buy flow) | ✅ 2026-06-30 |
| Double-click guard on medallions (no more "both windows open") | ✅ 2026-07-03 |
| DB sync: wiki Cloudflare circuit-breaker + shared cooldown + honest "pending" count (queued **and** error pages) | ✅ 2026-07-03 |
| Settings: readable checkboxes (Dashboard tabs), gold check indicator | ✅ 2026-07-03 |
| Companion orb selector: tolerant art matching + "(no art yet)" labels + live feedback | ✅ 2026-07-03 |
| GGG OAuth 2.1 PKCE flow (`core_engine/oauth_pkce.py`) + client_id field + "Test PoE2 API" button; email provider picker; "Open site" buttons for all link services | ✅ 2026-07-03 |

## Feature Wave 3 — plan of action (added 2026-07-03)

Christian's requested feature wave, broken into phases with trackable status.
Update the Status column as work lands: ☐ TODO → ◑ IN PROGRESS → ✅ DONE.
Effort: S (≤ half day) · M (1–2 days) · L (3–5 days) · XL (1–2 weeks).

### Phase 1 — The Kalandra look (full custom chrome)

Goal: every window the app opens matches the Mirror of Kalandra: golden
artistic borders, gold faces, gem accents (rubies, sapphires, emeralds,
diamonds), currency-orb iconography. Gorgeous, everywhere.

| ID | Item | Status | Effort | Plan |
|---|---|---|---|---|
| W3-01 | `gui_overlay/theme.py` — single shared theme module | ✅ DONE 2026-07-03 | M | Shipped: gold-leaf palette + four gems, `kalandra_qss()` builder (62 rule blocks), `paint_ornate_frame` / `draw_gem` / `draw_orb_dot` painters (lazy PyQt, headless-importable), gem-property buttons (`set_gem`). Dashboard + Settings now pull from it. 21 new stress checks (suite: 132/132). |
| W3-02 | Window chrome — **the window IS the Mirror** | ✅ CODE DONE 2026-07-03 (redesigned per Christian: art-shaped window, not a gold rectangle) — awaiting on-Windows visual check (`python -m gui_overlay.kalandra_window`, repo root) before W3-04/05/06 migrate onto it | L | Shipped: `MirrorWindow`/`MirrorDialog` drawn as the actual mirror_of_kalandra.png, alpha-masked shape, content inside the glass, face medallions = window buttons (red/blue/green gems in the art = close/min/max), star rosette = resize grip, aspect locked. Rectangular `KalandraWindow` kept as fallback. 205/205 stress checks. |
| W3-03 | Theme asset kit | ◑ IN PROGRESS — Christian is producing the art | M | Delivered 2026-07-03: `Window.png` (frame), `Close/Minimize/Maximize.png` (medallion buttons) — wired into `KalandraFrameWindow`. Still wanted: tab-header orb icons, gem accents for buttons, gold flourishes. Painted fallbacks cover anything missing. |
| W3-04 | Migrate Settings dialog to the frame chrome | ✅ DONE 2026-07-03 | S | Settings & Accounts + Character picker now `KalandraFrameDialog` (Christian's Window.png + medallions). |
| W3-05 | Migrate dashboard + all tabs | ✅ DONE 2026-07-03 | M | Dashboard is a `KalandraFrameWindow`; tabs/tables/scrollbars/combos/menus all themed via theme.py. Tab-header orb icons wait on more W3-03 art. |
| W3-06 | Migrate chat + dependencies dialogs; themed message boxes | ✅ DONE 2026-07-03 (main paths) | M | Chat with the Orb + Setup & Dependencies framed; `kinfo`/`kconfirm` replace the big QMessageBoxes (sync-finished, recording saved, consent, issue delete, `_info`). A few minor info boxes (export/import notices, key-saved toasts) still stock — sweep opportunistically. |

### Phase 2 — Build intelligence

| ID | Item | Status | Effort | Plan |
|---|---|---|---|---|
| W3-10 | Build (PoB) tab: **view toggle** — Container view ⇄ Text breakdown | ✅ DONE 2026-07-03 | M | Shipped: toggle button (persists as `build_view_mode`), Container view = stat chips (DPS/Life/ES/crit…), gear table (slot/item/mods), skill-group list with ★ main group, live-sim line; Text view unchanged. Slot icons upgrade with the W3-03 art kit. |
| W3-11 | Build Sim tab: **AI upgrade guide** | ◑ v1 SHIPPED 2026-07-03 | L | Shipped: "Suggest upgrades (AI)" — Orb reads the parsed build + live sim and proposes 3-5 concrete upgrades with reasons/costs. Remaining: sim-verified what-if diffs (+DPS/+EHP per proposal) and per-upgrade cards. |
| W3-12 | **PoB-accurate build view** (poe.ninja-style, but honest DPS) | ◑ v1 SHIPPED 2026-07-03 | L | Shipped: themed HTML character sheet export from the Build tab — real PoB stat chips (incl. TotalDot), gear, skills, live-sim line. Remaining: in-app interactive page + configurable damage source picker. |
| W3-13 | Crafting Planner: finish it | ✅ DONE 2026-07-03 | M | Shipped: goal parsing (base + stat keywords), three routes (Essence/Chaos/Omen) with live poe.ninja cost annotations, AI refinement of the draft plan via the Orb's ask path. Future nicety: exact mod tiers from poe2db data. |

### Phase 3 — Trading suite

| ID | Item | Status | Effort | Plan |
|---|---|---|---|---|
| W3-20 | **Ctrl+C price popup** (Exiled Exchange 2 / PoE Overlay style) | ✅ DONE 2026-07-03 — needs Christian's in-game test (checklist G1) | L | Shipped: Qt clipboard watcher (no hotkey lib needed — Windows notifies all clipboard changes), themed cursor-side card with parsed item, instant currency estimate (gear never fabricated), Trade ↗ + pre-filled Price Check button, 12s auto-dismiss/ESC, Settings toggle. |
| W3-21 | Price Check tab: **intuitive interface** | ✅ v3 CODE DONE 2026-07-10 — needs Christian's live test (open a search, confirm the filters arrive pre-filled) | M | v2: per-mod tier view + strategy verdict + embedded trade site. v3 (the remaining half): parsed item -> trade query JSON via the site's stat-id map (`/api/trade2/data/stats`, fetched once, cached 7 days in `data_engine/trade_stats_poe2.json`) -> `…?q=<json>`. Premium/good mods enabled at your rolls ("at least as good as mine", two-slot mods by average), the rest included but disabled; unmapped mods reported honestly. Plain search URL any time the map isn't ready. Clipboard popup's Trade ↗ upgrades too. `tests/trade_query_checks.py` (35). Sandbox couldn't reach the live endpoint, so the query-vs-site handshake is the thing to eyeball. |
| W3-22 | **Saved searches + scheduled live searches** | ◑ SAVED done 2026-07-03; scheduler TODO | M | Shipped: named saves (item + league) in Price Check with load/delete dropdown. Remaining: interval re-runs with new-listing notifications. |
| W3-23 | **Pricing insight engine** | ◑ v1 SHIPPED 2026-07-03 | L | Shipped: heuristic mod-value tiers (which mods drive price / can be excluded / lower value) + strategy advice, wired into Price Check. Remaining: empirical with/without trade-result sampling and suggested listing price. |
| W3-24 | Live Search tab: **embedded trade site** | ✅ DONE 2026-07-03 | M | Shipped: "Open here" loads the trade site in the tab (crash-safe lazy QWebEngineView); "Browser ↗" keeps the external path; graceful card when PyQt6-WebEngine is missing. Whisper/buy stays manual. |
| W3-25 | Currency Exchange: **player currency tracker** (incl. gold) | ✅ DONE 2026-07-03 | M | Shipped: holdings grid (majors + Gold + Mirror), saved to config, live portfolio value in Exalted + Divine equivalents. History chart later. |
| W3-26 | Currency Exchange: **daily movers + investment advice** | ✅ DONE 2026-07-03 | M | Shipped: every refresh snapshots to `economy_history`; "Today's market" shows ±3% movers vs 7-day average with buy/sell hints + disclaimer. AI narration & holdings-aware advice are easy follow-ons. |

### Phase 4 — Capture, filters, community

| ID | Item | Status | Effort | Plan |
|---|---|---|---|---|
| W3-30 | Filter Editor: **redesign for humans** | ◑ v1 SHIPPED 2026-07-03 | L | Shipped: plain-language block lines ("SHOW: Divine Orb · area >= 65"), painted color-swatch chips, live in-game label preview pane, gem action buttons, framed save confirm. Round-trip + `.bak` untouched. Remaining: category grouping + drag-to-reorder. |
| W3-31 | Unique/BiS Reserve tab: **snapshot item scanner** | ✅ v2 SHIPPED 2026-07-10 | L | v1: snapshot strip (newest ruby-medallion screenshots, view/open-folder/rescan) + one-click clipboard filing. v2: "🔍 Read item from snapshot" — OCRs the selected screenshot straight into the editor (2x upscale; the SAME optional adapters Craft Hunter ships: RapidOCR preferred, Tesseract fallback; feature explains the pip install when neither exists), auto-fills the name from the parsed text. Ctrl+C paste remains the exact route; the UI says OCR isn't gospel. |
| W3-32 | Issues/Changelog → **GitHub repo** | ✅ CODE DONE 2026-07-03 — needs Christian's token (Settings → GitHub → "Get a key") for a live test | M | Shipped: `core_engine/github_sync.py` (issues + changelog-as-prerelease, fail-closed auth, tolerant repo parsing), Settings "GitHub" keychain row, Issues-tab buttons "Post selected → GitHub" / "Publish changelog → GitHub". Repo: **https://github.com/castleism/Kalandra_Git**. |

| W3-33 | **Photo item scanner** (snapshot → item) | ☐ TODO | M | Two engines, best available wins: (a) offline Tesseract OCR on the tooltip crop (upscale 2x + threshold — PoE tooltips are high-contrast, OCR-friendly), (b) the multimodal AI brain reads the image directly (far more accurate on stylized fonts, ~fraction of a cent per scan, uses the key already in Settings). Output feeds the SAME parse_item_text pipeline as Ctrl+C — so Reserve bank, price check, and insights all work from a screenshot. |
| W3-34 | **Video fight analyzer** (clip → DPS/buffs/effects) | ☐ TODO | XL | Post-fight analysis of our OWN recordings (media_recorder already writes MP4s; opencv+numpy already installed). Phase 1: boss HP bar tracking by pixel-fill sampling at ~3fps → HP% curve → time-to-kill, and real DPS once boss HP totals come from the DB. Phase 2: buff/debuff icon detection via opencv template-matching against icon sprites from the scraped data. Phase 3: multimodal AI labels keyframes (ground effects, environment). Purely passive post-processing of recordings = ToS-clean (see 'Under ToS review' — we read pixels, never send input). |

## Feature Wave 4 — THE COMPANION (spec: `docs/DESIGN_COMPANION.md`)

> Captured 2026-07-04. Kalandra as a player-aware teammate: the owl guide,
> profile-calibrated AI, character intelligence, streamer suite, community
> data engine. Full phased spec lives in `docs/DESIGN_COMPANION.md`; these are
> the tracker lines.

| ID | Item | Status | Size | Notes |
|---|---|---|---|---|
| W4-01 | Owl guide: mirror's owl as menu companion (bubbles + tab walkthroughs) | ✅ SHIPPED 2026-07-04 | M | `owl_guide.py`; owl face + arrow finial cut from the mirror art. |
| W4-02 | Player profile + first-use interview (chip bubbles, leech-aware wording) | ✅ SHIPPED 2026-07-04 | M | `player_profile.py`, `owl_interview.py`; profile injected into every AI prompt. Right-click owl to redo. |
| W4-03 | Companion tab: threaded orb chats + friendly color-coded action log | ✅ v1 SHIPPED 2026-07-04 | L | `companion_tab.py`; auto-attendant stub (local templates, off by default). |
| W4-04 | PoB import + character deep-scan (auth via saved account, name or class/lvl/league) | ☐ TODO | L | DESIGN_COMPANION P1. Infer profile facts from imports instead of asking. |
| W4-05 | Character reviews + per-character orb threads + standard-shuffle detection | ☐ TODO | L | P2. Owl confirms playstyle/gear drift on review open. |
| W4-06 | Nerf-aware price intelligence (patch-note diff + league price curves) | ◑ v2 WIRED 2026-07-10 | L | P3. Engine (2026-07-04) + the real feeds (2026-07-10): `patches_from_db` mines patch-note/Version pages from the knowledge base, `price_series_from_db` reads the Exchange tab's `economy_history` snapshots, `nerf_watch()` is the one-call signal — and Price Check now shows an amber "🪓 Nerf watch" line for named items (background thread, local DB only). `tests/nerf_checks.py` 43 green. Remaining: surface in character reviews (W4-05 path). |
| W4-00 | Provider interfaces — every 3rd-party tool swappable (north star) | ✅ SHIPPED 2026-07-04 | M | `core_engine/providers.py`: BuildCalculator / Economy / TradeSearch / CraftSimulator / GameData / Capture + registry; migrate call sites opportunistically. |
| W4-07 | Character folders + roadmap files + PoB-as-calculator + build costing | ◑ FOUNDATION 2026-07-04 | XL | P4. `character_folio.py` shipped (folders, scaffold docs, budgeted prompt corpus). Remaining: review/roadmap generation, craft-vs-buy, character sheet panel. |
| W4-08 | BIS bank ↔ AI sims, live-search suggestions, notifications (desktop/email/SMS + orb bubble w/ trade link) | ☐ TODO | L | P5. Variant selectors (ilvl/spell level) in Reserve tab. |
| W4-09 | Auto-attendant researched edition (cadence + token-budget settings per topic) | ☐ TODO | XL | P6. Sources: build sites, YouTube, Reddit, forums, Twitch; sim-verified suggestions. |
| W4-10 | Streamer suite: OBS websocket, stream transcription → guide log + clips, live highlight overlays, replay buffer | ◑ PARTIAL 2026-07-05 | XL | P7. The OBS websocket + replay-buffer half SHIPPED as W4-21's capture path (`core_engine/obs_bridge.py`, registered as the `capture` provider). Remaining: transcription → guide log, highlight overlays. Overlay annotation only — zero game input. |
| W4-21 | Death review: playback of what killed you + PoB defensive autopsy | ✅ v1 SHIPPED 2026-07-05 | L | Client.txt death/zone watcher in the overlay (1s tail, exe-gated); on death OBS flushes its replay buffer → clip + context saved to `data_engine/deaths/`; Death Review tab (frame scrubber, evidence-only defensive audit of the ACTIVE PoB build, AI autopsy, post-the-clip folder button). `tests/death_checks.py` (42). Needs: OBS 28+ with WebSocket server + Replay Buffer enabled, `websocket-client` pip. |
| W4-11 | Grind tracker: loadout snapshots → per-mod return estimates (local-first) | ✅ v1 SHIPPED 2026-07-04 | L | P8. `grind_tracker.py` + Grind Tracker dashboard tab (snapshot form, run timer, income log, per-loadout + per-mod tables, live poe.ninja valuation). Community pooling stays P9. |
| W4-12 | Community data engine: opt-in price-check/grind telemetry + mod-value price model | ◑ LOCAL SEED 2026-07-04 | XL | P9. `price_ledger.py` shipped; every Price Check logged locally AND ledger estimates now display in the tab (honestly labeled). Remaining: community backend + poisoning defenses. poeprices.info proves feasibility. |
| W4-13 | 3D orbs: rig + load `assets/orbs/3d/<slug>.glb` (path already reserved in code) | ☐ TODO | L | QtQuick3D or embedded model-viewer; falls back to 2D art. |
| W4-14 | Ghost mode: overlay fades + click-through while the game has focus; Ctrl to interact | ✅ SHIPPED 2026-07-04 (r2: exe-based detection after browser false-positive) | M | `game_watch.py` (foreground PROCESS EXE + exact-title fallback, WS_EX_TRANSPARENT toggle, 150ms Ctrl poll) + split frame/orb paint opacities. Passive reads only — ToS-clean. `tests/ghost_checks.py` (36). |
| W4-15 | Installer/settings tab previews: screenshot of each dashboard tab during setup | ☐ NEEDS CHRISTIAN'S CAPTURES | M | Mechanism plan: `installer/assets/tab_previews/<tab>.png` shown by Kalandra-Setup.ps1 and the Settings tab picker. Blocked on real screenshots of each tab (can't be generated headlessly) — capture at 1280×800, one per tab, drop in that folder. |
| W4-16 | Custom dashboard tabs: user-added website (contained browser) or program (window adoption) | ✅ SHIPPED 2026-07-04 | M | Settings → Custom tabs; config `custom_tabs`; program tabs get dynamic PobLiveTab subclasses. |
| W4-17 | Modern email auth: Gmail OAuth2+PKCE+XOAUTH2, keychain-only tokens | ✅ SHIPPED 2026-07-04 | M | `email_oauth.py`; app passwords = legacy fallback. Notification sender (P5) plugs into `send_mail_oauth`. |
| W4-18 | Build (PoB) AI review button: mechanism deduction + sim-verifiable suggestions | ✅ v1 SHIPPED 2026-07-04 | L | W4-05's per-character review, on demand in the Build tab; saves to the folio. Remaining: auto-generate on import (W4-04) + standard-shuffle detection. |
| W4-19 | New-player arc: build finder conversation + guide→priced roadmap engine | ✅ v1 SHIPPED 2026-07-04 | L | `build_seeker.py` + owl hand-off + Companion seeding. Remaining: auto-fetch guide URLs (today: paste text/codes), auto-load variants into the PoB (live) tab, live-search auto-creation from watchlist (W4-08). |
| W4-20 | Install modes per add-on: "Local Copy" (default OS location, app points at it) / "Kalandra Contained" (bundled under tools\) / "Browser based" (contained web tab, e.g. pob.cool) | ☐ TODO | L | Installer redesign: Kalandra-Setup.ps1 asks per add-on; default flips FROM contained TO local-copy (%LOCALAPPDATA%\Programs), with detection of existing installs at standard paths (gui_overlay/dependencies.py already probes several). The uninstaller's Move-out (shipped 2026-07-04) is the migration path for existing bundles. Browser-based mode = custom web tab presets (W4-16 machinery). |

### Suggested build order

1. **W3-01/02/03** (theme foundation) — everything after lands beautiful.
2. **W3-04/05/06** (migrate windows) — the "gorgeous" payoff.
3. **W3-10, W3-13, W3-24** (PoB toggle, crafting planner, embedded trade) — high value, medium effort.
4. **W3-20/21** (Ctrl+C popup + price-check UX) — the flagship trading flow.
5. **W3-22/23, W3-25/26** (searches + currency intelligence).
6. **W3-11/12** (AI upgrade guide + honest build viewer).
7. **W3-30/31/32** (filter redesign, snapshot scanner, GitHub).

New optional dependencies this wave introduces (all guarded, app runs without
them): `PyQt6-WebEngine` (W3-24), `pytesseract` + Tesseract (W3-31), a global
hotkey library — clipboard listener only (W3-20).

ToS note (unchanged, hard rule): W3-20 reads the clipboard that the game
itself populates on Ctrl+C. No input is ever sent to the game; every buy,
whisper, and click in game is the player's.

## Feature Wave 5 — Craft Hunter (spec: `docs/CRAFT_HUNTER_SPEC.md`)

> Alert-only crafting mod sniper (spec written 2026-07-06). Hard rule from
> the spec (§2), same as everywhere else in Kalandra: **no input
> interception, ever** — we read what the game shows/writes, we never touch
> the game. The alarm informs the human; the human does every click.

| ID | Item | Status | Size | Notes |
|---|---|---|---|---|
| CH-P1 | Regex helper: target-mod list UI (autocomplete from `localized_knowledge.db` + curated templates), in-game stash-search regex generator (PoE dialect, ≤50 chars, honest budget degradation), clipboard-confirm HIT / keep-going wired into the W3-20 watcher | ✅ SHIPPED 2026-07-10 | M | `core_engine/craft_hunter.py` (pure engine, OCR-noise-tolerant matcher ready for P2) + `gui_overlay/craft_hunter.py` (tab in 🔨 Crafting + cursor toast); armed hunts replace the price popup. `tests/craft_checks.py` (78) all green. |
| CH-P2 | OCR watcher: one-time tooltip crop calibration, hash-skip capture loop, RapidOCR (optional import, pytesseract fallback), full-screen click-through flash + loud sound + F8 arm hotkey | ✅ CODE DONE 2026-07-10 — needs Christian's on-Windows check (calibrate → watch → flash/sound; use Windowed Fullscreen) | L | Watcher loop fully unit-tested with injected capture/OCR; flash is `WindowTransparentForInput` (can only be looked at); F8 = passive GetAsyncKeyState poll (ghost mode's Ctrl pattern, no hook). OCR engines lazy + optional (`rapidocr-onnxruntime` preferred, ~60 MB — kept OUT of the default install, commented in requirements.txt). Clipboard confirm stays authoritative. |
| CH-P3 | Polish: session stats → grind_tracker (orbs-per-hit), per-target sounds, essence/omen-aware hints from `offline_craft_guidance`, near-miss soft chime | ◑ v1 SHIPPED 2026-07-10 | M | Shipped: near-miss detection (amber, right-mod-low-roll), Route hints button (essence/chaos/omen routes + live prices), confirms-per-hit in session stats. Remaining: push stats into grind_tracker's per-mod tables; per-target sounds. |

## In progress / partial

| Item | Status |
|---|---|
| Game-file data extraction | ◑ Import of pre-extracted JSON done; in-process Oodle bundle decode TODO |
| PoB "unsupported mods" | ◑ Needs `unsupported.txt` from PoB dev mode; then add patterns to PoB's `ModParser.lua` |
| Your own (non-ladder) PoE2 characters via API | ☐ Blocked on GGG shipping the PoE2 OAuth API (letter drafted: `docs/GGG_OAuth_Application_Letter.md`) |
| Higher-fidelity face rig (layered art, blinks) | ☐ Optional — drop in layered mouth/eye art (`docs/VISEME_FACE_SETUP.md`) |

## Next up (close)

> Feature Wave 3 above is the active plan; these remain queued behind it.

1. **"Hey Kalandra" wake word** — lightweight always-on detector (low CPU) that
   only wakes transcription when it hears the phrase.
2. **ElevenLabs voices** — premium cloud TTS alongside the free local voice.
3. **DB status window** — ✅ SHIPPED 2026-07-10 (double-click the sync
   medallion: active DB path/size, pages, last sync, per-patch and
   per-source histograms, crawl frontier, source picker editing the same
   `sources_enabled` the sync worker honors, Sync-now button;
   `database_handler.db_status` is read-only + `tests/db_status_checks.py`
   (11)). Remaining nicety: a live "newer patch exists" probe — today the
   window shows last-sync age and says to re-sync after patches.
4. **PoE Overlay II Standalone** — add to the integrations list in setup/settings.
5. **Lock + audit dependencies** (quick win, see above).

## Mid-term

- **Character threads + orb identity** — each character gets a manually-chosen
  orb and its own preserved chat thread; switching characters never mixes
  builds. Loading a build can create/save it in a tabbed PoB instance.
- **Character Sheet (flagship)** — the in-game sheet but better: character +
  gear on the side, tree jewels listed, screenshot import slot, all of PoB's
  extra calculations surfaced. Interactive highlighting: hover "main skill
  damage" → everything related on screen lights up; off-screen contributors
  appear in a dropdown; unused passives/supports greyed at the bottom.
- **Dynamic FilterBlade filter** — auto-adjust the loot filter to exchange
  rates with a value threshold (e.g. "≥ 1 Divine"); confirm changes on boot.
- **Investment tracker** — currency invested per craft, alongside Reserve/BIS;
  alert on pickup of items matching wanted expedition-reforge mods.
- **Temple planner.**
- **Overlay transparency slider** (Settings) — ✅ SHIPPED 2026-07-10: live
  slider (35–100%), read from config every paint so it applies as you drag;
  ghost mode's fade multiplies on top of it.
- **Minimize-to-icon** when a menu opens, so two windows aren't fighting to
  stay on top.

## Under ToS review (build only with care)

- **DPS calculator via screen recording** — passive observation of boss HP,
  buffs, ground effects. Reading/displaying the screen is generally acceptable;
  the hard line is never sending input to the game.
- **Training Dummy / combo builder** — offline combo building and review is
  fine. Live "press this now" hints are a gray area: display-only, clearly
  optional, never automate the keypress.

## Deeper AI

- True "simulate build changes to optimize" brain — drive the live PoB engine
  to compute what-if changes (today the Orb guides you through PoB's Power
  Report instead).

## Routes considered and NOT taken — and why

- **Right-click context menu on the overlay** — REMOVED. It opened a menu that
  trapped the cursor over a frameless always-on-top window. Close is now
  hold-left-click + ESC; right-click is a deliberate no-op
  (`setContextMenuPolicy(NoContextMenu)`).
- **Any gameplay automation** (auto-buy, auto-whisper, auto-teleport, sending
  any input to the game) — permanent no. Violates GGG's ToS and risks bans.
  Everything Kalandra does is read-only and advisory; the player performs
  every in-game action. This also shaped Price Check / Live Search: they open
  the official trade site; you whisper and buy manually.
- **Plaintext fallback for secrets** — rejected. If the OS keychain is
  unavailable, saving is refused rather than written to a file. Fail closed.
- **Hard-pinning (`==`) dependencies in requirements.txt** — rejected. Pins to
  old versions force source builds needing a C++ toolchain most users don't
  have. `>=` floors + a committed lock file (pending) instead.
- **lxml for scraping** — rejected in favor of Python's built-in HTML parser;
  avoids a native build dependency for a marginal speed gain.
- **Reading the user's AI-provider account balance** — impossible, not just
  rejected: no provider exposes billing balance via API. Session token
  tracking + a user-set budget warning instead.
- **Transcript logging on by default** — rejected for privacy. Logging will be
  strictly opt-in; the repo excludes transcripts, configs, secrets, and DBs.
- **Bundling PoB / LuaJIT / Rhubarb / extractor binaries** — rejected
  (licensing + trust). Kalandra drives the user's own installed copies; the
  installer helps fetch and locate each and records verified revisions.
- **60 FPS overlay animation** — replaced with 30 FPS wall-clock physics,
  half-rate idle repaint, and zero repaints while hidden; plus a pre-scaled
  pixmap cache. Same look, roughly half the paint cost on weak hardware.
- **Per-frame smooth pixmap rescaling** — replaced by the `(name, w, h)` keyed
  cache; it was the top CPU cost on minimal hardware.
- **Redistributing poe2wiki content in a paid build** — on hold, not shipped:
  CC BY-NC licensing means a commercial release needs review/relicensing
  first (see gating table).
- **Waiting on GGG OAuth for personal characters** — deferred, not rejected:
  the PoE2 account API doesn't exist yet, so ladder browsing + PoB codes are
  the interim path. Revisit when GGG ships it.
