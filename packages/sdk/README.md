# agentbuilder (SDK, pre-alpha)

Define an agent once (Python or a spec file), then validate, compile, test, evaluate and run it, locally or in a sandbox, with safe defaults and a full trajectory for every run. Design: [PLAN.md section 16](../../PLAN.md).

**Status: 0.1 in progress.** Done so far: `agentbuilder.spec` (AgentSpec, JSON Schema, load/save, migrations), `agentbuilder.testing` (`FakeModel`, `FakeOpenAIServer`), `agentbuilder.tools` (`@tool`, manifests with risk tiers, MCP server wrapper, catalog), `agentbuilder.models` (BYOK constructors, safe credentials, evidence-based capability table) and `agentbuilder.compile` (compilers A and B). Not yet: runtime, trajectory reader, CLI, sandbox policy.

```bash
pip install -e "packages/sdk[dev]"        # from the repo root (make setup does this)
python -c "from agentbuilder.spec import AgentSpec; print(AgentSpec.load('packages/sdk/examples/specs/calculator.agent.yaml').name)"
make sdk-check                             # ruff + mypy + pytest, all offline and free
```

## What you can do today
```python
from agentbuilder.spec import AgentSpec
from agentbuilder.models import Model
from agentbuilder.tools import tool, ToolCatalog
from agentbuilder.compile import compile_agent, to_nat_yaml, to_fabric_config


@tool(namespace="demo", risk=0)  # manifest + input schema come from the type hints
def add_numbers(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


spec = AgentSpec(name="calc", model=Model.openai("gpt-4.1-mini"), tools=["demo.add_numbers"])
catalog = ToolCatalog().add_tools("demo", [add_numbers], command="python", args=["my_server.py"])
compiled = compile_agent(spec, catalog)  # no key needed; refuses unsafe specs (tier 3 tools by default)
print(to_nat_yaml(compiled))  # the workflow `nat run` executes
mapping = to_fabric_config(compiled)  # validates as a nemo_fabric.FabricConfig
```
Serve tools over MCP with `agentbuilder.tools.mcp_server.main([add_numbers])` (needs `pip install "agentbuilder[mcp]"`; `--log PATH` writes an audit log, `--mock` returns each tool's mock response and never runs the function).

## Rules
- **Credentials by reference only.** A spec holds `secret://name` or `env://NAME`, never a key; any key-like value anywhere in a spec is rejected.
- **Unknown fields are errors** (a typo like `toolz:` fails loudly).
- **No network calls at import.** Tests run offline with `FakeModel`.
- `0.x` makes no API stability promise; unsettled things belong in `agentbuilder.experimental`.
