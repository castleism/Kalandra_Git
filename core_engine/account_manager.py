"""
CORE_ENGINE/ACCOUNT_MANAGER.PY
Purpose: Secure storage + registry for all the external accounts/integrations.

SECURITY POLICY (fail closed): secrets are stored ONLY in the OS keychain via
`keyring` (Windows Credential Manager / macOS Keychain / Linux Secret Service).
If keyring is unavailable, the app refuses to store secrets at all rather than
writing them to a plaintext file. There is intentionally NO insecure fallback.

Install:
    pip install keyring
"""

try:
    import keyring
except Exception:
    keyring = None

KEYRING_SERVICE = "KalandraOverlay"


# Registry of everything the Settings panel should show.
# kind: "oauth" | "api_key" | "login" | "link"
SERVICES = {
    "pathofexile":        {"name": "Path of Exile (GGG account)", "kind": "oauth",
                           "note": "Official GGG OAuth (pending public PoE2 API)."},
    "poeninja":           {"name": "poe.ninja (PoE2)", "kind": "api_key",
                           "note": "Public economy JSON; key optional/not required."},
    "poe2_forums":        {"name": "PoE2 Forums (Early Access)", "kind": "login",
                           "note": "Patch notes, feedback, trading, builds. No official API."},
    "email":              {"name": "Email (account backup)", "kind": "oauth",
                           "note": "Used to back up your linked-account settings."},
    "youtube":            {"name": "YouTube", "kind": "oauth",
                           "note": "Google OAuth. Build guides / VODs."},
    "pathofbuilding":     {"name": "Path of Building 2", "kind": "link",
                           "note": "Local tool. Wired via pob_bridge (codes + saved builds)."},
    "poe_overlay":        {"name": "PoE Overlay", "kind": "link",
                           "note": "Companion overlay integration."},
    "neversink":          {"name": "NeverSink FilterBlade", "kind": "link",
                           "note": "Loot filter management."},
    "exiled_exchange2":   {"name": "Exiled Exchange 2", "kind": "link",
                           "note": "Price-check tool integration."},
    "craftofexile2":      {"name": "Craft of Exile 2", "kind": "link",
                           "note": "Crafting simulator (data via game-file extraction)."},
    "maxroll":            {"name": "Maxroll", "kind": "link",
                           "note": "Build guides / planners."},
    "mobalytics":         {"name": "Mobalytics", "kind": "link",
                           "note": "Build guides."},
    "poe2wiki":           {"name": "poe2wiki.net", "kind": "link",
                           "note": "Community wiki (CC BY-NC) — scraped data source."},
    "github":             {"name": "GitHub (issue & changelog sync)", "kind": "api_key",
                           "note": "Personal-access token ('repo' scope) so the Issues tab "
                                   "can post to github.com/castleism/Kalandra_Git."},
    "openai":             {"name": "OpenAI / ChatGPT (AI brain)", "kind": "api_key",
                           "note": "Powers the talking Divine Orb's answers."},
    "gemini":             {"name": "Google Gemini (AI brain)", "kind": "api_key",
                           "note": "Alternative AI brain for the Divine Orb."},
    "anthropic":          {"name": "Anthropic Claude (AI brain)", "kind": "api_key",
                           "note": "AI brain option for the Divine Orb."},
    "deepseek":           {"name": "DeepSeek (AI brain)", "kind": "api_key",
                           "note": "Low-cost AI brain option (OpenAI-compatible API)."},
    "mistral":            {"name": "Mistral (AI brain)", "kind": "api_key",
                           "note": "AI brain option (OpenAI-compatible API)."},
    "xai":                {"name": "xAI Grok (AI brain)", "kind": "api_key",
                           "note": "AI brain option (OpenAI-compatible API)."},
    "elevenlabs":         {"name": "ElevenLabs (cloud voice)", "kind": "api_key",
                           "note": "Optional premium TTS voices for the Orb."},
}


class AccountManager:
    def __init__(self):
        self._using_keyring = keyring is not None

    def storage_note(self):
        if self._using_keyring:
            return "Secrets are stored in your OS keychain (secure)."
        return ("keyring is NOT installed, so secret storage is DISABLED for your "
                "safety (no plaintext fallback). Run `pip install keyring` to enable "
                "saving API keys and tokens.")

    # -- public API ------------------------------------------------------------
    def set_secret(self, service, value):
        """Store a secret. Returns True on success, False if storage is disabled."""
        if not self._using_keyring:
            return False
        if not value:
            return self.clear(service)
        try:
            keyring.set_password(KEYRING_SERVICE, service, value)
            return True
        except Exception:
            return False

    def get_secret(self, service):
        if not self._using_keyring:
            return None
        try:
            return keyring.get_password(KEYRING_SERVICE, service)
        except Exception:
            return None

    def clear(self, service):
        if not self._using_keyring:
            return False
        try:
            keyring.delete_password(KEYRING_SERVICE, service)
        except Exception:
            pass
        return True

    def is_connected(self, service):
        return bool(self.get_secret(service))

    def list_services(self):
        return [{
            "id": sid, "name": meta["name"], "kind": meta["kind"],
            "note": meta["note"], "connected": self.is_connected(sid),
        } for sid, meta in SERVICES.items()]

    def list_service_meta(self):
        """Like list_services() but WITHOUT touching the OS keychain, so callers
        can build their UI instantly and check 'connected' afterwards in a
        background thread. (Each is_connected() call can stall on Windows.)"""
        return [{
            "id": sid, "name": meta["name"], "kind": meta["kind"],
            "note": meta["note"], "connected": None,
        } for sid, meta in SERVICES.items()]


if __name__ == "__main__":
    am = AccountManager()
    print(am.storage_note())
    for s in am.list_services():
        flag = "OK" if s["connected"] else "--"
        print(f"[{flag}] {s['name']} ({s['kind']}) :: {s['note']}")
