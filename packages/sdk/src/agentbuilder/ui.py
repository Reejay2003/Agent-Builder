"""`ab ui`: start the local SDK server and the web app, wait until both answer, open the browser.

The two processes talk over loopback with two separate random tokens made fresh at every start:
- API token: the web app's server -> the SDK server (validate, tools, runs). Browsers never see it.
- Vault token: the SDK server -> the web app (fetch a stored model key while the vault is unlocked).
They reach the web app through environment variables: AGENTBUILDER_API_URL, AGENTBUILDER_API_TOKEN,
AGENTBUILDER_VAULT_TOKEN.
"""

from __future__ import annotations

import os
import secrets
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Sequence
from dataclasses import dataclass, field
from http.server import ThreadingHTTPServer
from pathlib import Path

from agentbuilder.gateway import default_audit_log
from agentbuilder.models.vault import LocalVaultStore
from agentbuilder.server import LocalServer, build_server
from agentbuilder.tools import ToolCatalog

MIN_NODE = (22, 13)


def find_web_dir(start: Path | None = None) -> Path | None:
    """The repository's apps/web, found by walking up from `start` (default: this file, then the working directory)."""
    for origin in (start, Path(__file__).resolve(), Path.cwd()):
        for parent in [origin, *origin.parents] if origin else []:
            if (parent / "apps" / "web" / "package.json").is_file():
                return parent / "apps" / "web"
    return None


def node_version() -> tuple[int, ...] | None:
    node = shutil.which("node")
    if not node:
        return None
    out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10, check=False).stdout
    try:
        return tuple(int(p) for p in out.strip().lstrip("v").split(".")[:3])
    except ValueError:
        return None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _unreachable(url: str) -> str | None:
    """None when the server answers; otherwise why the last attempt failed (shown when `ab ui` gives up)."""
    try:
        urllib.request.urlopen(url, timeout=2)
    except urllib.error.HTTPError:
        return None  # any HTTP answer (a redirect to /login, a 404) means the server is up
    except (urllib.error.URLError, OSError) as exc:
        return str(getattr(exc, "reason", exc)) or type(exc).__name__
    return None


def _answers(url: str) -> bool:
    return _unreachable(url) is None


@dataclass
class UiSession:
    catalog: ToolCatalog
    web_dir: Path | None = None
    web_port: int = 3000
    api_port: int = 0
    web_command: Sequence[str] | None = None  # default: npm run dev (tests pass a stand-in)
    open_browser: bool = True
    startup_timeout: float = 120.0
    api_url: str = field(init=False, default="")
    web_url: str = field(init=False, default="")
    _server: ThreadingHTTPServer | None = field(init=False, default=None)
    _app: LocalServer | None = field(init=False, default=None)
    _web: subprocess.Popen[bytes] | None = field(init=False, default=None)

    def start(self) -> None:
        self.web_url = f"http://127.0.0.1:{self.web_port}"
        if _answers(self.web_url):
            raise RuntimeError(
                f"another program is already listening on {self.web_url}; choose a free port with --port"
            )
        api_token, vault_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self._app = LocalServer(
            token=api_token,
            catalog=self.catalog,
            stores=[LocalVaultStore(self.web_url, vault_token)],
            audit_log=default_audit_log(),
        )
        self._server = build_server(self._app, port=self.api_port)
        self.api_url = f"http://127.0.0.1:{self._server.server_port}"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        env = {
            **os.environ,
            "AGENTBUILDER_API_URL": self.api_url,
            "AGENTBUILDER_API_TOKEN": api_token,
            "AGENTBUILDER_VAULT_TOKEN": vault_token,
        }
        command = list(
            self.web_command or ["npm", "run", "dev", "--", "--hostname", "127.0.0.1", "--port", str(self.web_port)]
        )
        self._web = subprocess.Popen(command, cwd=self.web_dir, env=env)
        deadline = time.monotonic() + self.startup_timeout
        while (why := _unreachable(self.web_url)) is not None:
            if self._web.poll() is not None:
                self.stop()
                raise RuntimeError(f"the web app exited with code {self._web.returncode} before it was ready")
            if time.monotonic() > deadline:
                self.stop()
                raise TimeoutError(
                    f"the web app did not answer at {self.web_url} within {self.startup_timeout:.0f}s (last try: {why})"
                )
            time.sleep(0.5)
        if self.open_browser:
            webbrowser.open(self.web_url)

    def wait(self) -> None:
        """Block until the web app exits or the user presses Ctrl+C."""
        try:
            while self._web and self._web.poll() is None:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass

    def stop(self) -> None:
        if self._web and self._web.poll() is None:
            self._web.terminate()
            try:
                self._web.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._web.kill()
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._app:
            self._app.shutdown()
