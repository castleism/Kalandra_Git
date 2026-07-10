"""
TESTS/CRAFT_CHECKS.PY — sandbox checks for the Craft Hunter engine (CH-P1).

Covers template matching (exact + OCR-noise fuzzy), ranges, any/all and
hybrid multi-line targets, the stash-regex generator (dialect, 50-char
budget, numeric-range unrolling verified exhaustively), the mod-suggestion
feed, and junk-proofing. No Qt, no network, no OCR — pure engine, same
style as tests/death_checks.py.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [FAIL] {name}")


def guard(name, fn):
    """fn must not raise."""
    try:
        fn()
        check(name, True)
    except Exception as e:
        print(f"  [FAIL] {name}: raised {e}")
        globals()["FAIL"] += 1


from core_engine.craft_hunter import (
    BUILTIN_MOD_LINES, STASH_REGEX_BUDGET, TooltipWatcher,
    _range_alternatives, available_ocr, evaluate_item, frame_signature,
    frames_differ, make_grabber, make_ocr, match_line, match_target,
    mod_suggestions, normalize_mod_line, ocr_normalize, stash_regex,
    template_regex, value_in_range,
)

# ---- normalize -------------------------------------------------------------
check("tags stripped", normalize_mod_line(
    "+45 to maximum Life (augmented) (Tier: 3)") == "+45 to maximum Life")
check("implicit stripped", normalize_mod_line(
    "12% increased Rarity of Items found (implicit)")
    == "12% increased Rarity of Items found")
check("whitespace collapsed",
      normalize_mod_line("  95%   increased  Spell Damage ")
      == "95% increased Spell Damage")
check("junk-safe normalize", normalize_mod_line(None) == "")

# ---- template matching ------------------------------------------------------
ok, v = match_line("#% increased Spell Damage", "104% increased Spell Damage")
check("exact match + value", ok and v == [104.0])
ok, v = match_line("+# to maximum Life", "+45 to maximum Life (Tier: 3)")
check("tagged line still matches", ok and v == [45.0])
ok, v = match_line("+# to maximum Life", "45 to maximum Life")
check("missing printed + tolerated", ok and v == [45.0])
ok, v = match_line("Adds # to # Physical Damage",
                   "Adds 12 to 24 Physical Damage")
check("two-slot template", ok and v == [12.0, 24.0])
ok, _ = match_line("#% increased Spell Damage", "104% increased Cast Speed")
check("different mod rejected", not ok)
ok, _ = match_line("#% increased Spell Damage",
                   "104% increased Spell Damage while Dual Wielding")
check("longer line is a different mod", not ok)
check("case-insensitive",
      match_line("#% INCREASED spell DAMAGE", "104% increased Spell Damage")[0])
ok, v = match_line("#% increased Spell Damage",
                   "104% increaseed Spell Damage")     # OCR-ish typo
check("fuzzy fallback catches OCR noise", ok and v and v[0] == 104.0)
ok, _ = match_line("#% increased Spell Damage", "banana")
check("garbage rejected", not ok)
check("decimal values", match_line("Regenerate # Life per second",
                                   "Regenerate 32.4 Life per second")[1]
      == [32.4])

# ---- ranges ------------------------------------------------------------------
check("no range always passes", value_in_range([], None, None))
check("min inclusive", value_in_range([95.0], 95, None))
check("below min fails", not value_in_range([94.0], 95, None))
check("max inclusive", value_in_range([120.0], None, 120))
check("above max fails", not value_in_range([121.0], None, 120))
check("band", value_in_range([100.0], 95, 120))
check("first slot rules two-slot lines",
      value_in_range([12.0, 24.0], None, 15))
check("range needs a value", not value_in_range([], 95, None))

# ---- match_target: ranges + hybrids -----------------------------------------
T_SPELL = {"mod": "#% increased Spell Damage", "min": 95}
hit, _ = match_target(T_SPELL, ["104% increased Spell Damage"])
check("target hit in range", hit)
hit, why = match_target(T_SPELL, ["88% increased Spell Damage"])
check("right mod low roll = no hit", not hit and "88" in why)
hit, _ = match_target({"mod": "#% increased Spell Damage"},
                      ["3% increased Spell Damage"])
check("no-range target hits any roll", hit)
hybrid = {"mod": ["#% increased Spell Damage",
                  "+# to Level of all Spell Skills"], "min": 90}
hit, _ = match_target(hybrid, ["95% increased Spell Damage",
                               "+2 to Level of all Spell Skills",
                               "+40 to maximum Mana"])
check("hybrid: both lines present = hit", hit)
hit, why = match_target(hybrid, ["95% increased Spell Damage"])
check("hybrid: one line missing = no hit", not hit and "missing" in why)
hit, _ = match_target({"mod": "", "min": 1}, ["+45 to maximum Life"])
check("empty target never hits", not hit)

# ---- evaluate_item: any / all -------------------------------------------------
targets = [{"mod": "#% increased Spell Damage", "min": 95},
           {"mod": "+# to Level of all Spell Skills", "min": 2}]
mods_hit1 = ["104% increased Spell Damage", "+38 to maximum Mana"]
res = evaluate_item(targets, mods_hit1, mode="any")
check("any: one hit fires", res["checked"] and res["hit"])
res = evaluate_item(targets, mods_hit1, mode="all")
check("all: one hit does not fire", res["checked"] and not res["hit"])
res = evaluate_item(targets, ["104% increased Spell Damage",
                              "+3 to Level of all Spell Skills"], mode="all")
check("all: both hits fire", res["hit"])
check("per-target results reported", len(res["results"]) == 2
      and all(len(r) == 3 for r in res["results"]))
res = evaluate_item([], ["+45 to maximum Life"])
check("no targets = not checked", not res["checked"] and not res["hit"])
res = evaluate_item(targets, [])
check("no mods = checked, no hit", res["checked"] and not res["hit"])
guard("junk targets never crash", lambda: evaluate_item(
    [None, 42, {"mod": None}, {"mod": ["x", None]}, {"min": "banana"}],
    ["+45 to maximum Life"]))
guard("junk mod lines never crash", lambda: evaluate_item(
    targets, [None, 42, "", "()[]{}\\"]))

# ---- numeric range unrolling (exhaustive) -------------------------------------
for lo, hi, top in ((95, None, 999), (5, None, 999), (20, 35, 35),
                    (1, 100, 100), (150, 220, 220), (7, 7, 7),
                    (100, None, 999), (17, 230, 230)):
    alts = _range_alternatives(lo, hi)
    rx = re.compile("^(?:" + "|".join(alts) + ")$")
    bad = [v for v in range(0, 1300)
           if bool(rx.match(str(v))) != (lo <= v <= top)]
    check(f"range {lo}..{hi or 'open'} exact (alts: {'|'.join(alts)})",
          not bad)
    check(f"range {lo}..{hi or 'open'} dialect-safe tokens only",
          not re.search(r"[(){}+?^$]", "".join(alts)))
check("spec example scale: 95+ compact",
      len("|".join(_range_alternatives(95, None))) <= 20)
check("no range = no alternatives", _range_alternatives(None, None) == [])
check("inverted range tolerated", _range_alternatives(35, 20)
      == _range_alternatives(20, 35))
check("junk bounds fail soft", _range_alternatives("banana", None) == [])
check("fractional min rounds up (94.5 must not light 94)",
      not re.compile("^(?:" + "|".join(_range_alternatives(94.5, None))
                     + ")$").match("94"))
guard("junk min on a real mod never crashes the generator",
      lambda: stash_regex([{"mod": "+# to maximum Life", "min": "banana"}]))

# ---- stash regex ---------------------------------------------------------------
rx, notes = stash_regex([{"mod": "#% increased Spell Damage", "min": 95}])
check("regex within budget", 0 < len(rx) <= STASH_REGEX_BUDGET)
check("regex unrolls the range", "9[5-9]" in rx and "|" in rx)
check("anchor repeated per alternative (no groups)", "(" not in rx)
check("in-budget regex has no notes", notes == [])

rx, notes = stash_regex([{"mod": "#% increased Spell Damage", "min": 95},
                         {"mod": "+# to Level of all Spell Skills", "min": 2}])
check("two targets still within budget", 0 < len(rx) <= STASH_REGEX_BUDGET)
check("similar mods get distinct anchors", "spell damage" in rx
      and "spell skills" in rx)
check("dropped ranges are reported", any("ranges dropped" in n for n in notes))

rx, notes = stash_regex([{"mod": "+# to maximum Life", "min": 100, "max": 120},
                         {"mod": "+#% to Fire Resistance", "min": 40},
                         {"mod": "#% increased Attack Speed"},
                         {"mod": "#% increased Critical Damage Bonus"},
                         {"mod": "+# to maximum Mana"}])
check("five targets still within budget", 0 < len(rx) <= STASH_REGEX_BUDGET)

rx, notes = stash_regex([{"mod": "#% increased Attack Speed"}])
check("no-range target quotes its phrase", rx == '"attack speed"')
rx, _ = stash_regex([{"mod": "+# to maximum Life"}])
check("single-word anchor unquoted", rx == "life")
rx, _ = stash_regex([{"mod": "#% increased Spell Damage"},
                     {"mod": "#% increased Spell Damage"}])
check("duplicate targets collapse", rx == '"spell damage"')
check("no targets = empty regex", stash_regex([]) == ("", []))
guard("junk targets never crash the generator",
      lambda: stash_regex([{"mod": None}, {"mod": "###", "min": "x"}, {}]))
rx, _ = stash_regex([{"mod": "Adds # to # Physical Damage", "min": 20}])
check("range anchors stay within budget", len(rx) <= STASH_REGEX_BUDGET)

# ---- clipboard round trip (parse_item_text -> evaluate) ------------------------
from core_engine.trade_tools import parse_item_text

CLIP = """Item Class: Wands
Rarity: Rare
Storm Song
Attuned Wand
--------
Requirements:
Level: 58
Int: 120
--------
Item Level: 81
--------
Adds 4 to 7 Physical Damage (implicit)
--------
104% increased Spell Damage
+2 to Level of all Spell Skills
+38 to maximum Mana
12% increased Cast Speed
"""
info = parse_item_text(CLIP)
res = evaluate_item([{"mod": "#% increased Spell Damage", "min": 95}],
                    info.get("mods") or [])
check("clipboard round trip: hit", res["checked"] and res["hit"])
res = evaluate_item([{"mod": "#% increased Spell Damage", "min": 120}],
                    info.get("mods") or [])
check("clipboard round trip: false alarm", res["checked"] and not res["hit"])

# ---- near-miss (CH-P3) -----------------------------------------------------------
res = evaluate_item([{"mod": "#% increased Spell Damage", "min": 95}],
                    ["88% increased Spell Damage"])
check("near miss flagged", res["near_miss"] and not res["hit"])
res = evaluate_item([{"mod": "#% increased Spell Damage", "min": 95}],
                    ["+45 to maximum Life"])
check("wrong mod is not a near miss", not res["near_miss"])
res = evaluate_item([{"mod": "#% increased Spell Damage", "min": 95},
                     {"mod": "+# to maximum Life", "min": 200}],
                    ["104% increased Spell Damage", "+45 to maximum Life"])
check("a real hit silences near-miss", res["hit"] and not res["near_miss"])

# ---- OCR normalization (CH-P2) -----------------------------------------------------
check("O->0 inside numbers", ocr_normalize("1O4% increased Spell Damage")
      == "104% increased Spell Damage")
check("l->1 with sign", ocr_normalize("+l5 to maximum Life")
      == "+15 to maximum Life")
check("all-confusable token fixed", ocr_normalize("Adds lO to 24 Physical "
      "Damage") == "Adds 10 to 24 Physical Damage")
check("words never mangled", ocr_normalize("Orb of Alchemy")
      == "Orb of Alchemy")
check("Ilo words survive", ocr_normalize("+12% to Cold Resistance")
      == "+12% to Cold Resistance")
check("ocr text strips tags too", ocr_normalize("+45 to maximum Life "
      "(augmented)") == "+45 to maximum Life")
check("junk-safe ocr_normalize", ocr_normalize(None) == "")
ok, v = match_line("#% increased Spell Damage",
                   ocr_normalize("1O4% increased Spell Damage"))
check("normalized OCR line matches with the right value", ok and v == [104.0])

# ---- frame signatures (CH-P2) --------------------------------------------------------
A = bytes(range(256)) * 64
B = bytearray(A); B[0:4096] = b"\xff" * 4096
check("identical frames hash identically",
      frame_signature(A) == frame_signature(bytes(A)))
check("changed frames differ",
      frames_differ(frame_signature(A), frame_signature(bytes(B))))
check("signature accepts lists", isinstance(frame_signature([1, 2, 3]), int))
check("empty frame safe", frame_signature(b"") == 0)
check("junk frame safe", frame_signature(object()) == 0)
check("small hamming below threshold is 'same'",
      not frames_differ(0b1111, 0b1110, bits=6))

# ---- ocr factories fail soft (CH-P2) ---------------------------------------------------
kind, msg = available_ocr()
check("available_ocr returns a pair", isinstance(msg, str) and msg)
check("make_ocr consistent with probe",
      (make_ocr() is None) == (kind is None))
check("tiny region rejected",
      make_grabber({"left": 0, "top": 0, "width": 4, "height": 4}) is None)
guard("junk region fails soft", lambda: make_grabber({"left": "x"}))

# ---- TooltipWatcher loop (CH-P2, fully injected) ----------------------------------------
FRAME_MISS = b"\x10" * 4096
FRAME_HIT = b"\xf0" * 2048 + b"\x00" * 2048
script = {FRAME_MISS: "88% increased 5pell Damage",     # OCR-noisy miss
          FRAME_HIT: "1O4% increased Spell Damage"}     # OCR-noisy hit
feed = [FRAME_MISS, FRAME_MISS, FRAME_HIT, FRAME_HIT]
state = {"i": 0}


def _grab():
    f = feed[min(state["i"], len(feed) - 1)]
    state["i"] += 1
    return f


alarms = []
w = TooltipWatcher([{"mod": "#% increased Spell Damage", "min": 95}],
                   grab=_grab, ocr=lambda f: script[bytes(f)],
                   on_alarm=alarms.append)
seq = [w.poll_once() for _ in range(5)]
check("watcher sequence near-miss -> skip -> hit -> paused",
      seq[0] == "near-miss" and seq[1] == "unchanged"
      and seq[2] == "hit" and seq[3] == "paused" and seq[4] == "paused")
check("alarm fired exactly once", len(alarms) == 1 and alarms[0]["hit"])
check("hash-skip really skipped OCR", w.stats["ocr_calls"] == 2
      and w.stats["skipped"] == 1)
w.resume()
check("resume clears pause AND signature", w.poll_once() == "hit"
      and len(alarms) == 2)

w2 = TooltipWatcher([], grab=_grab, ocr=lambda f: "")
check("no targets = not configured", w2.poll_once() == "not-configured")
w3 = TooltipWatcher([{"mod": "+# to maximum Life"}], grab=lambda: None,
                    ocr=lambda f: "")
check("no frame fails soft", w3.poll_once() == "no-frame")
w4 = TooltipWatcher([{"mod": "+# to maximum Life"}], grab=_grab,
                    ocr=lambda f: "", foreground=lambda: False)
check("foreground gate idles", w4.poll_once() == "game-not-foreground")
boom = TooltipWatcher([{"mod": "+# to maximum Life"}],
                      grab=lambda: b"\x01" * 512,
                      ocr=lambda f: 1 / 0)
check("ocr exception fails soft", boom.poll_once().startswith("ocr-error"))
alarm_boom = TooltipWatcher([{"mod": "+# to maximum Life"}],
                            grab=lambda: b"\x02" * 512,
                            ocr=lambda f: "+45 to maximum Life",
                            on_alarm=lambda r: 1 / 0)
guard("alarm callback exception contained",
      lambda: alarm_boom.poll_once())
fresh = TooltipWatcher([{"mod": "+# to maximum Life"}], grab=lambda: None,
                       ocr=lambda f: "")
check("thread starts", fresh.start() is True)
check("double start refused", fresh.start() is False)
fresh.stop()
check("restart after stop allowed", fresh.start() is True)
fresh.stop()

# ---- suggestions ----------------------------------------------------------------
s = mod_suggestions(None)
check("builtin suggestions exist", len(s) >= 50)
check("builtin suggestions are templates", all("#" in x for x in s))
check("no dupes in suggestions", len(s) == len(set(s)))
s2 = mod_suggestions("/definitely/not/a/real/path.db")
check("missing DB fails soft to builtins", s2[:len(BUILTIN_MOD_LINES)]
      == list(BUILTIN_MOD_LINES))

print(f"RESULT: {PASS} passed, {FAIL} failed")
print("ALL GREEN" if FAIL == 0 else "NOT GREEN")
sys.exit(1 if FAIL else 0)
