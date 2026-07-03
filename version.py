"""
VERSION.PY  --  single source of truth for the Kalandra version.

Bump KALANDRA_VERSION here and it shows up in the overlay title, the dashboard,
the dialogs, and the installer (which reads this file). COMPATIBILITY lists the
dependency/resource revisions verified to work with THIS Kalandra revision.
"""

KALANDRA_VERSION = "0.1.0-pre.1"          # pre-release revision
KALANDRA_CHANNEL = "pre-release"

# Dependency / resource versions verified against this Kalandra revision.
# (Apps resolved at install time show the version last tested.)
COMPATIBILITY = {
    "python":      "3.12.x (64-bit)",
    "pip":         "see requirements.txt (PyQt6>=6.7, faster-whisper>=1.0, etc.)",
    "luajit":      "ScriptTiger LuaJIT-For-Windows (latest)",
    "rhubarb":     "Rhubarb Lip Sync 1.14.0",
    "pob_source":  "PathOfBuilding-PoE2 (latest branch)",
    "pob2_app":    "Path of Building 2 (latest, tested 2026-06)",
    "exiled2":     "Exiled Exchange 2 (latest, tested 2026-06)",
    "xiletrade":   "Xiletrade (latest, tested 2026-06)",
    "lailloken":   "Lailloken Exile-UI (latest, tested 2026-06)",
    "obsidian":    "Obsidian 1.x (latest)",
    "game":        "Path of Exile 2 0.x (current live)",
    "openai":      "OpenAI API (gpt-4o-mini)",
    "gemini":      "Google Gemini API (gemini-2.5-flash)",
}


def title(suffix=""):
    """Convenience: a window-title string with the version baked in."""
    base = f"Kalandra v{KALANDRA_VERSION}"
    return f"{base} — {suffix}" if suffix else base
