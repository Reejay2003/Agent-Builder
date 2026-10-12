"""JSON Schema for the AgentSpec, for editors and non-Python tools. The committed copy is checked by a test.
Regenerate after an intentional change: `python -m agentbuilder.spec.schema --write`."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from agentbuilder.spec.models import _TOOL_ID, SPEC_VERSION, AgentSpec

SCHEMA_PATH = Path(__file__).with_name("agent-spec.schema.json")


def agent_spec_json_schema() -> dict[str, Any]:
    schema = AgentSpec.model_json_schema()
    # A tool may also be written as a bare id string (`tools: [demo.add_numbers]`).
    schema["properties"]["tools"]["items"] = {
        "anyOf": [{"$ref": "#/$defs/ToolRef"}, {"type": "string", "pattern": _TOOL_ID.pattern}]
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://github.com/Reejay2003/Agent-Builder/schemas/agent-spec.v{SPEC_VERSION}.json",
        **schema,
    }


def schema_text() -> str:
    return json.dumps(agent_spec_json_schema(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--write" in args:
        SCHEMA_PATH.write_text(schema_text(), encoding="utf-8")
        print(f"wrote {SCHEMA_PATH}")
    else:
        sys.stdout.write(schema_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
