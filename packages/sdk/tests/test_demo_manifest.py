"""The committed demo manifest is generated from the SDK tool definitions; this keeps the two in sync."""

import json

import pytest

from tests.conftest import EXAMPLES
from tests.fixtures_tools import DEMO_DIR, demo_tools_on_path

COMMITTED = DEMO_DIR.parent / "tool-manifests" / "demo_tools.manifest.json"
pytestmark = pytest.mark.skipif(not COMMITTED.exists(), reason="needs the repository checkout")


def test_committed_manifest_matches_the_sdk_tool_definitions():
    demo_tools_on_path()
    from demo_tools import TOOLS

    from agentbuilder.tools import manifests_document

    generated = manifests_document(
        "agent-builder-demo", "packages/mcp-tools/demo_server.py", [t.manifest for t in TOOLS]
    )
    assert json.loads(COMMITTED.read_text(encoding="utf-8")) == generated, (
        "demo_tools.manifest.json is out of date; regenerate it from packages/mcp-tools/demo_tools.py"
    )


def test_example_spec_tools_exist_in_the_demo_manifest():
    ids = {t["id"] for t in json.loads(COMMITTED.read_text(encoding="utf-8"))["tools"]}
    from agentbuilder.spec import AgentSpec

    assert {t.id for t in AgentSpec.load(EXAMPLES / "calculator.agent.yaml").tools} <= ids
