# Kalandra — Competitive Landscape

*Maintained by the scheduled competitive-intelligence routine. Snapshot is
replaced each run; a changelog of deltas is kept at the bottom. Cross-check
against `docs/VISION_ACQUISITION.md` (the thesis this doc exists to serve)
and `docs/ROADMAP.md` (our own feature tracker).*

## Snapshot: 2026-07-10

PoE2 is in patch **0.5.0 "Return of the Ancients"** (shipped 2026-05-29),
its **final Early Access content patch** — only a short 0.5.5 balance/event
patch is scheduled for late July 2026 before the game goes polish-only
ahead of a 1.0 release targeted for shortly after ExileCon (Nov 7–8, 2026).
[[aoeah roadmap](https://www.aoeah.com/news/4681--poe-2-06-release-date-next-new-class--league-season-content)]
That means the current tooling ecosystem is stabilizing rather than adding
big new categories — most late-window activity is patch-compatibility
firefighting, not new product launches.

### The field, by category

**Price-check overlays** — the most contested category, and the one with
the clearest incumbent:
- **Exiled Exchange 2** (fork/spiritual successor to Awakened PoE Trade,
  whose maintainer declined to port to PoE2) is the dominant tool: 1.1k
  GitHub stars, 350k+ downloads on its latest installer alone, weekly
  release cadence. [[repo](https://github.com/Kvan7/Exiled-Exchange-2)] It
  breaks hard and often — trade-API response-shape changes threw
  `t.replace is not a function` on nearly every lookup after the 0.5.3
  patch [[#976](https://github.com/Kvan7/Exiled-Exchange-2/issues/976)],
  chat-linked price-check has been degraded since the 0.5 update
  [[#900](https://github.com/Kvan7/Exiled-Exchange-2/issues/900)], and it's
  effectively broken on Linux/Wayland — fragile enough that a new
  competitor (**Waystone**) was built in June 2026 specifically to serve
  Wayland users EE2 and Sidekick fail on.
  [[waystone](https://github.com/kriskruse/waystone)]
- **Sidekick** is the #2 player (497 stars, ~monthly releases, price
  check + map-danger tooltip + stash search + wealth tracker)
  [[repo](https://github.com/Sidekick-Poe/Sidekick)] — same fragility
  pattern, e.g. a quick-fix release the day after a trade API format
  change. [[v2026.6.5](https://github.com/Sidekick-Poe/Sidekick/releases)]
- **xiletrade** (PoE1+2, 106 stars) and **PoE Overlay II**
  (Overwolf-affiliated, claims "1M+ players", explicitly
  not-endorsed-by-GGG) round out the category.
  [[xiletrade](https://github.com/maxensas/xiletrade)]
  [[poeoverlay.com](https://www.poeoverlay.com/)]
- **GGG shipped a native in-client price checker with patch 0.5**
  (Shift+Alt+Left-click opens a pre-filled Market panel)
  [[GameRant](https://gamerant.com/path-of-exile-2-use-in-game-price-checker-poe2/)] —
  and it directly **killed a standalone competitor**: poe2helper.com
  discontinued itself around 2026-06-02, citing the native feature.
  [[poe2helper.com](https://poe2helper.com/)] **This is the sharpest signal
  in this snapshot**: GGG will absorb a utility feature the instant it's
  simple and popular enough to be worth their engineering time. Kalandra's
  W3-20/21 clipboard price-popup + prefilled trade search occupies the same
  space GGG just partially auto-cannibalized — see Gaps below.

**Loot filters** — a near-monopoly, and the most mature/stable category:
**FilterBlade + NeverSink's filter** (2.9k stars, MIT, Patreon-funded)
dominates with 7 strictness tiers, economy-driven auto-tiering rebuilt
every 4 hours, and a paid auto-updater that merges personal edits with
live economy data.
[[FilterBlade](https://www.filterblade.xyz/)]
[[repo](https://github.com/NeverSinkDev/NeverSink-Filter-for-PoE2)]
Fubgun's filters are the distant #2 (~79k followers). GGG hosts an
official in-game filter-ladder so players can follow any public filter
without touching a website at all. A forum thread literally asks *"GGG
Should Officially Hire Neversink and Integrate His Loot Filter System"*
[[thread](https://www.pathofexile.com/forum/view-thread/3884887)] — a
player wishlist, not a GGG statement, but it shows where community
sentiment already sits.

**Build planning** — Path of Building 2 is the unchallenged standard
(active, weekly-ish releases, v0.22.0 shipped 2026-06-30)
[[releases](https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2/releases)],
but has real, long-open UX complaints: re-importing a build **wipes all
per-skill configuration**
[[#1709](https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2/issues/1709), open since Jan 2026],
and the maintainer has openly declined to build passive-tree
allocation-order guidance because *"the UX... I know it'll be a lot more
work than it initially looks like."*
[[#1785](https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2/issues/1785)]
GGG shipped its own lightweight **native Build Planner** in 0.5 (import a
`.build` file, see tree/gems/gear notes in-client) and is actively
building an account-linked **"one-click subscribe" API** so community
build sites can push builds directly to a player's account — not live yet,
held back from the 0.5 launch.
[[FRVR](https://frvr.com/blog/news/path-of-exile-2-build-planner-will-never-include-official-ggg-builds/)]
Game Director Jonathan Rogers framed GGG's role explicitly: *"It's not on
us to decide what's good... We're there to put the tools [in], the
community are there to create the builds."* GGG is positioning itself as
build-tooling **infrastructure provider**, not curator or competitor —
important context for how far GGG is likely to go into "coach" territory
itself (see Policy section).

**Crafting simulators** — Craft of Exile, Path of Crafting, and PoE2Craft
all do mod-probability simulation with Omen support, but none pair that
with conversational, goal-driven planning or a live in-game alert loop —
that's Kalandra's Crafting Planner + Craft Hunter combination, and nothing
found in this research replicates it.

**Economy / wealth tracking** — poe.ninja remains the canonical public
economy feed. A newer entrant, **Exiled Tools**
(exiledtools.com — price terminal, farming/div-per-hour optimizer, net-worth
dashboard with "Ghost Wealth" detection), is the closest analog to
Kalandra's Currency Exchange + Grind Tracker combination, though it's
web-only and not overlay-integrated. **PoE2 MultiTool** (v1.0 reworked
2026-06-28, Patreon freemium) is the closest thing to an "everything"
aggregator competitor: trade overlay + rune-reward checker + campaign
tracker + regex stash-search generator + stash value calculator in one
app — worth watching as the nearest analog to Kalandra's own
all-in-one bet.
[[Patreon](https://www.patreon.com/Weexer/posts/huge-rework-of-1-162145808)]

**Photo/OCR item scanning** — **Exile Companion**, a mobile app
(iOS/Android, 20k+ downloads, 4.6★), photographs an in-game item and
returns a trade price via OCR + photo recognition, built specifically for
console players who can't run PC overlays.
[[forum thread](https://www.pathofexile.com/forum/view-thread/3864758)]
**PoeAncientsPriceHelper** (desktop, OCR-overlay reading the currency
exchange list with no clipboard needed, v3.6.0 shipped 2026-07-08) is the
closest desktop analog to Craft Hunter's OCR approach. Neither is a
build-in-progress AI companion — both are single-purpose scanners. This
validates rather than threatens W3-33 (Photo item scanner, still ☐ TODO in
`ROADMAP.md`): real demand exists, current implementations are narrow, and
Kalandra's version would feed the same `parse_item_text` pipeline as every
other input path (a structural advantage nothing else in this research has).

**Stash/character data tools** — multiple community projects
(`dominee/PoE2-butler`, `JuiceJournal`) are explicitly **blocked** on GGG
not yet exposing a PoE2 stash-tab API scope, shipping with mock data while
they wait for OAuth approval. This is the identical wall Kalandra hits
(`ROADMAP.md`: *"Your own (non-ladder) PoE2 characters via API — Blocked
on GGG shipping the PoE2 OAuth API"*) — nobody in the ecosystem has a way
around it; it's a shared constraint, not a competitive gap.

### Feature comparison vs. Kalandra

| Capability | Kalandra | Best-in-class competitor(s) | Verdict |
|---|---|---|---|
| Price-check overlay | ✅ Ctrl+C popup (W3-20) + prefilled trade search (W3-21) | Exiled Exchange 2, Sidekick | Competitive, but so is everyone — commodity feature. GGG is absorbing the simplest version of this itself. |
| Loot filter | ◑ Filter Editor (readable, round-trip edit) — not a filter *author* | FilterBlade/NeverSink (economy-auto-tiered, 2.9k★) | **Behind.** We edit filters; we don't generate/maintain one. Low incentive to compete head-on — NeverSink's moat (community trust + Patreon-funded live economy data) is deep. |
| Build planner (math engine) | ✅ Real PoB via LuaJIT headless — same engine as the standard | PoB2 (community standard) | At parity on math; ahead on integration (live sim inside the app, AI upgrade suggestions). |
| Build config persistence | Not evaluated this run | PoB2 wipes skill config on reimport (open complaint) | **Opportunity** if our build-import path preserves user config across reimports — worth a deliberate UX check. |
| Passive-tree allocation guidance | ☐ Not built | Nobody — PoB2 maintainer declined, cites UX cost | **Open gap, nobody serves it.** See roadmap candidates below. |
| Crafting simulation | ✅ Crafting Planner + Craft Hunter (goal parse → route → live alert) | Craft of Exile, Path of Crafting (simulators only) | **Ahead.** Nothing else pairs simulation with a conversational planner + live alert loop. |
| Economy/wealth tracking | ✅ Currency Exchange + Grind Tracker | Exiled Tools ("Ghost Wealth" net-worth), poe.ninja | Comparable feature set; Exiled Tools is a web dashboard only, not overlay-integrated with build/craft context like ours is. |
| Photo/OCR item scan | ◑ Reserve tab OCRs snapshots (W3-31); general photo scanner still ☐ TODO (W3-33) | Exile Companion (mobile, 20k+ downloads) | Validated demand, no strong desktop competitor — build it. |
| Death review / combat autopsy | ✅ Shipped (W4-21) — Client.txt watcher + OBS clip + PoB defensive audit | None found in this research | **Ahead, possibly unique.** Nothing in this scan does evidence-based death coaching. |
| AI companion / coaching layer | ✅ Owl guide, profile-calibrated prompts, build reviews, new-player arc | None found — every competitor is a single-purpose utility | **Category-defining gap in our favor.** This is the whole acquisition thesis's "advise like a coach" pillar, and nothing in the ecosystem attempts it. |
| Stash-data-dependent tools | Blocked on OAuth (same as everyone) | Same wall for all competitors | Shared constraint, not a gap. |
| All-in-one consolidation | ✅ Explicit design goal | PoE2 MultiTool (closest attempt, narrower scope: trade+runes+campaign+regex) | We're further along the "one app instead of six tabs of separate tools" bet than anyone else found. |

### Gaps where we're behind

1. **We don't author/maintain a loot filter.** FilterBlade/NeverSink's
   economy-auto-tiering is a real engineering + community-trust moat.
   Competing head-on is low-value; integrating with the existing
   ecosystem (import/manage a NeverSink or Fubgun filter inside Kalandra,
   rather than reinventing tiering) is more realistic than out-building it.
2. **No passive-tree leveling/allocation guidance**, and PoB2's own
   maintainer has explicitly punted on it. This sits squarely inside our
   "Advise like a coach" pillar and nobody else is building it.

### Gaps where nobody serves the need (opportunities)

1. **Post-patch tool fragility is the single most common community
   complaint found in this research** — trade-API schema drift breaking
   EE2/Sidekick for days at a time, filters needing hand-updates,
   Linux/Wayland breakage spawning entirely new competing tools. This is
   exactly the failure mode `docs/VISION_ACQUISITION.md`'s provider-seam
   architecture (W4-00) is designed to contain. **Nobody else in the
   ecosystem is architected against this** — it's a marketable strength,
   not just internal hygiene, if we make "doesn't break for a week after
   every patch" visible to users (status banner, graceful degradation)
   rather than a silent implementation detail.
2. **Tool fragmentation itself is a documented pain point.** The research
   surfaced a wave of small, single-purpose tools shipping right after
   each league launch (ExileCompass, RuneshapePriceChecker,
   PoeAncientsPriceHelper, multiple POE2Radar forks) — a signal that no
   single tool covers the need well, forcing players to run several apps
   at once. Chris Wilson's own 2017 stated discomfort with players
   "feeling forced" to download multiple third-party tools to stay
   competitive lines up directly with this. Consolidation is validated
   both by the market gap and by GGG's own stated philosophy.
3. **No AI-driven coaching/companion layer exists anywhere else in this
   research.** Every competitor found — overlays, filters, planners,
   trackers — is a single-purpose utility. The "Advise like a coach" /
   Orb companion pillar has zero direct competition right now.

### Policy / ToS news affecting our compliance posture

- **No new PoE2-specific ToS language found.** The operative rule remains
  what it's been since PoE1: no automation ("more than one action per
  keystroke/click"), no client modification or memory injection, no
  reading/writing game files or process memory — overlays that read the
  clipboard/screen and hit the public API within rate limits are fine.
  [[Terms of Use](https://www.pathofexile.com/legal/terms-of-use-and-privacy-policy)]
  [[forum FAQ](https://www.pathofexile.com/forum/view-thread/3584808)]
  This matches Kalandra's existing posture exactly — no changes needed.
- **PoE2 has server-side-only anti-cheat** (no kernel driver, no
  client-side monitoring); plain overlay windows are confirmed fine, and
  no PoE2-specific overlay ban wave was found in 2025-2026.
  [[backgrind.com analysis, updated 2026-07-03](https://backgrind.com/overlay-anticheat-checker/path-of-exile-2/)]
  The one historical overlay ban wave (PoE1, 2020, "POE Overlay") was
  triggered by that tool hammering GGG's API millions of times a day with
  an obfuscated user-agent — an abuse/load issue, not a blanket ban on
  overlays. Kalandra's local-first, low-request-volume design is
  structurally immune to this specific failure mode; worth stating
  plainly in the compliance posture docs if not already.
- **No confirmed 2025-2026 bot ban-wave for PoE2** despite a player
  complaint thread from Sep 2025 with zero staff replies. A real,
  confirmed enforcement action in this window was an **RMT crackdown**
  (April 2026, automated in-game warning messages, described by press as
  a coordinated sweep) — unrelated to overlay/companion tools.
  [[PCGamesN](https://www.pcgamesn.com/path-of-exile/rmt-crackdown)]
- **No public PoE2 trade-search API exists.** Confirmed by direct
  inspection of GGG's developer docs: *"There are currently limited APIs
  that return PoE2 game information."* Only Characters, Leagues, Currency
  Exchange (aggregate/historical), and the new Build Planner file format
  are documented for `realm=poe2`. No statement rules a trade API out
  permanently, but none is promised either.
  [[dev docs reference](https://www.pathofexile.com/developer/docs/reference)]
- **Real, still-open ban ambiguity remains a live user risk, not just a
  policy curiosity.** Two separate 2026 forum threads document permanent
  bans of players who claim to have used only mainstream tools (Exiled
  Exchange 2 in one case, PoB2 + "PoE Overlay" in the other), with GGG
  giving only boilerplate Section-7-ToS responses on appeal.
  [[thread](https://www.pathofexile.com/forum/view-thread/3777565)]
  [[thread](https://www.pathofexile.com/forum/view-thread/3748982)]
  The likely trigger in the documented case was request volume, not tool
  identity — reinforces (doesn't change) our existing local-first,
  minimal-request design as the right lane.
- **Strategic nuance for the acquisition thesis:** the closest historical
  precedent to "GGG acquires a community tool" is *not* an acquisition —
  it's a **hire**. GGG hired Path of Building's creator (Openarl) as an
  employee in 2018 and explicitly stated PoB would **not** become an
  official app; he kept maintaining it as a personal/community project.
  [[GGG announcement, 2018-11-07](https://www.pathofexile.com/forum/view-thread/2246498)]
  Combined with Jonathan Rogers' 2026 framing of GGG as an infrastructure
  provider that deliberately avoids curating community content, the more
  probable GGG playbook is "hire the builder, keep the tool independent"
  rather than "acquire the product and fold it into the game." This
  doesn't invalidate `VISION_ACQUISITION.md`'s thesis, but it's worth
  Christian weighing: the pitch may need to be "acquire Kalandra as a
  product + team" explicitly, since GGG's own stated pattern leans toward
  the softer, cheaper option of just hiring people.

## Roadmap candidates (ranked by acquisition-thesis value — Christian promotes, not auto-added to ROADMAP.md)

1. **Passive-tree leveling/allocation guidance inside the Orb companion.**
   *Rationale:* explicitly unclaimed — even PoB2's own maintainer declined
   it as too much UX work — and it's pure "advise like a coach," the exact
   pillar GGG would be buying.
2. **Post-patch resilience UX: visible "provider health" status + graceful
   degradation instead of silent breakage.** *Rationale:* turns our
   provider-seam architecture (W4-00) into a marketed differentiator
   against the ecosystem's single most common complaint (tools breaking
   for days after every patch) — and it's a UI layer on infrastructure we
   already have, not new plumbing.
3. **First-class photo/OCR item scanner, positioned for console and
   no-overlay players (extends W3-33).** *Rationale:* Exile Companion
   (mobile, 20k+ downloads, 4.6★) proves real demand outside PC-overlay
   users; nothing found pairs OCR scanning with a full companion (pricing
   + crafting + build context) the way Kalandra's existing
   `parse_item_text` pipeline would.
4. **"Import your toolbox" onboarding: pull in an existing NeverSink/
   Fubgun filter, PoB2 build, and saved trade searches on first run rather
   than asking users to abandon their setup.** *Rationale:* directly
   answers the ecosystem's documented fragmentation problem (players
   running 4-6 single-purpose tools at once) and echoes GGG's own stated
   discomfort (Chris Wilson, 2017) with forcing players into a pile of
   third-party downloads — makes Kalandra the consolidation play instead
   of one more app in the pile.
5. **Local-first stash/net-worth dashboard using OCR/clipboard capture
   instead of waiting on the PoE2 stash API.** *Rationale:* every
   competitor building a stash tracker is equally blocked on GGG's
   missing OAuth stash scope; approximating stash contents through the
   Reserve tab's existing OCR path would be a genuine first-mover gap
   rather than a race we're equally stuck in.

---

## Changelog

- **2026-07-10** — Initial baseline snapshot. First run of this routine;
  no prior snapshot to diff against. Established the comparison table,
  identified the GGG-native-price-checker-killed-a-competitor precedent,
  the Openarl-hire-not-acquisition nuance for the acquisition thesis, and
  five ranked roadmap candidates.
