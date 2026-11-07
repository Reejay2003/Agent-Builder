import json
from pathlib import Path

import pytest

from agentbuilder.library import calendar_tools, gmail_tools, google, sheets_tools, web_tools
from tests.fake_google import ACCESS, FakeGoogle

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def fake():
    server = FakeGoogle()
    google.set_client(google.GoogleClient(lambda: ACCESS, server.bases))
    yield server
    google.set_client(None)
    server.stop()


# ---- gmail ------------------------------------------------------------------------------------------------------


def test_gmail_read_returns_clean_one_line_fields(fake):
    mail = gmail_tools.read("from:alice", limit=5)
    assert [m["id"] for m in mail] == ["m1", "m2"]
    first = mail[0]
    assert first["from"] == "Alice <alice@example.com>" and first["date"].startswith("Thu, 5 Nov 2026")
    for field in first.values():
        assert "\n" not in field and "\x00" not in field and "‮" not in field  # no control or bidi characters
    assert "Bcc:" in first["subject"] and "\n" not in first["subject"]  # injected header text stays inert data
    assert fake.calls("/messages")[0]["query"]["q"] == ["from:alice"]
    assert all(r["auth"] == f"Bearer {ACCESS}" for r in fake.requests)


def test_gmail_read_clamps_the_limit_and_rejects_bad_queries(fake):
    gmail_tools.read("anything", limit=9999)
    assert fake.calls("/messages")[0]["query"]["maxResults"] == [str(gmail_tools.MAX_READ)]
    for bad in ("", "   ", "x" * 301):
        with pytest.raises(google.ToolError, match="query"):
            gmail_tools.read(bad)


def test_send_draft_only_creates_a_draft_and_never_calls_send(fake):
    answer = gmail_tools.send_draft("bob@example.com", "Hello", "Line one\nLine two")
    assert "NOT sent" in answer
    (call,) = fake.calls("/drafts")
    message = FakeGoogle.decode_raw(json.loads(call["body"])["message"]["raw"])
    assert "To: bob@example.com" in message and "Subject: Hello" in message and "Line two" in message
    assert not [r for r in fake.requests if r["path"].endswith("/send") or "messages/send" in r["path"]]


@pytest.mark.parametrize(
    "to, subject, body, fragment",
    [
        ("a@b.com, evil@x.com", "s", "b", "single plain email"),
        ("a@b.com\nBcc: evil@x.com", "s", "b", "single plain email"),
        ("Bob <bob@example.com>", "s", "b", "single plain email"),
        ("not-an-address", "s", "b", "single plain email"),
        ("a@b.com", "Hi\r\nBcc: evil@x.com", "b", "line breaks"),
        ("a@b.com", "", "b", "subject"),
        ("a@b.com", "s", "x" * 20_001, "body"),
    ],
)
def test_send_draft_refuses_header_injection_and_bad_input_before_calling_google(fake, to, subject, body, fragment):
    with pytest.raises(google.ToolError, match=fragment):
        gmail_tools.send_draft(to, subject, body)
    assert fake.requests == []


# ---- calendar ---------------------------------------------------------------------------------------------------


def test_list_events_returns_summary_fields_only(fake):
    (event,) = calendar_tools.list_events("2026-11-06T00:00:00+05:30", "2026-11-07T00:00:00+05:30")
    assert event == {
        "id": "e1", "title": "Sync", "start": "2026-11-06T10:00:00+05:30", "end": "2026-11-06T10:30:00+05:30",
        "location": "", "attendees": 2,
    }  # fmt: skip
    assert "secret agenda" not in json.dumps(event)  # the description is not passed on
    query = fake.calls("/events")[0]["query"]
    assert query["singleEvents"] == ["true"] and query["timeMin"] == ["2026-11-06T00:00:00+05:30"]


@pytest.mark.parametrize(
    "start, end, fragment",
    [
        ("2026-11-06T09:00:00", "2026-11-06T10:00:00+00:00", "timezone"),
        ("yesterday", "2026-11-06T10:00:00+00:00", "ISO 8601"),
        ("2026-11-06T10:00:00+00:00", "2026-11-06T09:00:00+00:00", "after start"),
        ("2026-01-01T00:00:00+00:00", "2026-06-01T00:00:00+00:00", "92 days"),
    ],
)
def test_list_events_validates_times_before_calling_google(fake, start, end, fragment):
    with pytest.raises(google.ToolError, match=fragment):
        calendar_tools.list_events(start, end)
    assert fake.requests == []


def test_create_event_asks_google_not_to_email_invitations(fake):
    answer = calendar_tools.create_event(
        "Lunch", "2026-11-06T13:00:00+05:30", "2026-11-06T14:00:00+05:30", ["bob@example.com"]
    )
    assert "Event created (id e2)" in answer
    (call,) = [r for r in fake.calls("/events") if r["method"] == "POST"]
    assert call["query"]["sendUpdates"] == ["none"]
    body = json.loads(call["body"])
    assert body["attendees"] == [{"email": "bob@example.com"}] and body["summary"] == "Lunch"


def test_create_event_validates_guests_title_and_length(fake):
    ok = ("2026-11-06T13:00:00+00:00", "2026-11-06T14:00:00+00:00")
    with pytest.raises(google.ToolError, match="single plain email"):
        calendar_tools.create_event("t", *ok, ["a@b.com,c@d.com"])
    with pytest.raises(google.ToolError, match="at most 20"):
        calendar_tools.create_event("t", *ok, [f"u{i}@example.com" for i in range(21)])
    with pytest.raises(google.ToolError, match="title"):
        calendar_tools.create_event(" ", *ok, [])
    with pytest.raises(google.ToolError, match="at most 2 days"):
        calendar_tools.create_event("t", "2026-11-06T13:00:00+00:00", "2026-11-12T14:00:00+00:00", [])
    assert fake.requests == []


# ---- sheets -----------------------------------------------------------------------------------------------------

SHEET = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"


def test_sheets_read_caps_rows_and_columns(fake):
    rows = sheets_tools.read(SHEET, "Sheet1!A1:Z999")
    assert len(rows) == sheets_tools.MAX_ROWS and len(rows[0]) == sheets_tools.MAX_COLS
    assert fake.calls("/values/")[0]["path"].endswith("/values/Sheet1%21A1%3AZ999")


@pytest.mark.parametrize(
    "sheet, cell_range", [("short", "A1"), (SHEET + "/../x", "A1"), (SHEET, "A1?x=1"), (SHEET, "../x"), (SHEET, "")]
)
def test_sheets_read_refuses_odd_ids_and_ranges_before_calling_google(fake, sheet, cell_range):
    with pytest.raises(google.ToolError):
        sheets_tools.read(sheet, cell_range)
    assert fake.requests == []


# ---- web --------------------------------------------------------------------------------------------------------


def test_search_results_are_parsed_from_real_duckduckgo_markup():
    results = web_tools.parse_results((FIX / "ddg_results.html").read_text(), 5)
    assert [r["url"] for r in results[:2]] == ["https://www.python.org/", "https://www.python.org/downloads/"]
    assert results[0]["title"] == "Welcome to Python.org" and results[0]["snippet"].startswith("The mission")
    assert len(web_tools.parse_results((FIX / "ddg_results.html").read_text(), 2)) == 2


def test_wrapped_links_are_unwrapped_and_non_web_links_are_dropped():
    html = (
        '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fa%3Fx%3D1&rut=z">Wrapped</a>'
        '<a class="result__snippet" href="x">Snippet one</a>'
        '<a class="result__a" href="javascript:alert(1)">Bad</a><a class="result__snippet" href="x">no</a>'
        '<a class="result__a" href="file:///etc/passwd">File</a>'
    )
    assert web_tools.parse_results(html, 5) == [
        {"title": "Wrapped", "url": "https://example.org/a?x=1", "snippet": "Snippet one"}
    ]


def test_search_uses_the_fetched_page_and_validates_the_query(monkeypatch):
    monkeypatch.setattr(web_tools, "_fetch", lambda q: (FIX / "ddg_results.html").read_text())
    assert len(web_tools.search("python", limit=2)) == 2
    assert len(web_tools.search("python", limit=0)) == 1  # clamped up to one
    with pytest.raises(google.ToolError, match="query"):
        web_tools.search(" ")


def test_an_unreadable_page_is_an_error_but_a_real_empty_search_is_an_empty_list(monkeypatch):
    captcha = "<html><body><form>Please verify you are human to continue</form></body></html>"
    monkeypatch.setattr(web_tools, "_fetch", lambda q: captcha)
    with pytest.raises(google.ToolError, match="could not be read"):
        web_tools.search("python")
    tricky = "<html><body><p>No results until you prove you are human</p><form>captcha</form></body></html>"
    monkeypatch.setattr(web_tools, "_fetch", lambda q: tricky)
    with pytest.raises(google.ToolError, match="could not be read"):  # the words "No results" are not enough
        web_tools.search("python")
    for empty in (
        '<html><body><div class="no-results">No results.</div></body></html>',
        '<html><body><div id="links" class="results"></div></body></html>',
    ):
        monkeypatch.setattr(web_tools, "_fetch", lambda q, page=empty: page)
        assert web_tools.search("qqzzxx") == []
