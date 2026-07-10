# Kalandra — Acquisition Dossier

*The document we would hand Grinding Gear Games tomorrow if the call came.
Rebuilt from repo reality each run by the acquisition-dossier-maintainer
routine (see `docs/ROUTINES.md`). Never let this flatter — every claim
below is checked against source at the time of writing.*

## Revision notes

- **2026-07-10 (this revision, initial build):** First build of this
  document — no prior version existed to diff against. Baseline: v0.1.0-pre.1,
  38 `core_engine/` modules + 14 `gui_overlay/` modules (~24,000 lines),
  **844/844 test checks green** across 13 suites. The repo is under active
  concurrent development from other scheduled routines (feature worker,
  nightly CI/test-hardener) while this dossier was being built — several
  numbers below were re-verified mid-run as other sessions committed: the
  **item-in-hand provider seam** landed (`core_engine/providers.py`) and
  the Ctrl+C clipboard watcher in `mirror_window.py` was migrated onto it
  — the first real proof of the "every pipeline swappable" law being
  enforced retroactively on old code, not just applied to new features.
  The **photo item scanner (W3-33)** went from code-complete-but-untested
  to fully covered (`tests/photo_scan_checks.py`, 28 checks) within this
  same run. `tests/companion_checks.py`'s capability-count assertion,
  stale at 6 when first read, was corrected to 7 by a concurrent commit
  before this document was finalized. Net: treat every count in this
  document as a snapshot of a fast-moving target, not a settled state —
  the next run will re-measure everything from scratch, as designed.
- `docs/PROVIDER_AUDIT.md` and `docs/GATING_RESEARCH.md` do not exist yet.
  Sections that would cite them instead cite `core_engine/providers.py`,
  `docs/VISION_ACQUISITION.md`'s pipeline matrix, and `docs/ROADMAP.md`'s
  gating table directly. Re-point those sections once the audit docs land.

---

## 1. Product inventory

Grouped by the six pre-GGG pillars in `docs/VISION_ACQUISITION.md`. Quality
evidence: **844 of 844 automated checks pass** across 13 suites (run
2026-07-10): `stress_test.py` 290, `craft_checks.py` 111, `pob_sim_checks.py`
55, `companion_checks.py` 97, `provider_checks.py` 49, `nerf_checks.py` 43,
`death_checks.py` 42, `trade_query_checks.py` 35, `extractor_checks.py` 33,
`ghost_checks.py` 31, `photo_scan_checks.py` 28, `recorder_checks.py` 19,
`db_status_checks.py` 11. Suites are hand-rolled `check()`/`guard()`
harnesses, not pytest, but run the same way in CI (`docs/CI_LOG.md`).

### Pillar 1 — Know everything (knowledge base)
- poe2db crawler with a persistent, resumable frontier (`core_engine/scraper.py`)
- poe2wiki MediaWiki-API scraper, CC BY-NC 3.0 attributed (`core_engine/wiki_scraper.py:4-5,42`)
- poe.ninja economy snapshot ingestion (`core_engine/poe_ninja.py`)
- DB status window: live path/size/pages/last-sync, per-patch and per-source
  histograms, crawl frontier, source picker (`database_handler.db_status`,
  read-only) — `tests/db_status_checks.py` (11)
- Verified-corrections layer over the AI's answers
- Patch/nerf intel mined from the knowledge base (`core_engine/nerf_intel.py`) —
  `tests/nerf_checks.py` (43)
- Game-file extraction R&D: pre-extracted JSON import done; in-process Oodle
  bundle decode still TODO (the prototype of the post-GGG data path)

### Pillar 2 — Compute everything (build math)
- Live headless PoB engine (LuaJIT) with Build Sim self-test
- Characters via PoB code/link, saved-builds folder, ladder browse
- Build (PoB) tab: Container view ⇄ Text breakdown toggle
- AI upgrade guide (v1): 3-5 concrete suggestions with reasons/costs;
  sim-verified what-if diffs still pending
- Themed HTML character-sheet export (real PoB stat chips incl. TotalDot)

### Pillar 3 — See what the player sees (read-only I/O)
- Ctrl+C clipboard item reader — now routed through the `item_in_hand`
  provider seam (`core_engine/providers.py`, `ClipboardItemInHand`); the
  overlay's own watcher (`gui_overlay/mirror_window.py`) calls
  `get_provider("item_in_hand")` instead of touching the clipboard directly
- Photo item scanner (W3-33) — AI-vision read first (user's configured
  brain) with offline OCR (RapidOCR/Tesseract, 2x upscale) as the free
  fallback, feeding the same `parse_item_text` pipeline as Ctrl+C
  (`core_engine/photo_scanner.py`, wired into `PriceCheckTab._scan_image`
  in `gui_overlay/dashboard.py`) — `tests/photo_scan_checks.py` (28)
- Reserve/BiS tab snapshot OCR ("Read item from snapshot") — same shared
  OCR adapters, auto-fills the name (shipped 2026-07-10)
- Craft Hunter tooltip OCR watcher (P2): calibrated crop, hash-skip loop,
  RapidOCR/Tesseract, full-screen flash + sound alarm
- Real MP4 screen recording with visible "● REC" indicator + one-time
  consent dialog
- `Client.txt` death/zone tail (`death_review`) — `tests/death_checks.py` (42)
- Ghost mode: overlay fades/click-through while the game has focus, exe-gated
  foreground detection — `tests/ghost_checks.py` (31)

### Pillar 4 — Advise like a coach
- Companion tab: threaded orb chats, color-coded action log
  (`tests/companion_checks.py`, 97)
- Owl guide + first-use profile interview, injected into every AI prompt
- Death Review tab: evidence-only defensive audit of the active PoB build,
  AI autopsy, clip playback — `tests/death_checks.py` (42)
- Build (PoB) AI review: mechanism deduction + sim-verifiable suggestions
- New-player arc: build-finder conversation → guide→priced roadmap
- Nerf watch in Price Check: patch-note diff + `economy_history` price
  curves surfaced as an amber warning — `tests/nerf_checks.py` (43)

### Pillar 5 — Trade without touching
- Price Check tab: item paste/scan → trade-site search, per-mod tier view,
  strategy verdict, embedded trade site; v3 prefills the official site's
  `?q=` filter JSON from the parsed item via the stat-id map
  (`tests/trade_query_checks.py`, 35)
- Currency Exchange tab: live poe.ninja rates, holdings tracker (incl. Gold/
  Mirror), daily-mover alerts vs 7-day average
- Live Search tab: embedded official trade site, manual whisper/buy flow
- Crafting Planner tab: NL goal → craft route (Essence/Chaos/Omen) with live
  cost annotations
- Filter Editor tab: exact round-trip `.filter` edits with `.bak` backup,
  plain-language block view
- Craft Hunter (P1): target-mod list, in-game stash-search regex generator,
  alert-only sniper — `tests/craft_checks.py` (111)

### Pillar 6 — Ship like a company
- Fail-closed secrets: OS keychain only, no plaintext fallback
  (`core_engine/account_manager.py:5-8,83-90`)
- Privacy policy (`docs/PRIVACY.md`) + Security & Privacy posture doc
- GitHub Issues/Changelog sync (fail-closed auth) — code done, needs a live
  token test
- GGG OAuth 2.1 PKCE flow + "Test PoE2 API" button (`core_engine/oauth_pkce.py`)
- CI/test-hardener routine with a running incident log (`docs/CI_LOG.md`)

---

## 2. The post-GGG product page

What the same codebase becomes with first-party data, pillar by pillar (full
pitch narrative in `docs/VISION_ACQUISITION.md` §"Post-GGG roadmap"). Swap
status below is read directly off `core_engine/providers.py`'s registry and
the pipeline matrix — **no `docs/PROVIDER_AUDIT.md` exists yet**, so this is
the provider-code ground truth, not an independently audited claim.

| Post-GGG feature | Pillar it becomes | Seam status today |
|---|---|---|
| **AI tutorial guide** — owl walks new players through real quests/mechanics/gems with ground truth | Advise like a coach | `GameData` seam ✅ SHIPPED (`ScrapedGameData`, W4-00) — swap the adapter to `.dat`/bundle reads, feature code unchanged |
| **Progress tracker** — real character/atlas/quest state | Compute + Advise | ⚠️ **no seam yet** — character state today comes from PoB import/ladder browse, not a provider interface; the vision doc's pipeline matrix does not list a "character state" row at all — this is the biggest structural gap for the pitch |
| **Craft guide** — Craft Hunter + planner with exact server-side odds | Trade / Advise | `CraftSimulator` seam ✅ SHIPPED (`LocalCraftPlanner`) for planning; the **tooltip-read half is *(needs seam)*** per the pipeline matrix — Craft Hunter's OCR watcher and the clipboard `item_in_hand` provider are two different code paths today (OCR still direct-reads the screen, not behind a provider) |
| **Death coach** — engine's own combat log instead of `Client.txt` inference | Advise like a coach | ⚠️ **no seam yet** — death/zone detection tails `Client.txt` directly in `gui_overlay/mirror_window.py`; not behind a provider interface |
| **Build advisor** — first-party build calculator parity | Compute everything | `BuildCalculator` seam ✅ SHIPPED (`PobCalculator`) — PoB stays as the offline calculator per the vision doc even after acquisition |
| **Trade companion** — sanctioned trade integration, real notifications | Trade without touching | `TradeSearchProvider` seam ✅ SHIPPED (`OfficialTradeSearch`) for search-URL building; no notification/auth surface exists to swap yet (correctly — we don't poll for it today) |

**Seams done (7 of 7 registered capabilities have a working adapter):**
`build_calculator`, `economy`, `trade_search`, `craft_simulator`, `game_data`,
`capture`, and — as of the uncommitted work this revision — `item_in_hand`.
Every one is a real, tested indirection: `core_engine/providers.py` registers
adapters behind `get_provider(name)`, and `set_provider(name, instance)` is
the literal swap point for an official-API adapter on acquisition day. This
is not aspirational; `gui_overlay/mirror_window.py`'s Ctrl+C handler already
goes through `get_provider("item_in_hand")` instead of touching
`QApplication.clipboard()` directly (verified in the working diff).

**Seams still needed** (pulled from `docs/VISION_ACQUISITION.md`'s pipeline
matrix, marked *(needs seam)*):
- **Tooltip live-read** — Craft Hunter's OCR watcher reads the screen crop
  directly; no `TooltipProvider` interface exists. Photo scanner and Reserve
  snapshot OCR have the same shape and could share one seam.
- **Player events (deaths, zones)** — `Client.txt` tail is direct file I/O
  in the overlay, not behind a provider.
- **Character/progress state** — not represented in the matrix at all; this
  is a real content gap in the vision doc, not just an unimplemented seam,
  because the post-GGG "progress tracker" pitch has nothing to point at.

---

## 3. Compliance & liability posture

### Read-only guarantee (file:line evidence)
- `core_engine/craft_hunter.py:19-22` — "we read what the game shows/writes;
  we NEVER touch the game. No input interception, no hooks, no sent clicks."
- `gui_overlay/game_watch.py:15-16` — ghost-mode foreground detection is
  "Purely passive: we only READ the foreground window and key[state]."
- `gui_overlay/mirror_window.py` Ctrl+C handler reads the clipboard the game
  itself writes; never calls a clipboard *write*. Now routed through
  `get_provider("item_in_hand")` (`core_engine/providers.py`,
  `ClipboardItemInHand.read()`), which documents the same guarantee in its
  class docstring: "Never touches the game; never writes the clipboard."
- `docs/ROADMAP.md` "Routes considered and NOT taken" — gameplay automation
  (auto-buy/whisper/teleport, any input to the game) is recorded as a
  **permanent no**, with the reasoning (ToS violation, ban risk) stated.

### Secrets: keychain-only, fail closed
- `core_engine/account_manager.py:5-8` — policy statement: secrets stored
  ONLY via `keyring` (OS credential vault); "intentionally NO insecure
  fallback."
- `core_engine/account_manager.py:83-90` — `set_secret()` returns `False`
  and refuses to write anything if `keyring` is unavailable, rather than
  falling back to a file. Enforced in code, not just documented.

### Privacy policy
`docs/PRIVACY.md` (last updated 2026-07-10, v0.1.0-pre): local-first data
table, exact conditions under which anything leaves the machine (fixed host
fetches; AI questions only with a user-supplied key; OBS stays on
localhost), user controls (delete `data_engine/`, clear keychain entries,
remove API keys). Explicitly not legal advice pending professional review.

### Fixed outbound host list
`core_engine/data_sources.py:26-32` — `SOURCES` tuple: `poe2db.tw`,
`poe.ninja`, `poe2wiki.net` (plus `pathofexile.com` for OAuth/trade,
referenced across `core_engine/oauth_pkce.py` and `trade_tools.py`, and
`github.com` only if the user connects the opt-in Issues/Changelog sync).
No dynamic host list, no telemetry endpoint.

### Licensing status of every data source
No `docs/GATING_RESEARCH.md` exists yet to pull a consolidated table from —
this section is built from source comments and the ROADMAP gating row
directly:
- **poe2wiki.net** — CC BY-NC 3.0, attributed in-code
  (`core_engine/wiki_scraper.py:4-5,42`). **Not cleared for commercial
  redistribution** — needs licensing review before a paid product ships
  with this content (open item, tracked in ROADMAP gating table).
- **poe2db.tw** — scraped as the primary, actively-tracked source of truth
  (`core_engine/data_sources.py:114-118`); commercial terms **not yet
  reviewed** (ROADMAP gating table, "Per-site ToS / licensing review": TODO).
- **poe.ninja** — public JSON API, commercial terms **not yet reviewed**
  (same ROADMAP row).
- **pathofexile.com (trade site)** — official first-party site; Kalandra
  only builds a URL and opens it, no scraping of authenticated content.
- **Craft of Exile** — link-out only in the current planner, no scraping.

### What's still open (ROADMAP gating table, `docs/ROADMAP.md` lines 29-40)
| Item | Status |
|---|---|
| Plaintext secrets fallback removed | ✅ DONE |
| Recording indicator + consent | ✅ DONE |
| Dependency pin + audit | ◑ PARTIAL — floors set, `pip-audit` clean as of 2026-07-10, but the exact-version lock file still needs generating on Windows (`pip freeze`); this revision's `pip-audit` re-run was **blocked** by a local Avast TLS-interception issue on the audit machine, not a dependency issue (`docs/CI_LOG.md`) |
| Code-signing the Windows build | ☐ TODO — needs an Authenticode cert (~$100-400/yr) |
| Per-site ToS / licensing review | ☐ TODO — see licensing table above |
| Privacy policy | ✅ DONE 2026-07-10, pending pre-commercial legal review |
| Sandboxed file writes | ◑ PARTIAL — all writes go under `data_engine/`, needs formalizing/documenting |

---

## 4. Integration cost estimate

Honest engineering read of what GGG would need to do to flip each pipeline
from public-data to first-party, given the seam status in §2.

| Pipeline | Effort to flip | Why |
|---|---|---|
| Item/mod/gem knowledge (`GameData`) | **Low** | Seam already exists and is exercised in production (`ScrapedGameData`). Write one adapter reading `.dat`/bundle data or an internal API into the same `search(term, limit)` contract; zero feature-code changes. |
| Build math (`BuildCalculator`) | **Low** | Seam exists (`PobCalculator`). An in-engine calculator adapter implementing `parse_build`/`stats_summary` drops in; PoB can stay as a secondary/offline calculator per the vision doc, so this can even be additive rather than a replacement. |
| Economy (`EconomyProvider`) | **Low** | Seam exists (`PoeNinjaEconomy`). Official economy feed adapter implements `currency_rates(league)`; UI (Currency Exchange tab, nerf watch) is already written against the interface, not poe.ninja directly. |
| Trade search (`TradeSearchProvider`) | **Low-Medium** | URL-builder seam exists and is genuinely swappable for search. Turning it into a *transactional* trade companion (notifications, in-app buy) is new surface, not a swap — today's `search_url` contract only covers "build a link," so this is where "low effort to swap" and "full post-GGG trade companion" diverge. |
| Item-in-hand (`ItemInHandProvider`) | **Low** | Newest seam (uncommitted this revision), already proven by migrating the production clipboard watcher onto it. An engine callback adapter implementing `read() -> (info, raw_text)` is a same-shape swap. |
| Tooltip live-read (Craft Hunter OCR) | **Medium** | *(needs seam)* — no interface exists yet; the OCR watcher, Reserve snapshot scan, and photo scanner are three separate call sites reading pixels/files directly. Defining one `TooltipProvider` (or folding into `item_in_hand`) before acquisition would turn this into a Low; today it's real refactor work, not just a new adapter. |
| Player events / death review | **Medium** | *(needs seam)* — `Client.txt` tail is inlined in `mirror_window.py`. Needs a `GameEventProvider` interface abstracting "death happened, zone changed" before an engine event stream can drop in without touching Death Review/grind-tracker call sites. |
| Character/progress state | **Medium-High** | No seam, not even documented in the pipeline matrix. This is the load-bearing pipeline for the "progress tracker" pitch (§2) and currently has the least architectural preparation of any post-GGG feature. Needs both a new provider interface AND a first pass at what "progress" data model even looks like. |
| Video capture (`CaptureProvider`) | **Low** | Seam exists with two working adapters already (`BuiltinCapture`, `ObsCapture`/W4-21) — proof the pattern scales to multiple simultaneous implementations, not just one. |
| Patch intel (`GameData`) | **Low** | Rides the same `GameData` seam as knowledge lookup; structured patch diffs from GGG would replace the scraped patch-note pages `nerf_intel.py` mines today. |

**Overall read:** 6 of 9 pipelines are a same-shape adapter swap (Low
effort) because the provider-interface law has actually been enforced, not
just aspired to — the `item_in_hand` migration in this revision is evidence
the team retrofits old code, not only new code. The three Medium/Medium-High
items (tooltip read, player events, character state) are exactly the ones
`docs/VISION_ACQUISITION.md` already flags as *(needs seam)*, plus the
undocumented character-state gap this audit surfaced. None of the nine are
architecturally blocked — all read pixels/files/APIs that a first-party
integration would trivially replace with better sources.

---

## 5. Traction

*Placeholder — Christian supplies these numbers. Do not invent figures here.*

| Metric | Value |
|---|---|
| Installs / active users | TODO |
| Community sentiment (Discord/Reddit/forum mentions) | TODO |
| Retention / session frequency | TODO |
| GitHub stars / issue engagement | TODO — repo: https://github.com/castleism/Kalandra_Git |
| Revenue (if any) | TODO |
