# agentbuilder (SDK, pre-alpha)

Define an agent once (Python or a spec file), then validate, compile, test, evaluate and run it, locally or in a sandbox, with safe defaults and a full trajectory for every run. Design: [PLAN.md section 16](../../PLAN.md).

**Status: 0.1 in progress.** Done so far: `agentbuilder.spec` (AgentSpec models, JSON Schema, load/save, migrations) and `agentbuilder.testing` (`FakeModel`, `FakeOpenAIServer`). Not yet: tools, models, compilers, runtime, CLI.

```bash
pip install -e "packages/sdk[dev]"        # from the repo root (make setup does this)
python -c "from agentbuilder.spec import AgentSpec; print(AgentSpec.load('packages/sdk/examples/specs/calculator.agent.yaml').name)"
make sdk-check                             # ruff + mypy + pytest, all offline and free
```

## Rules
- **Credentials by reference only.** A spec holds `secret://name` or `env://NAME`, never a key; any key-like value anywhere in a spec is rejected.
- **Unknown fields are errors** (a typo like `toolz:` fails loudly).
- **No network calls at import.** Tests run offline with `FakeModel`.
- `0.x` makes no API stability promise; unsettled things belong in `agentbuilder.experimental`.
