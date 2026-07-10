# Provider-Boundary Audit

*Maintained by the Provider-Boundary Auditor routine (`docs/ROUTINES.md` §4).
Cross-reference: `docs/VISION_ACQUISITION.md` (thesis + pipeline matrix) and
`core_engine/providers.py` (the seam). Rule: every game-data ingestion point
routes through a provider interface so acquisition day is a call-site swap,
not a rewrite.*

## How this doc is used

Each run: re-sweep for new violations, append/update entries below, migrate
exactly **one** violation (best value-to-risk), update this doc, update the
pipeline matrix row in `VISION_ACQUISITION.md`, extend
`tests/provider_checks.py`, run the full suite, note it in CHANGELOG/ROADMAP.
Entries move to "Migrated" once their call sites route through
`get_provider(...)` and the ABC exists. Never delete a migrated entry — it's
the paper trail that the debt was real and paid down.

---

## Migrated

### `item_in_hand` — clipboard Ctrl+C parse (2026-07-10)

- **Was:** `gui_overlay/mirror_window.py`'s `_on_clipboard_item` called
  `QApplication.clipboard().text()` and `core_engine.trade_tools.parse_item_text`
  directly. Pipeline-matrix row "Item-in-hand" was `*(needs seam)*`.
- **Now:** `ItemInHandProvider` ABC + `ClipboardItemInHand` default impl in
  `core_engine/providers.py`, registered as `"item_in_hand"`. The call site
  is now `get_provider("item_in_hand").read()` — the clipboard read, the
  "is this a PoE item copy" marker check, and the `parse_item_text` call all
  moved into the adapter; `mirror_window.py` keeps only its own debounce
  state (`_last_clip`/`_clip_ts`), which is UI-instance state, not a data
  source.
- **Post-GGG swap:** an engine-callback adapter implementing the same
  `read() -> (info, raw_text)` contract from the hovered/selected item the
  game hands us directly — no clipboard involved.
- **Proof:** `tests/provider_checks.py` — ABC is abstract and can't be
  bare-instantiated, `ClipboardItemInHand.available()` is `False` headless
  (no `QApplication`), `read()` fails soft to `(None, "")`, parsing logic
  verified against a real item-text fixture and edge cases (non-item text,
  empty, oversized), and an AST check on `mirror_window.py` proving
  `_on_clipboard_item` calls `get_provider("item_in_hand")` and no longer
  references `QApplication.clipboard()` or `parse_item_text` directly.

---

## Open violations (ordered value-to-risk, best first)

### 1. `gui_overlay/mirror_window.py:3644-3690` — AI/RAG context duplicates `game_data.search()`

`KalandraOverlayApp._rag_for_terms` (~3644-3660) and `_ai_context`
(~3682-3690) each do:

```python
sdb = KalandraDBHandler()
sc = KalandraScraper(sdb)
hits = sc.search(term, limit=per_term)   # / sc.search(text)
```

instead of `get_provider("game_data").search(term, limit=...)`.
`KalandraScraper.search()` (`core_engine/scraper.py:453`) and
`ScrapedGameData.search()` (`providers.py`) run the same `LIKE` query over
`knowledge_ledger` — this is a live duplicate of an already-registered
provider capability, and it's on the hot path for every AI voice/chat turn.

- **Route through:** `game_data`.
- **Risk:** low-medium. `ScrapedGameData.search()` returns `"topic: content"`
  strings; `scraper.search()` returns a trimmed snippet and (per the
  auditor's read) doesn't carry `source_url` through the same way. A
  behavior-preserving migration needs the provider's `search()` signature
  checked against both call sites' expectations before swapping, or a small
  extension (e.g. an optional `with_source=True` return shape).
- **Why it's #1:** highest call volume of any open item (every AI turn),
  and the fix is "call the seam that already exists" — no new interface
  needed.

### 2. `core_engine/craft_hunter.py:442` — `mod_suggestions()` raw sqlite on `localized_knowledge.db`

```python
con = sqlite3.connect(db_path)
con.execute("SELECT content_payload FROM knowledge_ledger WHERE ...")
```

Called from `gui_overlay/craft_hunter.py:_load_suggestions` (~771-786),
which builds `db_path` itself via `KalandraDBHandler._configured_db_dir()`
rather than going through the handler or `get_provider("game_data")`.
Note: `core_engine/craft_hunter.py` is otherwise exempt from the
OCR/clipboard sweep (it's the documented implementation of the "Tooltip
live-read" needs-seam row) — but this specific function is a *separate*,
unrelated raw-sqlite hit, not part of that exemption.

- **Route through:** `game_data`.
- **Risk:** low. Single `SELECT`, no writes, straightforward swap to
  `get_provider("game_data").search(...)` or a `KalandraDBHandler` cursor
  call with a `limit=400`-shaped query.

### 3. `core_engine/nerf_intel.py:185` and `:220` — raw sqlite on `localized_knowledge.db` and `economy_history`

```python
# patches_from_db(), line ~185
con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
con.execute("SELECT topic_tag, content_payload, source_url FROM knowledge_ledger WHERE ...")

# price_series_from_db(), line ~220
con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
con.execute("SELECT day, value FROM economy_history WHERE league=? AND lower(name)=lower(?) ...")
```

Never touches `KalandraDBHandler` or `get_provider(...)`. This is the exact
gap `docs/VISION_ACQUISITION.md`'s own pipeline matrix names: *"Patch intel
… (`nerf_intel`) → `GameData`"* — the team already declared the intended
seam and the code doesn't use it yet.

- **Route through:** `game_data` — but `GameDataProvider` currently only
  exposes generic `search(term, limit)`; patch-notes-by-date-range and
  economy-history-curve queries are shaped differently enough that this
  likely needs the interface extended (e.g. `patches(since=None)` /
  `price_series(league, name)`) rather than a bare call-site swap.
- **Risk:** low-medium. Read-only, two self-contained functions, but the
  interface extension needs a moment's thought so it doesn't turn into a
  grab-bag of unrelated methods on `GameDataProvider`.

### 4. `gui_overlay/dashboard.py` — three independent direct-OCR call sites

- `ExchangeTab._scan_holdings_screenshot` (~1694-1745):
  `import pytesseract; pytesseract.image_to_string(Image.open(path))`.
- `PriceCheckTab._scan_image` (~2121-2156): same direct `pytesseract` call.
- `ReserveTab._scan_snapshot` (~419-456): imports `available_ocr`/`make_ocr`
  from `core_engine.craft_hunter` and drives `cv2` + OCR directly for an
  unrelated feature (Reserve/BIS snapshot reading).

Three separate, hand-rolled OCR call sites in one file — a fourth copy of
OCR-engine-selection logic alongside `core_engine/craft_hunter.py`'s own
`available_ocr`/`make_ocr` (which is the documented implementation of the
"Tooltip live-read" needs-seam row).

- **Route through:** **needs new seam.** There is currently no OCR/vision
  provider capability — only `CaptureProvider` (recording, unrelated).
  Recommend a shared OCR entry point (extend `providers.py` with an
  `OcrProvider`/`TooltipReader`-style capability that
  `core_engine.craft_hunter`'s `available_ocr`/`make_ocr` becomes the
  default impl of), so all four call sites (these three plus craft_hunter's
  own P2 watcher) funnel through one adapter instead of four independent
  copies.
- **Risk:** low to consolidate mechanically (the OCR selection logic
  already exists and works); the win is de-duplication, not new capability.
  Slightly bigger than #1-#3 because it touches three call sites, not one.

### 5. `core_engine/item_art.py:53-66` — direct `requests.get` to `poe2db.tw`

```python
page = "https://poe2db.tw/us/" + key.strip().replace(" ", "_")
r = requests.get(page, headers=UA, timeout=timeout)
...
img_url = "https://poe2db.tw" + img_url
ir = requests.get(img_url, headers=UA, timeout=timeout)
```

Called from `gui_overlay/dashboard.py`'s `BuildTab._fill_container`
background art-fetch job (`from core_engine.item_art import get_art`). Not
on the seam-exemption list; raw HTTP straight to `poe2db.tw`, exactly the
rule-1 pattern.

- **Route through:** **needs new seam** — `GameDataProvider` only exposes
  text `search()`, not image/asset retrieval. Needs either a new capability
  (e.g. `item_art`/`asset`) or a `GameDataProvider.art(name)` extension.
- **Risk:** medium. Genuinely new interface surface, and `get_art()` has
  its own disk cache + lazy-fetch-on-background-thread behavior that a
  migration must preserve exactly (this is not just a call-site swap).

### 6. `gui_overlay/dashboard.py:1616-1647` — Exchange tab bypasses `get_provider("economy")`

```python
from core_engine.poe_ninja import PoENinja
self._ninja = PoENinja()
...
rows = self._ninja.get_currency(league) or []
...
self._ninja.store_history(wdb, league, rows)
ins = self._ninja.daily_insights(wdb, league, rows)
```

instead of `get_provider("economy").currency_rates(league)`.

- **Route through:** `economy`.
- **Risk:** medium. `EconomyProvider.currency_rates()` only returns a
  flattened `{name: chaos_value}` dict; the Exchange tab's movers/insights
  panel needs the richer per-row data (7-day average, deltas) plus
  `store_history`/`daily_insights` side effects. Needs `EconomyProvider`
  extended (e.g. `raw_rows(league)`, `record_history(league, rows)`,
  `daily_insights(league, rows)`) before the call site can swap cleanly —
  a bare swap to today's `currency_rates()` would regress the panel.

---

## Reviewed, not violations (architectural notes)

- **`gui_overlay/mirror_window.py` DB-Sync trigger** (`_init_backends`
  ~2591-2627, `trigger_database_scour_sync`/`_sync_worker` ~4072-4630)
  directly instantiates `KalandraScraper`, `WikiScraper`, `PoE2DataExtractor`,
  `PoENinja`. This is the "Sync & Scour" ingestion action (sapphire
  medallion) — the same role as `scripts/update_db.py`, just GUI-triggered.
  Providers model *read* access for feature code, not "run a full crawl,"
  so this isn't flagged as a violation — but it's the one place outside
  `scripts/*.py` that legitimately needs direct adapter access, worth
  knowing about if the seam ever tightens.
- **`gui_overlay/craft_hunter.py`** doing OCR/clipboard-adjacent work is the
  documented front-end of the Craft Hunter feature (calls
  `core_engine.craft_hunter`'s own OCR factories for its P2 tooltip
  watcher) — not an "other file" bypass.
- **`core_engine/grind_tracker.py`, `core_engine/price_ledger.py`** — both
  open their own private SQLite files (`data_engine/grind_tracker.db`,
  `data_engine/price_ledger.db`), never `localized_knowledge.db`. Legitimate
  self-owned local stores, not rule-3 violations.
- **`gui_overlay/grind_tab.py`** — its economy lookup already calls
  `get_provider("economy").currency_rates(league)` (~227-244). This is the
  one place in the audited surface that does it right; kept as the
  reference example.
- **`gui_overlay/owl_guide.py`, `core_engine/character_sheet.py`,
  `core_engine/build_seeker.py`, `main.py`** — clean; no direct third-party
  calls, no OCR/clipboard/Client.txt access, no raw sqlite on the shared DB.
- **`core_engine/death_review.py`** — `Client.txt` tailing and the OBS call
  are exactly its documented job (the "Player events" needs-seam row's
  current implementation, not a bypass of some other seam).

## Pipeline-matrix rows still `(needs seam)`

Per `docs/VISION_ACQUISITION.md`: **Tooltip live-read** (OCR — see
violation #4 above, which is the concrete call-site debt behind this row)
and **Player events** (`Client.txt` tail via `death_review`). A third row,
**Character list / identity**, was added to the matrix with candidate
interface `AccountData` (blocked on a GGG `client_id` for the official API
swap) — tracked there, not duplicated here since it has no known call-site
violation yet (single implementation, `poe_account.py`, not bypassed by
anything else).
