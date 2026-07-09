# Craft Hunter — design spec (alert-only mod sniper)

Status: **SPEC** (not started) · Target: `gui_overlay/craft_hunter.py` + `core_engine/craft_hunter.py`
Written 2026-07-06.

## 1. Goal

You're chaos-spamming (or alt/aug/essence-spamming) an item hunting for specific
mod(s) in specific value ranges. Kalandra watches the item tooltip and the
instant a target lands it **flashes the screen and plays a loud sound** so you
stop clicking. Supports multiple simultaneous targets ("stop on T1 spell damage
OR +2 gems"), each with its own numeric range.

## 2. Hard constraint: no input interception

The original idea included suppressing keystrokes/clicks until the alarm fires.
**We will not do that.** Kalandra's compliance line (see
`docs/SECURITY_AND_PRIVACY.md`, `trade_tools.py`, `mirror_window.py`) is:
*we read what the game shows/writes; we never touch the game.* A keyboard hook
that swallows input based on detected game state is the tool acting on the
game for you — squarely in GGG's bannable "automation/decision-making"
category, even though it's a stop rather than a go.

Cost of dropping it: human reaction to flash+sound is ~200–300 ms, so worst
case you burn **one** extra orb after the hit. Acceptable.

## 3. Detection pipeline

Two layers, cheapest first:

### 3a. Tooltip OCR (the live watcher)
- While hunting, the item tooltip is on screen (cursor hovers the item to
  spam). Capture a **user-calibrated crop** of the tooltip region only.
- Loop: grab crop → perceptual hash → if unchanged since last frame, skip
  (crafting clicks change the tooltip; idle frames are free). On change, OCR.
- OCR engine: RapidOCR (onnxruntime) preferred — ~50–120 ms on a small crop,
  pip-installable, no Tesseract binary dependency. Fallback: `pytesseract` if
  the user has Tesseract installed. Both optional-import, feature disabled if
  neither present (same pattern as Whisper in `voice_engine.py`).
- Parse OCR lines with the same normalizer as `trade_tools.parse_item_text`
  (strip tier tags, collapse whitespace, fuzzy-match digits `O→0`, `l→1`).
- Budget: capture 5–15 ms + hash 1 ms + OCR ~100 ms ⇒ **~8 checks/sec**,
  faster than anyone can spam chaos orbs.

### 3b. Clipboard confirm (authoritative)
- After the alarm, the user hovers + Ctrl+C as usual. The existing clipboard
  watcher (`mirror_window._on_clipboard_item`, W3-20) routes the text to the
  hunter, which re-checks targets against exact parsed values and shows
  HIT (green) / FALSE ALARM — keep going (red).
- OCR misreads are thus never trusted for the final keep/continue decision.

## 4. Target definition & matching

```
Target = {
  mod_line:  "#% increased Spell Damage",     # templated, # = number slot
  min: 95, max: None,                          # inclusive range, either optional
  mode: "any" | "all"                          # across the target list
}
```

- Mod picker fed from `localized_knowledge.db` mod tables (autocomplete),
  with a free-text row for anything not in the DB.
- Matching: template → regex (`#` → `(\d+(?:\.\d+)?)`), case-insensitive,
  tolerate OCR noise via `difflib` ratio ≥ 0.85 on the non-numeric part.
- Hybrid/multi-line mods: a target may define 2 lines that must both appear.
- List semantics: default **any** target hit ⇒ alarm; optional **all**.

## 5. Alarm

- Full-screen transparent click-through flash (3 pulses, theme accent color) —
  reuse the overlay window pattern from the medallion/mirror windows.
- Loud distinct sound (bundled .wav, `QSoundEffect`), volume slider.
- Big "⛔ TARGET HIT — STOP" toast near cursor until dismissed or Ctrl+C.
- Optional: auto-pause the watcher after a hit (don't re-alarm on same item).

## 6. Stash-regex helper (free win, ships first)

From the same target list, generate the in-game **stash/vendor search regex**
(≤ 50 chars, PoE regex dialect: `"..."` quoting, `|` alternation, numeric
ranges unrolled e.g. `r 9[5-9]|r 1\d\d`). The game itself then dims the tab
and lights the item when it hits — zero external detection, 100 % safe, works
even if OCR is off. Copy-to-clipboard button. This is also the fallback for
users who never calibrate OCR.

## 7. UI (new "Craft Hunter" tab)

1. Target list table: mod | min | max | any/all toggle | remove.
2. Calibrate button: user hovers item, presses hotkey, drags a rectangle over
   the tooltip once; region saved to `data_engine/config.json`.
3. Arm/Disarm toggle (global hotkey, e.g. F8) + status lamp (armed / hit /
   OCR-off).
4. Generated stash regex, live-updating, with copy button.
5. Session stats: attempts detected, hits, orbs-per-hit estimate (feeds
   `grind_tracker` later).

## 8. Integration points

| Existing | Reuse |
|---|---|
| `trade_tools.parse_item_text` | clipboard confirm parsing |
| `mirror_window._on_clipboard_item` | route copies to hunter when armed |
| `localized_knowledge.db` | mod autocomplete + tier ranges |
| `media_recorder` capture path | screen-grab primitives (crop only) |
| `theme.py` | flash color, tab styling |
| `data_engine/config.json` | targets, region, volume, hotkeys |

## 9. Phases

1. **P1 — Regex helper** (small): target list UI + stash-regex generator +
   clipboard-confirm matching. No OCR. Immediately useful.
2. **P2 — OCR watcher**: calibration, capture loop, hash-skip, RapidOCR,
   alarm. Optional dependency.
3. **P3 — Polish**: session stats → grind_tracker, per-target sounds,
   essence/omen-aware hints from `offline_craft_guidance`.

## 10. Open questions

- RapidOCR adds ~60 MB (onnxruntime) — bundle in installer or on-demand pip?
- Windowed vs exclusive-fullscreen capture: exclusive fullscreen may defeat
  `mss`/GDI grabs; document "use Windowed Fullscreen" like every overlay does.
- Should the alarm also fire on *near-miss* (e.g. right mod, low roll) with a
  softer chime? Useful for annul/aug decision points.
