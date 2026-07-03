"""
CORE_ENGINE/POE_ACCOUNT.PY
Purpose: Pull YOUR Path of Exile 2 characters + the league list WITHOUT requiring
GGG OAuth / a registered developer application.

How this works (verified against GGG's API design):
  * Your characters do NOT live on poe.ninja. poe.ninja only serves public economy
    data and public ladder builds -- it has no login and no concept of "your
    account". Your character list is owned by GGG (pathofexile.com).
  * The official api.pathofexile.com/character endpoints require OAuth (scope
    account:characters) -- that needs the developer app we're deferring.
  * BUT the legacy endpoint below returns your characters with NO OAuth:
        https://api.pathofexile.com/character-window/get-characters
        ?accountName=<name>&realm=poe2
    - Works with just your account name IF your character tab is public.
    - For a private tab, supply your POESESSID cookie (a browser session token).
      Storing POESESSID is like storing a login session, so we keep it in the
      OS keychain via AccountManager.

  * Leagues are fetched from the public trade data endpoint (no auth):
        https://www.pathofexile.com/api/trade2/data/leagues

Everything is guarded so a missing 'requests' or a network error degrades to a
clear message instead of crashing the overlay.
"""

try:
    import requests
except Exception:
    requests = None

GET_CHARACTERS_URL = "https://api.pathofexile.com/character-window/get-characters"
TRADE2_LEAGUES_URL = "https://www.pathofexile.com/api/trade2/data/leagues"

# GGG asks for a descriptive User-Agent with contact info.
HEADERS = {"User-Agent": "KalandraOverlay/1.0 (personal theorycrafting tool)"}

# Minimal fallback if the live league list can't be fetched.
FALLBACK_LEAGUES = ["Standard", "Hardcore"]


class PoEAccount:
    def __init__(self, logger=None):
        self.logger = logger

    def _log(self, msg):
        if self.logger:
            try:
                self.logger("POB", msg)
            except Exception:
                pass

    @property
    def available(self):
        return requests is not None

    # -- leagues ---------------------------------------------------------------
    def get_leagues(self):
        """Return a list of current PoE2 league names (softcore first)."""
        if not self.available:
            return list(FALLBACK_LEAGUES)
        try:
            r = requests.get(TRADE2_LEAGUES_URL, headers=HEADERS, timeout=12)
            if r.status_code == 200:
                data = r.json()
                leagues = []
                for entry in data.get("result", []):
                    name = entry.get("id") or entry.get("text")
                    if name:
                        leagues.append(name)
                if leagues:
                    return leagues
        except Exception as e:
            self._log(f"Could not fetch leagues: {e}")
        return list(FALLBACK_LEAGUES)

    @staticmethod
    def default_softcore_league(leagues):
        """Pick the current temporary SOFTCORE league as the sensible default.

        Heuristic: the first league that is NOT permanent (Standard) and NOT a
        Hardcore/SSF/Ruthless variant. Falls back to 'Standard'.
        """
        for name in leagues:
            low = name.lower()
            if low in ("standard", "hardcore"):
                continue
            if any(k in low for k in ("hardcore", "hc", "ssf", "ruthless")):
                continue
            return name
        return "Standard"

    # -- characters ------------------------------------------------------------
    def get_characters(self, account_name, league=None, poesessid=None):
        """Fetch the account's characters.

        Returns a dict: {"ok": bool, "characters": [...], "error": str|None}
        Each character: {name, league, class, ascendancy, level}
        """
        if not self.available:
            return {"ok": False, "characters": [], "error": "requests not installed"}
        if not account_name:
            return {"ok": False, "characters": [], "error": "No account name set."}

        params = {"accountName": account_name, "realm": "poe2"}
        cookies = {"POESESSID": poesessid} if poesessid else None
        try:
            r = requests.get(GET_CHARACTERS_URL, params=params, headers=HEADERS,
                             cookies=cookies, timeout=15)
            if r.status_code == 403:
                return {"ok": False, "characters": [],
                        "error": ("Access denied (403). Your character tab is likely "
                                  "private -- set it public on pathofexile.com, or add "
                                  "your POESESSID in Settings.")}
            if r.status_code == 404:
                return {"ok": False, "characters": [],
                        "error": ("PoE2 characters aren't exposed by GGG's public API "
                                  "yet (the website doesn't show them either). Right now "
                                  "only ladder/top characters are available publicly. Your "
                                  "own roster will need GGG's official OAuth API once they "
                                  "release it. Try 'Browse ladder' for public builds.")}
            if r.status_code != 200:
                return {"ok": False, "characters": [],
                        "error": f"Unexpected status {r.status_code}."}

            raw = r.json()
            chars = []
            for c in raw:
                chars.append({
                    "name": c.get("name", "?"),
                    "league": c.get("league", "?"),
                    "class": c.get("class", c.get("classId", "?")),
                    "ascendancy": c.get("ascendancyClass", 0),
                    "level": c.get("level", 0),
                })
            if league:
                chars = [c for c in chars if c["league"] == league]
            self._log(f"Fetched {len(chars)} characters for {account_name}.")
            return {"ok": True, "characters": chars, "error": None}
        except Exception as e:
            return {"ok": False, "characters": [], "error": str(e)}

    # -- public ladder (top characters) ----------------------------------------
    def get_ladder(self, league, limit=15):
        """Best-effort fetch of a league's PUBLIC ladder (top characters).

        This is the only PoE2 character data that's public right now (it's how
        poe.ninja sources builds). Endpoints are still in flux, so this is
        defensive: any failure returns a clear message instead of crashing.
        """
        if not self.available:
            return {"ok": False, "characters": [], "error": "requests not installed"}
        limit = max(1, min(int(limit), 200))
        candidates = [
            ("https://www.pathofexile.com/api/ladders/" + league, {"realm": "poe2", "limit": limit, "offset": 0}),
            ("https://api.pathofexile.com/league/" + league + "/ladder", {"realm": "poe2", "limit": limit}),
        ]
        for url, params in candidates:
            try:
                r = requests.get(url, params=params, headers=HEADERS, timeout=15)
                if r.status_code != 200:
                    continue
                data = r.json()
                entries = data.get("entries") or data.get("ladder", {}).get("entries", [])
                chars = []
                for e in entries:
                    c = e.get("character", {})
                    chars.append({
                        "name": c.get("name", "?"),
                        "league": league,
                        "class": c.get("class", "?"),
                        "ascendancy": 0,
                        "level": c.get("level", 0),
                        "rank": e.get("rank"),
                        "account": (e.get("account") or {}).get("name", ""),
                    })
                if chars:
                    self._log(f"Fetched {len(chars)} ladder characters for {league}.")
                    return {"ok": True, "characters": chars, "error": None}
            except Exception:
                continue
        return {"ok": False, "characters": [],
                "error": "Public PoE2 ladder API isn't reachable yet (GGG hasn't shipped it)."}

    @staticmethod
    def pob_import_hint(account_name):
        """Path of Building imports directly by account name on its Import tab.

        We return the human steps; PoB itself performs the GGG fetch + tree build,
        which avoids us reimplementing PoB's full XML construction.
        """
        return ("In Path of Building 2: Import/Export tab -> 'Import character "
                f"from website' -> Account name: {account_name} -> select the "
                "character. (Set your characters public on pathofexile.com first, "
                "or paste your POESESSID in PoB.)")


if __name__ == "__main__":
    acc = PoEAccount(logger=lambda c, m: print(f"[{c}] {m}"))
    print("available:", acc.available)
    ls = acc.get_leagues()
    print("leagues:", ls)
    print("default SC:", acc.default_softcore_league(ls))
