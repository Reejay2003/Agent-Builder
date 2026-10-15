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
        "model.reliability": bool(m.reliability.model_dump(exclude_defaults=True)),
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
        warnings.append(f"credential {ref} is resolved from the environment variable {key_env} at run time")

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
            warnings.append(
                f"tool {t.id} is tier {tier} and needs human approval, but approval enforcement arrives in SDK 0.3: "
                "it is NOT enforced yet"
            )
        if tier >= 1:
            warnings.append(
                f"tool {t.id} can change things (tier {tier}); sandbox policy arrives in SDK 0.3, "
                "nothing restricts it yet"
            )

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
        warnings=warnings,
    )
