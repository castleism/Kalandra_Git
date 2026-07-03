"""
CORE_ENGINE/VOICE_ENGINE.PY
Purpose: REAL voice for the Kalandra overlay, using the "hybrid" design you chose:

    LOCAL EARS   -> faster-whisper transcribes your microphone on-device (private, free)
    CLOUD BRAIN  -> an LLM (OpenAI or Google Gemini) generates the answer
    LOCAL VOICE  -> pyttsx3 speaks the reply out loud, on-device

The old overlay only flipped a boolean and printed a log line, so "testing testing
123" was never heard by anything. This module actually records the mic, transcribes
it, can ask the AI brain (with your scraped database as context), and speak back.

Everything is guarded: missing libraries or API keys degrade gracefully and report
WHY, instead of crashing the overlay.

Install:
    pip install faster-whisper sounddevice numpy        # local ears
    pip install pyttsx3                                  # local voice
    pip install openai           # if using OpenAI as the brain
    pip install google-generativeai   # if using Gemini as the brain

API keys are read from the AccountManager (OS keychain) or environment variables
OPENAI_API_KEY / GEMINI_API_KEY.
"""

import os
import json
import shutil
import subprocess
import threading
import time
import wave
import tempfile
import math
import random

import importlib.util

_ERR = []
try:
    import numpy as np
except Exception as e:
    np = None
    _ERR.append(f"numpy ({e})")


def _module_installed(name):
    """True if a module is importable WITHOUT actually importing (executing) it."""
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


# The speech libraries (faster-whisper/ctranslate2, sounddevice, pyttsx3) are
# HEAVY to import and were loading at app startup, which made launch feel clunky
# on minimal hardware. We now only PROBE that they're installed here (find_spec
# does not execute them) and import them LAZILY on first actual use of voice.
STT_AVAILABLE = (np is not None) and _module_installed("sounddevice") \
    and _module_installed("faster_whisper")
TTS_AVAILABLE = _module_installed("pyttsx3")

# Lazy module caches (populated on first use by the getters below).
_sd = None
_WhisperModel = None
_pyttsx3 = None


def _get_sd():
    global _sd
    if _sd is None:
        import sounddevice as sd
        _sd = sd
    return _sd


def _get_whisper():
    global _WhisperModel
    if _WhisperModel is None:
        from faster_whisper import WhisperModel as WM
        _WhisperModel = WM
    return _WhisperModel


def _get_pyttsx3():
    global _pyttsx3
    if _pyttsx3 is None:
        import pyttsx3 as p
        _pyttsx3 = p
    return _pyttsx3

STT_SAMPLERATE = 16000  # Whisper expects 16 kHz mono.


# ----------------------------------------------------------------------------
# AI PROVIDERS — every LLM the Orb can use. Most expose an OpenAI-compatible API
# (kind="openai" with a base_url); Anthropic and Gemini use their own SDKs.
# Model lists are editable in the UI because provider model IDs change over time.
# ----------------------------------------------------------------------------
PROVIDERS = {
    "openai": {
        "label": "OpenAI (GPT)", "service": "openai", "kind": "openai",
        "base_url": None, "env": "OPENAI_API_KEY",
        "key_url": "https://platform.openai.com/api-keys",
        "default_model": "gpt-4o-mini",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1", "o4-mini"],
    },
    "anthropic": {
        "label": "Anthropic (Claude)", "service": "anthropic", "kind": "anthropic",
        "base_url": None, "env": "ANTHROPIC_API_KEY",
        "key_url": "https://console.anthropic.com/settings/keys",
        "default_model": "claude-3-5-haiku-latest",
        "models": ["claude-3-5-haiku-latest", "claude-3-5-sonnet-latest",
                   "claude-3-7-sonnet-latest"],
    },
    "gemini": {
        "label": "Google (Gemini)", "service": "gemini", "kind": "gemini",
        "base_url": None, "env": "GEMINI_API_KEY",
        "key_url": "https://aistudio.google.com/app/apikey",
        "default_model": "gemini-2.5-flash",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
    },
    "deepseek": {
        "label": "DeepSeek", "service": "deepseek", "kind": "openai",
        "base_url": "https://api.deepseek.com", "env": "DEEPSEEK_API_KEY",
        "key_url": "https://platform.deepseek.com/api_keys",
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "mistral": {
        "label": "Mistral", "service": "mistral", "kind": "openai",
        "base_url": "https://api.mistral.ai/v1", "env": "MISTRAL_API_KEY",
        "key_url": "https://console.mistral.ai/api-keys/",
        "default_model": "mistral-large-latest",
        "models": ["mistral-large-latest", "mistral-small-latest"],
    },
    "xai": {
        "label": "xAI (Grok)", "service": "xai", "kind": "openai",
        "base_url": "https://api.x.ai/v1", "env": "XAI_API_KEY",
        "key_url": "https://console.x.ai/",
        "default_model": "grok-2-latest",
        "models": ["grok-2-latest", "grok-beta"],
    },
}


def provider_model_default(provider):
    return PROVIDERS.get(provider, {}).get("default_model", "")


class VoiceEngine:
    def __init__(self, whisper_model_size="base", brain="openai",
                 api_key_provider=None, logger=None,
                 openai_model="gpt-4o-mini", gemini_model="gemini-2.5-flash",
                 voice_id=None, voice_rate=None, model=None):
        """
        Parameters:
            whisper_model_size : "tiny" | "base" | "small" | "medium" | "large-v3"
            brain              : "openai" | "gemini" | "none"
            api_key_provider   : optional callable(service_name)->key (e.g. AccountManager.get_secret)
            logger             : optional callable(category, message)
            openai_model       : OpenAI chat model (default gpt-4o-mini)
            gemini_model       : Gemini model (default gemini-2.5-flash)
        """
        self.whisper_model_size = whisper_model_size
        self.brain = brain
        self.api_key_provider = api_key_provider
        self.logger = logger
        self.openai_model = openai_model
        self.gemini_model = gemini_model
        # The active chat model for the current provider. Falls back to the
        # legacy per-provider kwargs, then the provider's default.
        self.model = (model
                      or (openai_model if brain == "openai" else None)
                      or (gemini_model if brain == "gemini" else None)
                      or provider_model_default(brain))
        self.voice_id = voice_id        # SAPI/system voice id (None = default)
        self.voice_rate = voice_rate    # words per minute (None = default)
        self.last_usage = None          # token usage from the most recent reply

        self._model = None            # lazy-loaded WhisperModel
        self._tts = None              # lazy-loaded pyttsx3 engine
        self._stream = None
        self._frames = []
        self._listening = False

    # -- logging helper --------------------------------------------------------
    def _log(self, category, message):
        if self.logger:
            try:
                self.logger(category, message)
            except Exception:
                pass

    def availability_message(self):
        bits = []
        bits.append("Local transcription: " + ("ready" if STT_AVAILABLE else "MISSING (pip install faster-whisper sounddevice numpy)"))
        bits.append("Local voice (TTS): " + ("ready" if TTS_AVAILABLE else "MISSING (pip install pyttsx3)"))
        bits.append("AI brain: " + (self.brain if self._brain_key() else f"{self.brain} (no API key set)"))
        return "\n".join(bits)

    # -- key lookup ------------------------------------------------------------
    def _brain_key(self):
        prov = PROVIDERS.get(self.brain, {})
        service = prov.get("service", self.brain)
        env_name = prov.get("env", "")
        key = None
        if self.api_key_provider:
            try:
                key = self.api_key_provider(service)
            except Exception:
                key = None
        return key or (os.environ.get(env_name) if env_name else None)

    # -- microphone capture (LOCAL EARS) ---------------------------------------
    @property
    def is_listening(self):
        return self._listening

    def start_listening(self):
        """Begin capturing the microphone. Returns True if started."""
        if not STT_AVAILABLE or self._listening:
            return False
        self._frames = []
        try:
            self._stream = _get_sd().InputStream(
                samplerate=STT_SAMPLERATE, channels=1, dtype="int16",
                callback=lambda indata, frames, t, status: self._frames.append(indata.copy()),
            )
            self._stream.start()
            self._listening = True
            self._log("VOICE", "Microphone open. Listening...")
            return True
        except Exception as e:
            self._log("VOICE", f"Could not open microphone: {e}")
            return False

    def stop_listening_and_transcribe(self):
        """Stop the mic and return the transcribed text (or "")."""
        if not self._listening:
            return ""
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass
        self._listening = False

        if not self._frames:
            return ""
        audio_int16 = np.concatenate(self._frames, axis=0).flatten()
        audio_f32 = audio_int16.astype(np.float32) / 32768.0
        self._log("VOICE", "Transcribing captured audio with Whisper...")
        return self._transcribe_array(audio_f32)

    # -- transcription ---------------------------------------------------------
    def _ensure_model(self):
        if self._model is None and STT_AVAILABLE:
            self._log("VOICE", f"Loading Whisper model '{self.whisper_model_size}' (first run downloads it)...")
            # int8 on CPU keeps it light; works without a GPU.
            self._model = _get_whisper()(self.whisper_model_size, device="cpu", compute_type="int8")
        return self._model

    def _transcribe_array(self, audio_f32):
        model = self._ensure_model()
        if model is None:
            return ""
        segments, _info = model.transcribe(audio_f32, language="en", beam_size=1)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        self._log("VOICE", f"Heard: {text!r}")
        return text

    def transcribe_file(self, path):
        """Transcribe an existing audio/video file (used for screen recordings)."""
        if not STT_AVAILABLE or not path or not os.path.exists(path):
            return ""
        model = self._ensure_model()
        if model is None:
            return ""
        try:
            segments, _info = model.transcribe(path, language="en", beam_size=1)
            return " ".join(seg.text.strip() for seg in segments).strip()
        except Exception as e:
            self._log("VOICE", f"Transcription failed: {e}")
            return ""

    # -- AI brain (CLOUD) ------------------------------------------------------
    def ai_respond(self, user_text, context_snippets=None):
        """Generate a reply using the configured cloud brain.

        context_snippets: optional list of strings from the local PoE2 database
        (RAG) to ground the answer. Returns a string (may be a graceful fallback).
        """
        if not user_text:
            return ""
        key = self._brain_key()
        if not key:
            return ("[AI brain offline] No API key set for "
                    f"{self.brain}. Add one in Settings to enable spoken answers. "
                    f"You said: {user_text}")

        system = (
            "You are the Divine Orb, a concise Path of Exile 2 theorycrafting "
            "assistant inside the Kalandra app. "
            "IMPORTANT: When the context contains a 'CURRENT BUILD (from Path of "
            "Building)' block, that IS the user's own loaded character — analyze it "
            "directly and specifically. Never claim you 'cannot access links', "
            "'cannot see the build', or need a pastebin: if the build block is "
            "present you already have it; if it is absent, briefly tell the user how "
            "to load it (green Character Selector medallion, or paste a PoB code / "
            "pobb.in link in the chat). "
            "Ground your answer in the provided database context (poe2db) whenever it "
            "is relevant, and prefer it over generic knowledge. "
            "ANTI-FABRICATION RULES (critical): Only reference items, skills, supports, "
            "uniques, passives, and mechanics that appear in the provided CURRENT BUILD "
            "or database context. NEVER invent an item the user did not mention (e.g. do "
            "not assume they use a specific unique). If a 'VERIFIED CORRECTIONS' block is "
            "present, treat it as absolute ground truth that overrides everything else. "
            "Do not assert how a PoE2 mechanic, ailment, or damage type scales unless it "
            "is in the context or a correction — if you are not sure, say so plainly and "
            "tell the user to verify in Path of Building rather than guessing. Do not "
            "conflate distinct mechanics (for example, a physical damage-over-time debuff "
            "is not necessarily a Bleed). "
            "PASSIVE-TREE / REPATHING: when the user asks how to get more DPS, defence, "
            "or which passives to take, and a 'BUILD SCALING PROFILE' or tree-guidance "
            "block is provided, act as a GUIDE to Path of Building's tree Power Report: "
            "tell them which stat weights to set (from the profile) and how to read the "
            "node heatmap. Do NOT invent specific passive node names, exact DPS numbers, "
            "or point counts — those come from PoB's report on THEIR tree; you provide "
            "the strategy and the weights to use. "
            "Keep spoken replies under 4 sentences; typed answers can be longer when "
            "the user asks for build analysis."
        )
        context = ""
        if context_snippets:
            # The first snippet is the full build summary (always keep it); the
            # rest are RAG hits from the local poe2db/wiki knowledge base.
            context = "\n\nBUILD + DATABASE CONTEXT:\n" + "\n---\n".join(context_snippets[:12])

        self.last_usage = None
        kind = PROVIDERS.get(self.brain, {}).get("kind", "openai")
        base_url = PROVIDERS.get(self.brain, {}).get("base_url")
        try:
            if kind == "gemini":
                return self._gemini_chat(key, system, user_text + context)
            elif kind == "anthropic":
                return self._anthropic_chat(key, system, user_text + context)
            else:   # openai + all OpenAI-compatible providers (deepseek/mistral/xai)
                return self._openai_chat(key, system, user_text + context, base_url=base_url)
        except Exception as e:
            return self._explain_brain_error(e)

    def _capture_usage(self, prompt_t, completion_t):
        try:
            p = int(prompt_t or 0); c = int(completion_t or 0)
            self.last_usage = {"prompt_tokens": p, "completion_tokens": c,
                               "total_tokens": p + c, "model": self.model,
                               "provider": self.brain}
        except Exception:
            self.last_usage = None

    @staticmethod
    def _explain_brain_error(e):
        msg = str(e)
        low = msg.lower()
        if "insufficient_quota" in low or "quota" in low or "billing" in low or "429" in low:
            return ("Your AI provider says the account is out of credit/quota. Add billing "
                    "or credits on the provider's site, then try again.")
        if "api key" in low or "api_key" in low or "401" in low or "unauthorized" in low \
                or "permission" in low or "invalid" in low:
            return "The API key looks invalid or unauthorized. Re-check it in Settings."
        if "model" in low and ("not found" in low or "not supported" in low or "404" in low):
            return ("That AI model isn't available to your account. Set a different model in "
                    "Settings (e.g. gpt-4o-mini, or gemini-2.5-flash).")
        return f"AI brain error: {msg}"

    # Hard ceiling (seconds) on any single AI request, so a stalled network
    # connection can never leave the chat stuck on "Thinking..." forever.
    AI_TIMEOUT = 45

    def _openai_chat(self, key, system, user, base_url=None):
        """Works for OpenAI and any OpenAI-compatible API (DeepSeek, Mistral,
        xAI/Grok) via a base_url override."""
        from openai import OpenAI
        kwargs = {"api_key": key}
        if base_url:
            kwargs["base_url"] = base_url
        try:
            client = OpenAI(timeout=self.AI_TIMEOUT, **kwargs)
        except TypeError:
            client = OpenAI(**kwargs)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.4,
        )
        try:
            u = resp.usage
            self._capture_usage(getattr(u, "prompt_tokens", 0), getattr(u, "completion_tokens", 0))
        except Exception:
            pass
        return resp.choices[0].message.content.strip()

    def _anthropic_chat(self, key, system, user):
        import anthropic
        try:
            client = anthropic.Anthropic(api_key=key, timeout=self.AI_TIMEOUT)
        except TypeError:
            client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=self.model, max_tokens=1024, temperature=0.4,
            system=system, messages=[{"role": "user", "content": user}])
        try:
            u = resp.usage
            self._capture_usage(getattr(u, "input_tokens", 0), getattr(u, "output_tokens", 0))
        except Exception:
            pass
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        return ("".join(parts)).strip()

    def _gemini_chat(self, key, system, user):
        # New SDK first (google-genai); fall back to the legacy package.
        try:
            from google import genai
            from google.genai import types
            try:
                client = genai.Client(
                    api_key=key,
                    http_options=types.HttpOptions(timeout=self.AI_TIMEOUT * 1000))
            except Exception:
                client = genai.Client(api_key=key)
            resp = client.models.generate_content(
                model=self.model,
                contents=user,
                config=types.GenerateContentConfig(system_instruction=system),
            )
            try:
                um = resp.usage_metadata
                self._capture_usage(getattr(um, "prompt_token_count", 0),
                                    getattr(um, "candidates_token_count", 0))
            except Exception:
                pass
            return (resp.text or "").strip()
        except ImportError:
            import google.generativeai as genai
            genai.configure(api_key=key)
            model = genai.GenerativeModel(self.model, system_instruction=system)
            try:
                return model.generate_content(
                    user, request_options={"timeout": self.AI_TIMEOUT}).text.strip()
            except TypeError:
                return model.generate_content(user).text.strip()

    # -- text to speech (LOCAL VOICE) ------------------------------------------
    def speak(self, text, on_amplitude=None, on_viseme=None, on_done=None):
        """Speak text aloud and drive lip-sync.

        on_amplitude(level 0..1) is called ~30x/sec with the current loudness.
        on_viseme(shape) is called when the mouth shape changes, using Rhubarb
        Lip Sync's shapes ("A".."H","X") if Rhubarb is installed -- this is the
        real, phoneme-accurate lip-sync that drives the viseme sprite face. If
        Rhubarb isn't present we fall back to amplitude (and a cycling viseme so
        the mouth still moves). on_done() fires when finished. Runs on a
        background thread so the UI never blocks.
        """
        if not TTS_AVAILABLE or not text:
            if on_done:
                on_done()
            return False

        def _run():
            ok = False
            try:
                ok = self._speak_with_envelope(text, on_amplitude, on_viseme)
            except Exception as e:
                self._log("VOICE", f"Lip-sync TTS failed, using fallback: {e}")
            if not ok:
                try:
                    self._speak_with_synth_flap(text, on_amplitude, on_viseme)
                except Exception as e:
                    self._log("VOICE", f"TTS failed: {e}")
            for cb, val in ((on_amplitude, 0.0), (on_viseme, "X")):
                if cb:
                    try:
                        cb(val)
                    except Exception:
                        pass
            if on_done:
                try:
                    on_done()
                except Exception:
                    pass

        threading.Thread(target=_run, daemon=True).start()
        return True

    # -- TTS engine + voice selection -----------------------------------------
    @staticmethod
    def list_voices():
        """Return [(id, name)] of installed system voices, for the Settings picker."""
        if not TTS_AVAILABLE:
            return []
        try:
            eng = _get_pyttsx3().init()
            out = [(v.id, getattr(v, "name", v.id)) for v in eng.getProperty("voices")]
            eng.stop()
            return out
        except Exception:
            return []

    def _make_engine(self):
        eng = _get_pyttsx3().init()
        try:
            if self.voice_id:
                eng.setProperty("voice", self.voice_id)
            if self.voice_rate:
                eng.setProperty("rate", int(self.voice_rate))
        except Exception:
            pass
        return eng

    # -- Rhubarb lip-sync (audio -> timed viseme shapes) -----------------------
    def _rhubarb_path(self):
        # PATH, env var, config, or a vendored copy anywhere under tools/.
        p = shutil.which("rhubarb") or shutil.which("rhubarb.exe")
        if p:
            return p
        env = os.environ.get("RHUBARB_PATH")
        if env and os.path.exists(env):
            return env
        # config (written by install_dependencies.py)
        try:
            with open(os.path.join("data_engine", "config.json"), "r", encoding="utf-8") as f:
                cp = json.load(f).get("rhubarb_path")
            if cp and os.path.exists(cp):
                return cp
        except Exception:
            pass
        # vendored tools/ (recursive — the release zip keeps a subfolder + res/)
        import glob as _glob
        for name in ("rhubarb.exe", "rhubarb"):
            hits = _glob.glob(os.path.join("tools", "**", name), recursive=True)
            if hits:
                return os.path.abspath(hits[0])
        return None

    def _run_rhubarb(self, wav_path):
        """Return a list of {start,end,value} mouth cues, or None."""
        exe = self._rhubarb_path()
        if not exe:
            return None
        out = wav_path + ".rhubarb.json"
        try:
            subprocess.run([exe, "-f", "json", "-o", out, wav_path],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=120, check=False)
            with open(out, "r", encoding="utf-8") as f:
                data = json.load(f)
            try:
                os.remove(out)
            except Exception:
                pass
            return data.get("mouthCues", []) or None
        except Exception as e:
            self._log("VOICE", f"Rhubarb failed: {e}")
            return None

    def _speak_with_envelope(self, text, on_amplitude, on_viseme=None):
        """Render TTS to a wav, compute a loudness envelope, play it while
        emitting amplitude frames (and Rhubarb viseme shapes) in sync.
        Returns True on success."""
        if np is None or _sd is None:
            return False  # need numpy + sounddevice for real analysis/playback

        tmp = os.path.join(tempfile.gettempdir(), f"kalandra_tts_{os.getpid()}.wav")
        engine = self._make_engine()
        engine.save_to_file(text, tmp)
        engine.runAndWait()
        engine.stop()
        if not os.path.exists(tmp) or os.path.getsize(tmp) < 1024:
            return False

        with wave.open(tmp, "rb") as wf:
            sr = wf.getframerate()
            n = wf.getnframes()
            ch = wf.getnchannels()
            raw = wf.readframes(n)
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        if ch > 1:
            data = data.reshape(-1, ch).mean(axis=1)
        if data.size == 0:
            return False

        fps = 30
        hop = max(1, sr // fps)
        # Per-frame RMS envelope, normalized.
        frames = [float(np.sqrt(np.mean((data[i:i+hop] / 32768.0) ** 2)))
                  for i in range(0, data.size, hop)]
        peak = max(frames) or 1.0
        env = [min(1.0, (f / peak) ** 0.6) for f in frames]  # gamma for livelier motion

        # Real viseme timeline from Rhubarb (if installed).
        cues = self._run_rhubarb(tmp) if on_viseme else None

        def viseme_at(t):
            if not cues:
                return None
            for c in cues:
                if c["start"] <= t < c["end"]:
                    return c.get("value", "X")
            return "X"

        play = data / 32768.0
        try:
            _get_sd().play(play, sr)
        except Exception:
            pass
        frame_dt = hop / sr
        start = time.time()
        last_vis = None
        for i, level in enumerate(env):
            if on_amplitude:
                try:
                    on_amplitude(level)
                except Exception:
                    pass
            if on_viseme and cues:
                v = viseme_at(i * frame_dt)
                if v and v != last_vis:
                    last_vis = v
                    try:
                        on_viseme(v)
                    except Exception:
                        pass
            target = start + (i + 1) * frame_dt
            sleep = target - time.time()
            if sleep > 0:
                time.sleep(sleep)
        try:
            _get_sd().wait()
        except Exception:
            pass
        try:
            os.remove(tmp)
        except Exception:
            pass
        return True

    def _speak_with_synth_flap(self, text, on_amplitude, on_viseme=None):
        """Fallback: speak normally and emit a synthetic mouth-flap envelope (and
        a cycling viseme) for an estimated duration, so the orb still 'talks'."""
        words = max(1, len(text.split()))
        duration = max(1.0, words / 2.6)  # ~2.6 words/sec
        cycle = ["C", "B", "E", "D", "F", "C", "B", "H"]  # plausible mouth motion

        stop = threading.Event()

        def _flap():
            fps = 30
            t = 0.0
            vi = 0
            while not stop.is_set() and t < duration:
                base = 0.5 + 0.5 * math.sin(t * 22.0)
                level = max(0.0, min(1.0, base * (0.6 + 0.4 * random.random())))
                if on_amplitude:
                    try:
                        on_amplitude(level)
                    except Exception:
                        pass
                if on_viseme and int(t * 8) != vi:
                    vi = int(t * 8)
                    try:
                        on_viseme(cycle[vi % len(cycle)])
                    except Exception:
                        pass
                time.sleep(1.0 / fps)
                t += 1.0 / fps

        flap = threading.Thread(target=_flap, daemon=True)
        flap.start()
        try:
            engine = self._make_engine()
            engine.say(text)
            engine.runAndWait()
            engine.stop()
        finally:
            stop.set()
            flap.join(timeout=1.0)


if __name__ == "__main__":
    ve = VoiceEngine()
    print(ve.availability_message())
