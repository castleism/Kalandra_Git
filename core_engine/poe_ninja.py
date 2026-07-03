"""
CORE_ENGINE/POE_NINJA.PY
Purpose: Pull PUBLIC economy data from poe.ninja's open JSON API (no login, no
key). This is the only thing poe.ninja actually exposes programmatically --
currency/item pricing and public ladder build aggregates. It does NOT and cannot
return your personal characters (that's the GGG side -- see poe_account.py).

PoE2 economy endpoint (separate from PoE1's /api/data/...):
    https://poe.ninja/poe2/api/economy/currencyexchange/overview
        ?leagueName=<League>&overviewName=Currency
Response: {"lines":[{"id","primaryValue","volumePrimaryValue"}],
           "items":[{"id","name","icon"}]}  -- join lines->items by id for names.

Valid PoE2 leagues include: "Standard", "Dawn of the Hunt", "Rise of the Abyssal"
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
POE2_BASE = "https://poe.ninja/poe2/api/economy"
CURRENCY_URL = POE2_BASE + "/currencyexchange/overview"
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
                                 params={"leagueName": league, "overviewName": "Currency"},
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
                      f"Try a current league name (e.g. 'Standard', 'Rise of the Abyssal').")
        return stored


if __name__ == "__main__":
    pn = PoENinja(logger=lambda c, m: print(f"[{c}] {m}"))
    print("available:", pn.available)
