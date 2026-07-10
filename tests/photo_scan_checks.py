"""
TESTS/PHOTO_SCAN_CHECKS.PY — sandbox checks for the photo item scanner
engine (W3-33).

Covers engine selection/fallback ordering (AI vision vs offline OCR),
missing/corrupt-file handling, the 2x upscale helper, and available_engines
reporting. The AI-vision engine is a plain injected callable (the GUI wires
it to VoiceEngine.ai_read_image) so these checks never touch a network or
an API key; the OCR engine is exercised via a monkeypatched
core_engine.craft_hunter (same injection spirit as tests/craft_checks.py's
TooltipWatcher checks) since this sandbox has neither RapidOCR nor
Tesseract installed. No Qt, no network, no real OCR install required.
"""

import os
import sys
import tempfile

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


import core_engine.craft_hunter as ch
from core_engine.photo_scanner import (
    _VISION_PROMPT, available_engines, scan_item_photo,
)

# ---- missing file ------------------------------------------------------
res = scan_item_photo("Z:/does/not/exist.png")
check("missing file: no text", res["text"] == "")
check("missing file: engine None", res["engine"] is None)
check("missing file: error set", "not found" in (res["error"] or ""))
check("junk path safe", scan_item_photo(None)["error"])

# ---- AI-vision engine (pure injection, no network) ----------------------
with tempfile.TemporaryDirectory() as td:
    img_path = os.path.join(td, "tooltip.png")
    with open(img_path, "wb") as f:
        f.write(b"not a real image -- AI path never decodes it locally")

    calls = []

    def _good_ai(path, instruction):
        calls.append((path, instruction))
        return "Item Class: Rings\nRarity: Unique\nRing of Testing"

    res = scan_item_photo(img_path, ai_vision=_good_ai, prefer="ai")
    check("ai engine: text returned", "Ring of Testing" in res["text"])
    check("ai engine: engine tag", res["engine"] == "ai")
    check("ai engine: no error", res["error"] is None)
    check("ai engine: called with the image path", calls and calls[0][0] == img_path)
    check("ai engine: sent the PoE2 vision prompt", calls[0][1] == _VISION_PROMPT)

    def _empty_ai(path, instruction):
        return ""

    res = scan_item_photo(img_path, ai_vision=_empty_ai, prefer="ai")
    check("ai engine empty: no text", res["text"] == "")
    check("ai engine empty: engine None", res["engine"] is None)
    check("ai engine empty: error mentions ai", "ai:" in (res["error"] or ""))

    def _boom_ai(path, instruction):
        raise RuntimeError("provider down")

    res = scan_item_photo(img_path, ai_vision=_boom_ai, prefer="ai")
    check("ai engine raises: caught, not propagated", "provider down" in (res["error"] or ""))

    # prefer="ocr" must NEVER touch the (working) ai_vision callable.
    ocr_calls = []
    res = scan_item_photo(img_path, ai_vision=_good_ai, prefer="ocr")
    check("prefer=ocr ignores ai_vision", "Ring of Testing" not in res["text"])
    check("prefer=ocr: error mentions ocr (no engine installed here)",
          "ocr:" in (res["error"] or ""))

    # auto: with a working ai_vision, AI wins and OCR (which would fail on
    # this non-image file) is never reached.
    res = scan_item_photo(img_path, ai_vision=_good_ai, prefer="auto")
    check("auto prefers ai when both could run", res["engine"] == "ai")

    # auto: ai_vision present but empty -> falls back to OCR; both engines
    # fail in this sandbox (no OCR installed) so both show up in the error.
    res = scan_item_photo(img_path, ai_vision=_empty_ai, prefer="auto")
    check("auto falls back to ocr on empty ai result", res["engine"] is None)
    check("auto fallback error names both engines",
          "ai:" in res["error"] and "ocr:" in res["error"])

    # auto: no ai_vision at all -> OCR-only path (still degrades honestly).
    res = scan_item_photo(img_path, ai_vision=None, prefer="auto")
    check("auto with no ai_vision is ocr-only",
          res["engine"] is None and "ocr:" in res["error"] and "ai:" not in res["error"])

# ---- available_engines ---------------------------------------------------
kind, _msg = ch.available_ocr()
eng_none = available_engines(None)
check("no ai_vision -> no 'ai' entry", all(k != "ai" for k, _ in eng_none))
check("available_engines matches available_ocr (none installed here)",
      ("ocr" in [k for k, _ in eng_none]) == (kind is not None))

eng_with_ai = available_engines(lambda p, i: "x")
check("ai_vision wired -> 'ai' listed first", eng_with_ai and eng_with_ai[0][0] == "ai")

# ---- OCR path via a monkeypatched craft_hunter (no real engine needed) ---
_orig_available_ocr = ch.available_ocr
_orig_make_ocr = ch.make_ocr
try:
    import cv2
    import numpy as np

    ocr_seen = {}

    def _fake_available_ocr():
        return "fake", "OCR: fake engine"

    def _fake_make_ocr():
        def _run(img):
            ocr_seen["shape"] = img.shape
            return "Item Class: Amulets\nMocked Amulet"
        return _run

    ch.available_ocr = _fake_available_ocr
    ch.make_ocr = _fake_make_ocr

    with tempfile.TemporaryDirectory() as td:
        img_path = os.path.join(td, "snap.png")
        blank = np.zeros((40, 80, 3), dtype="uint8")
        cv2.imwrite(img_path, blank)

        res = scan_item_photo(img_path, ai_vision=None, prefer="ocr")
        check("ocr path: mocked text returned", "Mocked Amulet" in res["text"])
        check("ocr path: engine tag", res["engine"] == "ocr")
        check("ocr path: 2x upscale reached the engine",
              ocr_seen.get("shape") == (80, 160, 3))

        # auto with a working ai_vision should NOT reach OCR even though it
        # would succeed here too.
        res = scan_item_photo(img_path, ai_vision=lambda p, i: "AI won", prefer="auto")
        check("auto: ai still wins over a working ocr", res["engine"] == "ai")

        # corrupt/non-image file, OCR "available" -> clean error, not a crash.
        bad_path = os.path.join(td, "bad.png")
        with open(bad_path, "wb") as f:
            f.write(b"\x00\x01\x02 not an image")
        res = scan_item_photo(bad_path, prefer="ocr")
        check("ocr path: corrupt image fails soft",
              res["text"] == "" and "couldn't read the image file" in (res["error"] or ""))
finally:
    ch.available_ocr = _orig_available_ocr
    ch.make_ocr = _orig_make_ocr

# ---- sanity: photo_scanner never imports Qt or opens a socket at import --
guard("module import has no side effects", lambda: __import__("core_engine.photo_scanner"))

print(f"\nphoto_scan_checks: {PASS} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
