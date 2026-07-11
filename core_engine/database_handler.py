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
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_tag TEXT NOT NULL,
                content_payload TEXT NOT NULL,
                source_url TEXT NOT NULL,
                scraped_at TEXT NOT NULL,
                game_version_tag TEXT DEFAULT 'Patch 0.5.4',
                tags TEXT DEFAULT ''
            )
        """)
        # Migrate pre-existing databases that predate the `tags` column.
        try:
            cols = [r[1] for r in self.cursor.execute(
                "PRAGMA table_info(knowledge_ledger)").fetchall()]
            if "tags" not in cols:
                self.cursor.execute(
                    "ALTER TABLE knowledge_ledger ADD COLUMN tags TEXT DEFAULT ''")
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
                            tags=""):
        """
        Inserts newly parsed game data with an absolute, tr