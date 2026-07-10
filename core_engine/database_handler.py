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
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_tag TEXT NOT NULL,
                content_payload TEXT NOT NULL,
                source_url TEXT NOT NULL,
                scraped_at TEXT NOT NULL,
                game_version_tag TEXT DEFAULT 'Patch 0.5.4'
            )
        """)
        
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

    def insert_scoured_data(self, topic, content, url, version="Patch 0.5.4"):
        """
        Inserts newly parsed game data with an absolute, trackable timestamp.
        """
        current_time = datetime.now().isoformat()
        self.cursor.execute("""
            INSERT INTO knowledge_ledger (topic_tag, content_payload, source_url, scraped_at, game_version_tag)
            VALUES (?, ?, ?, ?, ?)
        """, (topic, content, url, current_time, version))
        self.conn.commit()
        return self.cursor.lastrowid

    def update_scoured_data(self, topic, content, url, version="Patch 0.5.4"):
        """Refresh an existing ledger entry in place (same source_url). Used by
        the crawler's re-check passes: page content changes after patches, and
        without this a re-fetch was silently discarded."""
        current_time = datetime.now().isoformat()
        self.cursor.execute("""
            UPDATE knowledge_ledger
               SET topic_tag=?, content_payload=?, scraped_at=?, game_version_tag=?
             WHERE source_url=?
        """, (topic, content, current_time, version, url))
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


def db_status(db_path=None):
    """Everything the DB status window shows, in one read-only pass.

    Returns a dict that is ALWAYS complete (zeros/None on any problem):
      path, exists, size_bytes, pages, last_scraped (ISO or None),
      versions {game_version_tag: pages}, sources {domain: pages},
      pending {queued, error, done}  (crawl_state, if present).
    Opens its own read-only connection — safe to call from the UI thread
    while a sync worker is writing (WAL)."""
    import sqlite3 as _sq
    if db_path is None:
        db_path = os.path.join(KalandraDBHandler._configured_db_dir(),
                               "localized_knowledge.db")
    out = {"path": db_path, "exists": os.path.exists(db_path),
           "size_bytes": 0, "pages": 0, "last_scraped": None,
           "versions": {}, "sources": {},
           "pending": {"queued": 0, "error": 0, "done": 0}}
    if not out["exists"]:
        return out
    try:
        out["size_bytes"] = os.path.getsize(db_path)
    except Exception:
        pass
    con = None
    try:
        con = _sq.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        cur = con.cursor()
        try:
            out["pages"] = cur.execute(
                "SELECT COUNT(*) FROM knowledge_ledger").fetchone()[0]
            out["last_scraped"] = cur.execute(
                "SELECT MAX(scraped_at) FROM knowledge_ledger").fetchone()[0]
            for tag, n in cur.execute(
                    "SELECT game_version_tag, COUNT(*) FROM knowledge_ledger "
                    "GROUP BY game_version_tag ORDER BY COUNT(*) DESC"):
                out["versions"][str(tag)] = n
            # domain histogram: substr math beats pulling every URL over
            for url, n in cur.execute(
                    "SELECT source_url, COUNT(*) FROM knowledge_ledger "
                    "GROUP BY source_url").fetchall()[:100000]:
                dom = str(url or "").split("//")[-1].split("/")[0] or "?"
                out["sources"][dom] = out["sources"].get(dom, 0) + n
        except Exception:
            pass
        try:
            for status, n in cur.execute(
                    "SELECT status, COUNT(*) FROM crawl_state "
                    "GROUP BY status"):
                key = str(status) if str(status) in out["pending"] else None
                if key:
                    out["pending"][key] = n
        except Exception:
            pass
    except Exception:
        pass
    finally:
        try:
            if con is not None:
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