"""
CORE_ENGINE/TAG_GRAPH.PY

Tag-driven retrieval over the local knowledge base. Answers "what scales / what
affects X?" FROM THE DATABASE rather than from the language model's memory —
the core of the Scaling & BIS Advisor (docs/SCALING_ADVISOR_SPEC.md).

The pipeline the player asked for:
    1. tags_for(entity)        -> the entity's real poe2db tags (e.g. Corrupted
                                  Blood -> Physical, Damage Over Time, ...)
    2. assets_with_tags(tags)  -> every knowledge-base asset that SHARES those
                                  tags, ranked by how many it shares (overlap),
                                  weighted so a rare shared tag counts more than
                                  a ubiquitous one (lift-style)
    3. scaling_sources(entity) -> 1 + 2, grouped by asset kind (skill / support
                                  gem / unique / mod / passive / other)
    4. context_block(entity)   -> a compact, prompt-ready block the Orb is told
                                  to ground on, so its answer names REAL assets

Relies on knowledge_ledger.tags (poe2db's own tags, added 2026-07-11). Coverage
grows as the crawler tags more page kinds; where the data isn't there yet, this
says so plainly instead of inventing — the anti-fabrication contract.

Read-only. No network, no game interaction.
"""

import math
import re


# Tags that appear on almost everything and therefore carry little signal on
# their own (used only to DOWN-weight, never to exclude).
_UBIQUITOUS = {"attack", "spell", "physical", "melee", "projectile", "aoe"}

# Rough page-kind inference — LEGACY FALLBACK only. Since 2026-07-12 the crawler
# classifies each page from poe2db's own markup and stores it in
# knowledge_ledger.kind; this tags+URL guess covers rows crawled before that.
_SKILLISH = {"attack", "spell", "aoe", "projectile", "melee", "channelling",
             "duration", "minion", "totem", "trap", "mine", "warcry", "slam",
             "chaining", "nova", "orb", "herald", "aura", "curse", "movement"}


def _norm(tag):
    return (tag or "").strip().lower()


def _split_tags(tags_str):
    """'Attack, AoE, Projectile' -> ['Attack','AoE','Projectile'] (order kept)."""
    if not tags_str:
        return []
    out, seen = [], set()
    for t in re.split(r"[,;|]", tags_str):
        t = t.strip()
        k = t.lower()
        if t and k not in seen:
            seen.add(k)
            out.append(t)
    return out


class KalandraTagGraph:
    """Reverse tag index over knowledge_ledger. Give it a db handler
    (KalandraDBHandler); every method is read-only and thread-safe as long as
    each thread uses its own handler (the app's convention)."""

    KINDS = ("skill_gem", "support_gem", "unique", "mod", "passive", "item",
             "other")

    def __init__(self, db_handler, community=None):
        """`community` is an optional CommunityTags overlay (player-reported
        tags/interactions, spec P2.5). Pass an instance to share one, pass
        False to disable, or leave None to lazily open the default file on
        first use. Community data only ever ADDS marked, non-authoritative
        hints — with an empty overlay every result is identical to before."""
        self.db = db_handler
        self._idf_cache = None
        self._community = community
        self._community_tried = community is not None

    @property
    def community(self):
        if not self._community_tried:
            self._community_tried = True
            try:
                from core_engine.community_tags import CommunityTags
                self._community = CommunityTags()
            except Exception:
                self._community = None
        return self._community or None

    # -- public API -----------------------------------------------------------
    def tags_for(self, entity):
        """The real poe2db tags of a named entity. Exact title match first, then
        a unique-ish 'contains' fallback. Returns [] if unknown/untagged."""
        name = (entity or "").strip()
        if not name:
            return []
        cur = self.db.cursor
        # Exact (case-insensitive) title match, preferring a row that HAS tags.
        cur.execute(
            "SELECT tags FROM knowledge_ledger "
            "WHERE lower(topic_tag)=lower(?) "
            "ORDER BY (tags IS NOT NULL AND tags!='') DESC LIMIT 1", (name,))
        row = cur.fetchone()
        if row and row[0]:
            return _split_tags(row[0])
        # Fallback: a title that contains the phrase, tagged, shortest title wins
        # (closest match), so "Corrupted Blood" resolves even if stored slightly
        # differently.
        like = f"%{name}%"
        cur.execute(
            "SELECT tags FROM knowledge_ledger "
            "WHERE topic_tag LIKE ? AND tags IS NOT NULL AND tags!='' "
            "ORDER BY length(topic_tag) ASC LIMIT 1", (like,))
        row = cur.fetchone()
        return _split_tags(row[0]) if row and row[0] else []

    def entities_in_text(self, text, limit=4, cap=8000):
        """Tagged entity titles that appear as a phrase in `text`, most-specific
        (longest) first. Lets the advisor pick what the player is actually asking
        about (e.g. 'how do I scale my corrupted blood build' -> Corrupted
        Blood)."""
        low = (text or "").lower()
        if not low:
            return []
        cur = self.db.cursor
        cur.execute("SELECT DISTINCT topic_tag FROM knowledge_ledger "
                    "WHERE tags IS NOT NULL AND tags!='' LIMIT ?", (cap,))
        hits = [t.strip() for (t,) in cur.fetchall()
                if t and len(t.strip()) >= 3 and t.strip().lower() in low]
        hits.sort(key=lambda s: -len(s))
        out, seen = [], set()
        for h in hits:
            k = h.lower()
            if k not in seen:
                seen.add(k)
                out.append(h)
            if len(out) >= limit:
                break
        return out

    def assets_with_tags(self, tags, exclude=None, kinds=None,
                         limit=40, min_overlap=1, candidate_cap=800):
        """Assets that share at least `min_overlap` of `tags`, ranked by a
        weighted overlap score (rarer shared tags score higher). Returns a list
        of dicts: {title, url, tags, overlap, score, kind}."""
        want = [t for t in (tags or []) if _norm(t)]
        if not want:
            return []
        want_norm = {_norm(t) for t in want}
        exclude_norm = _norm(exclude) if exclude else None
        idf = self._tag_idf()

        rows = self._candidate_rows(want, candidate_cap)
        scored = []
        for title, url, tags_str, stored_kind in rows:
            if exclude_norm and _norm(title) == exclude_norm:
                continue
            row_tags = _split_tags(tags_str)
            shared = [t for t in row_tags if _norm(t) in want_norm]
            if len(shared) < min_overlap:
                continue
            # The crawler's markup-verified classification wins; the tag/URL
            # inference only covers rows crawled before `kind` existed.
            kind = ((stored_kind or "").strip()
                    or self._infer_kind(url, row_tags))
            if kind not in self.KINDS:
                kind = "other"
            if kinds and kind not in kinds:
                continue
            # Weighted score: sum of each shared tag's idf (rarer -> higher),
            # with a small bonus for absolute overlap count.
            score = sum(idf.get(_norm(t), 1.0) for t in shared) + 0.1 * len(shared)
            scored.append({"title": title, "url": url, "tags": row_tags,
                           "overlap": len(shared), "shared": shared,
                           "score": round(score, 3), "kind": kind})
        scored.sort(key=lambda a: (-a["score"], -a["overlap"], a["title"].lower()))
        return scored[:limit]

    def community_tags_for(self, entity):
        """Player-reported tags for `entity` that the scrape doesn't already
        have — each {tag, verified, votes, id}. Marked data, never merged
        silently into the authoritative tag list."""
        ct = self.community
        if ct is None:
            return []
        try:
            scraped = {_norm(t) for t in self.tags_for(entity)}
            return [c for c in ct.tags_for(entity)
                    if _norm(c.get("tag")) not in scraped]
        except Exception:
            return []

    def community_appliers(self, entity):
        """Entities the community says APPLY `entity` (e.g. what applies
        Corrupted Blood) — feeds the advisor + the future meta-miner."""
        ct = self.community
        if ct is None:
            return []
        try:
            return ct.appliers_of(entity)
        except Exception:
            return []

    def scaling_sources(self, entity, per_kind=8, limit=48):
        """Everything the DB knows about scaling `entity`: its tags + the assets
        sharing them, grouped by kind. Community-reported tags (P2.5) widen the
        reverse lookup but are returned SEPARATELY and marked. Returns a
        structured dict (never raises)."""
        subject_tags = self.tags_for(entity)
        community = self.community_tags_for(entity)
        appliers = self.community_appliers(entity)
        result = {"subject": entity, "subject_tags": subject_tags,
                  "community_tags": community, "appliers": appliers,
                  "groups": {}, "total": 0, "note": ""}
        if not subject_tags and not community:
            result["note"] = ("No tags for this entity in the database yet — run a "
                              "Sync, or it may be a page kind we don't tag yet. "
                              "You can also suggest a tag yourself (player-reported).")
            return result
        lookup_tags = subject_tags + [c["tag"] for c in community]
        assets = self.assets_with_tags(lookup_tags, exclude=entity, limit=limit)
        groups = {}
        for a in assets:
            groups.setdefault(a["kind"], [])
            if len(groups[a["kind"]]) < per_kind:
                groups[a["kind"]].append(a)
        result["groups"] = groups
        result["total"] = sum(len(v) for v in groups.values())
        if result["total"] == 0:
            result["note"] = ("Found the entity's tags but no other tagged assets "
                              "share them yet — coverage grows as more pages are "
                              "crawled/tagged.")
        return result

    _KIND_LABELS = {"skill_gem": "Skill gems", "support_gem": "Support gems",
                    "unique": "Uniques", "mod": "Item mods", "passive": "Passives",
                    "item": "Base items", "other": "Other"}

    def context_block(self, entity, limit=40):
        """Prompt-ready grounding block for the Orb, or '' if we have nothing.
        The Orb is instructed to name ONLY assets that appear here. Community
        (player-reported) data is labeled so the Orb presents it as a hint,
        never as ground truth."""
        src = self.scaling_sources(entity, limit=limit)
        if not src["subject_tags"] and not src.get("community_tags"):
            return ""
        lines = [
            "SCALING SOURCES (from the local database — ground your answer in THIS. "
            "List only assets that appear below; if a category is empty, say the DB "
            "doesn't have it yet rather than guessing):",
        ]
        if src["subject_tags"]:
            lines.append(f"- {entity} tags: {', '.join(src['subject_tags'])}")
        comm = src.get("community_tags") or []
        if comm:
            verified = [c["tag"] for c in comm if c.get("verified")]
            unverified = [c["tag"] for c in comm if not c.get("verified")]
            if verified:
                lines.append(f"- {entity} tags (player-reported, VERIFIED by the "
                             f"maintainer): {', '.join(verified)}")
            if unverified:
                lines.append(f"- {entity} tags (player-reported, UNVERIFIED — "
                             "present these as community hints, never as fact): "
                             + ", ".join(unverified))
        appliers = src.get("appliers") or []
        if appliers:
            lines.append(f"- Applied by (player-reported): {', '.join(appliers)}")
        if src["total"] == 0:
            lines.append("- No other tagged assets in the DB share these tags yet "
                         "(coverage is still growing).")
            return "\n".join(lines)
        for kind in self.KINDS:
            items = src["groups"].get(kind)
            if not items:
                continue
            label = self._KIND_LABELS.get(kind, kind)
            names = ", ".join(f"{a['title']} [{', '.join(a['shared'])}]"
                              for a in items)
            lines.append(f"- {label}: {names}")
        return "\n".join(lines)

    # -- internals ------------------------------------------------------------
    def _candidate_rows(self, want, cap):
        """(title, url, tags, kind) rows that plausibly share a tag, cheaply.
        Uses the FTS tags column when available (fast), else a bounded scan of
        tagged rows."""
        cur = self.db.cursor
        if getattr(self.db, "fts_enabled", False):
            try:
                # OR of the wanted tags, restricted to the `tags` FTS column.
                phrases = " OR ".join('"%s"' % re.sub(r'"', "", t) for t in want)
                q = "tags : (%s)" % phrases
                cur.execute(
                    "SELECT l.topic_tag, l.source_url, l.tags, l.kind "
                    "FROM knowledge_fts f JOIN knowledge_ledger l ON l.id=f.rowid "
                    "WHERE knowledge_fts MATCH ? LIMIT ?", (q, cap))
                rows = cur.fetchall()
                if rows:
                    return rows
            except Exception:
                pass
        # Fallback: scan rows that have any tags (bounded).
        cur.execute(
            "SELECT topic_tag, source_url, tags, kind FROM knowledge_ledger "
            "WHERE tags IS NOT NULL AND tags!='' LIMIT ?", (cap,))
        return cur.fetchall()

    def _tag_idf(self):
        """Inverse-document-frequency per tag: rare tags weigh more. Cached."""
        if self._idf_cache is not None:
            return self._idf_cache
        idf = {}
        try:
            cur = self.db.cursor
            cur.execute("SELECT COUNT(*) FROM knowledge_ledger "
                        "WHERE tags IS NOT NULL AND tags!=''")
            n = cur.fetchone()[0] or 1
            freq = {}
            cur.execute("SELECT tags FROM knowledge_ledger "
                        "WHERE tags IS NOT NULL AND tags!='' LIMIT 200000")
            for (tags_str,) in cur.fetchall():
                for t in {_norm(x) for x in _split_tags(tags_str)}:
                    freq[t] = freq.get(t, 0) + 1
            for t, f in freq.items():
                # classic idf; ubiquitous tags get an extra damp
                val = math.log((n + 1) / (f + 1)) + 0.1
                if t in _UBIQUITOUS:
                    val *= 0.35
                idf[t] = max(0.05, val)
        except Exception:
            idf = {}
        self._idf_cache = idf
        return idf

    @staticmethod
    def _infer_kind(url, row_tags):
        """Best-effort page-kind for rows crawled before the stored `kind`
        column existed. Conservative: only classify what we're confident
        about."""
        norm = {_norm(t) for t in row_tags}
        if "support" in norm:
            return "support_gem"
        u = (url or "").lower()
        if "support" in u:
            return "support_gem"
        if norm & _SKILLISH:
            return "skill_gem"
        return "other"
