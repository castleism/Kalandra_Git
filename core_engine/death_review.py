"""
CORE_ENGINE/DEATH_REVIEW.PY — the "why did I die?" engine (W4-21).

The game will not tell you what killed you: PoE2's Client.txt logs THAT you
died and where, never the hit. So the answer is assembled from three sides:

  1. THE MOMENT  — a log watcher tails Client.txt; the instant a death line
     appears it asks OBS to flush its replay buffer (core_engine/obs_bridge),
     rewinding the last N seconds into a clip saved with the incident.
  2. THE CONTEXT — zone entries and recent log events around the death are
     kept with the incident (what map, what just happened).
  3. THE BUILD   — defensive_audit() reads the PoB build's own numbers and
     lists the holes (uncapped res, negative chaos res, thin eHP, no
     mitigation layer...), each with why it matters and what to do.

ai_autopsy_prompt() hands all three to the AI for the plain-words verdict.
Incidents live in data_engine/deaths/<stamp>/ (incident.json + the clip).
Pure Python except the OBS call; every step fails soft so a missing OBS or
build never breaks the watcher.
"""

import json
import os
import re
import shutil
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEATHS_DIR = os.path.join(ROOT, "data_engine", "deaths")

# ---------------------------------------------------------------------------
# 1. Client.txt parsing
# ---------------------------------------------------------------------------
# Log lines end in "] : <message>" for chat/notifications. Deaths:
#   ": You have been slain."           (you)
#   ": <name> has been slain."         (party member)
# Zones: ": You have entered <zone>."
_TAIL = re.compile(r"\] : (.+?)\s*$")
_DEATH_SELF = re.compile(r"^You have been slain\.?$", re.I)
_DEATH_OTHER = re.compile(r"^(\S{1,30}) has been slain\.?$", re.I)
_ZONE = re.compile(r"^You have entered (.+?)\.?$", re.I)


def parse_log_line(line):
    """-> {'kind': 'death'|'zone', ...} or None for anything else."""
    m = _TAIL.search(str(line or ""))
    if not m:
        return None
    msg = m.group(1)
    if _DEATH_SELF.match(msg):
        return {"kind": "death", "who": "you", "raw": msg}
    m2 = _DEATH_OTHER.match(msg)
    if m2:
        return {"kind": "death", "who": m2.group(1), "raw": msg}
    m3 = _ZONE.match(msg)
    if m3:
        return {"kind": "zone", "zone": m3.group(1), "raw": msg}
    return None


def find_client_log(config=None):
    """Locate logs/Client.txt: configured install dir first, then the same
    default locations the installer checks. -> path or None."""
    cands = []
    if config:
        gd = config.get("game_install_dir")
        if gd:
            cands.append(gd)
    cands += [
        r"C:\Program Files (x86)\Steam\steamapps\common\Path of Exile 2",
        r"C:\Program Files (x86)\Grinding Gear Games\Path of Exile 2",
        r"D:\SteamLibrary\steamapps\common\Path of Exile 2",
        r"E:\SteamLibrary\steamapps\common\Path of Exile 2",
    ]
    for c in cands:
        p = os.path.join(c, "logs", "Client.txt")
        if os.path.isfile(p):
            return p
    return None


class ClientLogWatcher:
    """Tail Client.txt from NOW (history is not replayed). poll() returns the
    new death/zone events since the last poll and remembers recent context."""

    CONTEXT_KEEP = 12

    def __init__(self, log_path):
        self.path = log_path
        self.zone = None
        self.recent = []          # last few parsed events, oldest first
        try:
            self._pos = os.path.getsize(log_path)
        except OSError:
            self._pos = 0

    def poll(self):
        events = []
        try:
            size = os.path.getsize(self.path)
            if size < self._pos:          # rotated/truncated: start over
                self._pos = 0
            if size == self._pos:
                return events
            with open(self.path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._pos)
                chunk = f.read()
                self._pos = f.tell()
        except OSError:
            return events
        for line in chunk.splitlines():
            ev = parse_log_line(line)
            if not ev:
                continue
            ev["ts"] = time.time()
            if ev["kind"] == "zone":
                self.zone = ev["zone"]
            ev["zone_at"] = self.zone
            self.recent = (self.recent + [ev])[-self.CONTEXT_KEEP:]
            events.append(ev)
        return events


# ---------------------------------------------------------------------------
# 2. The defensive audit (evidence only: silent about stats PoB didn't give)
# ---------------------------------------------------------------------------

def _num(stats, *names):
    for n in names:
        v = stats.get(n)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def defensive_audit(stats, level=None):
    """PoB PlayerStat dict -> [{'sev','title','why','fix'}], worst first.
    Every rule only fires when the stat is actually present."""
    f = []

    def add(sev, title, why, fix):
        f.append({"sev": sev, "title": title, "why": why, "fix": fix})

    for ele, key in (("Fire", "FireResist"), ("Cold", "ColdResist"),
                     ("Lightning", "LightningResist")):
        r = _num(stats, key)
        if r is None:
            continue
        if r < 75:
            gap = int(75 - r)
            # vs a capped character, damage taken scales (100-r)/25
            extra = int(((100 - r) / 25.0 - 1) * 100)
            add("critical" if gap > 10 else "warn",
                f"{ele} resistance {int(r)}% (cap is 75%)",
                f"You take ~{extra}% more {ele.lower()} damage than a capped "
                f"character — resistance is the single biggest defense in "
                f"the game.",
                f"Find {gap}% {ele.lower()} res on gear/charms — rings, "
                f"amulet and boots carry it cheaply.")
    ch = _num(stats, "ChaosResist")
    if ch is not None:
        if ch < 0:
            add("critical", f"Chaos resistance {int(ch)}% (negative)",
                "Negative chaos res multiplies every chaos/DoT hit — the "
                "classic 'health bar just melted' death.",
                "Get it to at least 0, then push toward +35% with gear "
                "affixes.")
        elif ch < 35:
            add("warn", f"Chaos resistance {int(ch)}%",
                "Chaos damage is common in the endgame and pierces energy "
                "shield.",
                "Suffix chaos res on jewellery is cheap early league.")
    life = _num(stats, "Life")
    es = _num(stats, "EnergyShield") or 0
    lvl = None
    try:
        lvl = float(level) if level else None
    except (TypeError, ValueError):
        pass
    if life is not None and lvl and lvl >= 60 and (life + es) < lvl * 55:
        add("warn", f"Effective pool {int(life + es)} at level {int(lvl)}",
            "The pool is thin for this level — big endgame hits will "
            "one-shot through it regardless of resists.",
            "Prioritize flat life/ES on every gear slot and % life/ES "
            "nodes near your tree path.")
    ehp = _num(stats, "TotalEHP")
    if ehp is not None and ehp < 5000:
        add("warn", f"PoB total eHP {int(ehp)}",
            "Under ~5k eHP most map bosses have a hit that kills from "
            "full.",
            "Layer defenses: pool first, then mitigation (armour/evasion/"
            "block) so the eHP number compounds.")
    arm = _num(stats, "Armour")
    eva = _num(stats, "Evasion")
    if arm is not None and eva is not None and arm < 2000 and eva < 2000 \
            and es < 1000:
        add("warn", "No mitigation layer (low armour, evasion AND ES)",
            "Everything that reaches you lands at full value — the pool "
            "is your only defense and it will not keep up.",
            "Pick ONE layer your gear supports and invest: armour %, "
            "evasion %, or ES recharge.")
    blk = _num(stats, "BlockChance")
    if blk is not None and 0 < blk < 20:
        add("note", f"Block chance {int(blk)}% (token)",
            "A few percent block barely changes outcomes but costs gear "
            "stats.",
            "Either stack block deliberately (shield + passives) or spend "
            "those affixes on res/life.")
    for name, key in (("physical", "PhysicalMaximumHitTaken"),
                      ("fire", "FireMaximumHitTaken"),
                      ("cold", "ColdMaximumHitTaken"),
                      ("lightning", "LightningMaximumHitTaken"),
                      ("chaos", "ChaosMaximumHitTaken")):
        mh = _num(stats, key)
        if mh is not None and mh < 3000:
            add("warn", f"Max {name} hit taken ~{int(mh)}",
                f"Any {name} hit above that number kills from full — "
                f"endgame slams exceed it easily.",
                f"This is your one-shot window; raise it with the pool + "
                f"{name} mitigation.")
    order = {"critical": 0, "warn": 1, "note": 2}
    f.sort(key=lambda x: order.get(x["sev"], 3))
    return f


# ---------------------------------------------------------------------------
# 3. Incidents on disk
# ---------------------------------------------------------------------------

def save_incident(event, clip_path=None, clip_msg="", context=None):
    """-> incident dict (also written to data_engine/deaths/<stamp>/).
    The clip is COPIED next to the record so OBS folder cleanups can't
    orphan it; if the copy fails the original path is kept as a pointer."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    d = os.path.join(DEATHS_DIR, stamp)
    os.makedirs(d, exist_ok=True)
    rec = {
        "stamp": stamp,
        "ts": event.get("ts", time.time()),
        "who": event.get("who", "you"),
        "zone": event.get("zone_at") or "unknown zone",
        "context": [
            {"kind": c.get("kind"), "raw": c.get("raw")}
            for c in (context or [])
        ],
        "clip": None,
        "clip_note": clip_msg,
    }
    if clip_path and os.path.exists(clip_path):
        try:
            dest = os.path.join(d, os.path.basename(clip_path))
            shutil.copy2(clip_path, dest)
            rec["clip"] = dest
        except OSError:
            rec["clip"] = clip_path
            rec["clip_note"] = (clip_msg + " (copy failed; pointing at the "
                                "OBS original)").strip()
    try:
        with open(os.path.join(d, "incident.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(rec, fh, indent=2)
    except OSError:
        pass
    return rec


def recent_incidents(limit=30):
    """Newest first. Missing/corrupt records are skipped, not fatal."""
    out = []
    try:
        stamps = sorted(os.listdir(DEATHS_DIR), reverse=True)[:limit]
    except OSError:
        return out
    for s in stamps:
        p = os.path.join(DEATHS_DIR, s, "incident.json")
        try:
            with open(p, encoding="utf-8") as fh:
                out.append(json.load(fh))
        except (OSError, ValueError):
            continue
    return out


# ---------------------------------------------------------------------------
# 4. Reports
# ---------------------------------------------------------------------------

_SEV_ICON = {"critical": "🟥", "warn": "🟧", "note": "🟨"}


def autopsy_markdown(rec, findings):
    lines = [f"# Death review — {rec.get('zone', '?')}",
             f"_{time.strftime('%Y-%m-%d %H:%M', time.localtime(rec.get('ts', 0)))}"
             f" — {rec.get('who', 'you')} died._", ""]
    if rec.get("clip"):
        lines += [f"Clip: `{rec['clip']}`", ""]
    elif rec.get("clip_note"):
        lines += [f"_No clip: {rec['clip_note']}_", ""]
    if rec.get("context"):
        lines.append("**Just before the death:**")
        lines += [f"- {c.get('raw')}" for c in rec["context"][-6:]]
        lines.append("")
    if findings:
        lines.append("**Defensive audit of the build:**")
        for x in findings:
            lines.append(f"- {_SEV_ICON.get(x['sev'], '•')} **{x['title']}** — "
                         f"{x['why']} _Fix: {x['fix']}_")
    else:
        lines.append("_No defensive gaps found from the PoB numbers — look "
                     "at the clip for a mechanic, not a stat sheet._")
    return "\n".join(lines)


def ai_autopsy_prompt(rec, findings, build_summary=""):
    gaps = "\n".join(f"- [{x['sev']}] {x['title']}: {x['why']}"
                     for x in findings) or "- none found"
    ctx = "\n".join(f"- {c.get('raw')}" for c in rec.get("context", [])[-6:]) \
        or "- (none logged)"
    return (
        "A Path of Exile 2 player just died and wants a plain-words autopsy.\n"
        f"Where: {rec.get('zone', 'unknown zone')}.\n"
        f"Log events just before the death:\n{ctx}\n"
        f"Defensive audit of their Path of Building character:\n{gaps}\n"
        + (f"Build summary:\n{build_summary}\n" if build_summary else "")
        + "\nGiven the zone and these defensive gaps, name the most likely "
          "KIND of thing that killed them (e.g. uncapped-lightning burst, "
          "chaos DoT, physical slam through a thin pool) and give exactly "
          "three concrete fixes ordered by impact-per-cost. Explain every "
          "game term — assume the player may be brand new. If the gaps "
          "don't explain the death, say so honestly and suggest what to "
          "look for in the replay clip."
    )


# ---------------------------------------------------------------------------
# 5. Orchestration (called from the overlay's watcher thread)
# ---------------------------------------------------------------------------

def capture_death(event, context, config=None):
    """Death event -> OBS replay flush -> saved incident. Never raises."""
    cfg = config or {}
    clip, msg = None, "OBS capture not attempted."
    try:
        from core_engine.obs_bridge import capture_replay
        clip, msg = capture_replay(
            host=cfg.get("obs_host", "127.0.0.1"),
            port=cfg.get("obs_port", 4455),
            password=cfg.get("obs_password") or _keyring_password())
    except Exception as e:
        msg = f"OBS capture failed: {e}"
    return save_incident(event, clip_path=clip, clip_msg=msg, context=context)


def _keyring_password():
    try:
        import keyring
        return keyring.get_password("KalandraOverlay", "obs_websocket")
    except Exception:
        return None
