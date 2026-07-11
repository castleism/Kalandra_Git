# Scaling & BIS Advisor — Spec

*Status: draft (2026-07-11). Author intent captured from Christian. House style:
goal → hard constraints → data pipeline → UI → integration points → phased plan
→ open questions. ToS line is absolute.*

## Goal

When a player asks "how do I scale my Corrupted Blood build?" (or any skill,
ailment, or damage type), the Orb must answer **from the database**, not from the
chatbot's own knowledge. Concretely, for a subject the answer should be built by:

1. Look up the subject entity (e.g. *Corrupted Blood*) in the knowledge base.
2. Read **all of its real poe2db tags** (e.g. `Physical, Damage Over Time,
   Area`).
3. For **each** of those tags, reverse-look-up every asset that carries the tag:
   - uniques that affect it,
   - item/affix mods to look for when crafting,
   - support gems and lineage/meta gems,
   - passive-tree nodes.
4. Return that consolidated, grouped list as the grounded context — the LLM only
   organizes and narrates it; it never invents the items.

On top of that retrieval, the advisor offers two actions:

- **Weighted PoB tree search** — open the player's *currently loaded* build in
  Path of Building's Power Report with stat weights set to the scaling focus, so
  the tree heatmap highlights the exact nodes worth pathing to.
- **BIS craft simulation** — for a chosen item slot and the player's level, pick
  the most effective mods to scale their focus (leftover mod budget going to
  their stated secondary offensive/defensive focus), simulate the best craftable
  item, link the player to the Craft of Exile simulator, show the estimated
  currency cost, and lay out the crafting steps **accounting for failed rolls**.

The north-star test: the advisor's output should be *specific* — real unique
names, real mod lines, real node clusters, real currency estimates — and every
specific must trace to a database row or a PoB/Craft-of-Exile computation, never
to the language model's memory.

## Hard constraints

- **ToS (absolute):** read-only and advisory. No input interception, no game
  automation, no writing to the client. The player performs every action; we
  only inform. Craft "steps" are instructions for the human, never executed.
- **Grounding rule:** the LLM must not name an item/mod/gem/node that is not in
  the supplied structured context. Reuse and tighten the existing
  ANTI-FABRICATION rules in `voice_engine.py`.
- **Provider seams:** all game-data access goes through a
  `core_engine/providers.py` interface (per `docs/VISION_ACQUISITION.md`). The
  tag graph is a new provider seam; add its row to the pipeline matrix with a
  best-future swap note (scrape → game-file extraction).
- **Degrade gracefully:** if a tag has no tagged assets yet (data not crawled),
  say so plainly rather than guessing. If PoB or Craft of Exile isn't reachable,
  the retrieval list still renders.

## Data pipeline

### Tag reverse-index (the core new capability)

The `knowledge_ledger.tags` column now stores each page's real poe2db tags (added
2026-07-11, sourced from the `<a class="GemTags">` chips). This spec needs a
**reverse index**: tag → assets carrying it.

New module `core_engine/tag_graph.py` (behind a provider interface):

- `tags_for(entity: str) -> list[str]` — the real tags of a named entity
  (exact/normalized title match against `knowledge_ledger`).
- `assets_with_tags(tags: list[str], kinds=None, limit=...) -> dict` — reverse
  lookup: for the given tags, return rows grouped by **kind** (`unique`, `mod`,
  `support_gem`, `lineage_gem`, `passive`, `skill`). Ranked by tag-overlap count
  (an asset matching more of the subject's tags ranks higher), then by source
  authority.
- Backed by SQL over `knowledge_ledger` using the FTS index on the `tags` column
  plus a `kind` classifier. A lightweight `kind` can be derived from
  `source_url`/page structure at crawl time and stored (new nullable
  `knowledge_ledger.kind` column + migration) so reverse queries are cheap.

**Data dependency (R&D, see open questions):** today only *gem* pages yield tags
(GemTags). Uniques, mods, and passives use different poe2db markup (item pages use
`KeywordPopups`; mod and passive pages have their own structures). The scraper's
`_extract_tags` must be extended per page-kind so uniques/mods/nodes get their
real tags too. Until that lands, the reverse index is gem-heavy and the advisor
must say what it can and cannot yet enumerate — never fabricate to fill gaps.

### Player-reported tags (community layer)

New uniques and newly-discovered interactions show up in play before poe2db
documents them. Let players close that gap by proposing tags so the graph updates
immediately instead of waiting on the scrape:

- A **"Suggest a tag / interaction"** action on any entity: the player proposes a
  tag, or a relationship (`this unique applies Corrupted Blood`, `X is affected by
  Y`).
- Stored in a **community layer distinct from scraped tags** — reuse the
  `knowledge_corrections.py` pattern (a JSON-backed, ship-safe overlay that
  survives DB rebuilds), each entry flagged `source="community"` with a
  confidence/vote field.
- The tag graph merges scraped + community tags, but marks community-sourced
  entries visibly (**"player-reported, unverified"**) so the advisor never
  presents them as authoritative. A promotion path (as with verified corrections
  today) lets a maintainer bless a community tag into ground truth.
- Abuse guard: local-only by default; any future shared/synced version needs
  moderation or voting. ToS unaffected — this is metadata about the game, not
  interaction with it.

### Meta-mining — empirical discovery via poe.ninja (second search method)

The tag graph finds **direct** scalers. Some of the best synergies are
**indirect**: Corrupted Blood is applied through warcries, so warcry-effect /
exert / duration scalers — and specific uniques — matter without sharing CB's
damage tags. Mine what top players actually run to surface these:

1. **Identify the appliers** — items/gems that apply the effect (for CB: a shield,
   the Corrupting Cry support, and a unique the player named — verify exact names
   before shipping). The tag graph + community "applies: <effect>" relationships
   feed this list.
2. **Query poe.ninja filtered to players using an applier** (reuse
   `core_engine/poe_ninja.py`; respect its rate limits — it's already a pipeline
   source).
3. **Aggregate co-occurrence** across those players: the next most common items,
   skills, supports, lineages, and passive allocations.
4. **Surface what the tag search missed** — entries common among these players but
   absent from the tag-graph result are the candidate **indirect scalers** to
   investigate (and prime candidates for a community tag once confirmed).

**DPS caveat (critical):** poe.ninja's DPS ranking is **not valid** for Corrupted
Blood — poe.ninja does not compute CB DPS. Rank these players by
co-occurrence/popularity, never by poe.ninja DPS. Real DPS for such builds
requires configuring CB as the **active skill in PoB** and computing it there
(`pob_sim`); the advisor can offer to do that per build. Also normalize
co-occurrence (movement skills, common utilities appear everywhere) — rank by
lift/PMI over raw frequency so genuinely *distinctive* shared choices rise.

Output: a **"Players running this also use…"** panel, clearly separated from the
tag-graph results, feeding both the narrated answer and the community-tag
suggestion queue.

### Weighted PoB tree search

Reuse `pob_bridge.analyze_scaling(build)` and `pob_bridge.tree_guidance(build)`
(already feed the AI context). The advisor maps the scaling focus → PoB stat
weights and opens the loaded build's Power Report with those weights preset.
Requires an existing loaded build (green Character Selector); otherwise it prompts
to load one.

### BIS craft planner

New module `core_engine/craft_planner.py` (provider seam), consuming:

- the tag reverse-index (which mods scale the focus),
- `trade_tools` stat-id map (`trade_stats_poe2.json`) to resolve real mod ids,
- `pob_sim` to score candidate items by the DPS/defence delta they produce on the
  loaded build,
- item-slot mod-pool rules (which mods can roll on which base/slot).

Output for a chosen slot + player level: the selected primary mods (focus),
secondary mods (stated secondary focus), a simulated finished item, an estimated
currency cost, a **Craft of Exile** deep link preloaded with the target mods, and
a human-readable step list that accounts for failed rolls (expected attempts,
fallback branches). All advisory.

## UI

- In the dashboard chat and/or a new "Scaling" pane: when the retrieval runs,
  render the grouped asset list directly (Uniques / Mods to craft / Support &
  Lineage gems / Passive nodes) as real, clickable rows (poe2db citations) —
  independent of the chatbot prose, so the player sees the DB result even if they
  ignore the narration.
- Two action buttons under the list: **"Open weighted tree in PoB"** and
  **"Plan a BIS craft…"** (slot + secondary-focus picker → planner output).
- Craft output shows: item preview, currency estimate, "Open in Craft of Exile"
  link, and the numbered step plan with retry expectations.

## Integration points (reuse, don't rebuild)

| Need | Existing module |
|------|-----------------|
| Tag data on pages | `core_engine/scraper.py` (`_extract_tags`, `tags` column) |
| KB storage / FTS | `core_engine/database_handler.py` |
| Grounded AI context | `gui_overlay/mirror_window.py` `_ai_context`, `voice_engine.py` |
| Loaded build + tree weights | `core_engine/pob_bridge.py` (`analyze_scaling`, `tree_guidance`) |
| Live stat recompute | `core_engine/pob_sim.py` |
| Mod / stat-id resolution | `core_engine/trade_tools.py`, `trade_stats_poe2.json` |
| Verified facts override | `core_engine/knowledge_corrections.py` |

## Phased plan

- **P1 — Tag reverse-lookup grounding (small, independently shippable).**
  `tag_graph.py` with `tags_for()` + `assets_with_tags()` over the existing
  `tags` column; a `kind` column + migration; feed a compact "SCALING SOURCES
  (from DB)" block into `_ai_context` so answers cite real assets; render the
  grouped list in the chat pane. Ships value immediately with gem-level tags and
  degrades honestly where uniques/mods aren't tagged yet. Tests:
  `tests/tag_graph_checks.py` (tags_for exact match, reverse lookup ranking,
  empty-tag degrade, no-fabrication contract).
- **P1.5 — Extend tag extraction to uniques/mods/passives** (Data Sentinel / R&D
  routine): per-page-kind `_extract_tags`, populate `kind`. Regression fixtures.
- **P2 — Weighted PoB tree search action:** map focus → stat weights, open Power
  Report on the loaded build. Reuses `pob_bridge`.
- **P2.5 — Community tag layer:** JSON overlay (`knowledge_corrections.py`
  pattern) + "Suggest a tag/interaction" UI + merge into `tag_graph` with
  trust/vote flags and an "applies: <effect>" relationship type. Feeds both the
  advisor and the meta-miner's applier list.
- **P3 — BIS craft planner:** `craft_planner.py`, Craft of Exile deep link,
  currency estimate, retry-aware step plan, `pob_sim` scoring. Largest slice;
  its own sub-spec once P1/P2 land.
- **P4 — Meta-mining via poe.ninja:** applier list → poe.ninja co-occurrence
  aggregation → "indirect scalers you might be missing" panel, with lift/PMI
  ranking and the DPS caveat baked in. Extends `poe_ninja.py`; confirmed indirect
  scalers flow back as community-tag suggestions. Needs its own sub-spec.

## Degradation

- No loaded build → retrieval still works; PoB/BIS actions prompt to load one.
- Optional deps (PoB engine, network to Craft of Exile) missing → list renders;
  actions show a clear "needs X" note.
- Tag not yet in DB → state it plainly; suggest running a Sync.

## Testable headlessly vs needs Windows eyes

- Headless: tag_graph queries, ranking, kind classification, context-block
  assembly, craft-planner mod selection and cost math (fixture builds).
- Needs Windows: the PoB Power Report launch, the dashboard pane rendering, and
  Craft of Exile deep-link open.

## Open questions

1. poe2db tag markup for **uniques, mods, and passive nodes** — what element/class
   carries their tags? (Gems use `<a class="GemTags">`; items showed
   `KeywordPopups`.) Drives P1.5.
2. `kind` classification: derive from `source_url` path segments, page structure,
   or a small rules table?
3. Ranking: is tag-overlap count the right primary sort, or weight by tag rarity
   (a rare shared tag is more meaningful than `Physical`)?
4. Craft cost model: pull live currency values (poe.ninja) vs static heuristics
   for the estimate?
5. Secondary-focus input: infer from the loaded build's existing scaling, or ask
   the player each time?
6. Community tags: local-only vs shared; if shared, moderation/voting model and
   how "unverified" is surfaced so it never masquerades as authoritative.
7. Meta-mining data access: can poe.ninja be filtered by item server-side, or
   must we sample player builds and aggregate client-side within rate limits?
   Co-occurrence normalization (lift/PMI) to stop ubiquitous items dominating.
8. Applier identification: model an explicit `applies: <effect>` relationship in
   the graph (scraped + community) so appliers are directly queryable for both
   the tag search and the meta-miner.
