# Kalandra — Stress Test & Placeholder Completion Report

This pass finished every unbuilt dashboard placeholder and expanded the
adversarial test suite. All work is local-only and ToS-clean (no game
automation, no fabricated prices, no logins on your behalf).

## What changed this session

**New / completed feature tabs** (all in `gui_overlay/dashboard.py`, backed by
pure-logic modules so they're testable):

- **Filter Editor** — real tab now wired in. Lists every block in your `.filter`,
  color-codes Show / Hide / Minimal, lets you flip a block's action and save.
  Saving writes a `.bak` backup first. Exact byte round-trip, so untouched parts
  of your filter are never reformatted. Backend: `core_engine/filter_editor.py`.
- **Currency Exchange** — live PoE2 economy from poe.ninja's public JSON (no
  login, no key). League picker, name filter, sortable value/volume table.
  Fetches off the UI thread so the dashboard never freezes. Backend:
  `core_engine/poe_ninja.py`.
- **Price Check** — paste an item (Ctrl+C in-game → Ctrl+V), Kalandra reads its
  rarity / name / base / item level / mods and opens the **official** trade
  search for your league. You read real listings and buy manually. Backend:
  `core_engine/trade_tools.py`.
- **Crafting Planner** — describe a goal in plain language; get a realistic PoE2
  craft path (Transmute → Augment → Regal → Essence/Rune/Omen → Exalt/Chaos/
  Divine) plus a one-click link to Craft of Exile for exact odds. Wires to an AI
  brain if one is configured; otherwise gives the offline heuristic.
- **Live Search** — opens the official trade site's live search for your league
  and explains the manual whisper-and-buy flow. No auto-buy, fully ToS-clean.

**New modules**

- `core_engine/trade_tools.py` — dependency-free item-paste parser + trade URL
  builders. No PyQt, no network, fully unit-tested.
- `core_engine/filter_editor.py` — `.filter` reader/editor with exact round-trip.

## Testing

`tests/stress_test.py` now runs **106 adversarial checks, 0 failures** across:
pob_bridge build parsing (malformed/empty/unicode XML, jewel + warcry DPS),
the three JSON trackers (unique IDs, persistence, corrupt-file recovery),
scraper snippet cleaning, account_manager fail-closed-without-keyring,
sqlite handler under 8 concurrent threads, the new **trade_tools** item parser
(rare vs normal/magic, requirement-line exclusion, URL building), and the new
**filter_editor** (6 exact round-trip cases incl. empty files + back-to-back
headers, action flips, invalid-action rejection, save→reload integrity).

All touched modules pass `py_compile`.

## Notes / still pending

- The PoB "unsupported items" fix still needs you to restart Path of Building in
  developer mode and load your build so it writes `unsupported.txt` — send me
  that file and I'll add the missing mods.
- Deploying directly to your machine still requires `C:\Kalandra` (or
  `D:\GIT\Kalandra`) to be connected to Cowork. Until then, this update ships as
  a code-only zip you extract over the project.
