"""Google sign-in and a small REST client for the Gmail, Calendar and Sheets tools. Standard library only.

Sign-in is the OAuth "installed app" flow with PKCE: `ab auth google` opens a browser, Google redirects back to a
loopback port on this machine, and the refresh token is saved to one private file (default
~/.config/agentbuilder/google-token.json, mode 0600, directory 0700; override with AGENTBUILDER_GOOGLE_TOKEN_FILE).
Tool servers read that file; no key travels through a spec, an environment variable or a log.

Google endpoints are constants here, never read from the client-secret file, so a crafted file cannot send the
client secret or a code to another host. Error messages are written for the model and the user: they never
contain a token.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCOPES = {
    "gmail.readonly": "https://www.googleapis.com/auth/gmail.readonly",
    "gmail.compose": "https://www.googleapis.com/auth/gmail.compose",
    "calendar.events": "https://www.googleapis.com/auth/calendar.events",
    "spreadsheets.readonly": "https://www.googleapis.com/auth/spreadsheets.readonly",
}
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API_BASES = {
    "gmail": "https://gmail.googleapis.com/gmail/v1",
    "calendar": "https://www.googleapis.com/calendar/v3",
    "sheets": "https://sheets.googleapis.com/v4",
}
MAX_RESPONSE = 2_000_000
TIMEOUT = 20.0
SIGN_IN_HINT = "run `ab auth google` to sign in again"


class ToolError(RuntimeError):
    """A tool could not do what was asked. The message is shown to the model and the user, so it holds no secrets."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None  # a redirect would carry the Authorization header to another host


_OPENER = urllib.request.build_opener(_NoRedirect)


def token_file() -> Path:
    override = os.environ.get("AGENTBUILDER_GOOGLE_TOKEN_FILE")
    return Path(override) if override else Path.home() / ".config" / "agentbuilder" / "google-token.json"


def _write_private(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.name == "agentbuilder":  # our own folder: tighten it even if it already existed
        os.chmod(path.parent, 0o700)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def _json_request(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    form: Mapping[str, str] | None = None,
    body: Any = None,
    timeout: float = TIMEOUT,
) -> Any:
    data: bytes | None = None
    all_headers = {"Accept": "application/json", "User-Agent": "agentbuilder/0.1", **(headers or {})}
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        all_headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        all_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=all_headers, method=method)
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE + 1)
    except urllib.error.HTTPError as exc:
        raise _http_error(exc) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ToolError(f"could not reach Google ({type(exc).__name__}); check the network and try again") from None
    if len(raw) > MAX_RESPONSE:
        raise ToolError("Google's answer was too large to read safely")
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        raise ToolError("Google sent an answer that is not valid JSON") from None


def _http_error(exc: urllib.error.HTTPError) -> ToolError:
    try:
        detail = str((json.loads(exc.read(20_000)).get("error") or {}).get("message", ""))[:200]
    except (ValueError, AttributeError):
        detail = ""
    if exc.code == 401:
        return ToolError(f"Google rejected the sign-in; {SIGN_IN_HINT}")
    if exc.code == 403:
        return ToolError(f"Google refused: the account has not granted this permission ({detail or 'forbidden'})")
    if exc.code == 404:
        return ToolError(f"Google could not find that item ({detail or 'not found'})")
    if exc.code == 429:
        return ToolError("Google's rate limit was reached; wait a minute and try again")
    return ToolError(f"Google returned HTTP {exc.code} ({detail or 'no details'})")


@dataclass
class RefreshingToken:
    """Gives out a valid access token, refreshing it from the saved refresh token when it is about to expire."""

    path: Path = field(default_factory=token_file)
    token_url: str = TOKEN_URL
    _access: str = ""
    _expires: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __call__(self) -> str:
        with self._lock:
            if self._access and time.monotonic() < self._expires - 60:
                return self._access
            try:
                saved = json.loads(self.path.read_text(encoding="utf-8"))
                form = {
                    "grant_type": "refresh_token",
                    "refresh_token": saved["refresh_token"],
                    "client_id": saved["client_id"],
                    "client_secret": saved["client_secret"],
                }
            except (OSError, ValueError, KeyError):
                raise ToolError(f"Google is not signed in; {SIGN_IN_HINT}") from None
            try:
                answer = _json_request("POST", self.token_url, form=form)
            except ToolError as exc:
                if "HTTP 400" in str(exc) or "HTTP 401" in str(exc):  # a revoked or expired (7-day test mode) token
                    raise ToolError(f"Google no longer accepts the saved sign-in; {SIGN_IN_HINT}") from None
                raise
            self._access = str(answer.get("access_token", ""))
            if not self._access:
                raise ToolError(f"Google did not return an access token; {SIGN_IN_HINT}")
            self._expires = time.monotonic() + float(answer.get("expires_in", 3000))
            return self._access


class GoogleClient:
    def __init__(self, token: Callable[[], str], bases: Mapping[str, str] | None = None) -> None:
        self._token = token
        self._bases = dict(API_BASES if bases is None else bases)

    def request(
        self,
        method: str,
        service: str,
        path: str,
        *,
        params: Sequence[tuple[str, str]] | None = None,
        body: Any = None,
    ) -> Any:
        url = self._bases[service] + path
        if params:
            url += "?" + urllib.parse.urlencode(list(params))
        return _json_request(method, url, headers={"Authorization": f"Bearer {self._token()}"}, body=body)

    def get(self, service: str, path: str, params: Sequence[tuple[str, str]] | None = None) -> Any:
        return self.request("GET", service, path, params=params)

    def post(self, service: str, path: str, body: Any, params: Sequence[tuple[str, str]] | None = None) -> Any:
        return self.request("POST", service, path, params=params, body=body)


_client: GoogleClient | None = None


def get_client() -> GoogleClient:
    """The shared client the tools use. Tests replace it with `set_client`."""
    global _client
    if _client is None:
        _client = GoogleClient(RefreshingToken())
    return _client


def set_client(client: GoogleClient | None) -> None:
    global _client
    _client = client


# ---- sign in (`ab auth google`) -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Endpoints:
    auth: str = AUTH_URL
    token: str = TOKEN_URL
    revoke: str = REVOKE_URL


def read_client_secret(path: str | Path) -> tuple[str, str]:
    """(client_id, client_secret) from the JSON file downloaded from Google Cloud ("Desktop app" client)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        installed = data["installed"]
        return str(installed["client_id"]), str(installed["client_secret"])
    except (OSError, ValueError, KeyError, TypeError):
        raise ToolError(
            'that is not a Google OAuth client file for a "Desktop app" (it should contain an "installed" section)'
        ) from None


def sign_in(
    client_secret_file: str | Path,
    scopes: Sequence[str] = tuple(SCOPES),
    *,
    open_browser: Callable[[str], object] = webbrowser.open,
    endpoints: Endpoints = Endpoints(),  # noqa: B008  frozen dataclass, safe as a default
    path: Path | None = None,
    timeout: float = 300.0,
) -> Path:
    """Run the browser sign-in and save the refresh token. Returns the token file's path."""
    client_id, client_secret = read_client_secret(client_secret_file)
    unknown = [s for s in scopes if s not in SCOPES]
    if unknown:
        raise ToolError(f"unknown scope(s): {', '.join(unknown)}")
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    received: dict[str, str] = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            got = {k: v[0] for k, v in query.items()}
            if got.get("state") != state:
                self.send_response(400)
                self.end_headers()
                return  # a stray request must not end the wait or be trusted
            received.update(got)
            body = b"Signed in. You can close this tab and return to the terminal."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            done.set()

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    redirect_uri = f"http://127.0.0.1:{server.server_port}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = (
            endpoints.auth
            + "?"
            + urllib.parse.urlencode(
                {
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "response_type": "code",
                    "scope": " ".join(SCOPES[s] for s in scopes),
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "access_type": "offline",
                    "prompt": "consent",
                    "state": state,
                }
            )
        )
        open_browser(url)
        if not done.wait(timeout):
            raise ToolError("sign-in timed out; run the command again")
    finally:
        server.shutdown()
        server.server_close()
    if "error" in received or "code" not in received:
        raise ToolError(f"Google did not grant access ({received.get('error', 'no code returned')})")
    answer = _json_request(
        "POST",
        endpoints.token,
        form={
            "grant_type": "authorization_code",
            "code": received["code"],
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
            "code_verifier": verifier,
        },
    )
    if not answer.get("refresh_token"):
        raise ToolError(
            "Google returned no refresh token; remove the app under your Google account's third-party access "
            "and sign in again"
        )
    target = path or token_file()
    _write_private(
        target,
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": answer["refresh_token"],
            "scopes": list(scopes),
            "saved_at": int(time.time()),
        },
    )
    return target


def status(path: Path | None = None) -> dict[str, Any]:
    """What is saved, without ever returning a secret."""
    target = path or token_file()
    try:
        saved = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"signed_in": False, "path": str(target)}
    return {
        "signed_in": bool(saved.get("refresh_token")),
        "path": str(target),
        "scopes": saved.get("scopes", []),
        "saved_days_ago": int((time.time() - float(saved.get("saved_at", time.time()))) // 86400),
    }


def sign_out(path: Path | None = None, *, endpoints: Endpoints = Endpoints()) -> bool:  # noqa: B008
    """Revoke the token at Google (best effort) and delete the file. True if a file was removed."""
    target = path or token_file()
    try:
        refresh = json.loads(target.read_text(encoding="utf-8")).get("refresh_token")
    except (OSError, ValueError):
        return False
    if refresh:
        with contextlib.suppress(ToolError):  # offline or already revoked: still remove the local copy
            _json_request("POST", endpoints.revoke, form={"token": refresh})
    target.unlink(missing_ok=True)
    return True
