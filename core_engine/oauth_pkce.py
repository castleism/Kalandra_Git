"""
CORE_ENGINE/OAUTH_PKCE.PY
A small, dependency-light OAuth 2.1 Authorization-Code + PKCE flow for desktop
apps (RFC 7636 + RFC 8252 loopback redirect).

Used for the GGG (pathofexile.com) account link. GGG issues client_ids for
public/PKCE clients on request (see docs/GGG_OAuth_Application_Letter.md at repo
root); until one is granted the Settings button explains what's pending.

Flow:
  1. Generate a code_verifier/challenge pair.
  2. Start a one-shot HTTP listener on 127.0.0.1:<port>.
  3. Open the system browser at the authorize URL.
  4. User signs in and approves; browser is redirected to the loopback with
     ?code=...; we exchange it at the token endpoint.

Everything runs in the CALLER's thread (call it from a worker thread, not the
UI thread). Returns a dict with either {"ok": True, "token": {...}} or
{"ok": False, "error": "..."}.
"""

import base64
import hashlib
import secrets
import socket
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    import requests
except Exception:
    requests = None

# GGG endpoints (https://www.pathofexile.com/developer/docs/authorization)
GGG_AUTHORIZE_URL = "https://www.pathofexile.com/oauth/authorize"
GGG_TOKEN_URL = "https://www.pathofexile.com/oauth/token"
GGG_DEFAULT_SCOPES = "account:profile account:leagues account:characters"

_SUCCESS_PAGE = b"""<html><body style='font-family:sans-serif;background:#14181f;color:#e8e8e8;text-align:center;padding-top:80px'>
<h2 style='color:#d4a373'>Kalandra is connected.</h2>
<p>You can close this tab and return to the overlay.</p></body></html>"""

_FAIL_PAGE = b"""<html><body style='font-family:sans-serif;background:#14181f;color:#e8e8e8;text-align:center;padding-top:80px'>
<h2 style='color:#e08a90'>Sign-in was not completed.</h2>
<p>You can close this tab and try again from the overlay.</p></body></html>"""


def _free_port(preferred=37337):
    """Use the preferred port if free (it must match the registered redirect
    URI), else raise — a random port would not match the registration."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", preferred))
        s.close()
        return preferred
    except OSError:
        s.close()
        raise RuntimeError(
            f"Port {preferred} is busy (another app is using it). "
            "Close whatever holds it and try again.")


def make_pkce_pair():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def run_pkce_flow(client_id, open_browser,
                  authorize_url=GGG_AUTHORIZE_URL, token_url=GGG_TOKEN_URL,
                  scopes=GGG_DEFAULT_SCOPES, port=37337, timeout=180,
                  logger=None):
    """Run the full loopback PKCE flow. `open_browser` is a callable(url) that
    launches the system browser (pass QDesktopServices.openUrl-wrapper from the
    UI). Blocks up to `timeout` seconds waiting for the redirect."""
    def _log(msg):
        if logger:
            try:
                logger("ACCOUNT", msg)
            except Exception:
                pass

    if requests is None:
        return {"ok": False, "error": "The 'requests' library is not installed."}
    if not client_id:
        return {"ok": False, "error": "No client_id configured."}

    try:
        port = _free_port(port)
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}

    verifier, challenge = make_pkce_pair()
    state = secrets.token_urlsafe(24)
    redirect_uri = f"http://127.0.0.1:{port}/callback"

    result = {}
    got_code = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.urlparse(self.path)
            params = dict(urllib.parse.parse_qsl(q.query))
            ok = (q.path == "/callback" and params.get("state") == state
                  and "code" in params)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(_SUCCESS_PAGE if ok else _FAIL_PAGE)
            if ok:
                result["code"] = params["code"]
            else:
                result.setdefault("error", params.get("error", "no code returned"))
            got_code.set()

        def log_message(self, *a):   # silence per-request stderr noise
            pass

    server = HTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    auth = (f"{authorize_url}?client_id={urllib.parse.quote(client_id)}"
            f"&response_type=code&scope={urllib.parse.quote(scopes)}"
            f"&state={state}&redirect_uri={urllib.parse.quote(redirect_uri)}"
            f"&code_challenge={challenge}&code_challenge_method=S256")
    _log("Opening browser for account sign-in...")
    try:
        open_browser(auth)
    except Exception as e:
        server.shutdown()
        return {"ok": False, "error": f"Could not open browser: {e}"}

    got_code.wait(timeout)
    server.shutdown()
    if "code" not in result:
        return {"ok": False,
                "error": result.get("error", "Timed out waiting for the sign-in "
                                             "redirect (3 min).")}

    _log("Sign-in approved — exchanging the code for a token...")
    try:
        r = requests.post(token_url, data={
            "client_id": client_id, "grant_type": "authorization_code",
            "code": result["code"], "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        }, headers={"User-Agent": "KalandraOverlay/0.1"}, timeout=30)
        if r.status_code != 200:
            return {"ok": False,
                    "error": f"Token endpoint returned HTTP {r.status_code}: "
                             f"{r.text[:300]}"}
        tok = r.json()
    except Exception as e:
        return {"ok": False, "error": f"Token exchange failed: {e}"}
    if "access_token" not in tok:
        return {"ok": False, "error": f"No access_token in response: {tok}"}
    _log("GGG account linked successfully.")
    return {"ok": True, "token": tok}
