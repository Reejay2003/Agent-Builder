# Work log: 2026-11-07 (reejay)

Written automatically by `.claude/hooks/log_work.py` after each Claude turn. Do not edit by hand.

## 00:13
<!-- turn:34efc131-0284-4db1-b6ee-ea3cd8f5cc45 -->
**Asked:** This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion of the conversation. Summary: 1. Primary Request and Intent: The owner (Reejay2003) is building "Agent Builder" as the Python SDK `agentbuilder` with a localhost web app (apps/web, owned by colleague Abhinav). Requests this session, in order: - Fix the Ponytail findings on the trajectory reader and compiler C, and test the policy on a real OpenShell microVM. - Answer…
**Files changed:** `packages/sdk/src/agentbuilder/cli.py`, `packages/sdk/src/agentbuilder/library/web_tools.py`, `packages/sdk/src/agentbuilder/server/app.py`, `packages/sdk/src/agentbuilder/tools/mcp_server.py`, `packages/sdk/src/agentbuilder/ui.py`, `packages/sdk/tests/test_cli_and_ui.py`, `packages/sdk/tests/test_gateway_and_library_servers.py`, `packages/sdk/tests/test_library_tools.py`, `packages/sdk/tests/test_tools_mcp.py`
**Claude replied:** Fixes 1 to 4 are done and the full check passes: ruff and mypy are clean and 245 SDK tests pass. Nothing is committed or pushed yet. 1. **Live runs of tier-2 tools are blocked.** A live run (`mock` false) that includes a tier-2 or higher tool under `require_human` now gets a field error on `mock` in the server (`server/app.py`). The message names the tool and says approvals arrive in SDK 0.3. Mock runs still work. Setting `approvals.tier2_external_comms` to `allow` lets a live run through. The new test fails when I disable the check and passes when I restore it. 2. **The audit log is on by default.** `ab ui` and `ab run --mock` now write every tool call to `~/.local/state/agentbuilder/tool-c…

## 00:27
<!-- turn:c1a9846c-b81f-4cf7-8fdd-dadd57afbcfc -->
**Asked:** model probe (P1.5): one real call that checks the model can use tools, then sets agent_mode: auto. The wizard's "model check" step depends on it. 4 Repair steps 1 to 3 in the wizard flow (tool-name suffix mapping and the others). lets do these now
**Files changed:** `COMPLETED.md`, `PLAN.md`, `packages/sdk-nat/src/agentbuilder_nat/local.py`, `packages/sdk-nat/tests/test_local_runner.py`, `packages/sdk/src/agentbuilder/cli.py`, `packages/sdk/src/agentbuilder/compile/compiled.py`, `packages/sdk/src/agentbuilder/compile/compiler.py`, `packages/sdk/src/agentbuilder/models/__init__.py`, `packages/sdk/src/agentbuilder/models/probe.py`, `packages/sdk/src/agentbuilder/repair.py`, `packages/sdk/src/agentbuilder/server/app.py`, `packages/sdk/tests/test_compile.py`, `packages/sdk/tests/test_model_probe.py`
**Claude replied:** **What this change does:** It adds a one-call model check (`probe_tool_calling`, `POST /model/check`, `ab probe-model`) that tells the wizard to write `agent_mode: auto` or `react`. It also makes the spec's repair steps take effect, and shows every repair in the run warnings. Load assumed: one person on one machine. Everything is tested offline with stub servers (268 SDK tests, 15 NAT tests, ruff and mypy clean). Nothing has run against a real provider, and nothing is committed or pushed. ## What it does - **Model check:** One chat request offers a single tool (`add_numbers`) and requires the model to call it. - A valid call gives `agent_mode: auto`. A model that doesn't call it, or a provid…

## 00:42
<!-- turn:24f91d55-49c9-443d-9968-ace94fe9dc38 -->
**Asked:** Run in an OpenShell sandbox in test mode. Compiler C and key passing are proven, but no SandboxRunner runs the agent inside the sandbox yet. do this 1st
**Files changed:** `COMPLETED.md`, `Makefile`, `packages/sdk-nat/pyproject.toml`, `packages/sdk-nat/sandbox/Dockerfile`, `packages/sdk-nat/src/agentbuilder_nat/sandbox.py`, `packages/sdk-nat/src/agentbuilder_nat/sandbox_main.py`, `packages/sdk-nat/tests/__init__.py`, `packages/sdk-nat/tests/test_sandbox_runner.py`, `packages/sdk/src/agentbuilder/compile/sandbox_policy.py`, `packages/sdk/tests/test_sandbox_policy.py`
**Claude replied:** The agent now runs inside a real OpenShell microVM. I ran it with a fake model and a mock Gmail tool, and it succeeded. Nothing is committed or pushed. ## What I built - **`SandboxRunner`** (`agentbuilder_nat/sandbox.py`) is a new runner called `sandbox`. Use it with `ab run --runner sandbox`. 1. It compiles the spec, writes the sandbox policy and the model's provider profile, and creates a one-run OpenShell provider that holds the key. The key goes through the environment of that one command, never the command line. 2. It starts the sandbox with `--no-keep`, reads one result line back, and always deletes the provider. 3. If the command fails or times out, it also deletes the sandbox. - **`s…

## 00:45
<!-- turn:ada5613f-ca5c-48ea-a053-10a9d64a19fc -->
**Asked:** So what I want you to do is, I want you to make a kind of functionalities added .md type of file, and in that add things that we have added to this platform. Things like the model probe is a thing, is a functionality that while explaining in my interview I should be able to handle, right? And the automatic repair step is also something like we should be adding in the functionality list So make a skill in Claude skills that adds such functionalities into that MD file as soon as we complete workin…
**Files changed:** `.claude/skills/log-functionality/SKILL.md`, `CLAUDE.md`, `FUNCTIONALITIES.md`
**Claude replied:** Writing the file itself, based on what I built and read this session.

## 00:49
<!-- turn:b7a52099-c81d-4a88-aa50-fe5a877d31ab -->
**Asked:** Actually, update this skill and make it such that only the functionalities that are not explicitly mentioned in the plan file, basically in the phases documentation, are added to the functionalities.md, so that the functionalities.md does not become too much cluttered with a lot of information.
**Files changed:** `.claude/skills/log-functionality/SKILL.md`, `FUNCTIONALITIES.md`

## 00:52
<!-- turn:bbb64912-1c03-4d06-939e-af33a338e750 -->
**Asked:** Okay, now make a list of open problems and also a list of problems using ponytail that might be in this area. And then tell me what to solve and what to fix. Basically make a full list.
**Also:** ran skill ponytail-audit
**Claude replied:** I'm checking the main suspects in the code before I write the audit, so each finding has a real case behind it.

## 00:55
<!-- turn:94572942-6b2c-4c48-a5c6-7529f8d5fa55 -->
**Asked:** let's fix the must fix problems first.
**Files changed:** `COMPLETED.md`, `packages/sdk/src/agentbuilder/models/probe.py`, `packages/sdk/src/agentbuilder/server/app.py`, `packages/sdk/tests/test_model_probe.py`, `packages/sdk/tests/test_server.py`
**Claude replied:** Running mutation checks: I'll undo each fix and confirm its test fails.

## 02:18
<!-- turn:0ec3efa1-00f3-402f-9e46-0b47c5d44591 -->
**Asked:** A running run can be forgotten (server/app.py, start_run) What this is: The server keeps the last 50 runs in memory. Problem: It drops the oldest one even if it is still running. Two runs execute at a time and the rest wait, so 50 quick clicks can push a waiting run out. Its result then comes back as "unknown run". Fix: Drop only finished runs, and refuse new runs while 50 are unfinished. If we skip it: A test run can silently vanish from the UI. The "ask a human first" rule is checked in one pl…
**Files changed:** `.github/workflows/sdk-ci.yml`, `COMPLETED.md`, `FUNCTIONALITIES.md`, `PLAN.md`, `packages/sdk-nat/src/agentbuilder_nat/local.py`, `packages/sdk-nat/src/agentbuilder_nat/sandbox.py`, `packages/sdk-nat/src/agentbuilder_nat/sandbox_main.py`, `packages/sdk-nat/tests/test_sandbox_runner.py`, `packages/sdk/src/agentbuilder/cli.py`, `packages/sdk/src/agentbuilder/compile/__init__.py`, `packages/sdk/src/agentbuilder/compile/compiler.py`, `packages/sdk/src/agentbuilder/server/app.py`, `packages/sdk/src/agentbuilder/spec/models.py`, `packages/sdk/src/agentbuilder/tools/mcp_server.py`, `packages/sdk/tests/test_cli_and_ui.py`, `packages/sdk/tests/test_compile.py`, `packages/sdk/tests/test_gateway_and_library_servers.py`, `packages/sdk/tests/test_model_probe.py`, `packages/sdk/tests/test_models.py`, `packages/sdk/tests/test_sandbox_policy.py`, `packages/sdk/tests/test_tools_mcp.py`
**Also:** ran skill log-functionality
**Claude replied:** Updating F5, F10 and F15, and adding two new entries (F17, F18) for the guards the plan doesn't describe:

## 10:44
<!-- turn:a7217ad0-55ab-49e5-8f35-d1385d2a9d49 -->
**Asked:** This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion of the conversation. Summary: 1. Primary Request and Intent: - The owner (Reejay2003) is building the "Agent Builder" `agentbuilder` Python SDK (`packages/sdk`) plus the runner package (`packages/sdk-nat`). The web app (`apps/web`) belongs to their colleague Abhinav. - Requests in this segment, in order: 1. Fix Ponytail item-2 findings 1–4 (done). 2. Build the model …

## 10:48
<!-- turn:17b02cb5-fe0c-4224-ae3e-cf9bad40e7fd -->
**Asked:** CI never ran the runners A new runners CI job installs the pinned NVIDIA stack and runs the runner tests offline. CI now also triggers on changes to sdk-nat, mcp-tools and the lock file. Reproduced in a clean environment: 8 + 23 tests pass what is a ci and what we did why we needed it?

## 10:57
<!-- turn:aaf225a1-b8df-4d49-8561-2469487fda29 -->
**Asked:** The sandbox image copies __pycache__ and has no .dockerignore, and nothing builds the image in CI. Add a .dockerignore. The audit log only grows. There is no size limit or rotation. Cut it at a size like 10 MB. web.search treats any page containing "No results" as an empty search. A captcha page with that text would pass. Check for the real result-list marker instead. Leftover small items: ab probe-model accepts a --tools flag it ignores. ab doctor does not check the mcp package. _write_private …
**Files changed:** `COMPLETED.md`, `FUNCTIONALITIES.md`, `packages/sdk-nat/sandbox/Dockerfile.dockerignore`, `packages/sdk-nat/tests/test_sandbox_runner.py`, `packages/sdk/src/agentbuilder/cli.py`, `packages/sdk/src/agentbuilder/library/google.py`, `packages/sdk/src/agentbuilder/library/web_tools.py`, `packages/sdk/src/agentbuilder/tools/mcp_server.py`, `packages/sdk/tests/test_cli_and_ui.py`, `packages/sdk/tests/test_library_tools.py`, `packages/sdk/tests/test_tools_mcp.py`
**Claude replied:** Before reporting, I'm tightening one edge in my own rotation code: it checked `exists()` and then `stat()` as two separate steps, which leaves a tiny window between them.

## 12:17
<!-- turn:9ee4104b-7f78-4e44-8867-518cb03695fb -->
**Asked:** The macOS CI test. Compiler D. The sandbox gaps (asking for approvals, collecting the audit log). Evals and ab eval. The control service. these 1st
**Files changed:** `.github/workflows/sdk-ci.yml`, `COMPLETED.md`, `FUNCTIONALITIES.md`, `Makefile`, `packages/sdk/src/agentbuilder/cli.py`, `packages/sdk/src/agentbuilder/compile/__init__.py`, `packages/sdk/src/agentbuilder/compile/compiled.py`, `packages/sdk/src/agentbuilder/compile/compiler.py`, `packages/sdk/src/agentbuilder/compile/guardrails_config.py`, `packages/sdk/src/agentbuilder/compile/policy_bundle.py`, `packages/sdk/src/agentbuilder/evals/__init__.py`, `packages/sdk/src/agentbuilder/evals/scoring.py`, `packages/sdk/src/agentbuilder/evals/suite.py`, `packages/sdk/src/agentbuilder/evals/suites/calculator_v1.yaml`, `packages/sdk/src/agentbuilder/evals/suites/personal_automation_v1.yaml`, `packages/sdk/tests/integration/test_eval_on_nat.py`, `packages/sdk/tests/test_cli_and_ui.py`, `packages/sdk/tests/test_compile.py`, `packages/sdk/tests/test_compiler_d.py`, `packages/sdk/tests/test_evals.py`, `services/control/pyproject.toml`, `services/control/src/agentbuilder_control/__init__.py`, `services/control/src/agentbuilder_control/__main__.py`, `services/control/src/agentbuilder_control/app.py`, `services/control/src/agentbuilder_control/db.py` (+1 more)
**Also:** committed, pushed
**Claude replied:** Now the full check across all four packages:

