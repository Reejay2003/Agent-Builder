"""Demo MCP server (stdio), built with the SDK: python packages/mcp-tools/demo_server.py [--log PATH] [--mock]

Every call is appended to the audit log (default /tmp/ab-demo-tool-calls.jsonl or $AB_TOOL_LOG) so tests can prove a tool ran."""

import os
import sys

from demo_tools import TOOLS

from agentbuilder.tools.mcp_server import main

if "--log" not in sys.argv:
    sys.argv += ["--log", os.environ.get("AB_TOOL_LOG", "/tmp/ab-demo-tool-calls.jsonl")]

if __name__ == "__main__":
    main(TOOLS, name="agent-builder-demo")
