"""
CORE_ENGINE/DATABASE_HANDLER.PY
Purpose: Manages the local SQLite database. Handles storage of game information, 
timestamps entries to ensure post-patch verification, and builds clickable 
web citations for the user overlay interface.

Dependencies: sqlite3, datetime (Standard Python Libraries)
"""
import sqlite3
from datetime import datetime
import os

class KalandraDBHandler:
    def __init__(self, db_dir=None, db_name="localized_knowledge.db"):
        """
        Initializes the database handler and ensures local storage directory exists.

        The database folder is configurable: pass db_dir, else read "dir_database"
        from data_engine/config.json, else default to "data_engine" (back-compat
        with existing installs so nobody's database goes missing).
        """
        if db_dir is None:
            db_dir = self._configured_db_dir()
        self.db_path = os.path.join(db_dir, db_name)
        # Ensure the data folder exists
        os.makedirs(db_dir, exist_ok=True)
        
        # Connect to the SQLite local database file.
        # check_same_thread=False is a safety net; the app also gives each
        # background worker its OWN handler/connection (the correct pattern),
        # so a single connection is never actively shared across threads at once.
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        # WAL + a busy timeout keep the DB responsive under the concurrent crawler
        # (many quick writes serialized behind one lock, plus background reads).
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute("PRAGMA busy_timeout=10000")
        except Exception:
            pass
        self.initialize_schema()

    @staticmethod
    def _configured_db_dir():
        try:
            import json
            with open(os.path.join("data_engine", "config.json"), "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return cfg.get("dir_database") or "data_engine"
        except Exception:
            return "data_engine"

    def initialize_schema(self):
        """
        Builds the localized knowledge tables and patch change logs.
        Every entry tracks when it was scraped, its source link, and live patch tags.
        """
        # Table 1: Scoured Game Data with Time Stamps & Citations
        # `tags` holds poe2db's OWN game tags for the page (e.g. a skill's
        # "Attack, AoE, Projectile, Lightning" line). PoE tags decide which
        # modifiers apply, so we store the source's real tags — never a
        # keyword set of our own invention.
        # `kind` is the page kind the scraper classified from poe2db's own
        # markup ('skill_gem', 'support_gem', 'unique', 'mod', 'passive',
        # 'item', or '' when unknown) so the tag graph can group reverse-lookup
        # results without guessing.
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_tag TEXT NOT NULL,
                content_payload TEXT NOT NULL,
                source_url TEXT NOT NULL,
                scraped_at TEXT NOT NULL,
                game_version_tag TEXT DEFAULT 'Patch 0.5.4',
                tags TEXT DEFAULT '',
                kind TEXT DEFAULT ''
            )
        """)
        # Migrate pre-existing databases that predate the `tags`/`kind` columns.
        try:
            cols = [r[1] for r in self.cursor.execute(
                "PRAGMA table_info(knowledge_ledger)").fetchall()]
            if "tags" not in cols:
                self.cursor.execute(
                    "ALTER TABLE knowledge_ledger ADD COLUMN tags TEXT DEFAULT ''")
            if "kind" not in cols:
                self.cursor.execute(
                    "ALTER TABLE knowledge_ledger ADD COLUMN kind TEXT DEFAULT ''")
        except Exception:
            pass
        
        # Table 2: Stream Clips & Player Ideas Ledger (The Idea Vault)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS player_ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                idea_summary TEXT NOT NULL,
                logged_at TEXT NOT NULL,
                associated_build TEXT DEFAULT 'Generic'
            )
        """)
        self.conn.commit()
        # Full-text search index over the knowledge ledger. This is what makes
        # AI grounding fast AND relevant: instead of a LIKE '%term%' scan (which
        # reads every row and returns whatever matches first, unranked), FTS5
        # keeps an inverted index and ranks hits by bm25 relevance. Built into
        # SQLite, so no new dependency; degrades gracefully if this SQLite build
        # lacks FTS5 (self.fts_enabled stays False and callers fall back to LIKE).
        self._init_fts()

    # ---- Full-text (FTS5) search index --------------------------------------
    def _init_fts(self):
        """Create the FTS5 mirror of knowledge_ledger + keep-in-sync triggers,
        and backfill existing rows once. Sets self.fts_enabled."""
        self.fts_enabled = False
        # Bump when the FTS schema changes so old indexes are rebuilt, not reused.
        FTS_SCHEMA_VERSION = 2
        try:
            ver = self.cursor.execute("PRAGMA user_version").fetchone()[0]
            # If an older-shape index exists (e.g. the first 2-column version),
            # drop it so we can recreate it with the tags column included.
            if ver < FTS_SCHEMA_VERSION:
                self.cursor.execute("DROP TABLE IF EXISTS knowledge_fts")
                for trg in ("knowledge_ledger_ai", "knowledge_ledger_ad",
                            "knowledge_ledger_au"):
                    self.cursor.execute("DROP TRIGGER IF EXISTS %s" % trg)
                self.conn.commit()
            # external-content FTS5: the index stores only the terms; the text
            # still lives once in knowledge_ledger (no data duplication). We index
            # topic_tag, the page's real poe2db `tags`, and content_payload, so a
            # search can be matched and bm25-ranked on the game's own tags.
            self.cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
                    topic_tag,
                    tags,
                    content_payload,
                    content='knowledge_ledger',
                    content_rowid='id',
                    tokenize='porter unicode61'
                )
            """)
            # Triggers keep the index current as the crawler inserts/updates/deletes.
            self.cursor.executescript("""
                CREATE TRIGGER IF NOT EXISTS knowledge_ledger_ai
                AFTER INSERT ON knowledge_ledger BEGIN
                    INSERT INTO knowledge_fts(rowid, topic_tag, tags, content_payload)
                    VALUES (new.id, new.topic_tag, new.tags, new.content_payload);
                END;
                CREATE TRIGGER IF NOT EXISTS knowledge_ledger_ad
                AFTER DELETE ON knowledge_ledger BEGIN
                    INSERT INTO knowledge_fts(knowledge_fts, rowid, topic_tag, tags, content_payload)
                    VALUES ('delete', old.id, old.topic_tag, old.tags, old.content_payload);
                END;
                CREATE TRIGGER IF NOT EXISTS knowledge_ledger_au
                AFTER UPDATE ON knowledge_ledger BEGIN
                    INSERT INTO knowledge_fts(knowledge_fts, rowid, topic_tag, tags, content_payload)
                    VALUES ('delete', old.id, old.topic_tag, old.tags, old.content_payload);
                    INSERT INTO knowledge_fts(rowid, topic_tag, tags, content_payload)
                    VALUES (new.id, new.topic_tag, new.tags, new.content_payload);
                END;
            """)
            self.conn.commit()
            # Backfill the index from existing rows once per schema version
            # (covers both first-ever build and the 2->3 column upgrade).
            if ver < FTS_SCHEMA_VERSION:
                self.cursor.execute(
                    "INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild')")
                self.cursor.execute("PRAGMA user_version = %d" % FTS_SCHEMA_VERSION)
                self.conn.commit()
            self.fts_enabled = True
        except Exception:
            # FTS5 not compiled in, or index build failed — callers fall back to
            # the LIKE scan so search still works, just slower/unranked.
            try:
                self.conn.rollback()
            except Exception:
                pass
            self.fts_enabled = False

    def rebuild_fts(self):
        """Force a full reindex (e.g. after a bulk import). No-op if FTS is off."""
        if not getattr(self, "fts_enabled", False):
            return False
        try:
            self.cursor.execute(
                "INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild')")
            self.conn.commit()
            return True
        except Exception:
            return False

    def insert_scoured_data(self, topic, content, url, version="Patch 0.5.4",
                            tags="", kind=""):
        """
        Inserts newly parsed game data with an absolute, trackable timestamp.
        `tags` is poe2db's own tag line for the page (may be ""); `kind` is the
        scraper's page-kind classification (may be "" when unknown).
        """
        current_time = datetime.now().isoformat()
        self.cursor.execute("""
            INSERT INTO knowledge_ledger (topic_tag, content_payload, source_url, scraped_at, game_version_tag, tags, kind)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (topic, content, url, current_time, version, tags or "", kind or ""))
        self.conn.commit()
        return self.cursor.lastrowid

    def update_scoured_data(self, topic, content, url, version="Patch 0.5.4",
                            tags="", kind=""):
        """Refresh an existing ledger entry in place (same source_url). Used by
        the crawler's re-check passes: page content changes after patches, and
        without this a re-fetch was silently discarded."""
        current_time = datetime.now().isoformat()
        self.cursor.execute("""
            UPDATE knowledge_ledger
               SET topic_tag=?, content_payload=?, scraped_at=?, game_version_tag=?, tags=?, kind=?
             WHERE source_url=?
        """, (topic, content, current_time, version, tags or "", kind or "", url))
        self.conn.commit()
        return self.cursor.rowcount

    def log_stream_idea(self, idea_text, build_name="Theorycraft"):
        """
        Saves a player's stream notes or raw mechanical theories into the vault.
        """
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cursor.execute("""
            INSERT INTO player_ideas (idea_summary, logged_at, associated_build)
            VALUES (?, ?, ?)
        """, (idea_text, current_time, build_name))
        self.conn.commit()

    def get_clickable_citation(self, record_id):
        """
        Constructs an HTML-safe clickable anchor link based on the database index ID.
        """
        self.cursor.execute("SELECT source_url FROM knowledge_ledger WHERE id = ?", (record_id,))
        result = self.cursor.fetchone()
        if result and result[0]:
            return f'<a href="{result[0]}" style="color: #d4a373; font-weight: bold;">[Source Document #{record_id}]</a>'
        return "[Citation Link Unavailable]"

    def close(self):
        """Safely terminates the database connection."""
        self.conn.close()


def db_status(db_path):
    """Read-only, one-pass health summary of a knowledge DB — the data layer
    behind the DB status window (double-click the sync medallion).

    Always returns the complete shape, fail-soft on every field:
      {exists, size_bytes, pages, last_scraped,
       versions:  {game_version_tag: count},
       sources:   {domain: count},
       pending:   {queued, error, done}}
    Never creates or modifies any file (opens sqlite read-only)."""
    import os as _os, sqlite3 as _sql
    out = {"exists": False, "size_bytes": 0, "pages": 0, "last_scraped": None,
           "versions": {}, "sources": {},
           "pending": {"queued": 0, "error": 0, "done": 0}}
    if not db_path or not _os.path.exists(db_path):
        return out
    out["exists"] = True
    try:
        out["size_bytes"] = _os.path.getsize(db_path)
    except OSError:
        pass
    try:
        uri = "file:" + db_path.replace(_os.sep, "/") + "?mode=ro"
        con = _sql.connect(uri, uri=True)
    except Exception:
        return out
    try:
        cur = con.cursor()
        try:
            cur.execute("SELECT COUNT(*), MAX(scraped_at) FROM knowledge_ledger")
            row = cur.fetchone()
            out["pages"] = int(row[0] or 0)
            out["last_scraped"] = row[1]
        except Exception:
            pass
        try:
            cur.execute("SELECT game_version_tag, COUNT(*) FROM knowledge_ledger "
                        "GROUP BY game_version_tag")
            out["versions"] = {k: v for k, v in cur.fetchall() if k}
        except Exception:
            pass
        try:
            from urllib.parse import urlparse
            cur.execute("SELECT source_url FROM knowledge_ledger")
            for (u,) in cur.fetchall():
                try:
                    host = urlparse(u).netloc
                except Exception:
                    host = ""
                if host:
                    out["sources"][host] = out["sources"].get(host, 0) + 1
        except Exception:
            pass
        try:
            cur.execute("SELECT status, COUNT(*) FROM crawl_state GROUP BY status")
            for status, n in cur.fetchall():
                if status in out["pending"]:
                    out["pending"][status] = int(n)
        except Exception:
            pass
    finally:
        try:
            con.close()
        except Exception:
            pass
    return out

# Interactive Self-Test Block
if __name__ == "__main__":
    print("Testing Kalandra Database System...")
    db = KalandraDBHandler()
    
    # Test Inserting a Scoured Website Resource
    doc_id = db.insert_scoured_data(
        topic="Widowhail Scaling Interaction",
        content="Widowhail bow increases equipped quiver stats by up to 250%.",
        url="https://poe2db.tw/us/Widowhail"
    )
    print(f"Successfully created localized record #{doc_id}.")
    print(f"Generated Interactive Link: {db.get_clickable_citation(doc_id)}")
    
    # Test Logging an On-Stream Idea Note
    db.log_stream_idea("Saw a reverse-chill setup abusing physical hits from Scolds helmet.")
    print("Logged streaming note to personal Idea Vault successfully.")
    db.close()