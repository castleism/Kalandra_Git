"""
CORE_ENGINE/PROVIDERS.PY — every third-party tool behind a swappable interface.

North-star rule from docs/DESIGN_COMPANION.md: PoB, poe.ninja, Craft of Exile,
the trade site, OBS — all modules, never load-bearing walls. Feature code
asks the registry for a capability; the day official APIs (or an
acquisition) replace a tool, ONE adapter changes and no feature code moves.

    from core_engine.providers import get_provider
    econ = get_provider("economy")        # -> EconomyProvider or None
    if econ and econ.available():
        rates = econ.currency_rates("Standard")

Adapters wrap the EXISTING modules lazily (nothing imports heavy deps at
module load), and every method degrades to None/empty rather than raising —
callers stay simple. Pure Python; headless-importable; stress-testable.
"""

from abc import ABC, abstractmethod


# ---------------------------------------------------------------------------
# Interfaces (the contracts feature code may rely on)
# ---------------------------------------------------------------------------

class Provider(ABC):
    """Base: every provider can say whether its backing tool is usable."""
    name = "provider"

    def available(self):
        return True


class BuildCalculator(Provider):
    """Build math. Today: headless Path of Building. Later: native calc."""
    name = "build_calculator"

    @abstractmethod
    def parse_build(self, code_or_xml):
        """PoB code / XML -> normalized build dict (or {'error': ...})."""

    @abstractmethod
    def stats_summary(self):
        """Short text of the active build's computed stats, '' if none."""


class EconomyProvider(Provider):
    """Market data. Today: poe.ninja public JSON. Later: official API."""
    name = "economy"

    @abstractmethod
    def currency_rates(self, league):
        """-> {currency_name: chaos_value} or {}."""


class TradeSearchProvider(Provider):
    """Item search. Today: official trade-site URL builder (player clicks).
    Later: official trade API. NEVER auto-buys — ToS hard rule."""
    name = "trade_search"

    @abstractmethod
    def search_url(self, item_info, league):
        """Parsed item info -> URL string the player can open, or ''."""


class CraftSimulator(Provider):
    """Craft planning/odds. Today: local planner + Craft of Exile link-out."""
    name = "craft_simulator"

    @abstractmethod
    def plan(self, goal_text):
        """Plain-language goal -> plan text/dict, or None."""


class GameDataProvider(Provider):
    """Game knowledge. Today: scraped poe2db/wiki SQLite. Later: API/files."""
    name = "game_data"

    @abstractmethod
    def search(self, term, limit=5):
        """-> list of text snippets (possibly empty)."""


class CaptureProvider(Provider):
    """Recording/replay. Today: built-in recorder; OBS websocket is W4-10."""
    name = "capture"

    @abstractmethod
    def is_recording(self):
        """-> bool"""


class ItemInHandProvider(Provider):
    """The item the player is currently looking at. Today: the Ctrl+C
    clipboard text PoE2 writes over a hovered item (W3-20), parsed by
    `trade_tools.parse_item_text`. Later: the game tells us the hovered/
    selected item directly (post-GGG engine callback) — no clipboard at all.
    """
    name = "item_in_hand"

    @abstractmethod
    def read(self):
        """-> (info, raw_text). `raw_text` is the exact clipboard text seen
        (possibly '' or non-item text — callers use it to debounce/log).
        `info` is the parsed item dict (name/base/rarity/mods/...) or None
        if there's nothing, the clipboard isn't a PoE item, or parsing
        failed/empty."""


# ---------------------------------------------------------------------------
# Current adapters (lazy imports; every call fails soft)
# ---------------------------------------------------------------------------

class PobCalculator(BuildCalculator):
    def __init__(self):
        self._bridge = None
        self._sim = None

    def _get_bridge(self):
        if self._bridge is None:
            try:
                from core_engine.pob_bridge import KalandraPoBBridge
                self._bridge = KalandraPoBBridge()
            except Exception:
                self._bridge = False
        return self._bridge or None

    def available(self):
        return self._get_bridge() is not None

    def parse_build(self, code_or_xml):
        b = self._get_bridge()
        if not b:
            return {"error": "PoB bridge unavailable"}
        try:
            return b.extract_full_build(code_or_xml)
        except Exception as e:
            return {"error": str(e)}

    def attach_sim(self, pob_sim):
        """The live LuaJIT sim is owned by the overlay; it hands it in here."""
        self._sim = pob_sim

    def stats_summary(self):
        try:
            if self._sim and self._sim.has_build():
                return self._sim.stats_summary() or ""
        except Exception:
            pass
        return ""


class PoeNinjaEconomy(EconomyProvider):
    def __init__(self):
        self._client = None

    def _get(self):
        if self._client is None:
            try:
                from core_engine.poe_ninja import PoENinja
                self._client = PoENinja()
            except Exception:
                self._client = False
        return self._client or None

    def available(self):
        c = self._get()
        try:
            return bool(c and c.available())
        except Exception:
            return False

    def currency_rates(self, league):
        c = self._get()
        if not c:
            return {}
        try:
            rows = c.get_currency(league) or []
            return {r["name"]: float(r["value"]) for r in rows
                    if r.get("name") and r.get("value") is not None}
        except Exception:
            return {}


class OfficialTradeSearch(TradeSearchProvider):
    def search_url(self, item_info, league):
        try:
            from core_engine.trade_tools import trade_search_url
            return trade_search_url(item_info, league) or ""
        except Exception:
            return ""


class LocalCraftPlanner(CraftSimulator):
    def plan(self, goal_text):
        try:
            from core_engine.trade_tools import offline_craft_guidance
            return offline_craft_guidance(goal_text)
        except Exception:
            return None


class ScrapedGameData(GameDataProvider):
    def search(self, term, limit=5):
        """LIKE search over the knowledge_ledger (same table the RAG uses)."""
        t = str(term or "").strip()
        if not t:
            return []
        try:
            from core_engine.database_handler import KalandraDBHandler
            db = KalandraDBHandler()
            try:
                rows = db.cursor.execute(
                    "SELECT topic_tag, content_payload FROM knowledge_ledger "
                    "WHERE topic_tag LIKE ? OR content_payload LIKE ? "
                    "LIMIT ?", (f"%{t}%", f"%{t}%", int(limit))).fetchall()
                return [f"{r[0]}: {r[1]}" for r in rows]
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        except Exception:
            return []


class BuiltinCapture(CaptureProvider):
    """The overlay owns the live ScreenRecorder; it hands it in here so any
    feature can ask 'are we recording?' without importing the GUI stack."""

    def __init__(self):
        self._rec = None

    def attach_recorder(self, recorder):
        self._rec = recorder

    def is_recording(self):
        try:
            return bool(self._rec and self._rec.is_recording())
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ClipboardItemInHand(ItemInHandProvider):
    """Reads the game-written Ctrl+C clipboard text and parses it. Never
    touches the game; never writes the clipboard. Qt import is lazy so this
    stays importable headless (available() is False without a QApplication)."""

    def _clipboard_text(self):
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is None:
                return None
            return app.clipboard().text() or ""
        except Exception:
            return None

    def available(self):
        return self._clipboard_text() is not None

    def read(self):
        txt = self._clipboard_text()
        if txt is None:
            return None, ""
        if not txt or len(txt) > 4000:
            return None, txt
        if "Rarity:" not in txt and "Item Class:" not in txt:
            return None, txt          # not a PoE item copy
        try:
            from core_engine.trade_tools import parse_item_text
            info = parse_item_text(txt)
        except Exception:
            return None, txt
        if not (info.get("name") or info.get("base")):
            return None, txt
        return info, txt


class ObsCapture(CaptureProvider):
    """OBS Studio via obs-websocket v5 (core_engine/obs_bridge) — the
    W4-10/W4-21 capture path. Swap in with set_provider("capture", ...)."""

    def __init__(self, host="127.0.0.1", port=4455, password=None):
        self._kw = {"host": host, "port": port, "password": password}

    def is_recording(self):
        try:
            from core_engine.obs_bridge import ObsClient
            with ObsClient(**self._kw) as c:
                return c.replay_buffer_active()
        except Exception:
            return False

    def save_replay(self):
        """-> (clip_path|None, msg): flush the replay buffer."""
        try:
            from core_engine.obs_bridge import capture_replay
            return capture_replay(**self._kw)
        except Exception as e:
            return None, str(e)


_REGISTRY = {}
_DEFAULTS = {
    "build_calculator": PobCalculator,
    "economy": PoeNinjaEconomy,
    "trade_search": OfficialTradeSearch,
    "craft_simulator": LocalCraftPlanner,
    "game_data": ScrapedGameData,
    "capture": BuiltinCapture,
    "item_in_hand": ClipboardItemInHand,
}


def get_provider(name):
    """Singleton per capability; None for unknown names (never raises)."""
    if name in _REGISTRY:
        return _REGISTRY[name]
    cls = _DEFAULTS.get(name)
    if cls is None:
        return None
    try:
        inst = cls()
    except Exception:
        return None
    _REGISTRY[name] = inst
    return inst


def set_provider(name, instance):
    """Swap point: official-API adapters (or tests) install themselves here."""
    _REGISTRY[name] = instance


def capabilities():
    return sorted(_DEFAULTS.keys())
