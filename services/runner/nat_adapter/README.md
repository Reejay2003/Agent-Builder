# NAT adapter for NeMo Fabric (ours)

Fabric ships no NAT adapter; NVIDIA publishes a source-only reference (`NVIDIA/NeMo-Fabric` `external/nat`, Apache-2.0, see `LICENSE-NVIDIA-Fabric`). This is our maintained copy, with additions marked "local patch" in the code:

| Addition | File | Switch |
|---|---|---|
| Tool-calling agent (`fabric.agent.tool_calling` -> NAT `tool_calling_agent`) beside the original ReAct | `src/.../nat/adapter.py`, `targets/simple-agent-toolcalling.fabric-target.json` | choose the target |
| Relay activation per run (ATOF + ATIF, artifacts in the result) | `adapter.py` | needs 4 settings, see COMPLETED.md Gotchas |
| Typed Relay LLM/tool events (model, tokens, tool args and results) | `src/.../nat/relay_events.py` | on whenever Relay is enabled; graph-node scopes opt-in `FABRIC_NAT_RELAY_GRAPH=1` |
| Deterministic tool-name repair (PLAN 4.4.2 step 1), every repair reported in `output.repairs` | `src/.../nat/repair.py` | `FABRIC_NAT_REPAIR=tool_names` (off by default; benefit unproven) |
| Debug tracebacks to a file | `adapter.py` | `FABRIC_NAT_DEBUG=1` |

Run the offline tests with `make test`. The adapter host runs as a subprocess and needs `PYTHONPATH=services/runner/nat_adapter/src` and the venv first on PATH (the Makefile and test harnesses set both).
Pinned in `requirements.txt`: NAT 1.9.0, Fabric 0.4.0, nemo-relay 0.9.4. Verified from a clean install: `make setup && make test`.
