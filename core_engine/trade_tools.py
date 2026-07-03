"""
CORE_ENGINE/TRADE_TOOLS.PY
Pure, dependency-free helpers for the Price Check / Live Search / Crafting tabs.
No PyQt, no network — just text parsing and URL building, so they're unit-testable
and reusable. The GUI layer (gui_overlay/dashboard.py) imports these.

Everything here is ToS-clean: we parse the item text the game itself puts on the
clipboard (Ctrl+C in-game) and build a link to the OFFICIAL trade site. We never
automate buying, never fabricate prices, and never log in for the user.
"""

from urllib.parse import quote


def is_number(v):
    try:
        float(v)
        return True
    except Exception:
        return False


def parse_item_text(text):
    """Parse the clipboard text PoE2 produces on Ctrl+C over an item.

    Sections are separated by lines made only of dashes. The first section is the
    header (Item Class / Rarity / name / base); later sections hold requirements,
    item level, and the explicit/implicit mods. Returns a dict with keys:
    rarity, name, base, item_class, ilvl, mods(list). Always returns a dict.
    """
    info = {"rarity": "", "name": "", "base": "", "item_class": "", "ilvl": "",
            "mods": []}
    if not text or not str(text).strip():
        return info
    raw_lines = [ln.rstrip("\r") for ln in str(text).split("\n")]

    sections, cur = [], []
    for ln in raw_lines:
        stripped = ln.strip()
        if stripped and set(stripped) == {"-"}:
            sections.append(cur)
            cur = []
        else:
            cur.append(ln)
    if cur:
        sections.append(cur)

    header = sections[0] if sections else []
    for ln in header:
        s = ln.strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith("item class:"):
            info["item_class"] = s.split(":", 1)[1].strip()
        elif low.startswith("rarity:"):
            info["rarity"] = s.split(":", 1)[1].strip()
        elif not info["name"]:
            info["name"] = s
        elif not info["base"]:
            info["base"] = s

    # Normal / Magic items have no unique name — the "name" line is the base.
    if info["rarity"].lower() in ("normal", "magic") and not info["base"]:
        info["base"] = info["name"]
        info["name"] = ""

    for sec in sections[1:]:
        for ln in sec:
            s = ln.strip()
            if not s:
                continue
            low = s.lower()
            if low.startswith("item level:"):
                info["ilvl"] = s.split(":", 1)[1].strip()
                continue
            if (low.startswith("requirements") or low.startswith("level ")
                    or low.startswith("level:") or low.startswith("sockets:")
                    or low.startswith("str") or low.startswith("dex")
                    or low.startswith("int")):
                continue
            if (any(ch.isdigit() for ch in s) or low.startswith("+")
                    or "increased" in low or "reduced" in low
                    or " to " in low or "(implicit)" in low or "(rune)" in low):
                info["mods"].append(s)
    return info


def trade_search_url(info, league):
    """The official PoE2 trade search page for a league. The site needs a POST to
    prefill a query, so we open the search page for the right league; the parsed
    item name/base is shown to the user to type/confirm. Guarantees correct site
    and league with zero automation."""
    league = (league or "Standard").strip() or "Standard"
    return f"https://www.pathofexile.com/trade2/search/poe2/{quote(league)}"


def live_search_url(league):
    league = (league or "Standard").strip() or "Standard"
    return f"https://www.pathofexile.com/trade2/search/poe2/{quote(league)}"


def offline_craft_guidance(goal):
    return (
        "Crafting plan (offline heuristic — connect an AI brain in Settings for a "
        "tailored, step-by-step plan):\n\n"
        f"Goal: {goal}\n\n"
        "General PoE2 approach:\n"
        "  1. Pick the right base: item level high enough for the tiers you want, "
        "and the correct base type for your damage/defense.\n"
        "  2. Normal -> Magic: Orb of Transmutation, then Augmentation for a "
        "second mod.\n"
        "  3. Magic -> Rare: Regal Orb adds a third mod.\n"
        "  4. Targeted mods: Essences for a guaranteed mod, Runes/Soul Cores for "
        "socketed effects, and Omens to bias outcomes.\n"
        "  5. Finish: Exalted Orbs add mods to a rare; Chaos Orbs reroll a single "
        "mod; Divine Orbs reroll numeric values within tier.\n\n"
        "For exact probabilities and cost, open Craft of Exile — it simulates the "
        "deterministic odds for your chosen base and mods.")


if __name__ == "__main__":
    sample = """Item Class: Spears
Rarity: Rare
Bramble Fang
Bronze Spear
--------
Requirements:
Level: 45
Str: 80
--------
Item Level: 72
--------
Adds 12 to 24 Physical Damage
18% increased Attack Speed
+45 to maximum Life
"""
    info = parse_item_text(sample)
    assert info["rarity"] == "Rare", info
    assert info["name"] == "Bramble Fang", info
    assert info["base"] == "Bronze Spear", info
    assert info["ilvl"] == "72", info
    assert any("Attack Speed" in m for m in info["mods"]), info
    print("parse OK:", info)
    print("url:", trade_search_url(info, "Standard"))
