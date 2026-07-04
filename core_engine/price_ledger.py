"""
CORE_ENGINE/PRICE_LEDGER.PY — every price check remembered (W4-12, local-first).

The seed of the community mod-value engine (docs/DESIGN_COMPANION.md P9): each
price check the player performs is parsed and logged locally — item, its
mods split into TEMPLATE + VALUES ("+120 to maximum Life" -> "+# to maximum
Life", [120.0]) — and, when a price is known, that price is attributed to
the mods. Over a league this yields naive but honest per-mod value
estimates that improve with every check.

LOCAL ALWAYS, uploaded NEVER (uploading is P9's opt-in community layer;
records carry a schema_version so they're upload-ready if consent arrives).

Thread-safe: a fresh SQLite connection per call (same pattern as the RAG
worker connections in mirror_window).

    from core_engine.price_ledger import PriceLedger
    led = PriceLedger()
    led.log_check(item_text, price=2.5, currency="divine", league="Standard")
    est = led.estimate_item(item_text, league="Standard")
    val = led.mod_value("+# to maximum Life", league="Standard")
"""

import os
import re
import sqlite3
import time

SCHEMA_VERSION = 1
DEFAULT_DB = os.path.join("data_engine", "price_ledger.db")

# Digits only (sign STAYS in the template so "+# Life" and "-# Life" stay
# distinct); letter-guard so item shorthand like "T15" isn't templated.
_NUM_TPL = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?")
_NUM_VAL = re.compile(r"(?<![A-Za-z\d])[-+]?\d+(?:\.\d+)?")


def mod_template(mod_text):
    """'+120 to maximum Life' -> ('+# to maximum Life', [120.0]).
    Numbers become '#'; the (signed) values come back separately."""
    s = str(mod_text or "").strip()
    if not s:
        return "", []
    vals = [float(m.group(0)) for m in _NUM_VAL.finditer(s)]
    tpl = _NUM_TPL.sub("#", s)
    tpl = re.sub(r"\s+", " ", tpl).strip()
    return tpl, vals


class PriceLedger:
    def __init__(self, db_path=DEFAULT_DB):
        self.db_path = db_path
        self._ensure_schema()

    # ------------------------------------------------ plumbing
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
                c.execute("""CREATE TABLE IF NOT EXISTS checks (
                    id INTEGER PRIMARY KEY,
                    ts TEXT NOT NULL,
                    league TEXT,
                    rarity TEXT, name TEXT, base TEXT, item_class TEXT,
                    ilvl INTEGER,
                    price REAL, currency TEXT,
                    source TEXT,
                    schema_version INTEGER NOT NULL)""")
                c.execute("""CREATE TABLE IF NOT EXISTS check_mods (
                    check_id INTEGER NOT NULL REFERENCES checks(id),
                    template TEXT NOT NULL,
                    v1 REAL, v2 REAL,
                    raw TEXT)""")
                c.execute("CREATE INDEX IF NOT EXISTS idx_mods_tpl "
                          "ON check_mods(template)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_checks_league "
                          "ON checks(league)")
        except Exception:
            pass

    # ------------------------------------------------ writing
    def log_check(self, item, price=None, currency=None, league=None,
                  source="price_check"):
        """`item` = raw clipboard text OR an already-parsed info dict.
        Returns the row id, or None on any failure (never raises)."""
        try:
            info = item if isinstance(item, dict) else self._parse(item)
            if not isinstance(info, dict) or not (info.get("name")
                                                  or info.get("base")):
                return None
            ilvl = None
            try:
                ilvl = int(str(info.get("ilvl", "")).strip() or 0) or None
            except Exception:
                pass
            with self._conn() as c:
                cur = c.execute(
                    "INSERT INTO checks (ts, league, rarity, name, base, "
                    "item_class, ilvl, price, currency, source, schema_version)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (time.strftime("%Y-%m-%d %H:%M:%S"), league,
                     info.get("rarity"), info.get("name"), info.get("base"),
                     info.get("item_class"), ilvl,
                     float(price) if price is not None else None,
                     currency, source, SCHEMA_VERSION))
                cid = cur.lastrowid
                for m in info.get("mods") or []:
                    tpl, vals = mod_template(m)
                    if not tpl:
                        continue
                    c.execute("INSERT INTO check_mods (check_id, template, "
                              "v1, v2, raw) VALUES (?,?,?,?,?)",
                              (cid, tpl,
                               vals[0] if len(vals) > 0 else None,
                               vals[1] if len(vals) > 1 else None,
                               str(m)[:300]))
            return cid
        except Exception:
            return None

    def _parse(self, text):
        try:
            from core_engine.trade_tools import parse_item_text
            return parse_item_text(text)
        except Exception:
            return {}

    # ------------------------------------------------ estimates
    def mod_value(self, template, league=None, min_samples=3):
        """Naive median of PRICED checks containing this mod template, in the
        checks' own currency mix reduced to a single number ONLY when the
        currency is uniform. Returns (median_price, currency, n) or None.
        Honest baseline — the P9 model replaces this, not the schema."""
        try:
            q = ("SELECT ch.price, ch.currency FROM checks ch "
                 "JOIN check_mods m ON m.check_id = ch.id "
                 "WHERE m.template = ? AND ch.price IS NOT NULL")
            args = [template]
            if league:
                q += " AND ch.league = ?"
                args.append(league)
            with self._conn() as c:
                rows = c.execute(q, args).fetchall()
            if len(rows) < min_samples:
                return None
            curs = {r[1] for r in rows}
            if len(curs) != 1:
                return None                      # mixed currencies: no lie
            prices = sorted(r[0] for r in rows)
            mid = prices[len(prices) // 2] if len(prices) % 2 else \
                (prices[len(prices) // 2 - 1] + prices[len(prices) // 2]) / 2
            return (mid, curs.pop(), len(rows))
        except Exception:
            return None

    def estimate_item(self, item, league=None):
        """Sum of known mod medians for the item's mods. Returns
        {'estimate': x, 'currency': c, 'known_mods': k, 'total_mods': t}
        or None if too little data. Clearly a floor-quality baseline."""
        try:
            info = item if isinstance(item, dict) else self._parse(item)
            mods = info.get("mods") or []
            total, cur, known = 0.0, None, 0
            for m in mods:
                tpl, _ = mod_template(m)
                mv = self.mod_value(tpl, league=league)
                if mv is None:
                    continue
                price, currency, _n = mv
                if cur is None:
                    cur = currency
                if currency != cur:
                    continue
                total += price
                known += 1
            if known == 0:
                return None
            return {"estimate": round(total, 2), "currency": cur,
                    "known_mods": known, "total_mods": len(mods)}
        except Exception:
            return None

    # ------------------------------------------------ stats / maintenance
    def stats(self):
        try:
            with self._conn() as c:
                checks = c.execute("SELECT COUNT(*) FROM checks").fetchone()[0]
                priced = c.execute("SELECT COUNT(*) FROM checks "
                                   "WHERE price IS NOT NULL").fetchone()[0]
                tpls = c.execute("SELECT COUNT(DISTINCT template) "
                                 "FROM check_mods").fetchone()[0]
            return {"checks": checks, "priced": priced, "mod_templates": tpls}
        except Exception:
            return {"checks": 0, "priced": 0, "mod_templates": 0}
