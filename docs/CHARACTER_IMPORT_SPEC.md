# Character Import & Deep-Scan — design spec (W4-04)

Status: **SPEC** (not started) · Target: `core_engine/character_import.py` (new)
+ `gui_overlay/owl_interview.py` (hook) + `gui_overlay/companion_tab.py` (entry point)
Written 2026-07-10.

## 1. Goal

DESIGN_COMPANION.md's P1 in one line: when the player mentions a past or
current character (by name, or just "class/level/league"), Kalandra finds
it, imports the full build, deep-scans every gem/support/item/passive, and
uses what it learns to (a) seed a `CharacterFolio` and (b) quietly fill in
`PlayerProfile` facts the owl interview would otherwise have to ask for.

This is glue, not new invention — every hard part already exists
(`pob_bridge` parses builds fully, `character_folio` already writes the
per-character folder shape, `poe_account` already talks to GGG's public
endpoints). What's missing is the orchestration that turns "the player just
told the owl about a character" into a populated folio, and the inference
step from folio → profile that DESIGN_COMPANION promised and never got
built (`player_profile.py` currently only accepts answers typed into the
interview UI; nothing writes to it from a scan).

## 2. Hard constraints (ToS line)

- **Read-only, always.** This spec never sends input to the game or to
  pathofexile.com beyond what a browser session already does. Every
  character/build source below is either (a) data the player pastes
  themselves, (b) PoB's own official-ish import (a widely-used third-party
  tool, not us reaching into GGG's account systems), or (c) GGG's
  already-public, unauthenticated endpoints (ladder).
- **No new auth mechanism invented.** We do not build a session-hijacking
  or scraping-login flow. The only "authenticated" character list path
  (§3c) reuses the *exact* optional `POESESSID` cookie field pattern PoB
  itself uses for its account importer — user pastes their own cookie
  value, we store it in the OS keychain via `account_manager`
  (`SERVICES["pathofexile"]`, already reserved), never plaintext, and it's
  never required. If GGG issues an OAuth `client_id` (`oauth_pkce.py` is
  ready and waiting — see `docs/GGG_OAuth_Application_Letter.md`), that
  becomes the preferred path and POESESSID becomes the fallback.
- **Nothing blocks on GGG.** The PoE2 character-list endpoint currently
  404s (`poe_account.get_characters`, confirmed in code — "PoE2 characters
  aren't exposed by GGG's public API yet"). The feature must work fully
  with that path dark: manual PoB code/link paste (already shipped) is
  never removed and stays the documented fallback everywhere in the UI.

## 3. Character discovery — three paths, cheapest/most-available first

### 3a. Manual PoB code / link paste (already shipped, zero new work)
The player pastes a PoB export code or a pobb.in/pastebin link.
`pob_bridge.resolve_link_to_code` → `extract_full_build` already does the
rest. This spec's job is only to route the *result* into `CharacterFolio`
(§4) instead of a one-off view, and to also feed profile inference (§5).

### 3b. PoB's own account import (embedded window, no new auth)
`PobLiveTab` (`gui_overlay/dashboard.py:2298`) already embeds the real PoB2
window and hot-reload-watches its builds folder. PoB's *own* "Import/Update
Character" feature (inside the embedded window, using the player's own PoE
session — nothing Kalandra touches) is how the player pulls a character
without typing a code by hand. When PoB writes/updates a build file in the
watched folder, `on_build_saved` already fires. New work: when the owl
interview is mid-flow and the player says "let's import it," surface a
one-line nudge — "open the Build tab, use PoB's Import Character, then come
back" — and treat the next `on_build_saved` event during that window as the
answer.

### 3c. Direct character list (optional, degrades to nothing today)
`poe_account.get_characters(account_name, league=None, poesessid=None)`
already exists and already handles the 404 case explicitly. New work:
1. A single optional Settings field — "PoE session cookie (optional)" —
   stored via `account_manager.set_secret("pathofexile", value)`. Skippable;
   the row already exists in `SERVICES`, nothing writes it yet.
2. If present, `character_import.list_characters(account_name)` calls
   `get_characters` with the cookie; on 404/403 (today's reality for PoE2)
   it fails soft — returns `[]` with a reason string, UI never shows an
   error, just skips straight to §3a/3b.
3. When GGG ships the endpoint (or a `client_id` arrives and `oauth_pkce`
   takes over auth), this path lights up with zero UI changes — the
   "matching characters" list just stops being empty.
4. Public **ladder** browsing (`get_ladder`) needs no auth at all and is
   already shipped/wired — this spec adds it as a fourth lookup option in
   the "I don't remember the exact name" flow (interview already asks
   "class/level/league" for exactly this case).

## 4. Deep scan → CharacterFolio

Once any path above yields a build (XML or code), the scan is already
fully specified by existing code — this spec just wires it up:

```
build      = pob_bridge.extract_full_build(xml_or_code)   # gems, supports,
                                                            # items+mods, tree,
                                                            # skill groups
scaling    = pob_bridge.analyze_scaling(build)             # damage-type profile
guidance   = pob_bridge.tree_guidance(build)                # passive notes
folio      = CharacterFolio(build["character_name"] or slug)
folio.write_scan(build)          # profile.json + auto review.md if none exists
folio.add_sim_note(scaling)      # sim_notes/ — reuses existing method
```

If `pob_sim` is available (`PoBSimulator.available`), attach it via the
`build_calculator` provider (`providers.PobCalculator.attach_sim`) first so
`stats_summary()` on the folio reflects live-simulated numbers, not just
static XML stats. If unavailable, the folio still gets the full static
scan — live stats are a bonus, never a gate (same optional-dependency
posture as everywhere else in the codebase).

## 5. Profile inference (the actual gap)

`PlayerProfile` (`core_engine/player_profile.py`) has no code path today
that sets facts from anything but the manual interview UI. New function:

```
def infer_from_scan(profile: PlayerProfile, build: dict) -> list[str]:
    """Set profile facts the scan makes obvious; return which fields changed."""
```

Conservative inference only — set a fact from a scan only when the
interview would otherwise have to ask and the scan answers it with no
ambiguity:
- Class/ascendancy + highest character level seen → contributes to "peak
  level" (never overwrites an explicit interview answer, only fills gaps
  the player skipped or hasn't reached yet).
- Multiple characters spanning several leagues → "leagues played" list.
- Damage-type mix across scanned characters (from `analyze_scaling`) →
  a soft signal for "meta vs niche taste," surfaced to the owl as a
  suggestion line, never silently set (this one is a taste judgment, not a
  fact — the interview's existing "no wrong answer" framing applies).
- Never touches the sensitive "how did those levels happen" question —
  that stays player-answered only, per DESIGN_COMPANION's explicit
  rationale.

Every inferred fact is shown to the player as a dismissible chip
("Owl noticed: Ascendant, level 97, Standard + Settlers — sound right?")
before it's saved, so nothing gets written silently.

## 6. UI

1. **Owl interview hook**: after the existing "free-text build history"
   question, if the player named specific characters, offer "Want me to
   pull that in?" → drives §3a/§3b/§3c in that preference order, shows a
   spinner ("scanning…"), then the inferred-fact chips from §5.
2. **Companion tab entry point**: a persistent "Import a character" action
   (not just interview-gated) for players who skip/redo the interview
   later — same pipeline, reachable any time.
3. **Character Sheet / folio list**: `list_folios()` already exists;
   surface it as a picker wherever a character needs selecting (Death
   Review, future Character Sheet flagship).
4. Settings: the optional POESESSID field from §3c, with inline copy
   explaining it's optional, stored in the OS keychain, and mirrors what
   PoB's own importer already asks for.

## 7. Integration points

| Existing | Reuse |
|---|---|
| `core_engine/pob_bridge.py` | code/link decode, full build extraction, scaling analysis, tree guidance |
| `core_engine/pob_sim.py` | optional live-stat attach via `providers.PobCalculator` |
| `core_engine/character_folio.py` | per-character folder writes (`write_scan`, `add_sim_note`, `list_folios`) |
| `core_engine/player_profile.py` | fact storage — new `infer_from_scan` writes here |
| `core_engine/poe_account.py` | `get_characters` (soft-fails today), `get_ladder`, `pob_import_hint` |
| `core_engine/oauth_pkce.py` | ready for when a GGG `client_id` exists; not wired until then |
| `core_engine/account_manager.py` | keychain storage for the optional POESESSID (`SERVICES["pathofexile"]`) |
| `gui_overlay/dashboard.py` `PobLiveTab` | embedded PoB window + hot-reload watch (the §3b import path) |
| `gui_overlay/owl_interview.py` | the hook point in §6.1 |
| `core_engine/providers.py` `BuildCalculator` | the seam the scan's stats go through — no new provider needed, this feature is a consumer |

### Pipeline-matrix update

`docs/VISION_ACQUISITION.md`'s matrix has no row for "who is this
character" — it should. Add:

| Data | Today's source | Provider seam | Post-GGG swap |
|---|---|---|---|
| Character list / identity | PoB's own import (§3b) + `poe_account.get_characters` (404 on PoE2 today) + public ladder | *(needs seam — candidate: `AccountData` provider wrapping §3a/b/c)* | Official character API (already the plan; `oauth_pkce.py` is pre-built, just needs a `client_id`) |

This spec does not build the provider ABC — three call sites is too thin to
justify one yet. Flagging it as the next `(needs seam)` candidate for the
provider-boundary routine once a second consumer (e.g. the Character Sheet
flagship) needs the same lookup.

## 8. Optional-dependency degradation

- No PoB install found → §3b unavailable, §3a (manual paste) still works
  fully; `dependencies.py`'s existing PoB-missing messaging covers this.
- `pob_sim` unavailable (no LuaJIT/headless harness) → scan proceeds with
  static XML stats only; live-sim fields simply absent from the folio, not
  an error.
- No POESESSID set → §3c always returns empty, UI never surfaces it as a
  failure, just skips to the working paths.
- `keyring` unavailable → same fail-closed posture as the rest of the app;
  the optional POESESSID field is disabled with the existing "keychain not
  available" messaging (`account_manager` already fails closed, no new
  code needed here).

## 9. What's testable headlessly vs needs on-Windows eyes

**Headless** (this is most of it): `infer_from_scan` logic against
synthetic build dicts; `character_import.list_characters` against a mocked
`poe_account` (404 path, populated path, network-error path); the full
§3a→§4 pipeline (code paste → folio write) end to end, since
`pob_bridge.extract_full_build` and `CharacterFolio` are both pure Python;
chip-dismiss/accept state machine for §5's confirmation UI (logic, not
paint).

**Needs Windows eyes**: the actual `PobLiveTab` embed + "open PoB, import,
come back" nudge timing (§3b) — window re-parenting and file-watch races
are exactly the kind of thing that only shows up on a real desktop; the
interview chip UI rendering (§6.1) against the real theme.

## 10. Phases

1. **P1 — Manual import → folio, small, independently shippable, no auth
   at all**: wire §3a (already-shipped code/link parsing) into
   `CharacterFolio.write_scan` + `add_sim_note`, ship `infer_from_scan`
   (§5) with the confirmation-chip flow, and the Companion tab entry point
   (§6.2). Zero new auth surface, zero new optional dependencies — pure
   glue between modules that already exist. This alone delivers "import a
   character and have the owl learn from it," which is the useful core of
   W4-04.
2. **P2 — PoB embedded-import hook (§3b)**: the interview nudge +
   `on_build_saved` handoff into the P1 pipeline. Needs on-Windows
   verification of the embed/watch timing.
3. **P3 — Optional POESESSID + `get_characters` (§3c)**: Settings field,
   keychain wiring, soft-fail UI. Low value until GGG exposes the PoE2
   endpoint, but costs little and is ready the moment it lands (and the
   `oauth_pkce` upgrade path is a drop-in swap later, not a rewrite).

## 11. Open questions

- Should ladder-browsed characters (public, not the player's own) get a
  folio too, or stay a separate "reference build" concept? Leaning
  separate — folios currently imply "this is one of my characters" for
  the profile-inference step in §5, and mixing in someone else's ladder
  character would corrupt those inferences.
- §5's "meta vs niche taste" signal is explicitly a suggestion, never
  auto-set — is a dismissible chip enough friction, or does taste-guessing
  need to stay interview-only entirely? Revisit after the first on-Windows
  test of how it reads to a player.
- When multiple characters import at once (e.g. after a ladder-browse
  session), does the confirmation-chip UI batch them into one card or show
  one per character? Defer to whoever builds P1 — a UI call, not an
  architecture one.
