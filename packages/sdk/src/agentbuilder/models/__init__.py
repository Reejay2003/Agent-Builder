"""Models: BYOK constructors, safe credential handling and the evidence-based capability table."""

from agentbuilder.models.capabilities import Capability, ModeResult, lookup, resolve_agent_mode, tier_for_rate
from agentbuilder.models.credentials import CredentialError, Secret, redact, resolve_credential, secret_env_name
from agentbuilder.models.probe import ProbeResult, probe_tool_calling
from agentbuilder.models.providers import DEFAULT_BASE_URL, Model, ResolvedModel, resolve_model

__all__ = [
    "DEFAULT_BASE_URL",
    "Capability",
    "CredentialError",
    "ModeResult",
    "Model",
    "ProbeResult",
    "ResolvedModel",
    "Secret",
    "lookup",
    "probe_tool_calling",
    "redact",
    "resolve_agent_mode",
    "resolve_credential",
    "resolve_model",
    "secret_env_name",
    "tier_for_rate",
]
