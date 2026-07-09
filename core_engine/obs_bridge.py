"""
CORE_ENGINE/OBS_BRIDGE.PY — talk to OBS Studio over obs-websocket v5 (W4-10).

Why OBS: it already captures the game efficiently (GPU-side), and its REPLAY
BUFFER keeps the last N seconds in memory. When the death reviewer's trigger
fires we ask OBS to flush that buffer to a file and OBS tells us where it
landed — a rewound clip you can review and post later, completely separate
from any full-session recording OBS may also be making.

Protocol (obs-websocket 5.x, bundled with OBS Studio 28+): a WebSocket at
ws://host:4455. The server greets with Hello (op 0, carrying an auth
challenge when a password is set); the client answers Identify (op 1);
Identified (op 2) means ready; requests are op 6, responses op 7.

Needs the pure-Python `websocket-client` package. Everything fails soft —
no OBS running / no package / wrong password comes back as (None, "reason"),
never an exception into the GUI. This is the CaptureProvider the provider
registry points at (north star: every third-party tool stays swappable).
"""

import base64
import hashlib
import json
import os
import time

DEFAULT_PORT = 4455


def build_auth(password, salt, challenge):
    """obs-websocket v5 auth string:
    b64(sha256( b64(sha256(password+salt)) + challenge ))."""
    secret = base64.b64encode(
        hashlib.sha256((str(password) + str(salt)).encode()).digest())
    return base64.b64encode(
        hashlib.sha256(secret + str(challenge).encode()).digest()).decode()


class ObsError(Exception):
    pass


class ObsClient:
    """Minimal obs-websocket v5 client. Use as a context manager or call
    close() yourself; every public helper returns plain data, no ws types."""

    def __init__(self, host="127.0.0.1", port=DEFAULT_PORT, password=None,
                 timeout=4.0):
        self.host, self.port = host, int(port or DEFAULT_PORT)
        self.password = password or ""
        self.timeout = timeout
        self._ws = None
        self._rid = 0

    # -- lifecycle ---------------------------------------------------------
    def connect(self):
        """Handshake to Identified. Raises ObsError with a human reason."""
        try:
            import websocket  # websocket-client
        except ImportError:
            raise ObsError("The 'websocket-client' package is not installed "
                           "(pip install websocket-client).")
        try:
            self._ws = websocket.create_connection(
                f"ws://{self.host}:{self.port}", timeout=self.timeout)
        except Exception as e:
            raise ObsError(f"OBS not reachable at {self.host}:{self.port} — "
                           f"is OBS running with obs-websocket enabled? ({e})")
        hello = self._recv()
        if hello.get("op") != 0:
            raise ObsError(f"Unexpected first message from OBS: {hello}")
        ident = {"rpcVersion": 1, "eventSubscriptions": 0}
        auth = (hello.get("d") or {}).get("authentication")
        if auth:
            if not self.password:
                raise ObsError("OBS requires a websocket password (OBS: "
                               "Tools > WebSocket Server Settings).")
            ident["authentication"] = build_auth(
                self.password, auth.get("salt", ""), auth.get("challenge", ""))
        self._send({"op": 1, "d": ident})
        resp = self._recv()
        if resp.get("op") != 2:
            raise ObsError("OBS rejected the connection — wrong websocket "
                           "password?")
        return self

    def close(self):
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass
        self._ws = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *_):
        self.close()

    # -- plumbing ------------------------------------------------------------
    def _send(self, obj):
        self._ws.send(json.dumps(obj))

    def _recv(self):
        return json.loads(self._ws.recv())

    def request(self, req_type, data=None):
        """op 6 -> matching op 7. Returns responseData dict (may be {})."""
        if not self._ws:
            raise ObsError("Not connected.")
        self._rid += 1
        rid = f"k{self._rid}"
        self._send({"op": 6, "d": {"requestType": req_type,
                                   "requestId": rid,
                                   "requestData": data or {}}})
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            msg = self._recv()
            if msg.get("op") == 7 and (msg["d"].get("requestId") == rid):
                st = msg["d"].get("requestStatus") or {}
                if not st.get("result"):
                    raise ObsError(st.get("comment") or
                                   f"{req_type} failed (code {st.get('code')})")
                return msg["d"].get("responseData") or {}
        raise ObsError(f"{req_type}: no response from OBS.")

    # -- replay buffer -------------------------------------------------------
    def version(self):
        return self.request("GetVersion")

    def replay_buffer_active(self):
        return bool(self.request("GetReplayBufferStatus").get("outputActive"))

    def start_replay_buffer(self):
        """Idempotent start. True if the buffer is running afterwards."""
        if self.replay_buffer_active():
            return True
        try:
            self.request("StartReplayBuffer")
        except ObsError:
            pass  # e.g. already starting
        time.sleep(0.4)
        return self.replay_buffer_active()

    def last_replay_path(self):
        try:
            return (self.request("GetLastReplayBufferReplay")
                    .get("savedReplayPath")) or None
        except ObsError:
            return None

    def save_replay_clip(self, settle=6.0):
        """Flush the replay buffer -> (saved_path, msg). Polls until the
        'last replay' path CHANGES so a stale clip from an earlier save is
        never mistaken for this one."""
        if not self.replay_buffer_active():
            if not self.start_replay_buffer():
                return None, ("OBS replay buffer is off and would not start "
                              "— enable it in OBS (Settings > Output > "
                              "Replay Buffer), then Start Replay Buffer.")
        before = self.last_replay_path()
        self.request("SaveReplayBuffer")
        deadline = time.time() + settle
        while time.time() < deadline:
            time.sleep(0.35)
            p = self.last_replay_path()
            if p and p != before and os.path.exists(p):
                return p, "saved"
        p = self.last_replay_path()
        if p and os.path.exists(p):
            return p, "saved (path unchanged — OBS may reuse filenames)"
        return None, "OBS accepted the save but never reported a clip path."


def capture_replay(host="127.0.0.1", port=DEFAULT_PORT, password=None):
    """One-shot convenience for worker threads: -> (clip_path|None, msg)."""
    try:
        with ObsClient(host, port, password) as c:
            return c.save_replay_clip()
    except ObsError as e:
        return None, str(e)
    except Exception as e:
        return None, f"OBS capture failed: {e}"


def obs_status(host="127.0.0.1", port=DEFAULT_PORT, password=None):
    """For the settings 'Test' button: -> (ok, human message)."""
    try:
        with ObsClient(host, port, password) as c:
            v = c.version()
            rb = c.replay_buffer_active()
            return True, (f"Connected — OBS {v.get('obsVersion', '?')}, "
                          f"websocket {v.get('obsWebSocketVersion', '?')}; "
                          f"replay buffer {'RUNNING' if rb else 'OFF'}"
                          + ("" if rb else " (start it, or Kalandra will try "
                                           "to when a death is captured)"))
    except ObsError as e:
        return False, str(e)
    except Exception as e:
        return False, f"{e}"
