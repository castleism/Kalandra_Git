# Kalandra — Vision & Acquisition Strategy

*Written 2026-07-10. This is the company north star; every routine, feature,
and refactor should be checkable against it.*

## The thesis

We build Kalandra into the tool the PoE2 community cannot play without — so
useful and so integral that Grinding Gear Games' best move is to acquire it
and ship it as the game's own AI companion. Everything we do serves one of
two states:

- **Pre-GGG (now):** the absolute pinnacle of everything PoE2-related that
  is buildable from what's publicly available — scraped knowledge, PoB's
  real engine, the official trade site, poe.ninja, the player's own screen,
  log, and clipboard. Read-only, ToS-spotless, local-first. Our compliance
  posture (see `SECURITY_AND_PRIVACY.md`, `PRIVACY.md`) is not just ethics —
  it's the asset: an acquirer inherits zero liability and zero ban-risk
  reputation.
- **Post-GGG (the exit):** GGG turns Kalandra into the official AI-driven
  tutorial guide, progress tracker, and craft guide — same brain, same UX,
  but fed by the game itself instead of scrapes and OCR.

Honest hedge, stated once: GGG has never acquired a community tool and may
never. The strategy is built so that **if the exit never happens, executing
it still produces the best standalone product in the ecosystem** — the two
goals are the same work.

## Business model (decided by Christian, 2026-07-10)

**Kalandra is free to the community, forever. The exit is acquisition, not
sales.** What follows from that: adoption is the only pre-GGG metric that
matters; the CC BY-NC-SA data sources are compatible with our free
distribution (attribution + license notices are our obligation — see
`docs/GATING_RESEARCH.md` rev 2); code signing is an adoption investment,
not a sales gate; and any future paid experiment must first re-read the
GATING_RESEARCH appendix, which flips the licensing analysis.

## The architectural law: every pipeline must be swappable

Because the endgame is direct integration, **no feature may hard-wire its
data source.** Every place we ingest game data must route through a provider
interface (`core_engine/providers.py`, W4-00) so that on acquisition day the
implementation flips from "scrape/OCR/clipboard" to "game files / game API /
in-process hooks" without touching the feature above it.

Practical rules for every contributor (human or routine):

1. New data need? Define or extend a provider interface first; implement the
   public-data version behind it.
2. Existing code that calls a third-party source directly (requests to
   poe2db/poe.ninja/pathofexile.com, tesseract/RapidOCR, clipboard parsing,
   Client.txt tailing) is **technical debt against the thesis** — migrate it
   behind a provider opportunistically, one call site at a time.
3. Every provider documents its **post-GGG swap plan** in the matrix below —
   what official surface would replace it (game files via
   `dat_parser`/`oodle_extractor`, official API, or engine callback).
4. The game-file extraction path (`core_engine/oodle_extractor.py`,
   `dat_parser.py`, `poe2_data_extract.py`) is not a side quest — it is the
   **prototype of the post-GGG pipeline** and gets sustained R&D.

## Pipeline matrix (source → provider → post-GGG swap)

| Data | Today's source | Provider seam | Post-GGG swap |
|---|---|---|---|
| Item/mod/gem knowledge | poe2db + poe2wiki scrape → `localized_knowledge.db` | `GameData` | Direct `.dat`/bundle read (dat_parser path) or official data API |
| Build math | user's PoB install, LuaJIT headless (`pob_sim`) | `BuildCalculator` | In-game character/skill API; PoB stays as offline calculator |
| Economy | poe.ninja snapshots + `economy_history` | `Economy` | Official trade/economy API feed |
| Trade search | official trade-site URLs + `?q=` prefill (W3-21) | `TradeSearch` | First-party trade API with auth |
| Item-in-hand | clipboard Ctrl+C parse (`trade_tools.parse_item_text`) | `ItemInHand` (2026-07-10) | Game tells us the hovered/selected item directly |
| Tooltip live-read | screen crop OCR (Craft Hunter P2) | *(needs seam)* | Same — hovered-item callback makes OCR obsolete |
| Player events (deaths, zones) | `Client.txt` tail (`death_review`) | *(needs seam)* | Game event stream |
| Video capture | OBS websocket / mss (`obs_bridge`, `media_recorder`) | `Capture` | Engine-side replay/capture API |
| Patch intel | patch-note pages in the ledger (`nerf_intel`) | `GameData` | Structured patch diffs from GGG |
| Character list / identity | PoB's own account import + `poe_account.get_characters` (404 on PoE2 today) + public ladder (`docs/CHARACTER_IMPORT_SPEC.md`) | *(needs seam — candidate: `AccountData`)* | Official character API — `oauth_pkce.py` is pre-built, waiting on a GGG `client_id` |

*(needs seam)* rows are the current priority for the provider-boundary
routine: define the interface even though only one implementation exists —
that's the whole point.

## Pre-GGG roadmap (pinnacle with public data)

The detailed tracker stays in `docs/ROADMAP.md`; these are the pillars and
what "pinnacle" means per pillar:

1. **Know everything** — complete, current knowledge base (scraper coverage,
   patch-note ingestion, verified-corrections layer, game-file extraction
   where legal for the user's own install).
2. **Compute everything** — real PoB math on tap (live sim, what-if diffs,
   sim-verified upgrade suggestions), never fabricated numbers.
3. **See what the player sees** — clipboard, screen (OCR), log, recordings;
   always read-only, always local.
4. **Advise like a coach** — the Orb/owl companion: profile-calibrated,
   evidence-only audits (death review), crafting routes, build reviews,
   new-player arc. This is the feature GGG is buying.
5. **Trade without touching** — price intelligence, prefilled official
   searches, nerf watch; the player performs every action.
6. **Ship like a company** — gating table in ROADMAP (signing, licensing,
   privacy, lock files), tests green, honest docs.

## Post-GGG roadmap (what we hand them)

What the same codebase becomes with first-party data — this is the pitch
deck's product page, kept current in the acquisition dossier:

1. **AI tutorial guide** — the owl walks new players through the actual game
   (quests, mechanics, gems) with ground truth instead of scraped pages;
   difficulty-aware, profile-calibrated (owl_interview already does this).
2. **Progress tracker** — real character/atlas/quest state from the game;
   grind tracker and time matrix become official play-session analytics.
3. **Craft guide** — Craft Hunter + crafting planner with exact server-side
   odds instead of heuristics; the alert loop replaced by the game just
   telling us the roll.
4. **Death coach** — death review fed by the engine's own combat log (what
   actually hit you), not log inference.
5. **Build advisor** — first-party build calculator parity, in-game overlay
   of the character sheet flagship.
6. **Trade companion** — sanctioned trade integration with real
   notifications (the thing we correctly refuse to poll for today).

## What this changes about how we work

- Feature workers check the pipeline matrix before adding any data source.
- The provider-boundary auditor routine keeps the seam