"""AgentSpec -> CompiledAgent. Pure and deterministic: the same spec and catalog always give the same result."""

from __future__ import annotations

from collections.abc import Mapping

from agentbuilder.compile.compiled import CompiledAgent, CompiledModel, CompiledTool
from agentbuilder.models import resolve_model, secret_env_name
from agentbuilder.spec import AgentSpec
from agentbuilder.tools import ToolCatalog


class CompileError(ValueError):
    """The spec cannot be compiled safely (unknown tool, policy violation, ...)."""


def _instructions(persona: str, rules: list[str]) -> str:
    parts = []
    if persona.strip():
        parts.append(persona.strip())
    if rules:
        parts.append("Rules:\n" + "\n".join(f"- {r.strip()}" for r in rules))
    return "\n\n".join(parts)


def _not_applied(spec: AgentSpec) -> list[str]:
    """Spec fields that are accepted but change nothing yet (silence would look like protection)."""
    m = spec.model
    candidates = {
        "guardrails.profile": True,  # even the default 'standard' is not enforced yet; never imply protection
        "model.reliability": bool(
            m.reliability.tier
            or m.reliability.mode != "normal"
            or m.reliability.repair.escalate_to
            or (m.reliability.repair.max_attempts != 3 and "reprompt" not in m.reliability.repair.steps)
        ),
        "model.routing": m.routing is not None,
        "model.max_tokens": m.max_tokens is not None,
        "sandbox.policy_preset": spec.sandbox.policy_preset is not None,
        "evals.suite": spec.evals.suite is not None,
        "knowledge": spec.knowledge is not None,
        "integrations": bool(spec.integrations),
        "channels": bool(spec.channels),
        "voice": spec.voice is not None,
    }
    return [name for name, is_set in candidates.items() if is_set]


def compile_agent(
    spec: AgentSpec, catalog: ToolCatalog, *, environ: Mapping[str, str] | None = None, parse_retries: int = 3
) -> CompiledAgent:
    """Resolve `spec` against `catalog`. Reads no secrets: the runtime resolves the key from the named variable."""
    model = resolve_model(spec.model, environ=environ or {}, need_key=False)
    warnings: list[str] = []

    ref = spec.model.credential_ref
    key_env = model.api_key_env
    if ref and ref.startswith("secret://"):
        key_env = secret_env_name(ref.removeprefix("secret://"))
        warnings.append(
            f"credential {ref} is resolved at run time from a secret store (the web app's vault under `ab ui`), "
            f"else from the environment variable {key_env}"
        )

    try:
        resolved = catalog.resolve([t.id for t in spec.tools])
    except KeyError as exc:
        raise CompileError(str(exc.args[0])) from exc

    for t in resolved:
        tier = t.manifest.risk_tier
        if tier >= 3 and spec.approvals.tier3_destructive == "block":
            raise CompileError(
                f"tool {t.id} is tier 3 (destructive or financial) and approvals.tier3_destructive is 'block'; "
                "remove the tool or set tier3_destructive: require_human"
            )
        if tier >= 2 and spec.approvals.tier2_external_comms == "require_human":
            warnings.append(f"tool {t.id} is tier {tier}: every live call waits for a person to approve it")
        if tier >= 1:
            warnings.append(
                f"tool {t.id} can change things (tier {tier}); only the sandbox runner limits its network access"
            )

    steps = spec.model.reliability.repair.steps
    if model.agent_mode != "react" and {"tool_names", "reprompt"} & set(steps):
        warnings.append("repair steps tool_names and reprompt only apply in ReAct mode; this agent uses tool calling")
    if "retry" in steps:
        warnings.append("repair step retry changes nothing yet: NAT already retries failed model calls by itself")
    if "reprompt" in steps:
        parse_retries = max(1, spec.model.reliability.repair.max_attempts)

    if unapplied := _not_applied(spec):
        warnings.append("these spec fields are accepted but NOT applied yet: " + ", ".join(unapplied))

    servers = catalog.servers_for(resolved)
    return CompiledAgent(
        name=spec.name,
        description=spec.description,
        spec_version=spec.spec_version,
        model=CompiledModel(
            provider=model.provider,
            model=model.model,
            base_url=model.base_url,
            api_key_env=key_env,
            temperature=model.temperature,
            agent_mode=model.agent_mode,
        ),
        instructions=_instructions(spec.instructions.persona, spec.instructions.rules),
        tools=[
            CompiledTool(
                id=t.id,
                server=t.server,
                mcp_name=t.mcp_name,
                risk_tier=t.manifest.risk_tier,
                side_effects=t.manifest.side_effects,
                egress_hosts=list(t.manifest.egress_hosts),
                fs_paths=list(t.manifest.fs_paths),
            )
            for t in resolved
        ],
        servers=list(servers.values()),
        guardrails_profile=spec.guardrails.profile,
        tier2_policy=spec.approvals.tier2_external_comms,
        tier3_policy=spec.approvals.tier3_destructive,
        sandbox_preset=spec.sandbox.policy_preset,
        parse_retries=parse_retries,
        repair_steps=[x for x in steps if x == "tool_names"] if model.agent_mode == "react" else [],
        warnings=warnings,
    )


APPROVAL_TIMEOUT = 600.0  # seconds a tool waits for a person; then the call is declined and never runs


def needs_approval(c: CompiledAgent) -> list[str]:
    """Tool ids whose live calls a person must approve first, by the spec's approval rules."""
    return [
        t.id
        for t in c.tools
        if (t.risk_tier == 2 and c.tier2_policy == "require_human")
        or (t.risk_tier >= 3 and c.tier3_policy == "require_human")
    ]


def unapproved_live_tools(c: CompiledAgent) -> list[str]:
    """Tools that would act on a live system with nobody asked first. Every caller (server, CLI, runners) refuses
    such a run. A tool is covered when its server runs in mock mode (`--mock`, added by the gateway) or asks for
    approval (`--approvals`, added by a runner that was given an approver; see `agentbuilder.approvals`)."""
    covered = {s.name for s in c.servers if "--mock" in s.args or "--approvals" in s.args}
    by_id = {t.id: t for t in c.tools}
    return [i for i in needs_approval(c) if by_id[i].server not in covered]


def approval_needed(tool_ids: list[str]) -> str:
    return (
        f"live runs of {', '.join(tool_ids)} need a person to approve each call, and this run has no one to ask: "
        "run it with `ab run` in a terminal or through the local server (the web app asks), use mock mode, "
        "or set approvals.tier2_external_comms to allow"
    )
