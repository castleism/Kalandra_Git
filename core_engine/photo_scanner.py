"""
CORE_ENGINE/PHOTO_SCANNER.PY
W3-33: turn a screenshot of an item tooltip into text, then hand it to the
SAME parse_item_text pipeline Ctrl+C already feeds -- so Reserve bank, Price
Check, and crafting insights all work from a photo too. Two engines, best
available wins:

  (a) offline OCR   -- the exact adapters Craft Hunter ships (RapidOCR
      preferred, pytesseract fallback), 2x upscale for small tooltip text.
      Free, local, no API key required.
  (b) AI vision      -- the user's already-configured AI brain reads the
      image directly. Far more accurate on PoE2's stylized fonts; costs a
      fraction of a cent per scan on a key the user already added in
      Settings for chat.

This module never talks to a network itself -- the AI-vision engine is
injected as a plain `callable(path, instruction) -> text` (the GUI layer
wires that to `VoiceEngine.ai_read_image`). Pass None to run OCR-only; the
feature still works with zero installs and zero API keys.
"""

import os

_VISION_PROMPT = (
    "This is a screenshot of a Path of Exile 2 item tooltip. Transcribe "
    "the tooltip's text EXACTLY as it appears, line by line, top to "
    "bottom: item class, rarity, name, base type, every mod line, "
    "sockets, item level, and any other tooltip lines. No commentary, no "
    "markdown, nothing invented. If a value is genuinely unreadable, write "
    "'?' in its place rather than guessing. Output ONLY the transcribed "
    "tooltip text."
)


def available_engines(ai_vision=None):
    """[(kind, label), ...] engines usable right now, in the order they'd
    be tried for prefer="auto". `ai_vision` is the same injected callable
    passed to scan_item_photo -- pass it here to report AI-vision status
    alongside OCR's."""
    out = []
    if callable(ai_vision):
        out.append(("ai", "AI vision (your configured brain)"))
    try:
        from core_engine.craft_hunter import available_ocr
        kind, msg = available_ocr()
        if kind:
            out.append(("ocr", msg))
    except Exception:
        pass
    return out


def _load_upscaled(path):
    """Read an image file and 2x-upscale it -- the same trick the Reserve
    tab's snapshot OCR (W3-31) uses to sharpen small tooltip text. Returns
    a numpy BGR array; raises on a missing/corrupt file."""
    import cv2
    img = cv2.imread(path)
    if img is None:
        raise RuntimeError("couldn't read the image file")
    return cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)


def _ocr_read(path):
    from core_engine.craft_hunter import available_ocr, make_ocr
    kind, msg = available_ocr()
    if not kind:
        return "", msg
    ocr = make_ocr()
    if not ocr:
        return "", msg
    img = _load_upscaled(path)
    text = (ocr(img) or "").strip()
    return text, (None if text else "no text found in the image")


def _ai_read(path, ai_vision):
    if not callable(ai_vision):
        return "", "no AI vision engine wired up"
    text = ai_vision(path, _VISION_PROMPT)
    text = (text or "").strip()
    return text, (None if text else "AI vision returned no text")


def scan_item_photo(path, ai_vision=None, prefer="auto"):
    """Turn a screenshot into tooltip text.

    prefer:
        "auto" -- AI vision first when one is wired up (more accurate on
                  stylized fonts), offline OCR as the fallback / sole path
                  when no AI vision engine is available.
        "ai"   -- force AI vision only (caller's choice, e.g. a UI toggle).
        "ocr"  -- force offline OCR only.

    Returns {"text": str, "engine": "ai"|"ocr"|None, "error": str|None}.
    `error` is only set when NOTHING produced usable text.
    """
    if not path or not os.path.isfile(path):
        return {"text": "", "engine": None, "error": "screenshot file not found"}

    if prefer == "ai":
        order = [("ai", lambda: _ai_read(path, ai_vision))]
    elif prefer == "ocr":
        order = [("ocr", lambda: _ocr_read(path))]
    elif callable(ai_vision):
        order = [("ai", lambda: _ai_read(path, ai_vision)),
                 ("ocr", lambda: _ocr_read(path))]
    else:
        order = [("ocr", lambda: _ocr_read(path))]

    errors = []
    for name, fn in order:
        try:
            text, err = fn()
        except Exception as e:
            text, err = "", str(e)
        if text:
            return {"text": text, "engine": name, "error": None}
        if err:
            errors.append(f"{name}: {err}")
    return {"text": "", "engine": None,
            "error": " / ".join(errors) or "no OCR or AI-vision engine available"}
