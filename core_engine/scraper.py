"""
CORE_ENGINE/SCRAPER.PY
Purpose: REAL data acquisition for the Kalandra overlay.

The old "DB Sync" only wrote two hardcoded markdown files (a fake Sorceress
profile) and popped a success dialog -- nothing was ever scraped, which is why
you never found a real database.

This module is a polite, rate-limited, RESUMABLE crawler for poe2db.tw. It walks
the site's category pages, extracts the readable text + source URL of every page,
and stores it in the existing SQLite knowledge base (KalandraDBHandler), so the
local database genuinely grows toward a full mirror of PoE2 data + change logs.

Design notes / etiquette:
  * robots.txt for poe2db.tw is "Allow: /", but we still self-throttle
    (default 1 request every ~0.6s) so we don't hammer a community site.
  * requests-cache keeps repeat runs cheap and offline-friendly.
  * Visited URLs are tracked in a crawl_state table, so a run can be stopped
    and resumed without re-fetching everything.
  * A stop_flag (threading.Event) lets the UI cancel a long crawl.

Install:
    pip install requests requests-cache beautifulsoup4 lxml
"""

import re
import time
import threading
import concurrent.futures
from collections import deque
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, urldefrag

_ERR = []
try:
    import requests
except Exception as e:
    requests = None
    _ERR.append(f"requests ({e})")

try:
    import requests_cache
except Exception:
    requests_cache = None  # optional; we fall back to a plain session

try:
    from bs4 import BeautifulSoup
except Exception as e:
    BeautifulSoup = None
    _ERR.append(f"beautifulsoup4 ({e})")


SCRAPER_AVAILABLE = (requests is not None) and (BeautifulSoup is not None)

USER_AGENT = "KalandraOverlay/1.0 (personal theorycrafting tool; contact: local user)"

# Seed pages -- the main category indexes from poe2db.tw/us/.
DEFAULT_SEEDS = [
    "Items", "Unique_item", "Skill_Gems", "Support_Gems", "Spirit_Gems",
    "Modifiers", "Ascendancy_class", "Quest", "Atlas_Passive_Skill",
    "Waystone", "Crafting", "Keyword", "Monsters", "Gem", "Currency",
]


class KalandraScraper:
    def __init__(self, db_handler, base_url="https://poe2db.tw/us/",
                 rate_limit_seconds=0.6, logger=None, progress=None):
        self.db = db_handler
        self.base_url = base_url
        self.host = urlparse(base_url).netloc
        self.rate_limit = rate_limit_seconds
        self.logger = logger
        self.progress = progress  # callable(done:int, total_hint:int, url:str)

        self._ensure_crawl_table()
        # The cached session opens a (potentially multi-GB) sqlite cache file, so
        # build it LAZILY on first use instead of at construction — the scraper is
        # created at app startup and the live crawl uses per-thread plain sessions
        # anyway, so this keeps launch fast and light.
        self._session = None
        self._tl = threading.local()       # per-thread sessions for concurrent crawl
        self._db_lock = threading.Lock()   # serialize all DB access across workers

    @property
    def session(self):
        if self._session is None:
            self._session = self._build_session()
        return self._session

    def _thread_session(self):
        """A plain requests.Session unique to each worker thread (thread-safe)."""
        s = getattr(self._tl, "session", None)
        if s is None:
            s = requests.Session()
            s.headers.update({"User-Agent": USER_AGENT})
            self._tl.session = s
        return s

    # -- helpers ---------------------------------------------------------------
    def _log(self, category, message):
        if self.logger:
            try:
                self.logger(category, message)
            except Exception:
                pass

    def availability_message(self):
        if SCRAPER_AVAILABLE:
            return "Scraper ready."
        return ("Scraper needs extra libraries. Run:\n"
                "    pip install requests requests-cache beautifulsoup4 lxml\n\n"
                f"Missing: {', '.join(_ERR) or 'unknown'}")

    def _build_session(self):
        if not SCRAPER_AVAILABLE:
            return None
        if requests_cache is not None:
            sess = requests_cache.CachedSession(
                cache_name="data_engine/poe2db_cache",
                backend="sqlite",
                expire_after=60 * 60 * 24,  # 24h
            )
        else:
            sess = requests.Session()
        sess.headers.update({"User-Agent": USER_AGENT})
        return sess

    def _ensure_crawl_table(self):
        self.db.cursor.execute("""
            CREATE TABLE IF NOT EXISTS crawl_state (
                url TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                fetched_at TEXT
            )
        """)
        self.db.conn.commit()

    def _already_done(self, url):
        self.db.cursor.execute("SELECT 1 FROM crawl_state WHERE url=? AND status='done'", (url,))
        return self.db.cursor.fetchone() is not None

    def _enqueue(self, url):
        """Persist a discovered URL as 'queued' (keeps the frontier across runs)."""
        self.db.cursor.execute(
            "INSERT OR IGNORE INTO crawl_state (url, status, fetched_at) VALUES (?,?,?)",
            (url, "queued", datetime.now().isoformat()))

    def _mark(self, url, status):
        self.db.cursor.execute(
            "INSERT OR REPLACE INTO crawl_state (url, status, fetched_at) VALUES (?,?,?)",
            (url, status, datetime.now().isoformat()),
        )
        self.db.conn.commit()

    def pending_count(self):
        self.db.cursor.execute("SELECT COUNT(*) FROM crawl_state WHERE status='queued'")
        return self.db.cursor.fetchone()[0]

    def _load_frontier(self):
        self.db.cursor.execute("SELECT url FROM crawl_state WHERE status='queued'")
        return [r[0] for r in self.db.cursor.fetchall()]

    def _url_exists_in_ledger(self, url):
        self.db.cursor.execute("SELECT 1 FROM knowledge_ledger WHERE source_url=?", (url,))
        return self.db.cursor.fetchone() is not None

    # -- URL filtering ---------------------------------------------------------
    def _is_followable(self, url):
        try:
            p = urlparse(url)
        except Exception:
            return False
        if p.netloc and p.netloc != self.host:
            return False
        # Only crawl the localized /us/ section; skip assets & non-page resources.
        if "/us/" not in p.path:
            return False
        # Skip query-string variants (sort/filter/pagination) -- these are the
        # main source of frontier bloat and usually duplicate page content.
        if p.query:
            return False
        if re.search(r"\.(png|jpg|jpeg|gif|webp|css|js|svg|ico|json|woff2?|ttf)$", p.path, re.I):
            return False
        return True

    # -- page parsing ----------------------------------------------------------
    def _parse(self, html, url):
        soup = BeautifulSoup(html, "html.parser")

        title_el = soup.find("h1") or soup.find("title")
        title = title_el.get_text(strip=True) if title_el else url

        # Try to detect the patch/version label poe2db shows.
        version = "Unknown"
        vtext = soup.get_text(" ", strip=True)
        m = re.search(r"\b0\.\d+(?:\.\d+)?\b", vtext)
        if m:
            version = f"Patch {m.group(0)}"

        # Remove non-content tags before extracting text.
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True))
        text = text[:200000]  # keep individual rows sane

        links = []
        for a in soup.find_all("a", href=True):
            full = urldefrag(urljoin(url, a["href"]))[0].split("?")[0]
            if self._is_followable(full):
                links.append(full)

        tags = self._extract_tags(soup)
        return title, text, version, links, tags

    @staticmethod
    def _extract_tags(soup):
        """Read poe2db's OWN game tags for a skill/support gem straight from the
        source markup. On poe2db each tag is an ``<a class="GemTags ...">`` chip
        (Attack, AoE, Projectile, Lightning, Chaining, ...). PoE tags decide
        which modifiers apply (a skill tagged Physical + Damage-over-time but NOT
        Bleeding is not scaled by Bleed mods), so we take the page's real tags
        rather than inventing keywords.

        Verified against the live site: the tags are element text, NOT the
        angle-bracket "<Attack>" form some renderers show, and poe2db prints the
        chip row twice — so we de-duplicate. Non-gem pages (items, passives,
        monsters) carry no GemTags chips, so this returns "" and we never
        fabricate a tag."""
        try:
            chips = soup.find_all("a", class_="GemTags")
        except Exception:
            return ""
        return KalandraScraper._dedup_tags(
            c.get_text(strip=True) for c in chips)

    @staticmethod
    def _dedup_tags(items):
        seen, out = set(), []
        for t in items:
            t = (t or "").strip()
            k = t.lower()
            if t and k not in seen:
                seen.add(k)
                out.append(t)
        return ", ".join(out[:40])

    def _fetch_and_parse(self, url):
        """Worker task (runs in a thread pool): fetch + parse one page.

        Returns a dict; does NO database work (that's serialized in the caller).
        """
        try:
            sess = self._thread_session()
            resp = sess.get(url, timeout=20)
            if (resp.status_code != 200
                    or "text/html" not in resp.headers.get("Content-Type", "")):
                return {"url": url, "ok": False}
            title, text, version, links, tags = self._parse(resp.text, url)
            return {"url": url, "ok": True, "title": title, "text": text,
                    "version": version, "links": links, "tags": tags}
        except Exception as e:
            return {"url": url, "ok": False, "error": str(e)}

    # -- main crawl ------------------------------------------------------------
    def requeue_stale(self, days=7, cap=2000):
        """Roll the OLDEST previously-crawled pages back to 'queued' so their
        CONTENT gets re-checked (poe2db pages change after every patch). Without
        this, a page marked 'done' was never fetched again — a "sync" after full
        site coverage made zero HTTP requests. Capped per run so a sync stays
        quick; repeated syncs rotate through the whole site over time."""
        try:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            with self._db_lock:
                # 'skip' rows are included: they're usually transient fetch
                # failures (timeouts, hiccups) that deserve another try later.
                self.db.cursor.execute(
                    "SELECT url FROM crawl_state WHERE status IN ('done','skip') "
                    "AND fetched_at < ? ORDER BY fetched_at ASC LIMIT ?",
                    (cutoff, int(cap)))
                urls = [r[0] for r in self.db.cursor.fetchall()]
                for u in urls:
                    self._mark(u, "queued")
            if urls:
                self._log("DATABASE",
                          f"Content refresh: re-checking {len(urls)} pages last "
                          f"fetched over {days} days ago.")
            return len(urls)
        except Exception as e:
            self._log("DATABASE", f"Stale requeue skipped: {e}")
            return 0

    def crawl(self, max_pages=50000, seeds=None, stop_flag=None,
              concurrency=10, delay=0.0):
        """Concurrent, resumable crawl with a PERSISTENT frontier.

        Network fetches run in parallel across `concurrency` worker threads
        (the slow, I/O-bound part); all database writes are serialized under a
        lock so SQLite stays consistent. Discovered links are persisted as
        'queued', so stopping/resuming never loses progress.

        Returns a dict: {stored, processed, pending}.
        """
        if not SCRAPER_AVAILABLE:
            self._log("DATABASE", "Scraper unavailable: " + self.availability_message())
            return {"stored": 0, "processed": 0, "pending": 0}

        concurrency = max(1, int(concurrency))
        seeds = seeds or DEFAULT_SEEDS
        with self._db_lock:
            for s in seeds:
                self._enqueue(urljoin(self.base_url, s))
            self.db.conn.commit()
            frontier = self._load_frontier()

        if not frontier:
            # Everything ever discovered is 'done'. A sync must still CHECK the
            # site: re-queue the seed index pages so we actually hit poe2db,
            # refresh their content, and discover any newly-added pages.
            with self._db_lock:
                for s in seeds:
                    self._mark(urljoin(self.base_url, s), "queued")
            frontier = self._load_frontier()
            self._log("DATABASE",
                      f"Frontier empty — re-checking {len(frontier)} poe2db "
                      f"index pages for new/changed content.")

        queue = deque(frontier)
        seen = set(frontier)
        stored = 0
        updated = 0
        processed = 0
        start_ts = time.time()
        with self._db_lock:
            self.db.cursor.execute("SELECT COUNT(*) FROM crawl_state WHERE status='done'")
            baseline_done = self.db.cursor.fetchone()[0]

        self._log("DATABASE",
                  f"poe2db crawl: {len(queue)} pages in frontier "
                  f"({concurrency} parallel fetchers).")

        def _record(result):
            """Serialized DB work for one finished fetch. Returns stored?(bool)."""
            nonlocal stored, updated
            url = result["url"]
            with self._db_lock:
                if result.get("ok") and result.get("text"):
                    if not self._url_exists_in_ledger(url):
                        try:
                            self.db.insert_scoured_data(
                                topic=result["title"], content=result["text"],
                                url=url, version=result["version"],
                                tags=result.get("tags", ""))
                            stored += 1
                        except Exception as e:
                            # One bad row must not abort the whole crawl; leave
                            # the page queued so the next sync retries it.
                            self._log("DATABASE", f"Store failed for {url}: {e}")
                            self._mark(url, "queued")
                            return
                    else:
                        # Re-fetched page: refresh the stored content in place.
                        try:
                            if self.db.update_scoured_data(
                                    topic=result["title"], content=result["text"],
                                    url=url, version=result["version"],
                                    tags=result.get("tags", "")):
                                updated += 1
                        except Exception:
                            pass
                    for link in result.get("links", []):
                        if link not in seen:
                            seen.add(link)
                            queue.append(link)
                            self._enqueue(link)
                    self._mark(url, "done")
                else:
                    self._mark(url, "skip")

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            in_flight = {}
            while (queue or in_flight) and processed < max_pages:
                if stop_flag is not None and stop_flag.is_set():
                    self._log("DATABASE", "Crawl paused by user (progress saved).")
                    break

                # Top up the in-flight set.
                while (queue and len(in_flight) < concurrency
                       and (processed + len(in_flight)) < max_pages):
                    url = queue.popleft()
                    with self._db_lock:
                        if self._already_done(url):
                            continue
                    fut = pool.submit(self._fetch_and_parse, url)
                    in_flight[fut] = url
                    if delay:
                        time.sleep(delay)

                if not in_flight:
                    break

                done, _ = concurrent.futures.wait(
                    in_flight, timeout=30,
                    return_when=concurrent.futures.FIRST_COMPLETED)
                for fut in done:
                    in_flight.pop(fut, None)
                    try:
                        result = fut.result()
                    except Exception as e:
                        result = {"url": "?", "ok": False, "error": str(e)}
                    _record(result)
                    processed += 1
                    if self.progress:
                        try:
                            self.progress(processed, max_pages, result.get("url", ""))
                        except Exception:
                            pass
                    if processed % 50 == 0:
                        elapsed = max(0.001, time.time() - start_ts)
                        rate = processed / elapsed * 60.0          # pages/min
                        remaining = len(queue) + len(in_flight)
                        eta = (remaining / rate) if rate > 0 else 0
                        self._log("DATABASE",
                                  f"Done {baseline_done + processed} | "
                                  f"discovered+queued ~{remaining} | "
                                  f"{rate:.0f} pages/min | ETA ~{eta:.0f} min")

        elapsed = max(0.001, time.time() - start_ts)
        rate = processed / elapsed * 60.0
        pending = self.pending_count()
        self._log("DATABASE",
                  f"Crawl section done in {elapsed/60:.1f} min ({rate:.0f} pages/min). "
                  f"Stored {stored} new, refreshed {updated}; "
                  f"{pending} pages still pending site-wide.")
        return {"stored": stored, "updated": updated, "processed": processed,
                "pending": pending, "elapsed_min": round(elapsed / 60, 1),
                "rate_per_min": round(rate)}

    def stats(self):
        self.db.cursor.execute("SELECT COUNT(*) FROM knowledge_ledger")
        ledger = self.db.cursor.fetchone()[0]
        self.db.cursor.execute("SELECT COUNT(*) FROM crawl_state WHERE status='done'")
        done = self.db.cursor.fetchone()[0]
        return {"ledger_rows": ledger, "pages_done": done}

    # Boilerplate that appears on EVERY poe2db page (site nav + the language
    # selector). It used to dominate every RAG snippet (and the CJK in it could
    # crash logging on a non-UTF-8 console), so we strip it before returning.
    _BOILERPLATE_MARKERS = (
        "Update cookie preferences", "繁體中文", "简体中文", "한국어", "Japanese",
        "Русский", "Português", "ภาษาไทย", "Français", "Deutsch", "Spanish",
        "TW ", "CN ", "US English", "KR ", "JP ", "RU ", "PO ", "TH ", "FR ", "DE ", "ES ",
        "Patreon", "PoE\nDB", "PoE2\nDB",
    )

    @classmethod
    def _clean_content(cls, text):
        """Drop the repeated site-nav/language-menu lines and collapse the
        whitespace so what's left is the page's actual substance."""
        if not text:
            return ""
        lines = []
        for raw in text.splitlines():
            ln = raw.strip()
            if not ln:
                continue
            if any(m.strip() and m.strip() in ln for m in cls._BOILERPLATE_MARKERS):
                continue
            # Single-word nav crumbs (language codes, menu items) add no value.
            if len(ln) <= 2:
                continue
            lines.append(ln)
        return " ".join(lines)

    @classmethod
    def _snippet_around(cls, content, term, width=420):
        """Return a window of cleaned text centered on where `term` actually
        occurs, instead of the page's first 600 chars (which were always nav)."""
        cleaned = cls._clean_content(content)
        if not cleaned:
            return ""
        low = cleaned.lower()
        idx = low.find(term.lower()) if term else -1
        if idx < 0:
            return cleaned[:width]
        start = max(0, idx - width // 4)
        snippet = cleaned[start:start + width]
        return ("…" + snippet) if start > 0 else snippet

    def search(self, term, limit=6):
        """Keyword retrieval for grounding AI answers (RAG context). Returns a
        snippet centered on the match, with site boilerplate stripped, so the AI
        sees the relevant content rather than every page's identical menu.

        Uses the FTS5 index (bm25-ranked, so the MOST relevant page for the term
        comes first) when available, and falls back to a LIKE scan otherwise."""
        term = (term or "").strip()
        if not term:
            return []
        rows = self._search_rows(term, limit)
        out = []
        for row in rows:
            t, c, u = row[0], row[1], row[2]
            tags = row[3] if len(row) > 3 else ""
            snip = self._snippet_around(c, term)
            if not snip:
                continue
            # Surface poe2db's real tags inline so the AI grounds on the game's
            # actual tag set (e.g. sees that Corrupted Blood is Physical/DoT and
            # carries NO Bleed tag) instead of guessing tag relationships.
            tagpart = f" [tags: {tags}]" if tags else ""
            out.append(f"{t}{tagpart} ({u}): {snip}")
        return out

    @staticmethod
    def _fts_query(term):
        """Turn a raw term into a safe FTS5 MATCH query. We quote each word as a
        phrase token so punctuation/operators in the term can never be
        interpreted as FTS syntax (and can't inject). Multi-word terms like
        'Lightning Arrow' become a ranked AND of the two words."""
        import re as _re
        words = _re.findall(r"[A-Za-z0-9]+", term)
        if not words:
            return None
        return " AND ".join('"%s"' % w for w in words)

    def _search_rows(self, term, limit):
        """(topic_tag, content_payload, source_url) rows for `term`, ranked by
        relevance via FTS5 when the index is present; LIKE scan as a fallback."""
        if getattr(self.db, "fts_enabled", False):
            q = self._fts_query(term)
            if q:
                try:
                    # bm25 column weights (topic_tag, tags, content_payload): a
                    # hit on the page's title or its real tag set outranks a hit
                    # buried in body text, so the right page surfaces first.
                    self.db.cursor.execute(
                        "SELECT l.topic_tag, l.content_payload, l.source_url, l.tags "
                        "FROM knowledge_fts f "
                        "JOIN knowledge_ledger l ON l.id = f.rowid "
                        "WHERE knowledge_fts MATCH ? "
                        "ORDER BY bm25(knowledge_fts, 5.0, 4.0, 1.0) LIMIT ?",
                        (q, limit),
                    )
                    rows = self.db.cursor.fetchall()
                    if rows:
                        return rows
                except Exception:
                    pass  # fall through to LIKE
        like = f"%{term}%"
        self.db.cursor.execute(
            "SELECT topic_tag, content_payload, source_url, tags FROM knowledge_ledger "
            "WHERE content_payload LIKE ? OR topic_tag LIKE ? OR tags LIKE ? LIMIT ?",
            (like, like, like, limit),
        )
        return self.db.cursor.fetchall()


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core_engine.database_handler import KalandraDBHandler

    db = KalandraDBHandler()
    sc = KalandraScraper(db, logger=lambda c, m: print(f"[{c}] {m}"))
    if not SCRAPER_AVAILABLE:
        print(sc.availability_message())
    else:
        # Small demo crawl.
        sc.crawl(max_pages=15)
        print("STATS:", sc.stats())
    db.close()
