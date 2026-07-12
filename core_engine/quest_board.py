"""
CORE_ENGINE/QUEST_BOARD.PY
Community Quest Board — P1, the local board (docs/COMMUNITY_QUEST_BOARD_SPEC.md).

Turns knowledge-base gaps into visible QUESTS the player completes using the
tool itself: tag an untagged unique, investigate a new interaction, confirm a
player-reported claim. The defining rule is enforced STRUCTURALLY:

    open → claimed → submitted → verified → closed   (+ reopened)

  * `closed` is unreachable except from `verified` — a quest can never be
    closed on an unconfirmed submission.
  * `verified` is reached only by independent agreement (>= threshold DISTINCT
    contributors whose proposals match) or a trusted maintainer's sign-off.
  * Closing a gap-generated quest additionally requires the gap to actually be
    gone (the entity now has scraped tags or verified community tags) — a
    quest cannot silently close while the data is still missing.
  * `recheck_gaps` re-opens closed quests whose gap detector fires again
    (a later scrape/patch reverted the data).

Verified tag/relationship resolutions are written into the community tag
layer (core_engine/community_tags.py) pre-verified — the early slice of the
spec's P2 wiring — so the Scaling Advisor benefits immediately.

Local-first (ship-safe JSON overlay, knowledge_corrections pattern); a
shared/synced board is a later phase with moderation. ToS: quests are about
METADATA (tags, interactions, item data) — never actions in the game client.
"""

import json
import os
import threading
import time

_DEFAULT_NAME = "community_quests.json"

QUEST_TYPES = ("tag", "investigate", "verify", "relationship")
STATUSES = ("open", "claimed", "submitted", "verified", "closed", "reopened")
# Statuses a submission/claim may act on (everything still "live").
_LIVE = ("open", "claimed", "submitted", "reopened")


def _default_path():
    base = "data_engine"
    try:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg = os.path.join(here, "data_engine", "config.json")
        if os.path.exists(cfg):
            with open(cfg, "r", encoding="utf-8") as f:
                base = json.load(f).get("dir_database", "data_engine") or "data_engine"
        if not os.path.isabs(base):
            base = os.path.join(here, base)
    except Exception:
        pass
    return os.path.join(base, _DEFAULT_NAME)


def _norm(s):
    return (s or "").strip().lower()


def _norm_proposal(p):
    """Canonicalize a proposal so independent submissions can be compared:
    'Physical, DoT' == 'physical,dot' == 'DoT ,  Physical'."""
    parts = sorted(t for t in (_norm(x) for x in (p or "").split(",")) if t)
    return ",".join(parts)


class QuestBoard:
    def __init__(self, path=None, verify_threshold=2, maintainers=None,
                 claim_ttl_hours=48, community=None):
        """`maintainers` is the trusted sign-off list (config). `community` is
        an optional CommunityTags instance for verified write-back."""
        self.path = path or _default_path()
        self.verify_threshold = max(1, int(verify_threshold))
        self.maintainers = [m for m in (maintainers or []) if m]
        self.claim_ttl = float(claim_ttl_hours) * 3600.0
        self.community = community
        self._lock = threading.Lock()
        self._items = []
        self._seq = 0
        self._load()

    # -- storage (ship-safe JSON overlay) ---------------------------------------
    def _load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self._items = data
                    return
        except Exception:
            pass
        self._items = []

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._items, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except Exception:
            pass

    def _get(self, qid):
        for q in self._items:
            if q.get("id") == qid:
                return q
        return None

    # -- creating quests ----------------------------------------------------------
    def post(self, qtype, subject, title="", criteria="", source="maintainer",
             subject_url=""):
        """Post a quest. Re-posting a live quest for the same type+subject
        returns the existing one (no duplicates on the board)."""
        qtype = _norm(qtype)
        subject = (subject or "").strip()
        if qtype not in QUEST_TYPES or not subject:
            return None
        with self._lock:
            for q in self._items:
                if (q.get("type") == qtype and _norm(q.get("subject")) == _norm(subject)
                        and q.get("status") in _LIVE):
                    return q
            self._seq += 1
            q = {
                "id": "qst_%d_%d" % (int(time.time() * 1000), self._seq),
                "type": qtype,
                "subject": subject,
                "subject_url": subject_url or "",
                "title": title or self._default_title(qtype, subject),
                "criteria": criteria or self._default_criteria(qtype, subject),
                "status": "open",
                "source": source if source in ("auto", "maintainer") else "maintainer",
                "created_at": time.strftime("%Y-%m-%d %H:%M"),
                "claims": [],          # {player, at(epoch)}
                "submissions": [],     # {player, evidence, proposal, at}
                "verifications": [],   # {how, by, at}
                "resolution": "",
                "contributor_credits": [],
            }
            self._items.append(q)
            self._save()
            return q

    @staticmethod
    def _default_title(qtype, subject):
        return {
            "tag": f"Tag {subject}",
            "investigate": f"Investigate {subject}",
            "verify": f"Verify: {subject}",
            "relationship": f"Confirm relationship: {subject}",
        }.get(qtype, subject)

    @staticmethod
    def _default_criteria(qtype, subject):
        return {
            "tag": (f"Supply {subject}'s REAL poe2db game tags (comma-separated). "
                    "Done when independently confirmed or maintainer-verified."),
            "investigate": (f"Document what {subject} is and what it interacts "
                            "with; propose tags/relationships with a source link."),
            "verify": (f"Independently confirm or refute: {subject}. "
                       "Attach evidence (poe2db/wiki/PoB link, screenshot, note)."),
            "relationship": (f"Confirm {subject} in play or via a source; "
                             "propose as 'applies: <target>' or "
                             "'affected_by: <target>'."),
        }.get(qtype, "")

    def generate_from_db(self, db_handler, cap=50):
        """Auto-generate TagQuests from untagged knowledge_ledger rows (the
        board fills itself). Existing live quests aren't duplicated; CLOSED
        quests whose gap is back get reopened instead of re-created."""
        new = []
        try:
            cur = db_handler.cursor
            cur.execute(
                "SELECT topic_tag, source_url FROM knowledge_ledger "
                "WHERE tags IS NULL OR tags='' ORDER BY id DESC LIMIT ?",
                (int(cap) * 4,))
            rows = cur.fetchall()
        except Exception:
            rows = []
        reopened = self.recheck_gaps(db_handler)
        for topic, url in rows:
            if len(new) >= cap:
                break
            topic = (topic or "").strip()
            if not topic:
                continue
            with self._lock:
                existing = [q for q in self._items
                            if q.get("type") == "tag"
                            and _norm(q.get("subject")) == _norm(topic)]
            if any(q.get("status") in _LIVE for q in existing):
                continue
            if existing:      # closed one was handled by recheck_gaps above
                continue
            q = self.post("tag", topic, source="auto", subject_url=url or "")
            if q is not None and q.get("status") == "open" and q not in new:
                new.append(q)
        return {"created": new, "reopened": reopened}

    # -- lifecycle ------------------------------------------------------------------
    def _active_claims(self, q, now=None):
        now = now or time.time()
        return [c for c in q.get("claims", [])
                if (now - float(c.get("at", 0))) < self.claim_ttl]

    def claim(self, qid, player):
        """Soft, NON-exclusive claim ('I'm working this'); expires after the
        TTL so abandoned claims free up. Any number of players may claim."""
        player = (player or "").strip()
        with self._lock:
            q = self._get(qid)
            if q is None or not player or q.get("status") not in _LIVE:
                return False
            q.setdefault("claims", []).append({"player": player, "at": time.time()})
            if q["status"] in ("open", "reopened"):
                q["status"] = "claimed"
            self._save()
            return True

    def submit(self, qid, player, evidence="", proposal=""):
        """Attach evidence + a proposal (for a TagQuest: the comma-separated
        tags; for a RelationshipQuest: 'applies: <target>'). Multiple
        independent submissions accumulate; verification is AUTOMATIC the
        moment `verify_threshold` DISTINCT contributors agree."""
        player = (player or "").strip()
        with self._lock:
            q = self._get(qid)
            if q is None or not player or q.get("status") not in _LIVE:
                return None
            q.setdefault("submissions", []).append({
                "player": player, "evidence": (evidence or "").strip(),
                "proposal": (proposal or "").strip(),
                "at": time.strftime("%Y-%m-%d %H:%M")})
            q["status"] = "submitted"
            self._auto_verify(q)
            self._save()
            return q

    def _auto_verify(self, q):
        """verified ⇐ >= threshold DISTINCT players share the same normalized
        proposal. A single player re-submitting never counts twice."""
        groups = {}
        for s in q.get("submissions", []):
            key = _norm_proposal(s.get("proposal"))
            if not key:
                continue
            groups.setdefault(key, set()).add(_norm(s.get("player")))
        for key, players in groups.items():
            if len(players) >= self.verify_threshold:
                winner = next(s.get("proposal") for s in q["submissions"]
                              if _norm_proposal(s.get("proposal")) == key)
                self._mark_verified(
                    q, how=f"community agreement ({len(players)} independent)",
                    by=sorted(players), resolution=winner)
                return True
        return False

    def signoff(self, qid, maintainer, resolution=""):
        """Trusted maintainer sign-off — the other road to `verified`."""
        with self._lock:
            q = self._get(qid)
            if q is None or q.get("status") not in _LIVE:
                return False
            if _norm(maintainer) not in {_norm(m) for m in self.maintainers}:
                return False
            res = resolution or next(
                (s.get("proposal") for s in reversed(q.get("submissions", []))
                 if s.get("proposal")), "")
            self._mark_verified(q, how="maintainer sign-off", by=[maintainer],
                                resolution=res)
            self._save()
            return True

    def _mark_verified(self, q, how, by, resolution):
        q["status"] = "verified"
        q["resolution"] = resolution or ""
        q.setdefault("verifications", []).append(
            {"how": how, "by": by, "at": time.strftime("%Y-%m-%d %H:%M")})
        credits = set(q.get("contributor_credits", []))
        for s in q.get("submissions", []):
            if _norm_proposal(s.get("proposal")) == _norm_proposal(resolution):
                credits.add(s.get("player"))
        q["contributor_credits"] = sorted(c for c in credits if c)
        self._writeback(q)

    def _writeback(self, q):
        """Early P2 slice: a VERIFIED tag/relationship resolution flows into
        the community tag layer, pre-verified, so the Scaling Advisor uses it
        immediately. Guarded — the board works fine without the layer."""
        ct = self.community
        if ct is None or not q.get("resolution"):
            return
        try:
            if q["type"] == "tag":
                for t in q["resolution"].split(","):
                    t = t.strip()
                    if t:
                        e = ct.suggest_tag(q["subject"], t,
                                           note="quest-board verified")
                        if e:
                            ct.verify(e["id"])
            elif q["type"] == "relationship":
                res = q["resolution"]
                for rel in ("applies", "affected_by"):
                    if _norm(res).startswith(rel + ":"):
                        target = res.split(":", 1)[1].strip()
                        e = ct.suggest_relation(q["subject"], rel, target,
                                                note="quest-board verified")
                        if e:
                            ct.verify(e["id"])
        except Exception:
            pass

    def close(self, qid, db_handler=None):
        """`closed` is ONLY reachable from `verified` (the spec's structural
        rule). For gap-generated TagQuests, pass the db handler: closing also
        requires the gap to actually be gone (scraped tags present, or
        verified community tags) — never close while the data is missing."""
        with self._lock:
            q = self._get(qid)
            if q is None or q.get("status") != "verified":
                return False
            if (db_handler is not None and q.get("source") == "auto"
                    and q.get("type") == "tag"
                    and not self._gap_gone(q, db_handler)):
                return False
            q["status"] = "closed"
            self._save()
            return True

    def _gap_gone(self, q, db_handler):
        try:
            cur = db_handler.cursor
            cur.execute("SELECT tags FROM knowledge_ledger "
                        "WHERE lower(topic_tag)=lower(?) "
                        "ORDER BY (tags IS NOT NULL AND tags!='') DESC LIMIT 1",
                        (q.get("subject", ""),))
            row = cur.fetchone()
            if row and (row[0] or "").strip():
                return True
        except Exception:
            pass
        ct = self.community
        if ct is not None:
            try:
                return any(t.get("verified") for t in ct.tags_for(q.get("subject")))
            except Exception:
                pass
        return False

    def recheck_gaps(self, db_handler):
        """Re-open CLOSED gap-generated quests whose gap detector fires again
        (a later scrape/patch wiped the tags). Returns the reopened quests."""
        reopened = []
        with self._lock:
            closed = [q for q in self._items
                      if q.get("status") == "closed" and q.get("source") == "auto"
                      and q.get("type") == "tag"]
        for q in closed:
            if not self._gap_gone(q, db_handler):
                with self._lock:
                    q["status"] = "reopened"
                    reopened.append(q)
        if reopened:
            with self._lock:
                self._save()
        return reopened

    # -- queries ----------------------------------------------------------------------
    def board(self, status=None, qtype=None):
        with self._lock:
            out = list(reversed(self._items))
        if status:
            out = [q for q in out if q.get("status") == status]
        if qtype:
            out = [q for q in out if q.get("type") == qtype]
        return out

    def get(self, qid):
        with self._lock:
            q = self._get(qid)
            return dict(q) if q else None

    def credits(self, player=None):
        """Contributor credit — quests each player helped verify (the
        gamified hook; no leaderboard needed for P1)."""
        counts = {}
        with self._lock:
            for q in self._items:
                if q.get("status") in ("verified", "closed"):
                    for p in q.get("contributor_credits", []):
                        counts[p] = counts.get(p, 0) + 1
        if player is not None:
            return counts.get(player, 0)
        return counts


if __name__ == "__main__":
    import tempfile
    qb = QuestBoard(path=os.path.join(tempfile.mkdtemp(), "q.json"),
                    maintainers=["castleism"])
    q = qb.post("tag", "Widowhail")
    qb.claim(q["id"], "exile1")
    qb.submit(q["id"], "exile1", "poe2db page", "Bow, Physical")
    qb.submit(q["id"], "exile2", "in-game check", "bow, physical")
    print("status:", qb.get(q["id"])["status"], "| credits:", qb.credits())
