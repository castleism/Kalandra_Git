# Game-File Data Extraction — Setup

This builds the **high-fidelity** part of the database: exact item/mod/gem/stat
data pulled from your Path of Exile 2 install (the same source Craft of Exile and
poe2db ultimately use). It powers the crafting simulator and makes everything
precise — and because game tables carry real foreign-key relationships, the
Obsidian vault ends up with accurate links (a mod links to the tags/stats it
touches, items link to their tags, etc.).

## The pipeline (and what's tested)

```
 .ggpk / Bundles2  --(Oodle decompress)-->  *.datc64  --(our parser)-->  rows
        ^ external converter                    ^ schema           --> SQLite DB
                                                                    --> Obsidian vault
```

- The **parser** (`core_engine/dat_parser.py`) and the **import + relationship +
  Obsidian linking** are written and unit-tested in this project.
- The **Oodle decompression** (turning the game's bundles into raw `.datc64`) is
  done by a proven external tool, because Oodle has no pure-Python decoder and it
  uses the game's own `oo2core` DLL. This is exactly how CoE/poe2db get their data
  too — they extract offline, then parse.

## In-process extraction (no external tool, when it's ready on your machine)

`core_engine/oodle_extractor.py` can decompress the game's own bundles
directly — no external converter, nothing installed beyond what PoE2 already
ships — using the game's own `oo2core_*.dll` via `ctypes`. This is confirmed
working end-to-end on a real install (index parse, path recovery, bundle
decompression, byte-exact table extraction all verified). One wrinkle seen in
practice: PoE2 doesn't always ship its own `oo2core_*.dll` at the install
root, so the extractor also scans sibling Steam games for a compatible one
(Oodle DLLs are widely reused across titles).

`PoE2DataExtractor.auto_update()` (in `core_engine/poe2_data_extract.py`)
tries this path automatically before falling back to "wait for externally
extracted files" — call `extract_in_process()` directly, or check
`in_process_status()` / `PoE2DataExtractor.scan()["in_process"]` to see
whether it's ready on this machine (install found + a compatible DLL
located). When it isn't ready, use the external-converter route below —
nothing about that path changes.

## Steps (external-converter route — the fallback)

1. **Extract the raw tables** with a community converter (run once per patch):
   - [poe2-datconverter](https://github.com/adainrivers/poe2-datconverter) — PoE2 DATC64 converter, or
   - [LibGGPK3 / ExtractBundledGGPK3](https://github.com/aianlinb/LibGGPK3).
   Point it at your PoE2 install and export the `data/*.datc64` tables.

2. **Drop the `.datc64` files** into:
   ```
   data_engine/game_data/        (or data_engine/game_data/data/)
   ```

3. **Import**: in the overlay, Settings → **Import game data**. It will:
   - download the column schema (`schema.min.json` from poe-tool-dev/dat-schema),
   - parse the tables it recognizes (BaseItemTypes, Mods, Tags, Stats, SkillGems, …),
   - store them with resolved relationships,
   - and rebuild the Obsidian vault so you can browse the interaction graph.

4. **Browse**: open `data_engine/vault` in Obsidian → Graph view.

## Notes

- The schema auto-downloads; if you're offline, grab it manually:
  https://github.com/poe-tool-dev/dat-schema/releases/download/latest/schema.min.json
  and place it at `data_engine/schema.min.json`.
- The fully self-contained extractor (Oodle via the game's own DLL through
  Python `ctypes`, no external tool) is done — see "In-process extraction"
  above. The converter route above stays as the fallback for machines where
  it isn't ready (no install detected, or no compatible oo2core DLL found).
- The extracted data is GGG's intellectual property — keep it local; don't
  redistribute it.
