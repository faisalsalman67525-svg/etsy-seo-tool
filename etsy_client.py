"""
etsy_client.py — one authenticated HTTP client for every Etsy v3 call.

Handles:
  * Bearer token + x-api-key headers on every request
  * Silent token refresh on 401 (once per request)
  * Etsy rate limits: 10 requests/second, 10,000/day
    - client-side throttle: max ~8 req/s (0.12 s between calls)
    - server 429: honour Retry-After, exponential back-off, max 3 retries
  * Clean EtsyAPIError with status + Etsy’s own error message
"""
from __future__ import annotations

import mimetypes
import time
from pathlib import Path
from typing import Any

import requests

from auth import (
    API_BASE,
    EtsyAuthError,
    get_api_key_header,
    get_valid_access_token,
    refresh_access_token,
)

# Stay just under Etsy's 10 QPS limit.
MIN_INTERVAL_SECONDS = 0.12
MAX_429_RETRIES = 3


class EtsyAPIError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class EtsyClient:
    def __init__(self):
        self._last_call_at = 0.0
        self._session = requests.Session()

    # -- internal ---------------------------------------------------------
    def _throttle(self) -> None:
        elapsed = time.time() - self._last_call_at
        if elapsed < MIN_INTERVAL_SECONDS:
            time.sleep(MIN_INTERVAL_SECONDS - elapsed)
        self._last_call_at = time.time()

    def _headers(self, token: str, is_json: bool = True) -> dict:
        headers = {
            "Authorization": f"Bearer {token}",
            # Etsy v3: x-api-key must be "keystring:shared_secret", not keystring alone.
            "x-api-key": get_api_key_header(),
        }
        if is_json:
            headers["Content-Type"] = "application/json"
        return headers

    @staticmethod
    def _error_message(resp: requests.Response) -> str:
        try:
            data = resp.json()
            return str(data.get("error") or data.get("message") or resp.text)[:500]
        except ValueError:
            return resp.text[:500]

    # -- core request -----------------------------------------------------
    def request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        json_body: dict | None = None,
        files: dict | None = None,
        data: dict | None = None,
        form: bool = False,
    ) -> Any:
        """
        endpoint: e.g. "/listings/active" or "/shops/123/listings"
        Returns parsed JSON (dict/list) or {} for empty 204 responses.
        """
        url = f"{API_BASE}{endpoint}"
        token = get_valid_access_token()
        retries_429 = 0
        refreshed_once = False

        while True:
            self._throttle()
            try:
                resp = self._session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_body,
                    files=files,
                    data=data,
                    headers=self._headers(token, is_json=(files is None and not form)),
                    timeout=60,
                )
            except requests.RequestException as exc:
                raise EtsyAPIError(f"Network error calling {endpoint}: {exc}") from exc

            if resp.status_code == 429 and retries_429 < MAX_429_RETRIES:
                wait = resp.headers.get("Retry-After")
                delay = float(wait) if wait else 2.0 * (2 ** retries_429)
                time.sleep(min(delay, 30))
                retries_429 += 1
                continue

            if resp.status_code == 401 and not refreshed_once:
                try:
                    token = refresh_access_token()["access_token"]
                except EtsyAuthError as exc:
                    raise EtsyAPIError(
                        "Session expired — please reconnect.", status=401
                    ) from exc
                refreshed_once = True
                continue

            if resp.status_code in (200, 201):
                if not resp.content:
                    return {}
                try:
                    return resp.json()
                except ValueError:
                    return {"raw": resp.text}

            if resp.status_code == 204:
                return {}

            raise EtsyAPIError(
                f"Etsy API {resp.status_code} on {method} {endpoint}: "
                f"{self._error_message(resp)}",
                status=resp.status_code,
            )

    # -- convenience wrappers ---------------------------------------------
    def get(self, endpoint: str, params: dict | None = None) -> Any:
        return self.request("GET", endpoint, params=params)

    def post(self, endpoint: str, json_body: dict | None = None) -> Any:
        return self.request("POST", endpoint, json_body=json_body)

    def put(self, endpoint: str, json_body: dict | None = None) -> Any:
        return self.request("PUT", endpoint, json_body=json_body)

    def put_form(self, endpoint: str, data: dict) -> Any:
        """PUT with application/x-www-form-urlencoded body (e.g. updateShop)."""
        return self.request("PUT", endpoint, data=data, form=True)

    def delete(self, endpoint: str) -> Any:
        return self.request("DELETE", endpoint)

    def post_multipart(
        self, endpoint: str, file_field: str, file_path: str | Path, extra: dict | None = None
    ) -> Any:
        """POST a single file field (images / digital files)."""
        path = Path(file_path)
        if not path.exists():
            raise EtsyAPIError(f"File not found: {path}")
        mime, _ = mimetypes.guess_type(str(path))
        with path.open("rb") as fh:
            files = {file_field: (path.name, fh, mime or "application/octet-stream")}
            return self.request("POST", endpoint, files=files, data=extra or {})
