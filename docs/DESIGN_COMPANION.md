# DESIGN: The Companion — Kalandra as a player-aware AI teammate

## North star

Kalandra is an AI guide that makes Path of Exile 2 accessible to the widest
possible range of players — a child should be able to understand a build,
how to reach it through crafting, and every mechanic that interacts with a
skill. The ambition: the tool everyone runs alongside the game, good enough
that GGG eventually wants it inside the game.

Two architectural consequences, binding on all phases below:

1. **Everything third-party is a module, never a load-bearing wall.**
   PoB, poe.ninja, Craft of Exile, FilterBlade, OBS, the trade site — each
   sits behind a provider interface so it can be swapped the day official
   APIs (or an acquisition) replace it:
   - `BuildCalculator` — PoB headless today; native/official calc later.
   - `EconomyProvider` — poe.ninja + trade-site scrape today; official
     trade API later.
   - `CraftSimulator` — Craft of Exile link-out + local planner today;
     native sim later.
   - `GameData` — scraped poe2db/wiki today; direct game-file or API later.
   - `CaptureProvider` — OBS websocket today; engine-level hooks later.
   New feature code talks to the interface, not the tool. Existing direct
   couplings get migrated behind these interfaces opportunistically.
2. **Explanation depth scales all the way down.** The profile's detail
   setting isn't just verbosity — "full" should reach genuinely
   child-accessible: plain words, one concept per bubble, pictures where
   the theme kit allows (the owl pointing its arrow at the thing being
   explained is exactly this). Every mechanic explanation should have a
   simplest-form version.

Direct game interaction remains OFF the table under current ToS — advisory
only. If sanctioned access ever arrives (API keys, partnership,
acquisition), the provider interfaces above are where it plugs in.

> Captured 2026-07-04 from Christian's design session. This is the canonical
> spec for the "Companion" arc: the owl interview, player profiling,
> character intelligence, auto-attendant, streamer suite, and the community
> data engine. docs/ROADMAP.md carries one-line entries pointing here.
>
> Hard rule inherited from the project: **no gameplay automation** (GGG ToS).
> Everything below reads, advises, notifies, and simulates — the player
> always performs the action (trades, crafts, purchases) themselves.

---

## P0 — Player profile + owl interview + Companion tab  ✅ SHIPPED 2026-07-04

- `core_engine/player_profile.py` — pure-Python profile store
  (`data_engine/player_profile.json`) + `prompt_block()` injected into every
  AI context (`mirror_window._ai_context`).
- `gui_overlay/owl_interview.py` — the owl asks 10 questions as chip-button
  bubbles after the welcome tour; resumable ("Ask me later" keeps partial
  answers); right-click the owl to redo.
- **The sensitive question, handled**: "how did those levels happen" is
  framed as calibration, never judgment — *"mostly your own mapping, or with
  help (party carries, rotas, temple leeching)? No wrong answer; it just
  tells me which mechanics you've actually driven yourself."* Includes
  "Prefer not to say." Rationale: a temple-leeched 100 and a solo-ground 100
  imply very different mechanical vocabularies; the AI should coach
  accordingly, and should ALSO infer silently from build history + gear
  wherever possible instead of asking.
- Questions cover: PoE1/PoE2 background, leagues played, peak level, climb
  style, solo/party/mix, meta vs niche taste, stance on overtuned/bugged
  mechanics (pre-nerf riders vs avoiders), typical endgame budget,
  preferred explanation depth, free-text build history.
- `gui_overlay/companion_tab.py` — new FIRST dashboard tab: threaded orb
  chats (JSON per thread in `data_engine/chat_threads/`), friendly
  color-coded action notes streamed from LOG_BUS between messages
  (Database=sapphire, Build/PoB=emerald, Voice&AI=gold, Capture=amber,
  errors=ruby; toggleable), AI input wired to the same brain as voice, and
  an auto-attendant STUB (local profile-gated templates, config key
  `companion_attendant`, default off).

## P1 — PoB import + character scan

During/after the interview, when the player names past builds:
1. Ask whether they remember character names, or just class/level/league.
2. Launch/attach PoB (existing PobLiveTab machinery), authenticate with the
   account details already stored via `account_manager` (keyring).
3. Import the matching characters; save each as a build file.
4. Deep-scan each: every gem, support, skill setup, item, passive tree.
5. From imports, INFER profile facts (mechanics familiarity, favored
   archetypes) — reduces how much the owl has to ask.

## P2 — Character reviews, per-character orbs, standard-shuffle awareness

- Generate a written review per imported character; each gets its own
  Companion thread with an auto-assigned orb identity (extends the existing
  "character threads + orb identity" roadmap idea).
- When the player opens a character's review page, the owl pops up to
  confirm playstyle/gear — things drift once characters hit Standard.
  (Motivating case: a stat-stack Gemling Legionnaire gutted mid-league;
  the player shuffled items across builds for weeks. The review should
  detect "this build predates nerf X" and say so.)
- Review contents: build identity, scaling profile, weak points, notable
  gear, estimated current value, what changed since its league.

## P3 — Nerf-aware price intelligence

- Price-check similar gear THIS league (existing trade search plumbing).
- For uniques: check whether the item was meaningfully nerfed since the
  character's league before trusting old value intuitions. Canonical
  examples: Hand of Wisdom and Action, Astramentis (nerf-sensitive price
  cliffs); Headhunter famously cheap in Temple league (supply/league
  mechanics, not nerf) — so the check needs BOTH patch-note diffing (wiki
  scraper already ingests patch data) and league-over-league price curves
  (poe.ninja history).
- Output feeds the character review and the build-cost estimator (P4).

## P4 — Character folders, roadmap files, PoB-as-calculator, build costing

- `data_engine/characters/<name>/` per imported character:
  `profile.json` (scan), `review.md`, `roadmap.md` (leveling → endgame gear
  ladder by level bracket), `sim_notes/` (what-if results), `watchlist.json`
  (items to hunt). These files are the injection corpus for any prompt
  about that character — small, curated, cheap in tokens.
- PoB as the calculator: every suggestion (passive change, support swap,
  item upgrade) runs through the headless sim before it's spoken.
- Simulated craft costing: crafting planner (existing) + live currency
  prices → expected cost to craft; compare with trade price of equivalent →
  "craft vs buy" verdict; sum across the roadmap → estimated build cost.
- Character sheet panel in the dashboard surfaces all of this per character.

## P5 — BIS bank integration, live-search suggestions, notifications

- Reserve / BIS tab becomes the item bank the AI can SEE: as the player
  marks off collected uniques (with item-level / spell-level / variant
  selectors where relevant), sims can slot banked items into any character —
  including teammates' characters loaded in PoB.
- Roadmap watchlist items → one-click "set up a live search" (existing
  LiveSearchTab); saved searches can be run or scheduled.
- Notifications: desktop (default), email, SMS (opt-in, via user-provided
  service creds). In-overlay: the orb pops a chat bubble with the trade
  link so the player can open it and initiate the purchase once they're in
  a safe area. No auto-whisper, no auto-buy.

## P6 — Auto-attendant, researched edition

- Settings → AI: per-topic research cadence + token budget checkboxes,
  each item labeled with relative token cost:
  new/updated builds (build sites, YouTube, Reddit, official forums,
  Twitch), passive/support/skill suggestions (sim-verified), item-to-build
  matches from the BIS bank, teammate-build synergies.
- Results post into the Companion thread as owl messages when the player
  lingers on the tab; every claim carries its source or sim result.
- Each character's roadmap folder is the working memory these jobs read
  and update.

## P7 — Streamer suite (OBS)

- Connect via obs-websocket (standard in OBS 28+).
- Full-stream transcription through the existing local Whisper engine;
  timestamped log file exportable as the skeleton of a written build guide,
  with links that open saved clips at the moments the tool was activated.
- Live assist overlays while explaining a build (classic build-video
  furniture, done live): highlight active buffs, highlight characters,
  magnified boss-HP/damage countdown inset. Overlay-window only — visual
  annotation, zero game input.
- Instant replay: lean on OBS's replay buffer for "show the last N seconds"
  playback triggered from the overlay.

## P8 — Grind tracker ("currency tracker")

- Snapshot a grind loadout: e.g. 4 tablets + 10 waystones, with their mods.
- Track currency/items gained across the runs of that snapshot; associate
  returns with the mods (and mod VALUES) used.
- Local-first: per-user SQLite; estimates improve as personal data grows.

## P9 — Community data engine

The pooled version of P8 + mod-based price estimation:
- Every price check (opt-in, asked during setup) is logged: parsed mods,
  values, listed price, league, date. Locally always; uploaded only with
  explicit consent.
- Mod-value model: estimate an item's price from its mods; live-recompute
  as the user toggles single mods / shifts weights ("what's the T1 attack
  speed roll actually worth on this base right now?").
- Same pooling for grind returns → community expected-value tables per
  map-mod combination.
- Reality check (researched): no off-the-shelf shortcut exists.
  poeprices.info proved the concept (ML over trade listings). Plan:
  local-first schema NOW (P8/P9 share it), community backend LATER —
  needs a small server (DB + aggregation API), auth, and data-poisoning
  defenses. Design the local schema so records are upload-ready
  (anonymized, league-stamped, versioned).

---

## Cross-cutting rules

- **Consent**: all telemetry (price-check logging, grind data, uploads) is
  opt-in at setup, per-category, revocable in Settings.
- **Token honesty**: any feature that spends API tokens shows its relative
  cost next to its toggle.
- **Tone**: the owl calibrates depth from the profile; sensitive questions
  are framed as calibration with a decline option; prefer silent inference
  from imported data over asking.
- **ToS**: read, advise, notify, simulate — never act in-game.
