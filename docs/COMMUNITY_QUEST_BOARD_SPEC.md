# Community Quest Board — Spec

*Status: draft (2026-07-11). Author intent captured from Christian. Sibling to
`docs/SCALING_ADVISOR_SPEC.md` (its community tag layer). House style. ToS line
is absolute.*

## Goal

Crowdsource the upkeep of Kalandra's knowledge base by turning data gaps into a
visible list of **quests** the community can complete *using the tool itself*.
Examples: tag an untagged unique, investigate a newly-added unique or a
newly-discovered interaction, confirm a reported "this applies Corrupted Blood"
relationship, or verify how a patch changed an item. A quest stays **open until
its completion is verified** — never auto-closed on a single unconfirmed
submission.

The board keeps the database current between poe2db scrapes and lets players who
*use* the tool feed it back into shape, with credit for doing so.

## Hard constraints

- **ToS (absolute):** read-only game posture. Quests are about *metadata* (tags,
  interactions, item data) — never actions in the game client. No automation.
- **Verification before close:** a quest only reaches `verified` via independent
  agreement (N confirmations) or a trusted maintainer's sign-off. Unverified
  contributions surface as "player-reported, unverified" (per the Scaling Advisor
  community layer) and never masquerade as ground truth.
- **Local-first:** ships fully functional local-only. Any shared/synced board is
  a later phase and needs moderation + anti-abuse (see open questions). Reuse the
  ship-safe JSON-overlay pattern from `knowledge_corrections.py`.
- **Provider seams:** anything that reads game data to *generate* quests goes
  through the existing provider interfaces (`providers.py`); add a row to the
  pipeline matrix if a new seam appears.

## Quest sources (how quests are created)

**Auto-generated from detected gaps** (the board should mostly fill itself):

- **Untagged / thinly-tagged entities** — rows in `knowledge_ledger` with empty
  or suspiciously sparse `tags` → *TagQuest*.
- **Newly-scraped pages** the crawler just discovered (new uniques/gems) that
  lack tags or a `kind` → *InvestigateQuest* + *TagQuest*.
- **Patch-flagged changes** — items/mechanics `nerf_intel` finds in fresh patch
  notes → *VerifyQuest* ("confirm how X changed").
- **Unverified community submissions** — every "player-reported" tag or
  `applies:<effect>` relationship from the Scaling Advisor community layer that
  hasn't hit its confirmation threshold → *VerifyQuest*.
- **Meta-mining leads** — candidate indirect scalers surfaced by the poe.ninja
  miner that aren't in the tag graph yet → *InvestigateQuest*.

**Manually posted** by maintainers (a free-form quest with a subject + acceptance
criteria) for anything the automation can't detect.

## Quest lifecycle

`open → claimed → submitted → verified → closed`, with `reopened` if later
contradicted.

- **open** — visible on the board, unclaimed.
- **claimed** — a player marks they're working it (soft, non-exclusive; expires
  so abandoned claims free up).
- **submitted** — a player attaches evidence (proposed tags, a poe2db/wiki/PoB
  link, a screenshot, a short note). Multiple independent submissions accumulate.
- **verified** — reached when submissions agree to threshold **or** a maintainer
  signs off. Only now is the underlying data change promoted (e.g. a TagQuest's
  tags get written into the community tag layer, eligible for maintainer
  promotion to ground truth).
- **closed** — verified *and* the DB reflects it. A gap-generated quest also
  requires the gap to actually be gone (entity now has verified tags), so a quest
  cannot silently close while the data is still missing.
- **reopened** — if a later scrape, patch, or contradicting submission
  invalidates the resolution.

The rule "stays open until verified complete" is enforced structurally: `closed`
is unreachable without a `verified` transition, and auto-generated quests
re-open automatically if their gap detector fires again.

## Quest types

| Type | Subject | "Done" means |
|------|---------|--------------|
| TagQuest | an entity | its real tags are supplied and verified |
| InvestigateQuest | a new unique / interaction | documented: what it is, what it interacts with, proposed tags/relationships |
| VerifyQuest | a community claim or patch change | independently confirmed or refuted |
| RelationshipQuest | `X applies/affects Y` | the relationship is confirmed and added to the graph |

## Data model

`community_quests` (JSON overlay, ship-safe, survives DB rebuilds):

- `id`, `type`, `subject_ref` (entity/url/claim id), `title`, `criteria`,
  `status`, `source` (`auto`|`maintainer`), `created_at`,
  `claims[]`, `submissions[]` (each: contributor, evidence, timestamp),
  `verifications[]` (confirmations / maintainer sign-off), `resolution`,
  `contributor_credits[]`.

Verification threshold and trusted-maintainer list are config.

## UI

- A **"Quest Board"** pane in the dashboard: filterable list (type, status,
  subject area), each quest showing title, criteria, current evidence, and
  progress toward verification.
- **Claim** and **Submit evidence** actions; a submit form pre-scoped to the
  quest type (e.g. a TagQuest form suggests tags and links straight into the
  community tag layer).
- A lightweight **contributor credit** view (quests you've helped verify) — the
  gamified hook. No leaderboards required for P1.
- Deep-links: a TagQuest row links to the entity in the app and to its poe2db
  page for reference.

## Integration points (reuse, don't rebuild)

| Need | Existing module |
|------|-----------------|
| Untagged-entity detection | `core_engine/database_handler.py` (`tags` column), `scraper.py` |
| Patch-change detection | `core_engine/nerf_intel.py` |
| New-page discovery | `core_engine/scraper.py` crawl state |
| Community tag write path | Scaling Advisor community layer (`knowledge_corrections.py` pattern) |
| Meta-mining leads | `core_engine/poe_ninja.py` (P4 of Scaling Advisor) |
| Verified-fact promotion | `core_engine/knowledge_corrections.py` |

## Phased plan

- **P1 — Local quest board (small, shippable).** `core_engine/quest_board.py`:
  JSON-backed quest store + a generator that turns untagged `knowledge_ledger`
  rows and maintainer-posted entries into quests; the lifecycle state machine
  (open→claimed→submitted→verified→closed) with a config threshold; a dashboard
  pane listing/claiming/submitting. Local-only. Tests:
  `tests/quest_board_checks.py` (gap→quest generation, state transitions,
  can't-close-without-verify, reopen-on-regap).
- **P2 — Wire to the community tag layer:** completing/verifying a TagQuest or
  RelationshipQuest writes the (verified) tags/relationship into the tag graph;
  auto-generate VerifyQuests from unverified community submissions.
- **P3 — Auto-quests from patches + meta-mining:** `nerf_intel` patch diffs and
  poe.ninja indirect-scaler leads spawn Investigate/Verify quests.
- **P4 — Shared/synced board (future, beyond local-first):** a backend so quests
  and verifications are community-wide. Requires moderation, anti-abuse, identity
  — its own sub-spec; do not half-build.

## Degradation

- Offline / no new data → board shows existing open quests; generation just
  doesn't add new ones.
- No maintainer configured → verification relies solely on the independent-
  confirmation threshold.

## Testable headlessly vs needs Windows eyes

- Headless: quest generation from gaps, the full lifecycle state machine,
  verification thresholds, reopen logic, write-back into the tag layer.
- Needs Windows: the Quest Board pane rendering and the submit/claim flows.

## Open questions

1. **Local-only vs shared:** P1 is local (a player's own to-do list against the
   DB). The real payoff is a *shared* board — but that needs a backend,
   moderation, and identity. Ship local first; design the JSON schema so it can
   sync later.
2. **Verification threshold:** how many independent agreeing submissions equal
   "verified" without a maintainer? Does it vary by quest type (a tag needs fewer
   than a subtle interaction)?
3. **Anti-abuse / credit:** how to stop spam or bad-faith submissions from
   reaching `verified`; what contributor credit is motivating without inviting
   gaming.
4. **Auto-detecting "game changes that need investigation":** how much can
   `nerf_intel` patch-diffing generate on its own vs needing a human to post the
   quest?
5. **Claim model:** soft/non-exclusive claims with expiry (assumed) vs hard
   assignment — the former is friendlier for a many-player board.
