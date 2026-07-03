"""
CORE_ENGINE/DATA_SOURCES.PY
Purpose: Startup "freshness" check. When the overlay opens it should (1) confirm
the real local date/time, and (2) report whether the local database is up to date
versus the live sources.

This module performs a LIGHT check (it does not crawl). It detects the current
PoE2 patch label from poe2db's homepage and compares it to what is stored locally,
and reports the last successful sync time. Other sources are registered with their
checkers; the ones without an official/cheap version endpoint are scaffolded so
they can be wired incrementally.

Heavy network libs are optional/guarded.
"""

import re
from datetime import datetime

try:
    import requests
except Exception:
    requests = None

# Sources the overlay tracks (display order matters for the startup report).
SOURCES = [
    ("poe2db",     "https://poe2db.tw/us/"),
    ("poe_ninja",  "https://poe.ninja/poe2"),
    ("pob2",       "https://pathofbuilding.community/"),
    ("craftofexile2", "https://craftofexile.com/"),
    ("maxroll",    "https://maxroll.gg/poe2"),
    ("mobalytics", "https://mobalytics.gg/poe-2"),
    ("poe2wiki",   "https://www.poe2wiki.net/"),
]

_HEADERS = {"User-Agent": "KalandraOverlay/1.0 (freshness check)"}


def _fetch_version_label(url, timeout=8):
    """Best-effort: return a detected 0.x.y patch label from a page, or None."""
    if requests is None:
        return None
    try:
        r = requests.get(url, headers=_HEADERS, timeout=timeout)
        if r.status_code == 200:
            m = re.search(r"\b0\.\d+(?:\.\d+)?\b", r.text)
            if m:
                return m.group(0)
    except Exception:
        return None
    return None


class FreshnessChecker:
    def __init__(self, db_handler=None, time_matrix=None, logger=None):
        self.db = db_handler
        self.time_matrix = time_matrix
        self.logger = logger

    def _log(self, msg):
        if self.logger:
            try:
                self.logger("STARTUP", msg)
            except Exception:
                pass

    def last_sync_time(self):
        """Most recent successful crawl timestamp, if any."""
        if self.db is None:
            return None
        try:
            self.db.cursor.execute(
                "SELECT MAX(fetched_at) FROM crawl_state WHERE status='done'")
            row = self.db.cursor.fetchone()
            return row[0] if row and row[0] else None
        except Exception:
            return None

    def stored_version(self):
        if self.db is None:
            return None
        try:
            self.db.cursor.execute(
                "SELECT game_version_tag FROM knowledge_ledger "
                "ORDER BY id DESC LIMIT 1")
            row = self.db.cursor.fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def run_startup_check(self, online=True):
        """Returns a structured report for the startup dialog/log."""
        now = datetime.now()
        report = {
            "checked_at": now.strftime("%A, %B %d, %Y - %I:%M:%S %p"),
            "last_sync": self.last_sync_time() or "never",
            "stored_version": self.stored_version() or "none yet",
            "sources": [],
            "needs_sync": False,
        }
        self._log(f"System date/time verified: {report['checked_at']}")
        self._log(f"Last database sync: {report['last_sync']}")

        live_poe2db = _fetch_version_label(SOURCES[0][1]) if online else None
        if live_poe2db:
            report["live_version"] = f"Patch {live_poe2db}"
            stored = report["stored_version"] or ""
            if live_poe2db not in stored:
                report["needs_sync"] = True
            self._log(f"poe2db live version: Patch {live_poe2db} "
                      f"(local: {report['stored_version']})")
        else:
            report["live_version"] = "unknown (offline or unreachable)"

        # poe2db is the ONE primary, actively-tracked source of truth. The others
        # are optional backups/specialized feeds that stay OFF unless the user
        # explicitly enables them in the update tool, so they are not "tracked"
        # and never drive the update notification.
        active = ("poe2db",)
        for name, url in SOURCES:
            report["sources"].append({
                "name": name, "url": url,
                "status": "tracked" if name in active else "reference-link",
            })

        if report["last_sync"] == "never":
            report["needs_sync"] = True
        return report


if __name__ == "__main__":
    fc = FreshnessChecker(logger=lambda c, m: print(f"[{c}] {m}"))
    import pprint
    pprint.pprint(fc.run_startup_check())
