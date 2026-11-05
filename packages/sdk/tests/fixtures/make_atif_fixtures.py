"""Regenerate the ATIF fixtures. Needs the NAT/Fabric/Relay stack; offline and free.

    python tests/fixtures/make_atif_fixtures.py

Runs compiled demo agents through Fabric against the fake model with Relay on, then keeps a trimmed copy of each
trajectory. The NAT-native sample is copied from a real `nat eval` run if one exists locally (spikes/s4-relay-eval/out).
"""

import asyncio
import glob
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SDK = HERE.parents[1]
ROOT = SDK.parents[1]
sys.path[:0] = [
    str(SDK),
    str(ROOT / "packages" / "mcp-tools"),
    str(ROOT / "services" / "runner" / "nat_adapter" / "src"),
]
os.environ.update(
    LLM_API_KEY="fake-key", ADAPTER_PYTHON=sys.executable, PYTHONPATH=str(ROOT / "services/runner/nat_adapter/src")
)

import nemo_fabric  # noqa: E402
from demo_tools import TOOLS  # noqa: E402

from agentbuilder.compile import compile_agent, to_fabric_config  # noqa: E402
from agentbuilder.spec import AgentSpec  # noqa: E402
from agentbuilder.testing import FakeModel, FakeOpenAIServer, ToolCall, Turn  # noqa: E402
from agentbuilder.tools import ToolCatalog  # noqa: E402

SCRIPTS = {
    "tool_calling": [
        Turn.calls(ToolCall("add_numbers", {"a": 17.5, "b": 25}), ToolCall("count_words", {"text": "one two three"})),
        Turn.say("17.5 plus 25 is 42.5 and the text has 3 words."),
    ],
    "react": [
        Turn.react("demo__add_numbers", {"a": 17.5, "b": 25}),
        Turn.react_final("17.5 plus 25 is 42.5."),
    ],
}


def trimmed(path: str) -> dict:
    with open(path) as f:
        data = json.load(f)

    def strip(t: dict) -> None:
        (t.get("extra") or {}).pop("observed_events", None)  # raw event log: large, not read by the reader
        for sub in t.get("subagent_trajectories") or []:
            strip(sub)

    strip(data)
    return data


for mode, script in SCRIPTS.items():
    out = Path(tempfile.mkdtemp())
    spec = AgentSpec.load(SDK / "examples" / "specs" / "calculator.agent.yaml")
    model = FakeModel(script)
    with FakeOpenAIServer(model) as server:
        spec = spec.model_copy(
            update={"model": spec.model.model_copy(update={"agent_mode": mode, "base_url": server.base_url})}
        )
        catalog = ToolCatalog().add_tools(
            "demo", TOOLS, command=sys.executable, args=[str(ROOT / "packages/mcp-tools/demo_server.py")]
        )
        cfg = to_fabric_config(
            compile_agent(spec, catalog),
            adapter_dir=str(ROOT / "services/runner/nat_adapter"),
            relay_output_dir=str(out),
        )
        result = asyncio.run(
            nemo_fabric.Fabric().run(
                nemo_fabric.FabricConfig.model_validate(cfg), base_dir=str(out), input="demo question"
            )
        )
    assert result.to_mapping()["status"] == "succeeded", result.to_mapping().get("error")
    (atif,) = glob.glob(str(out / "**" / "nemo-relay-atif-*.json"), recursive=True)
    target = HERE / "atif" / f"relay_{mode}.json"
    target.write_text(json.dumps(trimmed(atif), indent=1, sort_keys=True) + "\n")
    print("wrote", target.relative_to(ROOT), f"({target.stat().st_size} bytes)")

# NAT-native eval output (one item), copied from a real `nat eval` run if one exists locally
for src in sorted(glob.glob(str(ROOT / "spikes/s4-relay-eval/out/tool_calling/workflow_output_atif.json"))):
    with open(src) as f:
        items = json.load(f)
    item = next(
        i
        for i in items
        if any(
            c.get("function_name", "").startswith("demo_tools__")
            for s in i["trajectory"]["steps"]
            for c in (s.get("tool_calls") or [])
        )
    )
    (HERE / "atif" / "nat_native_eval.json").write_text(json.dumps([item], indent=1, sort_keys=True) + "\n")
    print("wrote nat_native_eval.json from", Path(src).relative_to(ROOT))
