"""
CORE_ENGINE/GRIND_TRACKER.PY — what does this loadout actually earn? (W4-11)

Snapshot what you're grinding with (e.g. 4 tablets + 10 waystones, WITH
their mods), record what each run returns, and over time the tracker can
say which mods correlate with income. Local-first: personal SQLite; the
community-pooled expected-value tables are P9 (records carry
schema_version so they're upload-ready under P9's opt-in).

Mods are stored templated via price_ledger.mod_template, so "23% increased
Quantity" and "31% increased Quantity" aggregate under one template while
keeping their values for the weighted stats that come with more data.

    from core_engine.grind_tracker import GrindTracker
    gt = GrindTracker()
    lid = gt.snapshot("juiced breach", [
        {"name": "Breach Tablet", "mods": ["23% increased Quantity"]},
        {"name": "Waystone T15", "mods": ["Area contains 2 Breaches"]},
    ], league="Standard")
    rid = gt.record_run(lid, income=[("divine", 0.4), ("chaos", 55)],
                        minutes=12.5)
    gt.loadout_stats(lid, rates={"divine": 180, "chaos": 1})
    gt.mod_returns(rates={"divine": 180, "chaos": 1})
"""

import os
import sqlite3
import time

from core_engine.price_ledger import mod_template

SCHEMA_VERSION = 1
DEFAULT_DB = os.path.join("data_engine", "grind_tracker.db")


class GrindTracker:
    def __init__(self, db_path=DEFAULT_DB):
        self.db_path = db_path
        self._ensure_schema()

    def _conn(self):
        d = os.path.dirname(self.db_path)
        if d:
            os.makedirs(d, exist_ok=True)
        c = sqlite3.connect(self.db_path, timeout=10)
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def _ensure_schema(self):
        try:
            with self._conn() as c:
                c.execute("""CREATE TABLE IF NOT EXISTS loadouts (
                    id INTEGER PRIMARY KEY, ts TEXT NOT NULL,
                    name TEXT NOT NULL, league TEXT,
                    schema_version INTEGER NOT NULL)""")
                c.execute("""CREATE TABLE IF NOT EXISTS loadout_items (
                    loadout_id INTEGER NOT NULL REFERENCES loadouts(id),
                    item_name TEXT, qty INTEGER DEFAULT 1)""")
                c.execute("""CREATE TABLE IF NOT EXISTS loadout_mods (
                    loadout_id INTEGER NOT NULL REFERENCES loadouts(id),
                    item_name TEXT, template TEXT NOT NULL,
                    v1 REAL, raw TEXT)""")
                c.execute("""CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY,
                    loadout_id INTEGER NOT NULL REFERENCES loadouts(id),
                    ts TEXT NOT NULL, minutes REAL)""")
                c.execute("""CREATE TABLE IF NOT EXISTS run_income (
                    run_id INTEGER NOT NULL REFERENCES runs(id),
                    currency TEXT NOT NULL, amount REAL NOT NULL)""")
                c.execute("CREATE INDEX IF NOT EXISTS idx_lm_tpl "
                          "ON loadout_mods(template)")
        except Exception:
            pass

    # ------------------------------------------------ recording
    def snapshot(self, name, items, league=None):
        """items = [{'name': str, 'qty': int, 'mods': [str,...]}, ...].
        Returns loadout id or None."""
        try:
            with self._conn() as c:
                cur = c.execute(
                    "INSERT INTO loadouts (ts, name, league, schema_version) "
                    "VALUES (?,?,?,?)",
                    (time.strftime("%Y-%m-%d %H:%M:%S"), str(name or "loadout"),
                     league, SCHEMA_VERSION))
                lid = cur.lastrowid
                for it in items or []:
                    iname = str((it or {}).get("name", "") or "item")[:120]
                    qty = int((it or {}).get("qty", 1) or 1)
                    c.execute("INSERT INTO loadout_items (loadout_id, "
                              "item_name, qty) VALUES (?,?,?)",
                              (lid, iname, qty))
                    for m in (it or {}).get("mods") or []:
                        tpl, vals = mod_template(m)
                        if not tpl:
                            continue
                        c.execute("INSERT INTO loadout_mods (loadout_id, "
                                  "item_name, template, v1, raw) "
                                  "VALUES (?,?,?,?,?)",
                                  (lid, iname, tpl,
                                   vals[0] if vals else None, str(m)[:300]))
            return lid
        except Exception:
            return None

    def record_run(self, loadout_id, income, minutes=None):
        """income = [(currency, amount), ...]. Returns run id or None."""
        try:
            with self._conn() as c:
                cur = c.execute(
                    "INSERT INTO runs (loadout_id, ts, minutes) VALUES (?,?,?)",
                    (int(loadout_id), time.strftime("%Y-%m-%d %H:%M:%S"),
                     float(minutes) if minutes is not None else None))
                rid = cur.lastrowid
                for currency, amount in income or []:
                    try:
                        c.execute("INSERT INTO run_income (run_id, currency, "
                                  "amount) VALUES (?,?,?)",
                                  (rid, str(currency), float(amount)))
                    except Exception:
                        continue
            return rid
        except Exception:
            return None

    # ------------------------------------------------ valuation helpers
    @staticmethod
    def _value(income_rows, rates):
        """[(currency, amount)] -> chaos-equivalent via rates dict
        ({currency: chaos_value}); unknown currencies count 0."""
        total = 0.0
        for currency, amount in income_rows:
            try:
                total += float(amount) * float((rates or {}).get(currency, 0))
            except Exception:
                continue
        return total

    # ------------------------------------------------ stats
    def loadout_stats(self, loadout_id, rates=None):
        """-> {'runs': n, 'total_chaos': x, 'per_run': y, 'per_hour': z|None}"""
        try:
            with self._conn() as c:
                runs = c.execute("SELECT id, minutes FROM runs WHERE "
                                 "loadout_id=?", (int(loadout_id),)).fetchall()
                if not runs:
                    return {"runs": 0, "total_chaos": 0.0,
                            "per_run": 0.0, "per_hour": None}
                total, mins = 0.0, 0.0
                timed = True
                for rid, m in runs:
                    inc = c.execute("SELECT currency, amount FROM run_income "
                                    "WHERE run_id=?", (rid,)).fetchall()
                    total += self._value(inc, rates)
                    if m is None:
                        timed = False
                    else:
                        mins += m
            n = len(runs)
            return {"runs": n, "total_chaos": round(total, 2),
                    "per_run": round(total / n, 2),
                    "per_hour": round(total / (mins / 60.0), 2)
                    if timed and mins > 0 else None}
        except Exception:
            return {"runs": 0, "total_chaos": 0.0, "per_run": 0.0,
                    "per_hour": None}

    def mod_returns(self, rates=None, league=None, min_runs=3):
        """Per mod template: average chaos-equivalent PER RUN across every
        loadout carrying that mod. -> [{'template','avg_per_run','runs'}...]
        sorted best-first. Correlation, not causation — labeled honestly and
        it firms up as the data grows (community pooling is P9)."""
        try:
            out = []
            with self._conn() as c:
                q = "SELECT DISTINCT template FROM loadout_mods"
                tpls = [r[0] for r in c.execute(q).fetchall()]
                for tpl in tpls:
                    lq = ("SELECT DISTINCT lm.loadout_id FROM loadout_mods lm")
                    args = []
                    if league:
                        lq += (" JOIN loadouts lo ON lo.id = lm.loadout_id "
                               "WHERE lm.template=? AND lo.league=?")
                        args = [tpl, league]
                    else:
                        lq += " WHERE lm.template=?"
                        args = [tpl]
                    lids = [r[0] for r in c.execute(lq, args).fetchall()]
                    total, nruns = 0.0, 0
                    for lid in lids:
                        for rid, in c.execute("SELECT id FROM runs WHERE "
                                              "loadout_id=?", (lid,)).fetchall():
                            inc = c.execute("SELECT currency, amount FROM "
                                            "run_income WHERE run_id=?",
                                            (rid,)).fetchall()
                            total += self._value(inc, rates)
                            nruns += 1
                    if nruns >= min_runs:
                        out.append({"template": tpl,
                                    "avg_per_run": round(total / nruns, 2),
                                    "runs": nruns})
            out.sort(key=lambda d: -d["avg_per_run"])
            return out
        except Exception:
            return []
