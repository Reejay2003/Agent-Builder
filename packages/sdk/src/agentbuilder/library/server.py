"""Serve one namespace of the library over MCP stdio.

python -m agentbuilder.library.server gmail [--mock] [--log PATH]
"""

from __future__ import annotations

import sys

from agentbuilder.library.catalog import TOOLS_BY_NAMESPACE
from agentbuilder.tools.mcp_server import main


def run(argv: list[str]) -> None:
    if not argv or argv[0] not in TOOLS_BY_NAMESPACE:
        raise SystemExit(
            f"usage: python -m agentbuilder.library.server {{{'|'.join(TOOLS_BY_NAMESPACE)}}} [--mock] [--log PATH]"
        )
    main(TOOLS_BY_NAMESPACE[argv[0]], name=f"agentbuilder-{argv[0]}", argv=argv[1:])


if __name__ == "__main__":
    run(sys.argv[1:])
