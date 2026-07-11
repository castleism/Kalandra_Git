# Kalandra — Vision & North Star

*Written 2026-07-10, reframed 2026-07-11: product first. This is the north
star; every routine, feature, and refactor should be checkable against it.*

## The thesis

Build the PoE2 companion players genuinely love — useful every session,
trustworthy by construction, and free. Quality and player trust are the
whole strategy: no growth hacks, no monetization, no pitching ourselves to
anyone. If Kalandra ever earns bigger opportunities, they'll come from
being excellent, not from asking. We ship; that's the entire plan.

What "excellent" means here: the best of everything PoE2-related that's
buildable from what's publicly available — scraped knowledge, PoB's real
engine, the official trade site, poe.ninja, the player's own screen, log,
and clipboard. Read-only, ToS-spotless, local-first. Our compliance
posture (see `SECURITY_AND_PRIVACY.md`, `PRIVACY.md`) is a feature players
can verify, not a marketing line.

## Business model (decided 2026-07-10)

**Kalandra is free to the community.** No monetization plans. What follows:
player adoption and retention are the metrics that matter; the CC BY-NC-SA
data sources are compatible with free distribution (attribution + license
notices are our obligation — see `docs/GATING_RESEARCH.md` rev 2); code
signing is an adoption investment, not a sales gate; and any future paid
experiment must first re-read the GATING_RESEARCH appendix, which flips
the licensing analysis.

## The architectural law: every pipeline must be swappable

**No feature may hard-wire its data source.** Every place we ingest game
data routes through a provider interface (`core_engine/providers.py`,
W4-00). This is straight engineering value, proven already in week one:

- **Resilience** — poe.ninja rewrote their site and our sentinel swapped
  the endpoint behind the seam without touching a single feature.
- **Licensing hygiene** — sources can be added, replaced, or dropped as
  their terms require, per-seam.
- **Testability** — every seam takes an injected fake; that's why the
  whole watcher/parser stack tests headlessly.
- **Future flexibility** — if better sources ever exist (official APIs,
  the user's own game files via the `dat_parser`/`oodle_extractor` path,
  or anything else), each pipeline flips independently, feature code
  untouched.

Practical rules for every contributor (human or routine):

1. New data need? Define or extend a provider interface first; implement
   the current-source version behind it.
2. Existing code that calls a third-party source directly (requests to
   poe2db/poe.ninja/pathofexile.com, tesseract/RapidOCR, clipboard
   parsing, Client.txt tailing) is **technical debt** — migrate it behind
   a provider opportunistically, one call site at a time.
3. Every provider documents its **best-future swap** in the matrix below —
   what a first-party or game-file source would replace it with, if one
   ever exists.
4. The game-file extraction path (`core_engine/oodle_extractor.py`,
   `dat_parser.py`, `poe2_data_extract.py`) is not a side quest — it is
   the eventual replacement for scraping (the user's own install is the
   most accurate, most licensing-clean source there is) and gets
   sustained R&D.

## Pipeline matrix (source → provider → best-future swap)

| Data | Today's source | Provider seam | Best-future swap |
|---|---|---|---|
| Item/mod/gem knowledge | poe2db + poe2wiki scrape → `localized_knowledge.db` | `GameData` | Direct `.dat`/bundle read (dat_parser path) or official data API |
| Build math | user's PoB install, LuaJIT headless (`pob_sim`) | `BuildCalculator` | First-party character/skill API; PoB stays as offline calculator |
| Economy | poe.ninja snapshots + `economy_history` | `Economy` | Official trade/economy API feed |
| Trade search | official trade-site URLs + `?q=` prefill (W3-21) | `TradeSearch` | First-party trade API with auth |
| Item-in-hand | clipboard Ctrl+C parse (`trade_tools.parse_item_text`) | `ItemInHand` (2026-07-10) | Game surfaces the hovered/selected item directly |
| Tooltip live-read | screen crop OCR (Craft Hunter P2) | *(needs seam)* | Same — a hovered-item callback makes OCR obsolete |
| Player events (deaths, zones) | `Client.txt` tail (`death_review`) | *(needs seam)* | Game event stream |
| Video capture | OBS websocket / mss (`obs_bridge`, `media_recorder`) | `Capture` | Engine-side replay/capture API |
| Patch intel | patch-note pages in the ledger (`nerf_intel`) | `GameData` | Structured patch diffs from the source |
| Character list / identity | PoB's own account import + `poe_account.get_characters` (404 on PoE2 today) + public ladder (`docs/CHARACTER_IMPORT_SPEC.md`) | *(needs seam — candidate: `AccountData`)* | Official character API — `oauth_pkce.py` is pre-built, waiting on a client_id |

*(needs seam)* rows are the current priority for the provider-boundary
routine: define the interface even though only one implementation exists —
that's the whole point.

## Product pillars

The detailed tracker stays in `docs/ROADMAP.md`; these are the pillars and
what "best" means per pillar:

1. **Know everything** — complete, current knowledge base (scraper
   coverage, patch-note ingestion, verified-corrections layer, game-file
   extraction where legal for the user's own install).
2. **Compute everything** — real PoB math on tap (live sim, what-if diffs,
   sim-verified upgrade suggestions), never fabricated numbers.
3. **See what the player sees** — clipboard, screen (OCR), log,
   recordings; always read-only, always local.
4. **Advise like a coach** — the Orb/owl companion: profile-calibrated,
   evidence-only audits (death review), crafting routes, build reviews,
   new-player arc. The heart of the product.
5. **Trade without touching** — price intelligence, prefilled official
   searches, nerf watch; the player performs every action.
6. **Ship like professionals** — gating table in ROADMAP (signing,
   licensing, privacy, lock files), tests green, honest docs.

## How we work

- Feature workers check the pipeline matrix before adding any data source.
- The provider-boundary auditor routine keeps the seams honest.
- The game-file R&D routine keeps the scrape-replacement pipeline real,
  not theoretical.
- We measure ourselves on whether players would miss Kalandra if it
  disappeared — nothing else.
