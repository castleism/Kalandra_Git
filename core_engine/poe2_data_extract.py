"""
CORE_ENGINE/POE2_DATA_EXTRACT.PY
Purpose: Pull game data straight from your Path of Exile 2 install — the same
source Craft of Exile and poe2db ultimately use. This is the cleanest, highest-
fidelity data (exact numbers, no scraping), but it requires decompressing GGG's
bundle format, which needs a native step.

HONEST STATUS:
  * Detecting the install and locating the data bundles: implemented here.
  * Importing ALREADY-EXTRACTED data (a folder of .json / .csv produced by a
    community extractor) into the knowledge base: implemented here.
  * Decompressing the raw bundles in-process: wired to `oodle_extractor.py`
    via `extract_in_process()` / `auto_update()`. Confirmed working against a
    real install (see that module's docstring) using the game's own oo2core
    DLL if present, or a compatible one from any other installed Steam game.
    When no install/DLL is found, this falls back to the external-converter
    route below unchanged — nothing about that path is removed.

RECOMMENDED EXTRACTOR (fallback when in-process extraction isn't ready,
e.g. no compatible oo2core DLL found on this machine — run once, then we
import the result):
  * SnowsMe / community "pathofexile-dat" tooling, or LibGGPK3 / Bundle tools.
  These produce per-table JSON (e.g. BaseItemTypes.json, SkillGems.json, Mods.json).
Place the exported JSON files in:  data_engine/game_data/
and run import_extracted_dir().
"""

import os
import glob
import json

try:
    from core_engine import dat_parser
    from core_engine.oodle_extractor import OodleExtractor
except Exception:
    import dat_parser  # when run directly from core_engine/
    from oodle_extractor import OodleExtractor

try:
    import requests
except Exception:
    requests = None

# Tables worth importing for build/craft Q&A. Extend freely.
DEFAULT_TABLES = [
    "BaseItemTypes", "Mods", "ModType", "Tags", "Stats",
    "SkillGems", "ActiveSkills", "GrantedEffects",
    "ItemClasses", "Essences", "Currency",
]
SCHEMA_PATH = os.path.join("data_engine", "schema.min.json")

# Common PoE2 install locations to probe (Windows).
INSTALL_CANDIDATES = [
    r"C:\Program Files (x86)\Grinding Gear Games\Path of Exile 2",
    r"C:\Program Files\Grinding Gear Games\Path of Exile 2",
    r"C:\Program Files (x86)\Steam\steamapps\common\Path of Exile 2",
    r"C:\Program Files\Steam\steamapps\common\Path of Exile 2",
    r"D:\Steam\steamapps\common\Path of Exile 2",
    r"D:\SteamLibrary\steamapps\common\Path of Exile 2",
]


class PoE2DataExtractor:
    def __init__(self, db_handler=None, logger=None):
        self.db = db_handler
        self.logger = logger

    def _log(self, msg):
        if self.logger:
            try:
                self.logger("DATABASE", msg)
            except Exception:
                pass

    def find_install(self):
        """Return the PoE2 install path if found, else None."""
        for p in INSTALL_CANDIDATES:
            if os.path.isdir(p):
                # Sanity: bundles live under Bundles2 or a Content.ggpk file exists.
                if (os.path.exists(os.path.join(p, "Content.ggpk"))
                        or os.path.isdir(os.path.join(p, "Bundles2"))):
                    return p
        return None

    def status(self):
        install = self.find_install()
        extracted = self.extracted_files()
        return {
            "install_found": bool(install),
            "install_path": install,
            "extracted_files": len(extracted),
            "extracted_dir": self.extracted_dir(),
            "note": ("Ready to import." if extracted else
                     "No extracted JSON yet. Run a community extractor and place "
                     "its JSON in data_engine/game_data/ (see module docstring)."),
        }

    @staticmethod
    def extracted_dir():
        return os.path.join("data_engine", "game_data")

    def extracted_files(self):
        return sorted(glob.glob(os.path.join(self.extracted_dir(), "*.json")))

    # ----------------------------------------------------------------------
    # In-process extraction (no external converter) — confirmed working
    # end-to-end against a real install; see oodle_extractor.py docstring.
    # ----------------------------------------------------------------------
    def in_process_status(self):
        """Can we self-extract .datc64 tables without an external converter?"""
        ex = OodleExtractor(logger=self.logger)
        return ex.status()

    def extract_in_process(self, tables=None, out_dir=None):
        """Pull .datc64 tables straight from the install via OodleExtractor,
        skipping the external-converter step entirely. Returns the same
        {"written": [...], "missing": [...]} shape as OodleExtractor.extract_tables,
        or {"written": [], "missing": tables, "reason": ...} if not ready
        (no install found, no oo2core DLL located, etc.)."""
        ex = OodleExtractor(logger=self.logger)
        st = ex.status()
        tables = tables or DEFAULT_TABLES
        if not st["ready"]:
            reason = ("no PoE2 install found" if not st["install"] else
                       "no Oodle DLL located" if not st["oo2core_dll"] else
                       "Bundles2/_.index.bin not found")
            self._log(f"In-process extraction skipped: {reason}.")
            return {"written": [], "missing": list(tables), "reason": reason}
        result = ex.extract_tables(tables, out_dir or self.datc64_dir())
        self._log(f"In-process extraction: wrote {len(result['written'])}, "
                  f"missing {len(result['missing'])}.")
        return result

    def import_extracted_dir(self):
        """Import already-extracted per-table JSON into the knowledge base.

        Each JSON is expected to be a list of row dicts (the usual extractor
        output). We store a compact summary row per table plus per-entry rows
        when an obvious name field exists.
        """
        if self.db is None:
            self._log("No database handler; cannot import.")
            return 0
        files = self.extracted_files()
        if not files:
            self._log("No extracted JSON found in " + self.extracted_dir())
            return 0
        stored = 0
        for path in files:
            table = os.path.splitext(os.path.basename(path))[0]
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                self._log(f"Skip {table}: {e}")
                continue
            rows = data if isinstance(data, list) else data.get("rows", [])
            for row in rows:
                if not isinstance(row, dict):
                    continue
                name = (row.get("Name") or row.get("name") or row.get("Id")
                        or row.get("id"))
                if not name:
                    continue
                content = json.dumps(row, ensure_ascii=False)[:8000]
                self.db.insert_scoured_data(
                    topic=f"[{table}] {name}",
                    content=content,
                    url=f"gamefile://{table}",
                    version="game-data")
                stored += 1
            self._log(f"Imported {table}: {len(rows)} rows.")
        self._log(f"Game-data import complete: {stored} entries.")
        return stored


    # ----------------------------------------------------------------------
    # Schema-driven .datc64 import (the real, high-fidelity path)
    # ----------------------------------------------------------------------
    def ensure_schema(self, path=SCHEMA_PATH):
        """Download the poe-tool-dev schema.min.json if we don't have it."""
        if os.path.exists(path):
            return path
        if requests is None:
            self._log("Can't fetch schema (requests missing). Download manually:")
            self._log("  " + dat_parser.SCHEMA_URL)
            return None
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            r = requests.get(dat_parser.SCHEMA_URL, timeout=30)
            if r.status_code == 200:
                with open(path, "wb") as f:
                    f.write(r.content)
                self._log("Downloaded dat schema.")
                return path
        except Exception as e:
            self._log(f"Schema download failed: {e}")
        return None

    @staticmethod
    def datc64_dir():
        return os.path.join("data_engine", "game_data")

    def _find_datc64(self, folder, table):
        """Find a table's .datc64 file (case-insensitive, with/without data/)."""
        for cand in (table, table.lower()):
            for sub in ("", "data"):
                p = os.path.join(folder, sub, cand + ".datc64")
                if os.path.exists(p):
                    return p
        # last resort: glob
        hits = glob.glob(os.path.join(folder, "**", table + ".datc64"), recursive=True)
        hits += glob.glob(os.path.join(folder, "**", table.lower() + ".datc64"), recursive=True)
        return hits[0] if hits else None

    @staticmethod
    def _row_name(row):
        for k in ("Name", "Id", "name", "id"):
            if row.get(k):
                return str(row[k])
        # else first string-ish value
        for v in row.values():
            if isinstance(v, str) and v:
                return v
        return None

    def import_datc64_dir(self, folder=None, tables=None, schema_path=SCHEMA_PATH):
        """Parse extracted .datc64 tables and import them with RESOLVED
        relationships so the Obsidian export shows real interactions (a mod links
        to the tags/stats it touches, items link to their tags, etc.).

        Returns number of entries stored.
        """
        if self.db is None:
            self._log("No database handler; cannot import.")
            return 0
        folder = folder or self.datc64_dir()
        tables = tables or DEFAULT_TABLES
        sp = self.ensure_schema(schema_path)
        if not sp:
            self._log("No schema available; cannot parse .datc64.")
            return 0
        schema = dat_parser.load_schema(sp)

        # Pass 1: parse each available table; build a name index per table so we
        # can resolve foreign-row references to readable [[topic]] links.
        parsed = {}     # table -> list[row dict]
        cols_by = {}    # table -> columns
        name_index = {} # table -> {rowindex: "[Table] Name"}
        for table in tables:
            path = self._find_datc64(folder, table)
            if not path:
                continue
            columns = dat_parser.get_table_columns(schema, table)
            if not columns:
                self._log(f"No schema for table {table}; skipping.")
                continue
            try:
                with open(path, "rb") as f:
                    rows = dat_parser.parse(f.read(), columns)
            except Exception as e:
                self._log(f"Parse failed for {table}: {e}")
                continue
            parsed[table] = rows
            cols_by[table] = columns
            idx = {}
            for i, row in enumerate(rows):
                nm = self._row_name(row)
                if nm:
                    idx[i] = f"[{table}] {nm}"
            name_index[table] = idx
            self._log(f"Parsed {table}: {len(rows)} rows.")

        # Pass 2: store each row, resolving references to other entries' exact
        # topics. The Obsidian exporter cross-links by those topic strings, so the
        # graph shows item<->tag<->mod interactions.
        stored = 0
        for table, rows in parsed.items():
            columns = cols_by[table]
            for i, row in enumerate(rows):
                nm = self._row_name(row)
                if not nm:
                    continue
                topic = f"[{table}] {nm}"
                related = []
                lines = []
                for col in columns:
                    cval = row.get(col["name"])
                    ref_table = col.get("references")
                    if ref_table and ref_table in name_index:
                        targets = cval if isinstance(cval, list) else [cval]
                        for t in targets:
                            if isinstance(t, int) and t in name_index[ref_table]:
                                related.append(name_index[ref_table][t])
                    elif cval not in (None, "", [], False):
                        lines.append(f"{col['name']}: {cval}")
                content = f"{topic}\n\n" + "\n".join(lines[:60])
                if related:
                    # Mention related entries by EXACT topic so the vault links them.
                    content += "\n\nInteractions / related: " + ", ".join(sorted(set(related))[:60])
                self.db.insert_scoured_data(
                    topic=topic, content=content[:8000],
                    url=f"gamefile://{table}", version="game-data")
                stored += 1
            self._log(f"Imported {table}: {len(rows)} entries.")
        self._log(f"Game-data .datc64 import complete: {stored} entries "
                  f"(open the Obsidian vault to see the interaction graph).")
        if stored:
            self._write_state(stored)
        return stored

    # ----------------------------------------------------------------------
    # Version awareness + boot automation (reference, don't duplicate)
    # ----------------------------------------------------------------------
    # We DON'T copy raw game files. We keep a pointer to the install + a version
    # token, parse only the tables we need into SQLite, and re-import when the
    # game (or the extracted files) change.
    STATE_PATH = os.path.join("data_engine", "game_data_state.json")

    def index_path(self):
        """The bundle index (its mtime is our 'game version' proxy)."""
        install = self.find_install()
        if not install:
            return None
        for rel in (os.path.join("Bundles2", "_.index.bin"), "Content.ggpk"):
            p = os.path.join(install, rel)
            if os.path.exists(p):
                return p
        return None

    def game_version_token(self):
        """A cheap token that changes when the game is patched."""
        ip = self.index_path()
        if ip:
            try:
                return f"{int(os.path.getmtime(ip))}-{os.path.getsize(ip)}"
            except Exception:
                return None
        return None

    def _read_state(self):
        try:
            with open(self.STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write_state(self, rows):
        try:
            os.makedirs(os.path.dirname(self.STATE_PATH), exist_ok=True)
            src_token = None
            files = (glob.glob(os.path.join(self.datc64_dir(), "**", "*.datc64"), recursive=True)
                     + self.extracted_files())
            if files:
                src_token = str(int(max(os.path.getmtime(f) for f in files)))
            with open(self.STATE_PATH, "w", encoding="utf-8") as f:
                json.dump({"game_version": self.game_version_token(),
                           "data_token": src_token, "rows": rows}, f)
        except Exception:
            pass

    def scan(self):
        """Estimate what's available to sync (for the Settings panel)."""
        datc = glob.glob(os.path.join(self.datc64_dir(), "**", "*.datc64"), recursive=True)
        js = self.extracted_files()
        total = 0
        for f in datc + js:
            try:
                total += os.path.getsize(f)
            except Exception:
                pass
        recognized = [t for t in DEFAULT_TABLES if self._find_datc64(self.datc64_dir(), t)]
        st = self._read_state()
        gv = self.game_version_token()
        data_token = None
        if datc + js:
            try:
                data_token = str(int(max(os.path.getmtime(f) for f in (datc + js))))
            except Exception:
                pass
        needs_import = bool((datc or js) and data_token != st.get("data_token"))
        return {
            "install_found": bool(self.find_install()),
            "install_path": self.find_install(),
            "game_version": gv,
            "game_changed": bool(gv and gv != st.get("game_version")),
            "extracted_files": len(datc) + len(js),
            "extracted_mb": round(total / (1024 * 1024), 1),
            "recognized_tables": recognized,
            "last_imported_rows": st.get("rows", 0),
            "needs_import": needs_import,
            "in_process": self.in_process_status(),
        }

    def auto_update(self, force=False):
        """Run on boot: import extracted data if it's new (or game changed).

        If no .datc64/JSON has been dropped in yet but in-process extraction
        is ready (real install + oo2core DLL located), self-extract the
        default tables first — no external converter needed."""
        s = self.scan()
        if s["extracted_files"] == 0:
            if s["in_process"]["ready"]:
                self.extract_in_process()
                s = self.scan()
            if s["extracted_files"] == 0:
                return {"status": "no-data", "scan": s}
        if not (force or s["needs_import"] or s["game_changed"]):
            return {"status": "up-to-date", "scan": s}
        n = self.import_datc64_dir()
        try:
            n += self.import_extracted_dir()
        except Exception:
            pass
        return {"status": "imported", "rows": n, "scan": self.scan()}


if __name__ == "__main__":
    ex = PoE2DataExtractor(logger=lambda c, m: print(f"[{c}] {m}"))
    import pprint
    pprint.pprint(ex.status())
