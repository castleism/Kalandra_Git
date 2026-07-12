"""
CORE_ENGINE/COMMUNITY_TAGS.PY
Player-reported tags & interactions — the community layer of the Scaling &
BIS Advisor (docs/SCALING_ADVISOR_SPEC.md, P2.5).

New uniques and newly-discovered interactions show up in play before poe2db
documents them. This layer lets the player close that gap immediately: propose
a tag ("Widowhail: Bow") or a relationship ("The Peacemaker's Draught APPLIES
Corrupted Blood"), and the tag graph starts using it on the next question —
no waiting for a scrape.

Hard rules (from the spec):
  * Stored in a JSON overlay DISTINCT from scraped tags (the proven
    knowledge_corrections.py pattern: ship-safe, survives DB rebuilds), every
    entry flagged source="community" with votes + a verified flag.
  * The tag graph merges these in but marks them visibly — "player-reported,
    unverified" — so the advisor NEVER presents them as authoritative. A
    maintainer can promote (verify) an entry into ground truth, mirroring how
    verified corrections work today.
  * Local-only by default. Any future shared/synced version needs moderation
    or voting first (abuse guard). ToS unaffected: this is metadata about the
    game, never interaction with it.

Public API:
    CommunityTags(path=None)
    .suggest_tag(entity, tag, note="")               -> entry (dedup → +1 vote)
    .suggest_relation(entity, relation, target, "")  -> entry (dedup → +1 vote)
        relation ∈ {"applies", "affected_by"}
    .vote(entry_id, delta=1)                         -> new vote count | None
    .verify(entry_id, verified=True)                 -> bool (promotion path)
    .delete(entry_id)                                -> bool
    .all()                                           -> list (newest first)
    .tags_for(entity)                                -> [{tag, verified, votes, id}]
    .relations_for(entity)                           -> [{relation, target, ...}]
    .appliers_of(effect)                             -> [entity, ...] ("applies")
"""

import json
import os
import threading
import time

_DEFAULT_NAME = "community_tags.json"

RELATIONS = ("applies", "affected_by")


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


class CommunityTags:
    def __init__(self, path=None):
        self.path = path or _default_path()
        self._lock = threading.Lock()
        self._items = []
        self._seq = 0
        self._load()

    # -- storage ---------------------------------------------------------------
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
        self._items = []   # no seed: every entry here is a real player report

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._items, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except Exception:
            pass

    def _make(self, kind, entity, **extra):
        self._seq += 1
        e = {
            "id": "ct_%d_%d" % (int(time.time() * 1000), self._seq),
            "kind": kind,                    # "tag" | "relation"
            "entity": (entity or "").strip(),
            "source": "community",           # NEVER authoritative
            "votes": 1,
            "verified": False,               # maintainer promotion flips this
            "added": time.strftime("%Y-%m-%d %H:%M"),
        }
        e.update(extra)
        return e

    def _find_dup(self, kind, entity, key, value):
        en = _norm(entity)
        vn = _norm(value)
        for e in self._items:
            if (e.get("kind") == kind and _norm(e.get("entity")) == en
                    and _norm(e.get(key)) == vn):
                return e
        return None

    # -- proposals ---------------------------------------------------------------
    def suggest_tag(self, entity, tag, note=""):
        """Propose that `entity` carries game tag `tag`. Re-proposing an
        existing suggestion counts as a vote for it instead of duplicating."""
        entity = (entity or "").strip()
        tag = (tag or "").strip()
        if not entity or not tag:
            return None
        with self._lock:
            dup = self._find_dup("tag", entity, "tag", tag)
            if dup is not None:
                dup["votes"] = int(dup.get("votes", 1)) + 1
                self._save()
                return dup
            e = self._make("tag", entity, tag=tag, note=(note or "").strip())
            self._items.append(e)
            self._save()
            return e

    def suggest_relation(self, entity, relation, target, note=""):
        """Propose a relationship: `entity` APPLIES `target` (e.g. a unique
        that applies Corrupted Blood) or `entity` is AFFECTED_BY `target`."""
        entity = (entity or "").strip()
        target = (target or "").strip()
        relation = _norm(relation)
        if not entity or not target or relation not in RELATIONS:
            return None
        with self._lock:
            dup = None
            en = _norm(entity)
            for e in self._items:
                if (e.get("kind") == "relation" and _norm(e.get("entity")) == en
                        and e.get("relation") == relation
                        and _norm(e.get("target")) == _norm(target)):
                    dup = e
                    break
            if dup is not None:
                dup["votes"] = int(dup.get("votes", 1)) + 1
                self._save()
                return dup
            e = self._make("relation", entity, relation=relation, target=target,
                           note=(note or "").strip())
            self._items.append(e)
            self._save()
            return e

    # -- curation ----------------------------------------------------------------
    def vote(self, entry_id, delta=1):
        with self._lock:
            for e in self._items:
                if e.get("id") == entry_id:
                    e["votes"] = int(e.get("votes", 1)) + int(delta)
                    self._save()
                    return e["votes"]
        return None

    def verify(self, entry_id, verified=True):
        """Maintainer promotion: a verified entry may be treated as ground
        truth by consumers (mirrors the verified-corrections flow)."""
        with self._lock:
            for e in self._items:
                if e.get("id") == entry_id:
                    e["verified"] = bool(verified)
                    self._save()
                    return True
        return False

    def delete(self, entry_id):
        with self._lock:
            n = len(self._items)
            self._items = [e for e in self._items if e.get("id") != entry_id]
            if len(self._items) != n:
                self._save()
                return True
            return False

    # -- queries -----------------------------------------------------------------
    def all(self):
        with self._lock:
            return list(reversed(self._items))

    def tags_for(self, entity):
        """Community tag proposals for an entity, most-voted first."""
        en = _norm(entity)
        if not en:
            return []
        with self._lock:
            hits = [e for e in self._items
                    if e.get("kind") == "tag" and _norm(e.get("entity")) == en]
        hits.sort(key=lambda e: (-int(e.get("votes", 1)), e.get("added", "")))
        return [{"tag": e.get("tag", ""), "verified": bool(e.get("verified")),
                 "votes": int(e.get("votes", 1)), "id": e.get("id")}
                for e in hits if e.get("tag")]

    def relations_for(self, entity):
        en = _norm(entity)
        if not en:
            return []
        with self._lock:
            hits = [e for e in self._items
                    if e.get("kind") == "relation"
                    and _norm(e.get("entity")) == en]
        hits.sort(key=lambda e: (-int(e.get("votes", 1)), e.get("added", "")))
        return [{"relation": e.get("relation"), "target": e.get("target", ""),
                 "verified": bool(e.get("verified")),
                 "votes": int(e.get("votes", 1)), "id": e.get("id")}
                for e in hits if e.get("target")]

    def appliers_of(self, effect):
        """Entities the community says APPLY `effect` (e.g. which items/gems
        apply Corrupted Blood). Feeds the advisor and, later, the poe.ninja
        meta-miner's applier list (spec P4)."""
        fn = _norm(effect)
        if not fn:
            return []
        with self._lock:
            hits = [e for e in self._items
                    if e.get("kind") == "relation"
                    and e.get("relation") == "applies"
                    and _norm(e.get("target")) == fn]
        hits.sort(key=lambda e: (-int(e.get("votes", 1)), e.get("added", "")))
        out, seen = [], set()
        for e in hits:
            k = _norm(e.get("entity"))
            if k and k not in seen:
                seen.add(k)
                out.append(e.get("entity"))
        return out


if __name__ == "__main__":
    import tempfile
    ct = CommunityTags(path=os.path.join(tempfile.mkdtemp(), "ct.json"))
    ct.suggest_tag("Widowhail", "Bow")
    ct.suggest_relation("The Peacemaker's Draught", "applies", "Corrupted Blood")
    print("tags_for Widowhail:", ct.tags_for("Widowhail"))
    print("appliers_of Corrupted Blood:", ct.appliers_of("Corrupted Blood"))
