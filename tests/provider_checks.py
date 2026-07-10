"""
TESTS/PROVIDER_CHECKS.PY — sandbox checks for the provider-boundary seam
(core_engine/providers.py, W4-00) and the provider-boundary auditor routine.

Covers: every declared capability resolves to a registered default impl,
each default is (or degrades to) the right ABC, available()/methods never
raise, set_provider() swap-in works, and the item_in_hand seam specifically
(2026-07-10 migration) — headless available()==False, read() fails soft,
and the mirror_window call site no longer touches QApplication.clipboard()
or trade_tools.parse_item_text directly. No Qt, no network.
"""

import ast
import os
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


from core_engine import providers as P

# ---- registry shape ---------------------------------------------------------
caps = P.capabilities()
check("capabilities() lists item_in_hand", "item_in_hand" in caps)
check("capabilities() is sorted", caps == sorted(caps))

for cap in caps:
    inst = P.get_provider(cap)
    check(f"{cap}: resolves to an instance", inst is not None)
    check(f"{cap}: is a Provider", isinstance(inst, P.Provider))
    guard(f"{cap}: available() doesn't raise", lambda inst=inst: inst.available())
    check(f"{cap}: get_provider is a singleton", P.get_provider(cap) is inst)

check("unknown capability -> None", P.get_provider("not_a_real_provider") is None)

# ---- set_provider swap-in ----------------------------------------------------
class _FakeEconomy(P.EconomyProvider):
    def currency_rates(self, league):
        return {"Divine Orb": 200.0}


P.set_provider("economy", _FakeEconomy())
econ = P.get_provider("economy")
check("set_provider swaps the singleton", isinstance(econ, _FakeEconomy))
check("swapped provider serves calls", econ.currency_rates("Standard") == {"Divine Orb": 200.0})

# ---- item_in_hand: the ABC ----------------------------------------------------
check("ItemInHandProvider is a Provider subclass",
      issubclass(P.ItemInHandProvider, P.Provider))
check("ItemInHandProvider.read is abstract",
      getattr(P.ItemInHandProvider.read, "__isabstractmethod__", False))


def _no_instantiate_abc():
    P.ItemInHandProvider()


try:
    _no_instantiate_abc()
    check("bare ItemInHandProvider can't be instantiated", False)
except TypeError:
    check("bare ItemInHandProvider can't be instantiated", True)

# ---- item_in_hand: the default clipboard adapter, headless (no QApplication) --
clip = P.ClipboardItemInHand()
check("headless: available() is False (no QApplication)", clip.available() is False)
info, txt = clip.read()
check("headless: read() fails soft to (None, '')", info is None and txt == "")

# get_provider registers the same default class
default_item_in_hand = P.get_provider("item_in_hand")
check("registry default is ClipboardItemInHand",
      isinstance(default_item_in_hand, P.ClipboardItemInHand))

# ---- item_in_hand: parsing logic (exercised directly, no Qt needed) -----------
FAKE_APP = None


class _FakeClipboard:
    def __init__(self, text):
        self._text = text

    def text(self):
        return self._text


class _StubbedClip(P.ClipboardItemInHand):
    def __init__(self, text):
        super().__init__()
        self._stub_text = text

    def _clipboard_text(self):
        return self._stub_text


ITEM_TEXT = (
    "Item Class: Boots\n"
    "Rarity: Rare\n"
    "Hollow Ward\n"
    "Slink Boots\n"
    "--------\n"
    "Requirements:\n"
    "Level: 60\n"
    "--------\n"
    "Item Level: 82\n"
    "--------\n"
    "+45 to maximum Life\n"
    "20% increased Movement Speed\n"
)

info, txt = _StubbedClip(ITEM_TEXT).read()
check("real item text -> parsed info", info is not None and info.get("name") == "Hollow Ward")
check("real item text -> raw text passed through", txt == ITEM_TEXT)

info, txt = _StubbedClip("just some regular copied text, not an item").read()
check("non-item clipboard text -> info is None", info is None)
check("non-item clipboard text -> raw text still returned (for debounce)", bool(txt))

info, txt = _StubbedClip("").read()
check("empty clipboard -> (None, '')", info is None and txt == "")

info, txt = _StubbedClip("x" * 5000).read()
check("oversized clipboard text rejected", info is None)

# ---- call-site check: mirror_window no longer bypasses the seam --------------
mw_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "gui_overlay", "mirror_window.py")
with open(mw_path, "r", encoding="utf-8") as f:
    mw_src = f.read()

tree = ast.parse(mw_src)
fn = next((n for n in ast.walk(tree)
           if isinstance(n, ast.FunctionDef) and n.name == "_on_clipboard_item"), None)
check("_on_clipboard_item still exists", fn is not None)
if fn is not None:
    body_src = ast.get_source_segment(mw_src, fn) or ""
    check("_on_clipboard_item uses get_provider('item_in_hand')",
          'get_provider("item_in_hand")' in body_src)
    check("_on_clipboard_item no longer calls QApplication.clipboard() directly",
          "QApplication.clipboard()" not in body_src)
    check("_on_clipboard_item no longer imports parse_item_text directly",
          "parse_item_text" not in body_src)

print(f"RESULT: {PASS} passed, {FAIL} failed")
print("ALL GREEN" if FAIL == 0 else "NOT GREEN")
sys.exit(1 if FAIL else 0)
