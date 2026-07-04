"""
CORE_ENGINE/CHARACTER_SHEET.PY  --  Shareable character page. (W3-12 v1)

Builds a themed, self-contained HTML page from the overlay's parsed build
view — like a poe.ninja character profile, except the numbers come from the
LOCAL Path of Building parse/sim, so a Corrupted Blood character shows its
real DoT DPS instead of a website's zero.

Pure string building: no PyQt, no network — fully unit-testable.
"""

import html as _html
from datetime import datetime

_CSS = """
body { background:#0c0e12; color:#e8e6df; font-family:'Segoe UI',sans-serif;
       max-width:980px; margin:24px auto; padding:0 16px; }
h1 { color:#c8aa6e; letter-spacing:1px; border-bottom:2px solid #8a6d3b;
     padding-bottom:8px; }
h2 { color:#c8aa6e; margin-top:28px; }
.meta { color:#9aa4b2; }
.chips { display:flex; flex-wrap:wrap; gap:10px; margin:16px 0; }
.chip { background:#14181f; border:1px solid #8a6d3b; border-radius:8px;
        padding:8px 14px; }
.chip b { color:#f0d9a8; display:block; font-size:18px; }
.chip span { color:#9aa4b2; font-size:12px; }
table { border-collapse:collapse; width:100%; background:#14181f; }
th { color:#c8aa6e; text-align:left; padding:8px 10px;
     border-bottom:1px solid #8a6d3b; }
td { padding:7px 10px; border-bottom:1px solid #232a35; vertical-align:top; }
.slot { color:#c8aa6e; white-space:nowrap; }
.mods { color:#8fa0c0; font-size:13px; }
.main { color:#f0d9a8; font-weight:bold; }
.sup { color:#9aa4b2; }
.note { color:#7d8694; font-size:12px; margin-top:26px;
        border-top:1px solid #232a35; padding-top:10px; }
"""

# Which PlayerStats become headline chips, in display order.
_CHIP_STATS = [
    ("CombinedDPS", "Combined DPS"), ("TotalDPS", "Total DPS"),
    ("TotalDot", "DoT DPS"), ("Life", "Life"), ("EnergyShield", "Energy Shield"),
    ("Mana", "Mana"), ("Armour", "Armour"), ("Evasion", "Evasion"),
    ("CritChance", "Crit Chance"), ("CritMultiplier", "Crit Multi"),
    ("Str", "STR"), ("Dex", "DEX"), ("Int", "INT"),
]


def _fmt(v):
    try:
        f = float(v)
        if abs(f) >= 10000:
            return f"{f:,.0f}"
        if abs(f) >= 100:
            return f"{f:,.0f}"
        return f"{f:g}"
    except (TypeError, ValueError):
        return _html.escape(str(v))


def build_character_sheet_html(view, embedded=False):
    """view = overlay.current_build_view() dict. Returns a full HTML page.
    embedded=True emits QTextBrowser-safe markup (Qt's rich-text engine has
    no flexbox, so the stat chips become a styled table row) — this powers
    the Build (PoB) tab's one-page, poe.ninja-style container view."""
    view = view or {}
    full = view.get("full") if isinstance(view.get("full"), dict) else {}
    name = view.get("character") or "Exile"
    cls = full.get("class_name", "?")
    asc = full.get("ascendancy", "None")
    lvl = full.get("level", "?")
    main = full.get("main_skill") or ""
    stats = full.get("stats") or {}

    out = ["<!DOCTYPE html><html><head><meta charset='utf-8'>",
           f"<title>{_html.escape(str(name))} — Kalandra character sheet</title>",
           f"<style>{_CSS}</style></head><body>"]
    out.append(f"<h1>{_html.escape(str(name))}</h1>")
    out.append(f"<div class='meta'>{_html.escape(str(cls))} / "
               f"{_html.escape(str(asc))} · Level {_html.escape(str(lvl))}"
               + (f" · main skill <b style='color:#f0d9a8;'>"
                  f"{_html.escape(str(main))}</b>" if main else "")
               + "</div>")

    # Honest numbers, front and center.
    chips = []
    for key, label in _CHIP_STATS:
        v = stats.get(key)
        if v in (None, "", "0", "0.0"):
            continue
        chips.append(f"<div class='chip'><b>{_fmt(v)}</b>"
                     f"<span>{label}</span></div>")
        if len(chips) >= 10:
            break
    if chips and embedded:
        # QTextBrowser: chips as a one-row table with inline styles.
        cells = []
        for key, label in _CHIP_STATS:
            v = stats.get(key)
            if v in (None, "", "0", "0.0"):
                continue
            cells.append(
                "<td style='background:#14181f;border:1px solid #8a6d3b;"
                "padding:6px 12px;'>"
                f"<b style='color:#f0d9a8;font-size:16px;'>{_fmt(v)}</b><br>"
                f"<span style='color:#9aa4b2;font-size:11px;'>{label}</span></td>")
            if len(cells) >= 10:
                break
        out.append("<table cellspacing='6'><tr>" + "".join(cells[:5])
                   + "</tr><tr>" + "".join(cells[5:]) + "</tr></table>")
    elif chips:
        out.append("<div class='chips'>" + "".join(chips) + "</div>")
    # Resistances line (poe.ninja shows these front and center).
    res_bits = []
    for key, label, col in (("FireResist", "Fire", "#e87284"),
                            ("ColdResist", "Cold", "#7aa2e8"),
                            ("LightningResist", "Lightning", "#f0d9a8"),
                            ("ChaosResist", "Chaos", "#c98ae8")):
        v = stats.get(key)
        if v not in (None, ""):
            res_bits.append(f"<b style='color:{col};'>{_fmt(v)}%</b> {label}")
    if res_bits:
        out.append("<div class='meta'>Resistances: " + " · ".join(res_bits)
                   + "</div>")
    # Scaling profile (computed from the parse — see pob_bridge).
    sc = view.get("scaling") or {}
    if sc.get("damage_types") or sc.get("mechanics"):
        bits = []
        if sc.get("damage_types"):
            bits.append("scales via <b style='color:#f0d9a8;'>"
                        + _html.escape(", ".join(sc["damage_types"][:3])) + "</b>")
        if sc.get("mechanics"):
            bits.append("mechanics: "
                        + _html.escape(", ".join(sc["mechanics"][:4])))
        bits.append("crit-based" if sc.get("crit_based") else "non-crit")
        out.append("<div class='meta'>Profile: " + " · ".join(bits) + "</div>")
    if view.get("sim"):
        out.append(f"<div class='meta'>Live PoB engine: "
                   f"{_html.escape(str(view['sim']))}</div>")

    items = full.get("items") or []
    if items:
        out.append("<h2>Equipment</h2><table><tr><th>Slot</th><th>Item</th>"
                   "<th>Mods</th></tr>")
        for it in items:
            mods = " · ".join(_html.escape(m) for m in (it.get("mods") or []))
            out.append(f"<tr><td class='slot'>{_html.escape(str(it.get('slot', '—')))}"
                       f"</td><td>{_html.escape(str(it.get('name', '?')))}</td>"
                       f"<td class='mods'>{mods}</td></tr>")
        out.append("</table>")

    skills = full.get("skills") or []
    if skills:
        out.append("<h2>Skills</h2><table><tr><th>Skill</th>"
                   "<th>Supports</th></tr>")
        for grp in skills:
            if not isinstance(grp, dict):
                continue
            klass = "main" if grp.get("is_main") else ""
            star = "★ " if grp.get("is_main") else ""
            sups = ", ".join(_html.escape(str(s))
                             for s in (grp.get("supports") or []))
            out.append(f"<tr><td class='{klass}'>{star}"
                       f"{_html.escape(str(grp.get('active', '?')))}</td>"
                       f"<td class='sup'>{sups}</td></tr>")
        out.append("</table>")

    out.append(f"<div class='note'>Generated by Kalandra "
               f"{datetime.now().strftime('%Y-%m-%d %H:%M')} · stats from the "
               f"player's own Path of Building data — DoT/DPS numbers are the "
               f"build's real configured output, not a ladder site's guess.</div>")
    out.append("</body></html>")
    return "\n".join(out)
