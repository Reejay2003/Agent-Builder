"""The control service: immutable spec versions, runs tied to the version they ran, and the access rules."""

import os
import time

import pytest
from agentbuilder.runtime import RunResult
from fastapi.testclient import TestClient

from agentbuilder_control import create_app

TOKEN = "t" * 40
SPEC = {
    "name": "inbox-helper",
    "model": {"provider": "openai", "model": "gpt-4.1-mini"},
    "tools": [{"id": "gmail.read"}],
}


class Recorder:
    name = "recorder"

    def __init__(self):
        self.calls = []

    def run(self, compiled, prompt, *, environ=None, approve=None):
        self.calls.append((compiled, prompt))
        return RunResult(status="succeeded", text=f"done: {prompt}")


def client(url="sqlite://", runner=None):
    runner = runner or Recorder()
    app = create_app(url, TOKEN, runner_factory=lambda: runner)
    c = TestClient(app, base_url="http://127.0.0.1")
    c.headers["X-AgentBuilder-Token"] = TOKEN
    return c, runner


def wait(c, run_id):
    for _ in range(100):
        run = c.get(f"/runs/{run_id}").json()
        if run["status"] != "running":
            return run
        time.sleep(0.02)
    raise AssertionError("the run did not finish")


def flow(c, runner):
    made = c.post("/agents", json={"spec": SPEC})
    assert made.status_code == 201 and made.json()["version"] == 1
    assert "spec_version: 1" in made.json()["spec_yaml"]  # the SDK wrote it
    assert c.post("/agents", json={"spec": SPEC}).status_code == 409  # a second agent with the same name

    v2 = c.post("/agents/inbox-helper/versions", json={"spec": {**SPEC, "description": "second"}})
    assert v2.status_code == 201 and v2.json()["version"] == 2
    assert c.get("/agents/inbox-helper/versions/1").json()["spec"]["description"] == ""  # versions never change
    assert c.get("/agents/inbox-helper").json()["version"] == 2
    assert c.get("/agents").json() == {"agents": [{"name": "inbox-helper", "latest_version": 2}]}

    started = c.post("/agents/inbox-helper/runs", json={"prompt": "any mail?", "version": 1})
    assert started.status_code == 202 and started.json()["version"] == 1
    run = wait(c, started.json()["run_id"])
    assert run["status"] == "succeeded" and run["text"] == "done: any mail?" and run["version"] == 1
    compiled, _ = runner.calls[0]
    assert all("--mock" in s.args for s in compiled.servers)  # mock unless the caller says otherwise


def test_specs_are_versioned_and_runs_name_the_version_they_ran():
    flow(*client())


def test_the_sdk_judges_every_spec_before_it_is_stored():
    c, _ = client()
    bad = c.post("/agents", json={"spec": {**SPEC, "name": "Has Spaces"}})
    assert bad.status_code == 422 and bad.json()["errors"][0]["field"] == "name"
    unknown = c.post("/agents", json={"spec": {**SPEC, "tools": [{"id": "no.such_tool"}]}})
    assert unknown.status_code == 422 and unknown.json()["errors"][0]["field"] == "tools"
    c.post("/agents", json={"spec": SPEC})
    renamed = c.post("/agents/inbox-helper/versions", json={"spec": {**SPEC, "name": "other"}})
    assert renamed.status_code == 422 and renamed.json()["errors"][0]["field"] == "spec.name"
    assert c.get("/agents/nobody").status_code == 404 and c.get("/runs/nope").status_code == 404
    assert c.post("/agents/inbox-helper/runs", json={"prompt": "x", "version": 9}).status_code == 404


def test_a_live_tier2_run_is_refused_here_because_no_one_could_approve_it():
    c, runner = client()
    c.post("/agents", json={"spec": {**SPEC, "tools": [{"id": "calendar.create_event"}]}})
    refused = c.post("/agents/inbox-helper/runs", json={"prompt": "book it", "mock": False})
    assert refused.status_code == 422 and "approval" in refused.json()["errors"][0]["message"]
    assert runner.calls == []


def test_a_crashing_runner_leaves_a_failed_run_not_a_stuck_one():
    class Broken:
        name = "broken"

        def run(self, *a, **kw):
            raise RuntimeError("the key was sk-secret")

    c, _ = client(runner=Broken())
    c.post("/agents", json={"spec": SPEC})
    run = wait(c, c.post("/agents/inbox-helper/runs", json={"prompt": "x"}).json()["run_id"])
    assert run["status"] == "failed" and run["error"] == "unexpected RuntimeError"  # never the exception text


def test_only_loopback_callers_with_the_token_and_no_browser_get_in():
    c, _ = client()
    assert c.get("/agents", headers={"X-AgentBuilder-Token": "wrong"}).status_code == 401
    assert c.get("/agents", headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.get("/agents", headers={"Host": "evil.example"}).status_code == 403
    assert c.get("/agents").status_code == 200


@pytest.mark.postgres
def test_the_same_flow_on_a_real_postgres():
    url = os.environ.get("AGENTBUILDER_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("set AGENTBUILDER_TEST_POSTGRES_URL to a throwaway Postgres database")
    from sqlalchemy import create_engine, text

    with create_engine(url).begin() as conn:  # a clean slate: this database is for tests only
        conn.execute(text("DROP TABLE IF EXISTS runs, agent_versions, agents CASCADE"))
    flow(*client(url))
