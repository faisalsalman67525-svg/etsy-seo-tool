"""
auth.py — Etsy API v3 OAuth 2.0 with PKCE.

This tool only reads public data, so it requests read-only scopes
(listings_r, shops_r). Each user connects with their own Etsy app
credentials — nothing is shared.

Flow:
  1. Generate a PKCE code_verifier / code_challenge (S256).
  2. Open https://www.etsy.com/oauth/connect in the browser.
  3. A tiny local server on http://localhost:8080/callback captures `code`.
  4. Exchange the code for access + refresh tokens at
     https://api.etsy.com/v3/public/oauth/token
  5. Save tokens to tokens.json (NOT .env — .env is only for the
     Keystring / Shared Secret). Refresh automatically when expired.

Required setup in the Etsy Developer Portal (https://www.etsy.com/developers):
  - Callback URL must be exactly: http://localhost:8080/callback
  - Scopes below must be enabled for your app.

Never commit .env or tokens.json — both are in .gitignore.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration — loaded from .env, never hardcoded
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
TOKEN_FILE = BASE_DIR / "tokens.json"

AUTH_URL = "https://www.etsy.com/oauth/connect"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
API_BASE = "https://openapi.etsy.com/v3/application"

REDIRECT_URI = "http://localhost:8080/callback"
CALLBACK_HOST = "localhost"
CALLBACK_PORT = 8080

# Read-only: this tool only searches public listings and shops.
SCOPES = [
    "listings_r",
    "shops_r",
]

# Etsy access tokens live ~1 hour (3600 s). Refresh 60 s early.
REFRESH_BUFFER_SECONDS = 60


class EtsyAuthError(Exception):
    """Raised for any OAuth / token problem with a human-readable message."""


def get_client_id() -> str:
    client_id = os.getenv("ETSY_API_KEY", "").strip()
    if not client_id:
        raise EtsyAuthError(
            "ETSY_API_KEY is missing. Copy .env.example to .env and paste "
            "your Etsy Keystring (Client ID) there."
        )
    return client_id


def get_shared_secret() -> str:
    return os.getenv("ETSY_SHARED_SECRET", "").strip()


def get_api_key_header() -> str:
    """
    CRITICAL FIX (2026-11-20): Etsy v3 requires the x-api-key header to be
    `keystring:shared_secret` — NOT the keystring alone.
    Docs: "Every request to a v3 endpoint must include an x-api-key header
    containing your keystring and shared secret separated by a colon."
    Sending only the keystring caused 403 Forbidden on /users/me and on
    the shop-name lookup, even though OAuth login itself had succeeded
    (the token exchange uses client_id only, so it worked fine).
    """
    client_id = get_client_id()
    secret = get_shared_secret()
    return f"{client_id}:{secret}" if secret else client_id


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------
def generate_code_verifier() -> str:
    """43–128 char URL-safe verifier. secrets.token_urlsafe(64) ≈ 86 chars."""
    return secrets.token_urlsafe(64)


def generate_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def build_auth_url(client_id: str, code_challenge: str, state: str) -> str:
    params = {
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "client_id": client_id,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


# ---------------------------------------------------------------------------
# Token storage
# ---------------------------------------------------------------------------
def save_tokens(token_data: dict) -> dict:
    """Add obtained_at / expires_at, then write tokens.json (0600)."""
    now = int(time.time())
    token_data = dict(token_data)
    token_data["obtained_at"] = now
    expires_in = int(token_data.get("expires_in", 3600))
    token_data["expires_at"] = now + expires_in
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2), encoding="utf-8")
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass
    return token_data


def load_tokens() -> dict | None:
    if not TOKEN_FILE.exists():
        return None
    try:
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) and data.get("access_token") else None


def clear_tokens() -> None:
    try:
        TOKEN_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def is_token_expired(token_data: dict | None = None) -> bool:
    token_data = token_data or load_tokens()
    if not token_data:
        return True
    expires_at = int(token_data.get("expires_at", 0))
    return time.time() >= expires_at - REFRESH_BUFFER_SECONDS


def token_status() -> dict:
    """Small, safe summary for the UI — never returns the token itself."""
    data = load_tokens()
    if not data:
        return {"connected": False, "expires_at": None, "seconds_left": 0}
    seconds_left = max(0, int(data.get("expires_at", 0)) - int(time.time()))
    return {
        "connected": True,
        "expired": is_token_expired(data),
        "expires_at": data.get("expires_at"),
        "seconds_left": seconds_left,
        "has_refresh_token": bool(data.get("refresh_token")),
    }


# ---------------------------------------------------------------------------
# Token exchange / refresh
# ---------------------------------------------------------------------------
def exchange_code_for_token(code: str, code_verifier: str) -> dict:
    payload = {
        "grant_type": "authorization_code",
        "client_id": get_client_id(),
        "redirect_uri": REDIRECT_URI,
        "code": code,
        "code_verifier": code_verifier,
    }
    resp = requests.post(TOKEN_URL, data=payload, timeout=30)
    if resp.status_code != 200:
        raise EtsyAuthError(
            f"Token exchange failed ({resp.status_code}): {resp.text[:500]}"
        )
    return save_tokens(resp.json())


def refresh_access_token(refresh_token: str | None = None) -> dict:
    refresh_token = refresh_token or (load_tokens() or {}).get("refresh_token")
    if not refresh_token:
        raise EtsyAuthError(
            "No refresh token saved. Please connect again from the dashboard."
        )
    payload = {
        "grant_type": "refresh_token",
        "client_id": get_client_id(),
        "refresh_token": refresh_token,
    }
    resp = requests.post(TOKEN_URL, data=payload, timeout=30)
    if resp.status_code != 200:
        # Refresh token itself is dead — force a clean re-login.
        if resp.status_code in (400, 401):
            clear_tokens()
        raise EtsyAuthError(
            f"Token refresh failed ({resp.status_code}): {resp.text[:500]}"
        )
    data = resp.json()
    # Etsy sometimes omits refresh_token on refresh; keep the old one.
    if "refresh_token" not in data:
        data["refresh_token"] = refresh_token
    return save_tokens(data)


def get_valid_access_token() -> str:
    """Return a live access token, refreshing silently if needed."""
    tokens = load_tokens()
    if not tokens:
        raise EtsyAuthError("Not connected. Click 'Connect to Etsy' first.")
    if is_token_expired(tokens):
        tokens = refresh_access_token(tokens.get("refresh_token"))
    return tokens["access_token"]


# ---------------------------------------------------------------------------
# Local callback server — captures ?code=...&state=...
# ---------------------------------------------------------------------------
class _CallbackHandler(BaseHTTPRequestHandler):
    # Set by run_local_server_and_wait() before serving.
    result: dict = {}
    expected_state: str = ""

    def do_GET(self):  # noqa: N802 — http.server naming
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        code = (query.get("code") or [None])[0]
        state = (query.get("state") or [None])[0]
        error = (query.get("error") or [None])[0]

        # BUG FIX (2026-11-20): `self.result = ...` only set an attribute
        # on this one handler *instance*, so run_local_server_and_wait()
        # reading `Handler.result` (the class attribute) always saw {} and
        # timed out after 5 minutes — even though the browser showed
        # "Connected to Etsy". Store it on the class (and the server) instead.
        if error:
            result = {"error": error}
        elif code and state == self.expected_state:
            result = {"code": code, "state": state}
        else:
            result = {"error": "state_mismatch_or_missing_code"}
        type(self).result = result
        self.server.result = result  # type: ignore[attr-defined]

        body = (
            "<html><body style='font-family:sans-serif;padding:40px'>"
            "<h2>Connected to Etsy ✓</h2>"
            "<p>You can close this tab and return to the app.</p>"
            "</body></html>"
            if "code" in result
            else "<html><body style='font-family:sans-serif;padding:40px'>"
            "<h2>Login failed</h2><p>Please close this tab and try again.</p>"
            "</body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body.encode())))
        self.end_headers()
        self.wfile.write(body.encode())
        # Shut the server down from a new thread (can't join from handler).
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, *args):  # silence default logging
        pass


def run_local_server_and_wait(expected_state: str, timeout: int = 300) -> str:
    """Serve http://localhost:8080/callback once, return the auth code."""
    handler = type(
        "Handler",
        (_CallbackHandler,),
        {"result": {}, "expected_state": expected_state},
    )
    server = ThreadingHTTPServer((CALLBACK_HOST, CALLBACK_PORT), handler)
    server.result = {}  # type: ignore[attr-defined]
    server.timeout = timeout
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    try:
        server.server_close()
    except Exception:
        pass
    # Prefer the server-stored result, fall back to the class attribute.
    result = getattr(server, "result", None) or handler.result
    if not result:
        raise EtsyAuthError(
            "Timed out waiting for Etsy login (5 minutes). "
            "Check the callback URL in the Etsy Developer Portal is exactly "
            f"{REDIRECT_URI} and try again."
        )
    if "error" in result:
        raise EtsyAuthError(f"Etsy login failed: {result['error']}")
    return result["code"]


def ensure_authenticated(open_browser: bool = True) -> dict:
    """
    Full first-time login. Returns saved token dict.
    If a valid (or refreshable) token already exists, returns it unchanged.
    """
    existing = load_tokens()
    if existing:
        try:
            get_valid_access_token()
            return load_tokens()  # type: ignore[return-value]
        except EtsyAuthError:
            pass  # fall through to a fresh login

    client_id = get_client_id()
    verifier = generate_code_verifier()
    challenge = generate_code_challenge(verifier)
    state = secrets.token_urlsafe(32)
    url = build_auth_url(client_id, challenge, state)

    print(f"Opening browser:\n{url}")
    if open_browser:
        webbrowser.open(url)
    print("Waiting for Etsy login on http://localhost:8080/callback ...")
    code = run_local_server_and_wait(expected_state=state)
    return exchange_code_for_token(code, verifier)


def get_shop_id_by_name(shop_name: str) -> int:
    """
    GET /shops?shop_name=... — the reliable way to get a shop_id.
    Uses only the shops_r scope (already granted), unlike /users/me
    which Etsy returns 403 for on some apps/scopes.
    Returns the shop_id, or raises EtsyAuthError.
    """
    token = get_valid_access_token()
    resp = requests.get(
        f"{API_BASE}/shops",
        params={"shop_name": shop_name},
        headers={
            "Authorization": f"Bearer {token}",
            "x-api-key": get_api_key_header(),
        },
        timeout=30,
    )
    if resp.status_code == 401:
        token = refresh_access_token()["access_token"]
        resp = requests.get(
            f"{API_BASE}/shops",
            params={"shop_name": shop_name},
            headers={
                "Authorization": f"Bearer {token}",
                "x-api-key": get_api_key_header(),
            },
            timeout=30,
        )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", []) if isinstance(data, dict) else []
    if not results:
        raise EtsyAuthError(f"No Etsy shop found with name '{shop_name}'.")
    return int(results[0]["shop_id"])


def get_user_and_shop_id() -> dict:
    """
    Returns {'user_id': ..., 'shop_id': ...}.
    Tries GET /users/me first; on 403 (seen on some apps — /users/me
    needs a profile scope this app does not request) falls back to
    GET /shops?shop_name=<ETSY_SHOP_NAME>.
    """
    token = get_valid_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "x-api-key": get_api_key_header(),
    }
    resp = requests.get(f"{API_BASE}/users/me", headers=headers, timeout=30)
    if resp.status_code == 401:
        token = refresh_access_token()["access_token"]
        headers["Authorization"] = f"Bearer {token}"
        resp = requests.get(f"{API_BASE}/users/me", headers=headers, timeout=30)
    if resp.status_code == 403:
        shop_name = os.getenv("ETSY_SHOP_NAME", "").strip()
        if not shop_name:
            raise EtsyAuthError(
                "/users/me returned 403 for this app. Set ETSY_SHOP_NAME "
                "in .env to your shop name and try again (the app then "
                "uses the shops_r scope to find your shop)."
            )
        print(
            f"/users/me returned 403 — falling back to shop-name lookup "
            f"for '{shop_name}' (shops_r scope)."
        )
        shop_id = get_shop_id_by_name(shop_name)
        return {"user_id": None, "shop_id": shop_id, "shop_name": shop_name}
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    # python auth.py  — run the login flow from the terminal.
    tokens = ensure_authenticated()
    print("Connected. Token expires in", tokens.get("expires_in"), "seconds.")
    print("Saved to tokens.json — do not share this file.")
    try:
        me = get_user_and_shop_id()
        print(f"User ID: {me.get('user_id')}  Shop ID: {me.get('shop_id')}")
    except Exception as exc:  # noqa: BLE001 — CLI convenience
        print(f"Could not fetch shop info yet: {exc}")
