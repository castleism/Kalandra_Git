"""
CORE_ENGINE/OBSIDIAN_EXPORT.PY
Turn the scraped/extracted SQLite knowledge base into a BROWSABLE OBSIDIAN VAULT.

You open the vault folder in Obsidian ("Open folder as vault") and get a
user-friendly map of all the game data. Search a skill and you can immediately
see everything that interacts with it: the damage it can scale, the uniques that
affect it, the passives, the support gems, and the mechanics it touches.

How the relationships are built
  * Every knowledge entry becomes one note, filed into a category SUBFOLDER
    (Skills / Support Gems / Uniques & Items / Passives / Mechanics / Currency /
    Patch Notes / Economy / Other) so the vault is easy to browse.
  * KEYWORD HUB notes are generated for the core scaling/mechanic terms
    (Lightning, Projectile, Critical Strike, Bleed, Minion, Area of Effect, ...).
    Every note that mentions a keyword links to that hub, and each hub lists all
    the skills / supports / uniques / passives / mechanics that share it. That is
    what lets you click a skill and trace every way to scale or interact with it.
  * A title-mention pass adds direct [[wikilinks]] under "Related".
  * Per-category Maps-of-Content and a home note tie it together.

No account or network needed -- Obsidian is a local app.
"""

import os
import re

INVALID_FS = re.compile(r'[\\/:*?"<>|#\^\[\]]')
_WORD_RX = re.compile(r"[a-z0-9']+")

CHANGE_KEYWORDS = {
    "nerf":   re.compile(r"\b(nerf|reduced|decreased|lowered|no longer|removed)\b", re.I),
    "buff":   re.compile(r"\b(buff|increased|improved|raised|now also|added)\b", re.I),
    "rework": re.compile(r"\b(rework|reworked|redesign|replaced|changed to)\b", re.I),
}

# Curated scaling / mechanic keyword hubs. Each becomes a hub note that gathers
# everything sharing it. (name -> regex). Keep names clean for filenames.
KEYWORD_HUBS = {
    # damage types
    "Physical Damage":  r"\bphysical\b",
    "Fire Damage":      r"\bfire\b|\bignit|\bburn",
    "Cold Damage":      r"\bcold\b|\bfreeze|\bchill",
    "Lightning Damage": r"\blightning\b|\bshock\b",
    "Chaos Damage":     r"\bchaos\b",
    "Elemental Damage": r"\belemental\b",
    # delivery / gem tags
    "Attack":           r"\battack(s|ing)?\b",
    "Spell":            r"\bspell(s)?\b",
    "Projectile":       r"\bprojectile(s)?\b",
    "Area of Effect":   r"\barea of effect\b|\baoe\b|\barea damage\b",
    "Melee":            r"\bmelee\b",
    "Minion":           r"\bminion(s)?\b|\bsummon",
    "Totem":            r"\btotem(s)?\b",
    "Trap":             r"\btrap(s)?\b",
    "Mine":             r"\bmine(s)?\b",
    "Channelling":      r"\bchannell?ing\b",
    "Duration":         r"\bduration\b",
    "Aura":             r"\baura(s)?\b",
    "Curse":            r"\bcurse(s|d)?\b|\bhex\b|\bmark\b",
    "Herald":           r"\bherald\b",
    "Warcry":           r"\bwarcry|\bcry\b",
    # ailments / defences / stats
    "Critical Strike":  r"\bcritical\b|\bcrit\b",
    "Ignite":           r"\bignit",
    "Shock":            r"\bshock",
    "Chill / Freeze":   r"\bchill|\bfreeze|\bfrozen",
    "Poison":           r"\bpoison",
    "Bleed":            r"\bbleed|\bcorrupt(ed|ing) blood\b|\bhaemorrhage",
    "Stun":             r"\bstun",
    "Armour Break":     r"\barmour break|\bbreak armour",
    "Energy Shield":    r"\benergy shield\b|\bES\b",
    "Life":             r"\blife\b",
    "Mana":             r"\bmana\b",
    "Spirit":           r"\bspirit\b",
    "Leech":            r"\bleech\b",
    "Block":            r"\bblock\b",
    "Evasion":          r"\bevasion\b|\bevade\b",
    "Attack Speed":     r"\battack speed\b",
    "Cast Speed":       r"\bcast speed\b",
    "Damage over Time": r"\bdamage over time\b|\bdot\b|\bover time\b",
}
_HUBS_COMPILED = {name: re.compile(rx, re.I) for name, rx in KEYWORD_HUBS.items()}

# When game files are extracted, topics arrive prefixed "[TableName] Name".
# That gives us an EXACT category (better than guessing from scraped text).
TABLE_FOLDERS = {
    "baseitemtypes": "Uniques & Items", "uniquestashlayout": "Uniques & Items",
    "itemclasses": "Uniques & Items", "armourtypes": "Uniques & Items",
    "weapontypes": "Uniques & Items", "flasks": "Uniques & Items",
    "skillgems": "Skills", "activeskills": "Skills", "grantedeffects": "Skills",
    "grantedeffectsperlevel": "Skills",
    "supportgems": "Support Gems",
    "passiveskills": "Passives", "passiveskilltypes": "Passives",
    "mods": "Mods", "modtype": "Mods", "modfamily": "Mods",
    "stats": "Mechanics", "tags": "Mechanics", "buffdefinitions": "Mechanics",
    "essences": "Currency", "currencyitems": "Currency", "currency": "Currency",
    "catalysts": "Currency",
}


def _table_folder(topic):
    """If topic is '[TableName] Something', map it to an exact folder."""
    m = re.match(r"^\[([A-Za-z0-9_]+)\]", topic or "")
    if m:
        return TABLE_FOLDERS.get(m.group(1).lower())
    return None


# Routing: (tag, folder) in priority order. First match wins.
CATEGORY_ROUTING = [
    ("type/support",  "Support Gems"),
    ("type/skill",    "Skills"),
    ("type/passive",  "Passives"),
    ("type/item",     "Uniques & Items"),
    ("type/mechanic", "Mechanics"),
    ("type/currency", "Currency"),
]


def _slug(title):
    s = INVALID_FS.sub(" ", title).strip()
    s = re.sub(r"\s+", " ", s)
    return s[:120] or "untitled"


def _classify(topic, version, content):
    """Return (ntype, tags[]) derived from title + body."""
    t = (topic or "").lower()
    v = (version or "").lower()
    scan = t + " " + (content or "")[:2000].lower()
    tags = set()

    if topic.startswith("[Economy]") or "poe.ninja" in v:
        ntype = "economy"
    elif "poe2wiki" in v:
        ntype = "wiki"; tags.add("source/poe2wiki")
    elif "game-data" in v or topic.startswith("["):
        ntype = "data"; tags.add("source/gamefiles")
    elif "patch" in v:
        ntype = "data"; tags.add("source/poe2db")
    else:
        ntype = "data"

    if any(k in scan for k in ("unique", "amulet", "ring", "armour", "weapon",
                               "flask", "bow", "quiver", "wand", "sceptre", "shield",
                               "helmet", "gloves", "boots", "belt", "jewel")):
        tags.add("type/item")
    if "support" in scan:
        tags.add("type/support")
    elif "gem" in scan or "skill" in scan or "spell" in scan:
        tags.add("type/skill")
    if any(k in scan for k in ("passive", "ascendanc", "keystone", "notable", "anoint")):
        tags.add("type/passive")
    if any(k in scan for k in ("mechanic", "keyword", "crafting", "modifier", "ailment",
                               "chill", "freeze", "ignite", "shock", "poison", "bleed")):
        tags.add("type/mechanic")
    if any(k in scan for k in ("currency", "orb", "essence", "rune", "catalyst")):
        tags.add("type/currency")

    if re.search(r"\bpatch\b|\b0\.\d+(?:\.\d+)?\b|hotfix|changelog", content, re.I):
        tags.add("patch")
    for change, rx in CHANGE_KEYWORDS.items():
        if rx.search(content or ""):
            tags.add(change)

    tags.add(f"kind/{ntype}")
    return ntype, sorted(tags)


def _category_folder(tags, ntype):
    for tag, folder in CATEGORY_ROUTING:
        if tag in tags:
            return folder
    if ntype == "economy":
        return "Economy"
    if "patch" in tags:
        return "Patch Notes"
    return "Other"


class ObsidianExporter:
    def __init__(self, db_handler, out_dir=None, logger=None, progress=None):
        # Vault location is configurable; default to a clean top-level folder.
        if out_dir is None:
            out_dir = self._configured_vault_dir()
        self.db = db_handler
        self.out_dir = out_dir
        self.logger = logger
        # progress(done, total, phase) — called periodically so the UI/terminal
        # can show that a big export is actually moving.
        self.progress = progress

    @staticmethod
    def _configured_vault_dir():
        try:
            import json
            with open(os.path.join("data_engine", "config.json"), "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return cfg.get("dir_vault") or "KalandraVault"
        except Exception:
            return "KalandraVault"

    def _log(self, msg):
        if self.logger:
            try:
                self.logger("DATABASE", msg)
            except Exception:
                pass

    def _rows(self):
        self.db.cursor.execute(
            "SELECT id, topic_tag, content_payload, source_url, game_version_tag "
            "FROM knowledge_ledger ORDER BY id")
        return self.db.cursor.fetchall()

    def _tick(self, done, total, phase):
        if self.progress:
            try:
                self.progress(done, total, phase)
            except Exception:
                pass

    def export(self, max_links_per_note=40):
        rows = self._rows()
        if not rows:
            self._log("Nothing to export -- run a DB sync / game extraction first.")
            return {"notes": 0, "path": self.out_dir}
        self._log(f"Obsidian export starting: {len(rows)} entries -> {self.out_dir}")

        os.makedirs(self.out_dir, exist_ok=True)
        for sub in ("Skills", "Support Gems", "Uniques & Items", "Passives",
                    "Mods", "Mechanics", "Currency", "Patch Notes", "Economy", "Other",
                    "Keywords", "_Maps"):
            os.makedirs(os.path.join(self.out_dir, sub), exist_ok=True)

        # 1) unique filename per entry
        filename_for, used, notes = {}, set(), []
        for (rid, topic, content, url, version) in rows:
            base = _slug(topic or f"entry-{rid}")
            name = base if base.lower() not in used else f"{base} ({rid})"
            used.add(name.lower())
            filename_for[rid] = name
            notes.append((rid, topic or name, content or "", url or "", version or ""))

        # 2) title index for direct cross-links.
        # The old approach compiled ONE regex with thousands of alternations and
        # ran it over every note's full body — O(notes x body x titles), which
        # pegged a core for minutes-to-hours on big knowledge bases and (thanks
        # to the GIL) froze the whole app. Instead: index titles by their first
        # word; per note, tokenize the body once and only test the few titles
        # whose first word actually appears.
        title_to_file = {}
        first_word_index = {}    # first token -> [(title_lower, filename)]
        for (rid, topic, content, url, version) in notes:
            tl = topic.lower()
            title_to_file[tl] = filename_for[rid]
            if len(topic) >= 4:
                toks = _WORD_RX.findall(tl)
                if toks:
                    first_word_index.setdefault(toks[0], []).append((tl, filename_for[rid]))

        # 3) write notes; collect category + keyword-hub membership
        categories = {}                      # folder -> [filename]
        hub_members = {h: [] for h in KEYWORD_HUBS}   # hub -> [(folder, filename)]
        total = len(notes)
        for done, (rid, topic, content, url, version) in enumerate(notes, 1):
            if done % 500 == 0 or done == total:
                self._tick(done, total, "notes")
            ntype, tags = _classify(topic, version, content)
            folder = _table_folder(topic) or _category_folder(tags, ntype)
            categories.setdefault(folder, []).append(filename_for[rid])

            scan = (topic + " " + content[:4000])
            hubs = [h for h, rx in _HUBS_COMPILED.items() if rx.search(scan)]
            for h in hubs:
                hub_members[h].append((folder, filename_for[rid]))

            related = []
            body_low = content[:20000].lower()
            body_toks = set(_WORD_RX.findall(body_low))
            seen = set()
            tlow = topic.lower()
            for tok in body_toks:
                for (tl, target) in first_word_index.get(tok, ()):
                    if tl == tlow or tl in seen or target == filename_for[rid]:
                        continue
                    idx = body_low.find(tl)
                    if idx < 0:
                        continue
                    # word-boundary check on both sides of the match
                    end = idx + len(tl)
                    if (idx == 0 or not body_low[idx - 1].isalnum()) and \
                            (end >= len(body_low) or not body_low[end].isalnum()):
                        seen.add(tl)
                        related.append(target)
                        if len(related) >= max_links_per_note:
                            break
                if len(related) >= max_links_per_note:
                    break
            related.sort()

            fm = ["---", f'title: "{topic}"', f"source: {url}",
                  f"version: {version}", f"category: {folder}", "tags:"]
            for tg in tags:
                fm.append(f"  - {tg}")
            fm.append("---")

            body = [f"# {topic}", ""]
            if url:
                body += [f"> Source: {url}", ""]
            body.append(content.strip())
            if hubs:
                body += ["", "## Scaling & Keywords",
                         "*(everything below interacts with or scales this)*"]
                for h in hubs:
                    body.append(f"- [[Keyword - {h}|{h}]]")
            if related:
                body += ["", "## Related"]
                for r in related:
                    body.append(f"- [[{r}]]")

            path = os.path.join(self.out_dir, folder, filename_for[rid] + ".md")
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(fm) + "\n\n" + "\n".join(body) + "\n")
            except Exception as e:
                self._log(f"Failed writing {path}: {e}")

        # 4) keyword hub notes (grouped by category so it's easy to read)
        hubs_written = 0
        for hub, members in hub_members.items():
            if not members:
                continue
            hubs_written += 1
            by_cat = {}
            for (folder, fn) in members:
                by_cat.setdefault(folder, []).append(fn)
            out = [f"# {hub}", "",
                   f"Everything in the knowledge base that scales with or interacts "
                   f"with **{hub}** ({len(members)} entries). Use this to find supports, "
                   f"uniques, passives and skills that work together.", ""]
            for cat in sorted(by_cat):
                out.append(f"## {cat}")
                for fn in sorted(set(by_cat[cat])):
                    out.append(f"- [[{fn}]]")
                out.append("")
            with open(os.path.join(self.out_dir, "Keywords", f"Keyword - {hub}.md"),
                      "w", encoding="utf-8") as f:
                f.write("\n".join(out) + "\n")

        # 5) category MOCs
        for folder, members in categories.items():
            moc = [f"# Map of Content — {folder}", "", f"{len(set(members))} entries.", ""]
            for m in sorted(set(members)):
                moc.append(f"- [[{m}]]")
            with open(os.path.join(self.out_dir, "_Maps", f"MOC - {folder}.md"),
                      "w", encoding="utf-8") as f:
                f.write("\n".join(moc) + "\n")

        # 6) home note
        index = ["# Kalandra Knowledge Map", "",
                 "Open this folder in Obsidian (**Open folder as vault**), then use",
                 "**Search** and the **Graph view** to explore the game.", "",
                 "Tip: open a skill, look at its **Scaling & Keywords**, and click a",
                 "keyword to see every unique, passive and support that interacts with it.",
                 "", "## Browse by category"]
        for folder in sorted(categories):
            index.append(f"- [[MOC - {folder}|{folder}]] ({len(set(categories[folder]))})")
        index += ["", "## Scaling & mechanic hubs"]
        for hub in sorted(h for h, m in hub_members.items() if m):
            index.append(f"- [[Keyword - {hub}|{hub}]]")
        with open(os.path.join(self.out_dir, "Kalandra Knowledge Map.md"),
                  "w", encoding="utf-8") as f:
            f.write("\n".join(index) + "\n")

        self._log(f"Obsidian vault exported: {len(notes)} notes, {hubs_written} keyword "
                  f"hubs -> {self.out_dir}")
        return {"notes": len(notes), "hubs": hubs_written, "path": self.out_dir}


def main(argv=None):
    """CLI entry so the overlay can export in a SEPARATE PROCESS. A Python
    thread can't help here: the export is CPU-bound and the GIL lets it starve
    the UI. A subprocess uses its own interpreter and leaves the app smooth.

    Prints progress lines to stdout as it goes and a final line
    'RESULT {json}' the parent parses."""
    import sys
    import json as _json
    import argparse
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core_engine.database_handler import KalandraDBHandler

    ap = argparse.ArgumentParser(description="Export the knowledge base to an Obsidian vault.")
    ap.add_argument("--out", default=None, help="vault output folder")
    args = ap.parse_args(argv)

    def _say(msg):
        try:
            print(msg, flush=True)
        except Exception:
            pass

    db = KalandraDBHandler()
    try:
        ex = ObsidianExporter(
            db, out_dir=args.out,
            logger=lambda c, m: _say(f"[{c}] {m}"),
            progress=lambda done, total, phase: _say(
                f"[DATABASE] Export progress: {done}/{total} {phase}"))
        result = ex.export()
        _say("RESULT " + _json.dumps(result))
        return 0
    except Exception as e:
        _say(f"[DATABASE] Export failed: {e}")
        _say('RESULT {"notes": 0, "path": "", "error": "%s"}' % str(e).replace('"', "'"))
        return 1
    finally:
        try:
            db.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
