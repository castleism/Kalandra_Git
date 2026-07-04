"""
CORE_ENGINE/WIKI_SCRAPER.PY
Purpose: Build out the local knowledge base from poe2wiki.net using its official
MediaWiki API (the site runs MediaWiki 1.40). Content is licensed CC BY-NC 3.0,
so for this personal, non-commercial tool we store it WITH attribution and a
source link, and we self-throttle to be polite.

Approach (works on any MediaWiki):
  1. action=query&list=allpages  -> enumerate article titles (with continuation)
  2. action=parse&page=<title>&prop=text -> page HTML -> plain text
  3. store into the shared knowledge_ledger via KalandraDBHandler, resumable via
     the crawl_state table.

Install:
    pip install requests beautifulsoup4
"""

import time
import random
import threading
import concurrent.futures
from datetime import datetime

try:
    import requests
except Exception:
    requests = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

WIKI_SCRAPER_AVAILABLE = (requests is not None) and (BeautifulSoup is not None)

# A realistic browser User-Agent reduces Cloudflare challenges on the wiki.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
}
ATTRIBUTION = ("Source: poe2wiki.net (Content under CC BY-NC 3.0). ")


class WikiScraper:
    def __init__(self, db_handler, base="https://www.poe2wiki.net",
                 rate_limit_seconds=0.7, logger=None, progress=None):
        self.db = db_handler
        self.base = base.rstrip("/")
        self.rate_limit = rate_limit_seconds
        self.logger = logger
        self.progress = progress
        self.api_url = None
        self._fail_count = 0
        self._throttled = False
        self._cooldown_until = 0.0   # shared: when Cloudflare throttles, ALL workers pause
        self._consec_fail = 0        # consecutive failures -> circuit breaker
        self._tl = threading.local()
        self._db_lock = threading.Lock()
        self._ensure_table()

    def _session(self):
        s = getattr(self._tl, "s", None)
        if s is None:
            s = requests.Session()
            s.headers.update(HEADERS)
            self._tl.s = s
        return s

    def _log(self, msg):
        if self.logger:
            try:
                self.logger("DATABASE", msg)
            except Exception:
                pass

    def availability_message(self):
        if WIKI_SCRAPER_AVAILABLE:
            return "Wiki scraper ready."
        return "Wiki scraper needs: pip install requests beautifulsoup4"

    def _ensure_table(self):
        self.db.cursor.execute("""
            CREATE TABLE IF NOT EXISTS crawl_state (
                url TEXT PRIMARY KEY, status TEXT NOT NULL, fetched_at TEXT)
        """)
        self.db.conn.commit()

    def _mark(self, url, status):
        self.db.cursor.execute(
            "INSERT OR REPLACE INTO crawl_state (url, status, fetched_at) VALUES (?,?,?)",
            (url, status, datetime.now().isoformat()))
        self.db.conn.commit()

    def _done(self, url):
        self.db.cursor.execute("SELECT 1 FROM crawl_state WHERE url=? AND status='done'", (url,))
        return self.db.cursor.fetchone() is not None

    def _detect_api(self):
        if not WIKI_SCRAPER_AVAILABLE:
            return None
        sess = self._session()
        # Retry across both API paths a few times — the detection probe itself can
        # hit a transient Cloudflare challenge (a non-JSON body).
        for attempt in range(3):
            for path in ("/w/api.php", "/api.php"):
                url = self.base + path
                try:
                    r = sess.get(url, params={"action": "query", "meta": "siteinfo",
                                              "format": "json"}, timeout=15)
                    if r.status_code == 200 and "json" in r.headers.get("Content-Type", "") \
                            and "query" in r.json():
                        self.api_url = url
                        return url
                except Exception:
                    pass
            time.sleep(2.0 * (attempt + 1) + random.uniform(0, 1.0))
        return None

    def list_all_pages(self, hard_cap=5000):
        titles = []
        apcontinue = None
        while len(titles) < hard_cap:
            params = {"action": "query", "list": "allpages", "aplimit": "200",
                      "apnamespace": "0", "format": "json"}
            if apcontinue:
                params["apcontinue"] = apcontinue
            try:
                r = requests.get(self.api_url, params=params, headers=HEADERS, timeout=15)
                data = r.json()
            except Exception as e:
                self._log(f"allpages failed: {e}")
                break
            for p in data.get("query", {}).get("allpages", []):
                titles.append(p["title"])
            # Heartbeat so the user can see enumeration is alive, not frozen.
            if len(titles) % 1000 < 200:
                self._log(f"  ...enumerated {len(titles)} wiki page titles so far")
            cont = data.get("continue", {})
            apcontinue = cont.get("apcontinue")
            if not apcontinue:
                break
            time.sleep(self.rate_limit)
        self._log(f"Enumeration complete: {len(titles)} page titles.")
        return titles

    def _html_to_text(self, html):
        soup = BeautifulSoup(html, "html.parser")
        # Prefer the main content area if present.
        main = soup.find(id="mw-content-text") or soup.find(id="bodyContent") or soup
        for tag in main(["script", "style", "noscript"]):
            tag.decompose()
        return main.get_text("\n", strip=True)[:200000]

    def fetch_page_text(self, title):
        """Get a page's text. Tries the MediaWiki API (JSON) first; if the API
        returns a non-JSON body (Cloudflare/rate-limit) or fails, falls back to
        fetching the rendered page HTML directly. Retries once with backoff."""
        params = {"action": "parse", "page": title, "prop": "text",
                  "redirects": "1",  # resolve redirect pages to their target
                  "formatversion": "2", "format": "json"}
        sess = self._session()
        # If another worker just got throttled, wait out the shared cooldown
        # instead of hammering Cloudflare (which extends the block).
        wait = self._cooldown_until - time.time()
        if wait > 0:
            time.sleep(min(wait, 90))
        # Up to 3 API attempts with exponential backoff; back off HARD on an
        # explicit rate-limit/blocked status (429/503/403) so the site recovers.
        for attempt in range(3):
            try:
                r = sess.get(self.api_url, params=params, timeout=20)
                ctype = r.headers.get("Content-Type", "")
                if r.status_code == 200 and "json" in ctype:
                    html = r.json().get("parse", {}).get("text", "")
                    return self._html_to_text(html) if html else ""
                if r.status_code in (429, 503, 403):
                    self._throttled = True
                    self._cooldown_until = max(self._cooldown_until,
                                               time.time() + 30.0 * (attempt + 1))
                    time.sleep(3.0 * (attempt + 1) + random.uniform(0, 1.5))
                else:
                    time.sleep(1.0 * (attempt + 1) + random.uniform(0, 0.5))
            except Exception:
                time.sleep(1.0 * (attempt + 1))

        # Fallback: the rendered article page HTML directly (one retry).
        for attempt in range(2):
            try:
                r = sess.get(self.page_url(title), timeout=20)
                if r.status_code == 200 and r.text:
                    return self._html_to_text(r.text)
                if r.status_code in (429, 503, 403):
                    self._throttled = True
                    self._cooldown_until = max(self._cooldown_until,
                                               time.time() + 30.0 * (attempt + 1))
                    time.sleep(3.0 * (attempt + 1))
            except Exception:
                time.sleep(1.0)
        self._fail_count += 1
        return ""

    def page_url(self, title):
        return f"{self.base}/wiki/{title.replace(' ', '_')}"

    def crawl(self, max_pages=2000, stop_flag=None, concurrency=3):
        """Concurrent MediaWiki crawl. poe2wiki sits behind Cloudflare and
        rate-limits aggressively, so concurrency defaults LOW (3) with per-request
        exponential backoff. Pages that still fail are marked for retry on the
        next run, so re-running steadily fills the gaps."""
        if not WIKI_SCRAPER_AVAILABLE:
            self._log("Wiki scraper unavailable: " + self.availability_message())
            return 0
        self._log("Detecting poe2wiki MediaWiki API endpoint (a few seconds)...")
        if not self._detect_api():
            self._log("Could not locate the poe2wiki MediaWiki API endpoint "
                      "(site may be down or blocking). It'll be retried next sync.")
            return 0
        self._log(f"API ready: {self.api_url}")

        concurrency = max(1, int(concurrency))
        self._log("Enumerating poe2wiki pages via MediaWiki API (this is the quiet "
                  "step that can take a minute)...")
        titles = self.list_all_pages(hard_cap=max_pages * 3)
        # Skip pages already stored in a previous run (resumable).
        todo = []
        for t in titles:
            if len(todo) >= max_pages:
                break
            if not self._done(self.page_url(t)):
                todo.append(t)
        self._log(f"Found {len(titles)} wiki pages; fetching {len(todo)} new "
                  f"with {concurrency} parallel fetchers.")

        stored = 0
        processed = 0

        def _store(title, text):
            nonlocal stored
            url = self.page_url(title)
            with self._db_lock:
                if text:
                    self._consec_fail = 0
                    try:
                        self.db.insert_scoured_data(
                            topic=title, content=ATTRIBUTION + url + "\n\n" + text,
                            url=url, version="poe2wiki")
                        stored += 1
                        self._mark(url, "done")
                    except Exception as e:
                        # A single DB hiccup must not abort the whole sync.
                        self._log(f"DB write failed for {title}: {e} (will retry next sync)")
                        self._mark(url, "error")
                else:
                    # Don't bury it as 'done' -- leave it 'error' so the NEXT sync
                    # retries it (most failures are transient throttling).
                    self._consec_fail += 1
                    self._mark(url, "error")

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {}
            it = iter(todo)
            # Prime the pool.
            for _ in range(concurrency):
                try:
                    t = next(it)
                except StopIteration:
                    break
                futures[pool.submit(self.fetch_page_text, t)] = t
            while futures:
                if stop_flag is not None and stop_flag.is_set():
                    self._log("Wiki crawl paused (progress saved).")
                    break
                if self._consec_fail >= 30:
                    # Circuit breaker: Cloudflare is blocking EVERY request.
                    # Without this, the rest of the run burns ~20s per page
                    # marking thousands of pages 'error' — which looked like
                    # the sync "stopping partway". Stop cleanly instead;
                    # 'error' pages are retried on the next sync.
                    self._log("poe2wiki is blocking all requests right now "
                              "(30 consecutive failures). Stopping this source "
                              "for this run — progress is saved and the failed "
                              "pages will be retried next sync. Tip: wait 10-15 "
                              "minutes before re-syncing so the block expires.")
                    break
                done, _ = concurrent.futures.wait(
                    futures, timeout=30,
                    return_when=concurrent.futures.FIRST_COMPLETED)
                for fut in done:
                    title = futures.pop(fut)
                    try:
                        text = fut.result()
                    except Exception:
                        text = ""
                    _store(title, text)
                    processed += 1
                    if self.progress:
                        try:
                            self.progress(processed, len(todo), self.page_url(title))
                        except Exception:
                            pass
                    if processed % 50 == 0:
                        ok_pct = int(100 * stored / processed) if processed else 0
                        extra = "  (site throttling — backing off)" if self._throttled else ""
                        self._log(f"Wiki: {processed}/{len(todo)} fetched, "
                                  f"stored {stored} ({ok_pct}% ok), "
                                  f"{self._fail_count} to retry{extra}")
                        self._throttled = False  # reset the window flag
                    # Refill.
                    if not (stop_flag is not None and stop_flag.is_set()):
                        try:
                            t = next(it)
                            futures[pool.submit(self.fetch_page_text, t)] = t
                        except StopIteration:
                            pass

        self._log(f"poe2wiki crawl finished. Stored {stored} pages this run "
                  f"({self._fail_count} unreadable — will be retried on the next sync).")
        return stored


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core_engine.database_handler import KalandraDBHandler
    db = KalandraDBHandler()
    ws = WikiScraper(db, logger=lambda c, m: print(f"[{c}] {m}"))
    print(ws.availability_message())
    db.close()
