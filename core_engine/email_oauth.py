"""
CORE_ENGINE/EMAIL_OAUTH.PY — modern email auth: OAuth 2.0 + XOAUTH2, no
app passwords.

Why: app passwords are a legacy bypass — a static secret that never
expires, skips MFA, and grants full mailbox access. The modern path
(what Gmail itself recommends; app passwords are being phased out):

  * OAuth 2.0 authorization-code flow for INSTALLED apps (RFC 8252):
    system browser + loopback redirect — the user signs in AT GOOGLE,
    with their MFA; Kalandra never sees the password.
  * PKCE (RFC 7636, S256) — no usable secret in the client.
  * Scope-minimal: https://mail.google.com/ only (SMTP/IMAP), revocable
    any time at myaccount.google.com/permissions.
  * Storage: tokens ONLY in the OS keychain (Windows Credential Manager
    via keyring/account_manager) — never in config.json, never on disk.
  * Transport: SMTP over implicit TLS (port 465) with AUTH XOAUTH2;
    access tokens auto-refresh (1h lifetime), refresh token rotates per
    Google policy.

One-time setup (Google requires an OAuth client per app — free):
  1. console.cloud.google.com → create project → OAuth consent screen
     (External, add yourself as test user).
  2. Credentials → Create credentials → OAuth client ID → Desktop app.
  3. Paste the client_id (+ client_secret*) into Kalandra Settings.
  * Desktop-app client_secrets are not confidential per RFC 8252 — PKCE
    is the actual protection; Google still issues one, so we accept it.

Pure stdlib (http.server, secrets, hashlib, ssl, smtplib): no new deps.
"""

import base64
import hashlib
import http.server
import json
import secrets
import smtplib
import socket
import threading
import time
import urllib.parse
import urllib.request

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GMAIL_SCOPE = "https://mail.google.com/"
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465
SECRET_ID = "email_oauth_google"        # keychain slot (JSON token bundle)


# ---------------------------------------------------------------------------
# PKCE + loopback flow
# ---------------------------------------------------------------------------

def _pkce_pair():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class _CodeCatcher(http.server.BaseHTTPRequestHandler):
    code = None
    state = None

    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _CodeCatcher.code = (q.get("code") or [None])[0]
        got_state = (q.get("state") or [None])[0]
        ok = _CodeCatcher.code and got_state == _CodeCatcher.state
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        msg = ("✅ Kalandra is connected — you can close this tab."
               if ok else "⚠ Sign-in failed or was tampered with — close this "
                          "tab and try again from Kalandra.")
        self.wfile.write(f"<h2>{msg}</h2>".encode())
        if not ok:
            _CodeCatcher.code = None

    def log_message(self, *a):            # silence request logging
        pass


def run_gmail_oauth(client_id, client_secret, open_browser, timeout=180):
    """Full installed-app flow. `open_browser(url)` is injected by the GUI.
    Returns {'ok': True, 'token': {...}} or {'ok': False, 'error': str}.
    The token dict: access_token, refresh_token, expires_at, email?"""
    if not client_id:
        return {"ok": False, "error": "No Google client_id configured."}
    try:
        # Loopback on an ephemeral port — exactly what RFC 8252 prescribes.
        srv = http.server.HTTPServer(("127.0.0.1", 0), _CodeCatcher)
        port = srv.server_address[1]
        redirect = f"http://127.0.0.1:{port}/"
        verifier, challenge = _pkce_pair()
        state = secrets.token_urlsafe(24)
        _CodeCatcher.code, _CodeCatcher.state = None, state

        params = {
            "client_id": client_id, "redirect_uri": redirect,
            "response_type": "code", "scope": GMAIL_SCOPE,
            "code_challenge": challenge, "code_challenge_method": "S256",
            "state": state, "access_type": "offline", "prompt": "consent",
        }
        open_browser(GOOGLE_AUTH + "?" + urllib.parse.urlencode(params))

        srv.timeout = 1
        deadline = time.time() + timeout
        while _CodeCatcher.code is None and time.time() < deadline:
            srv.handle_request()
        srv.server_close()
        if not _CodeCatcher.code:
            return {"ok": False, "error": "Timed out waiting for the browser "
                                          "sign-in (3-minute window)."}

        data = {
            "client_id": client_id, "code": _CodeCatcher.code,
            "code_verifier": verifier, "grant_type": "authorization_code",
            "redirect_uri": redirect,
        }
        if client_secret:
            data["client_secret"] = client_secret
        tok = _post_form(GOOGLE_TOKEN, data)
        if "error" in tok:
            return {"ok": False, "error": f"{tok.get('error')}: "
                                          f"{tok.get('error_description', '')}"}
        bundle = {
            "access_token": tok["access_token"],
            "refresh_token": tok.get("refresh_token", ""),
            "expires_at": time.time() + int(tok.get("expires_in", 3600)) - 60,
            "client_id": client_id,
            "client_secret": client_secret or "",
        }
        return {"ok": True, "token": bundle}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _post_form(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"error": f"HTTP {e.code}"}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Token upkeep + XOAUTH2 transport
# ---------------------------------------------------------------------------

def refresh_if_needed(bundle):
    """Return a live bundle, refreshing via the refresh_token when expired.
    Raises RuntimeError with a human reason on failure."""
    if not isinstance(bundle, dict) or not bundle.get("refresh_token"):
        raise RuntimeError("No stored Google token — connect Gmail in Settings.")
    if time.time() < float(bundle.get("expires_at", 0)):
        return bundle
    data = {
        "client_id": bundle.get("client_id", ""),
        "refresh_token": bundle["refresh_token"],
        "grant_type": "refresh_token",
    }
    if bundle.get("client_secret"):
        data["client_secret"] = bundle["client_secret"]
    tok = _post_form(GOOGLE_TOKEN, data)
    if "error" in tok:
        raise RuntimeError(f"Token refresh failed: {tok.get('error')} "
                           f"{tok.get('error_description', '')}".strip())
    bundle = dict(bundle)
    bundle["access_token"] = tok["access_token"]
    bundle["expires_at"] = time.time() + int(tok.get("expires_in", 3600)) - 60
    if tok.get("refresh_token"):               # Google may rotate it
        bundle["refresh_token"] = tok["refresh_token"]
    return bundle


def xoauth2_string(address, access_token):
    """SASL XOAUTH2 initial response (RFC pattern Gmail expects)."""
    return base64.b64encode(
        f"user={address}\x01auth=Bearer {access_token}\x01\x01".encode()
    ).decode()


def send_mail_oauth(address, bundle, to_addr, subject, body_text):
    """Send a plain-text mail over implicit-TLS SMTP with XOAUTH2.
    Returns the (possibly refreshed) bundle. Raises on failure."""
    bundle = refresh_if_needed(bundle)
    from email.mime.text import MIMEText
    msg = MIMEText(body_text, "plain", "utf-8")
    msg["From"], msg["To"], msg["Subject"] = address, to_addr, subject
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as s:
        s.ehlo()
        code, resp = s.docmd(
            "AUTH", "XOAUTH2 " + xoauth2_string(address, bundle["access_token"]))
        if code != 235:
            raise RuntimeError(f"XOAUTH2 rejected ({code}): {resp!r} — "
                               "reconnect Gmail in Settings.")
        s.sendmail(address, [to_addr], msg.as_string())
    return bundle


# ---------------------------------------------------------------------------
# Keychain helpers (storage NEVER touches config.json / disk)
# ---------------------------------------------------------------------------

def store_bundle(account_manager, address, bundle):
    try:
        payload = json.dumps({"address": address, "bundle": bundle})
        return bool(account_manager and
                    account_manager.set_secret(SECRET_ID, payload))
    except Exception:
        return False


def load_bundle(account_manager):
    """-> (address, bundle) or (None, None)."""
    try:
        raw = account_manager.get_secret(SECRET_ID) if account_manager else None
        if not raw:
            return None, None
        d = json.loads(raw)
        return d.get("address"), d.get("bundle")
    except Exception:
        return None, None
