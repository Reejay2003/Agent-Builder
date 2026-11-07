import base64
import hashlib
import json
import os
import stat
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agentbuilder.library import google
from tests.fake_google import ACCESS, REFRESH, FakeGoogle


@pytest.fixture
def fake():
    server = FakeGoogle()
    yield server
    server.stop()


@pytest.fixture
def client_file(tmp_path):
    f = tmp_path / "client_secret.json"
    f.write_text(json.dumps({"installed": {"client_id": "cid.apps.example", "client_secret": "csecret-for-tests"}}))
    return f


def endpoints(fake):
    return google.Endpoints(auth=fake.url + "/auth", token=fake.url + "/token", revoke=fake.url + "/revoke")


def browser_that_approves(seen):
    """Plays the user's browser: opens the consent URL's redirect with a code (or a hostile stray request first)."""

    def open_browser(url):
        query = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}
        seen.update(query)
        redirect = query["redirect_uri"]
        with pytest.raises(urllib.error.HTTPError):  # a request with the wrong state is refused and ignored
            urllib.request.urlopen(f"{redirect}/?code=evil&state=wrong", timeout=5)
        urllib.request.urlopen(f"{redirect}/?code=the-code&state={query['state']}", timeout=5).read()

    return open_browser


def test_sign_in_uses_pkce_saves_a_private_token_file_and_never_prints_secrets(fake, client_file, tmp_path):
    seen = {}
    target = tmp_path / "cfg" / "agentbuilder" / "google-token.json"
    saved = google.sign_in(
        client_file, open_browser=browser_that_approves(seen), endpoints=endpoints(fake), path=target
    )
    assert saved == target
    assert seen["code_challenge_method"] == "S256" and seen["access_type"] == "offline"
    assert (
        "gmail.readonly" in seen["scope"] and "gmail.send" not in seen["scope"]
    )  # the minimum, and never the send scope
    exchange = fake.token_requests[0]
    assert exchange["code"] == "the-code" and exchange["client_secret"] == "csecret-for-tests"
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(exchange["code_verifier"].encode()).digest()).rstrip(b"=").decode()
    )
    assert challenge == seen["code_challenge"]  # the verifier really matches the challenge Google was given
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600 and stat.S_IMODE(os.stat(target.parent).st_mode) == 0o700
    assert json.loads(target.read_text())["refresh_token"] == REFRESH
    info = google.status(target)
    assert info["signed_in"] and REFRESH not in json.dumps(info) and "csecret" not in json.dumps(info)


def test_sign_in_rejects_a_bad_client_file_and_unknown_scopes(tmp_path, client_file):
    bad = tmp_path / "bad.json"
    bad.write_text('{"web": {}}')
    with pytest.raises(google.ToolError, match="Desktop app"):
        google.sign_in(bad, path=tmp_path / "t.json")
    with pytest.raises(google.ToolError, match="unknown scope"):
        google.sign_in(client_file, scopes=["gmail.send"], path=tmp_path / "t.json")


def test_sign_in_times_out_without_a_browser_approval(fake, client_file, tmp_path):
    with pytest.raises(google.ToolError, match="timed out"):
        google.sign_in(
            client_file, open_browser=lambda url: None, endpoints=endpoints(fake), path=tmp_path / "t.json", timeout=0.3
        )
    assert not (tmp_path / "t.json").exists()


def saved_token(tmp_path):
    path = tmp_path / "google-token.json"
    path.write_text(
        json.dumps({"client_id": "cid", "client_secret": "cs", "refresh_token": REFRESH, "scopes": [], "saved_at": 0})
    )
    return path


def test_the_access_token_is_cached_and_refreshed_from_the_saved_token(fake, tmp_path):
    token = google.RefreshingToken(path=saved_token(tmp_path), token_url=fake.url + "/token")
    assert token() == ACCESS and token() == ACCESS
    assert len(fake.token_requests) == 1 and fake.token_requests[0]["refresh_token"] == REFRESH


def test_missing_or_revoked_sign_in_tells_the_user_to_sign_in_again(fake, tmp_path):
    with pytest.raises(google.ToolError, match="ab auth google"):
        google.RefreshingToken(path=tmp_path / "none.json", token_url=fake.url + "/token")()
    fake.refresh_status = 400
    with pytest.raises(google.ToolError, match="no longer accepts"):
        google.RefreshingToken(path=saved_token(tmp_path), token_url=fake.url + "/token")()


@pytest.mark.parametrize(
    "status, fragment",
    [(401, "sign-in"), (403, "permission"), (404, "could not find"), (429, "rate limit"), (500, "HTTP 500")],
)
def test_google_errors_become_plain_messages_without_the_token(fake, status, fragment):
    fake.fail_with = status
    client = google.GoogleClient(lambda: ACCESS, fake.bases)
    with pytest.raises(google.ToolError, match=fragment) as caught:
        client.get("gmail", "/users/me/messages")
    assert ACCESS not in str(caught.value)


def test_a_redirect_is_never_followed_so_the_token_cannot_be_sent_elsewhere():
    hits = []

    class Target(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(307)
            self.send_header("Location", f"http://127.0.0.1:{target.server_port}/x")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass

    target, redirect = HTTPServer(("127.0.0.1", 0), Target), HTTPServer(("127.0.0.1", 0), Redirect)
    for s in (target, redirect):
        threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        client = google.GoogleClient(lambda: ACCESS, {"gmail": f"http://127.0.0.1:{redirect.server_port}"})
        with pytest.raises(google.ToolError):
            client.get("gmail", "/x")
    finally:
        target.shutdown()
        redirect.shutdown()
    assert hits == []


def test_sign_out_revokes_at_google_and_removes_the_file(fake, tmp_path):
    path = saved_token(tmp_path)
    assert google.sign_out(path, endpoints=endpoints(fake)) is True
    assert not path.exists() and fake.calls("/revoke")
    assert google.sign_out(path, endpoints=endpoints(fake)) is False
