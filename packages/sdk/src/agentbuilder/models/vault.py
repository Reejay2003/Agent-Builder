"""A SecretStore that asks the Agent Builder web app's key vault for a key, over loopback.

`secret://modelcfg/3/api_key` becomes `GET <web app>/api/internal/secrets/modelcfg/3/api_key` with the shared token in
`X-AgentBuilder-Token`. The web app answers only while a user is signed in and the vault is unlocked.
The key is returned to the caller in memory; nothing here logs or stores it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from agentbuilder.models.credentials import CredentialError

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
TOKEN_HEADER = "X-AgentBuilder-Token"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect: it would carry the token to wherever the redirect points."""

    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


class LocalVaultStore:
    def __init__(self, base_url: str, token: str, *, timeout: float = 5.0) -> None:
        host = urllib.parse.urlsplit(base_url).hostname
        if host not in LOOPBACK:
            raise ValueError(f"the key vault must be on this machine (127.0.0.1 or localhost), got {base_url!r}")
        if not token:
            raise ValueError("a vault token is required")
        self._base = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout

    def get(self, name: str) -> str | None:
        url = f"{self._base}/api/internal/secrets/{urllib.parse.quote(name, safe='/')}"
        request = urllib.request.Request(url, headers={TOKEN_HEADER: self._token, "Accept": "application/json"})
        try:
            with _OPENER.open(request, timeout=self._timeout) as response:
                value = json.load(response).get("value")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if exc.code == 423:
                raise CredentialError(
                    "the key vault is locked: sign in to the web app and unlock it, then retry"
                ) from exc
            if 300 <= exc.code < 400:
                raise CredentialError(
                    "the web app redirected the key request (is the vault endpoint missing, or are you signed out?)"
                ) from exc
            if exc.code in (401, 403):
                raise CredentialError("the web app refused this SDK server's token (restart `ab ui`)") from exc
            raise CredentialError(f"the key vault returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise CredentialError(f"cannot reach the key vault at {self._base}: {type(exc).__name__}") from exc
        return value if isinstance(value, str) else None
