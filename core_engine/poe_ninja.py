"""
CORE_ENGINE/POE_NINJA.PY
Purpose: Pull PUBLIC economy data from poe.ninja's open JSON API (no login, no
key). This is the only thing poe.ninja actually exposes programmatically --
currency/item pricing and public ladder build aggregates. It does NOT and cannot
return your personal characters (that's the GGG side -- see poe_account.py).

PoE2 economy endpoint (separate from PoE1's /api/data/...):
    https://poe.ninja/poe2/api/economy/exchange/current/overview
        ?league=<League>&type=Currency
Response: {"lines":[{"id","primaryValue","volumePrimaryValue"}],
           "items":[{"id","name","icon"}]}  -- join lines->items by id for names.

Valid PoE2 leagues include: "Standard", "Hardcore", "Runes of Aldur"
(challenge leagues change; use the exact name shown on poe.ninja/poe2/economy).

Polite use: we cache via requests-cache if available and pass a descriptive UA.
"""

try:
    import requests
except Exception:
    requests = None

try:
    import requests_cache
except Exception:
    requests_cache = None

# PoE2 economy API (undocumented but public; powers poe.ninja/poe2/economy).
# 2026-07-10: poe.ninja rewrote its frontend (Astro) and moved this off
# /currencyexchange/overview?leagueName=&overviewName= (now a Cloudflare-
# cached 404) to /exchange/current/overview?league=&type= — confirmed via
# the live page's own network calls. Response shape (top-level "items"/
# "lines") is unchanged, so only the URL + param names moved.
POE2_BASE = "https://poe.ninja/poe2/api/economy"
CURRENCY_URL = POE2_BASE + "/exchange/current/overview"
ITEM_URL = POE2_BASE + "/item/overview"
HEADERS = {"User-Agent": "KalandraOverlay/1.0 (personal theorycrafting tool)"}

# Overviews to try for items (names vary; we attempt and skip what 404s).
ITEM_OVERVIEWS = ["UniqueWeapon", "UniqueArmour", "UniqueAccessory", "UniqueJewel"]


class PoENinja:
    def __init__(self, logger=None):
        self.logger = logger
        if requests is None:
            self.session = None
        elif requests_cache is not None:
            self.session = requests_cache.CachedSession(
                cache_name="data_engine/poeninja_cache", backend="sqlite",
                expire_after=60 * 30)  # 30 min -- prices move
            self.session.headers.update(HEADERS)
        else:
            self.session = requests.Session()
            self.session.headers.update(HEADERS)

    def _log(self, msg):
        if self.logger:
            try:
                self.logger("DATABASE", msg)
            except Exception:
                pass

    @property
    def available(self):
        return self.session is not None

    def get_currency(self, league):
        """Return [{name, value, volume}] for PoE2 currency in `league`."""
        if not self.available:
            return []
        try:
            r = self.session.get(CURRENCY_URL,
                                 params={"league": league, "type": "Currency"},
                                 timeout=15)
            if r.status_code != 200:
                self._log(f"poe.ninja currency HTTP {r.status_code} for league '{league}' "
                          f"(check the league name on poe.ninja/poe2/economy).")
                return []
            data = r.json()
            names = {it.get("id"): it.get("name") for it in data.get("items", [])}
            out = []
            for ln in data.get("lines", []):
                cid = ln.get("id")
                out.append({"name": names.get(cid, cid),
                            "value": ln.get("primaryValue"),
                            "volume": ln.get("volumePrimaryValue")})
            return out
        except Exception as e:
            self._log(f"poe.ninja currency fetch failed: {e}")
        return []

    def store_economy(self, db_handler, league):
        """Snapshot PoE2 economy data into the knowledge base for offline/AI use."""
        if not self.available or db_handler is None:
            return 0
        rows = self.get_currency(league)
        stored = 0
        for r in rows:
            name, val = r.get("name"), r.get("value")
            if name and val is not None:
                db_handler.insert_scoured_data(
                    topic=f"[Economy] {name}",
                    content=(f"{name}: relative value {val} (league {league}); "
                             f"trade volume {r.get('volume')}."),
                    url=f"https://poe.ninja/poe2/economy/{league}",
                    version=f"poe.ninja {league}")
                stored += 1
        if stored:
            self._log(f"Stored {stored} PoE2 economy rows from poe.ninja ({league}).")
        else:
            self._log(f"poe.ninja returned no economy rows for league '{league}'. "
                      f"Try a current league name (e.g. 'Standard', 'Runes of Aldur').")
        return stored


    # -- W3-26: price history + daily movers ---------------------------------
    def store_history(self, db_handler, league, rows=None):
        """Append today's currency values to economy_history (one row per
        currency per day — re-running the same day updates in place)."""
        if db_handler is None:
            return 0
        from datetime import date
        rows = rows if rows is not None else self.get_currency(league)
        if not rows:
            return 0
        cur = db_handler.cursor
        cur.execute("""CREATE TABLE IF NOT EXISTS economy_history(
            day TEXT NOT NULL, league TEXT NOT NULL, name TEXT NOT NULL,
            value REAL, volume REAL,
            PRIMARY KEY (day, league, name))""")
        today = date.today().isoformat()
        n = 0
        for r in rows:
            name, val = r.get("name"), r.get("value")
            if not name or val is None:
                continue
            try:
                cur.execute(
                    "INSERT OR REPLACE INTO economy_history VALUES (?,?,?,?,?)",
                    (today, league, str(name), float(val),
                     float(r.get("volume") or 0)))
                n += 1
            except Exception:
                continue
        db_handler.conn.commit()
        return n

    def daily_insights(self, db_handler, league, rows=None, days=7, top=6):
        """Compare today's values to the trailing average -> movers + advice.

        Returns {'movers': [(name, value, avg, delta_pct)...high&low mixed],
                 'advice': [str, ...], 'history_days': int}. Pure SQL + math;
        advisory only, clearly heuristic."""
        out = {"movers": [], "advice": [], "history_days": 0}
        if db_handler is None:
            return out
        try:
            cur = db_handler.cursor
            cur.execute("SELECT COUNT(DISTINCT day) FROM economy_history "
                        "WHERE league=?", (league,))
            out["history_days"] = int(cur.fetchone()[0])
            if out["history_days"] < 2:
                out["advice"].append(
                    "Collecting history — refresh once a day; movers appear "
                    "after two days of snapshots.")
                return out
            cur.execute("""
                SELECT h.name, h.value, avg(p.value) AS avg_v
                FROM economy_history h
                JOIN economy_history p
                  ON p.name = h.name AND p.league = h.league
                 AND p.day < h.day
                 AND p.day >= date(h.day, ?)
                WHERE h.league = ? AND h.day = (
                    SELECT MAX(day) FROM economy_history WHERE league = ?)
                GROUP BY h.name
                HAVING avg_v > 0
            """, (f"-{int(days)} day", league, league))
            deltas = []
            for name, value, avg_v in cur.fetchall():
                delta = (value - avg_v) / avg_v * 100.0
                deltas.append((name, value, avg_v, delta))
            deltas.sort(key=lambda t: abs(t[3]), reverse=True)
            out["movers"] = [d for d in deltas if abs(d[3]) >= 3.0][:top]

            for name, value, avg_v, delta in out["movers"]:
                if delta > 0:
                    out["advice"].append(
                        f"{name} is {delta:+.0f}% vs its {days}-day average — "
                        f"a SELL window if you're sitting on a stack.")
                else:
                    out["advice"].append(
                        f"{name} is {delta:+.0f}% vs its {days}-day average — "
                        f"cheap right now; a BUY window if your build needs it.")
            if not out["movers"]:
                out["advice"].append(
                    f"No currency moved more than 3% vs its {days}-day average "
                    "— a quiet market; hold.")
            out["advice"].append(
                "Heuristic signals from public poe.ninja data — not financial "
                "advice for your exalts; you place every trade yourself.")
        except Exception as e:
            self._log(f"daily_insights failed: {e}")
        return out


if __name__ == "__main__":
    pn = PoENinja(logger=lambda c, m: print(f"[{c}] {m}"))
    print("available:", pn.available)
