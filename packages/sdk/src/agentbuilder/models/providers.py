"""Model constructors and resolution: from a provider and a model id to a ready-to-use endpoint description."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from agentbuilder.models.capabilities import resolve_agent_mode
from agentbuilder.models.credentials import Secret, SecretStore, resolve_credential
from agentbuilder.spec.models import ModelSpec

DEFAULT_BASE_URL: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://localhost:11434/v1",
    "nvidia_hosted": "https://integrate.api.nvidia.com/v1",
}
DEFAULT_KEY_ENV: dict[str, str | None] = {
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "nvidia_hosted": "NVIDIA_API_KEY",
    "openai_compatible": "LLM_API_KEY",
    "ollama": None,  # local, no key
}


def _spec(provider: str, model: str, api_key_env: str | None, **kw: Any) -> ModelSpec:
    env = api_key_env if api_key_env is not None else DEFAULT_KEY_ENV[provider]
    return ModelSpec.model_validate(
        {"provider": provider, "model": model, "credential_ref": f"env://{env}" if env else None, **kw}
    )


class Model:
    """Constructors for the common providers. Each returns a `ModelSpec`; keys are referenced, never stored."""

    @staticmethod
    def openai(model: str, *, api_key_env: str | None = None, **kw: Any) -> ModelSpec:
        return _spec("openai", model, api_key_env, **kw)

    @staticmethod
    def openrouter(model: str, *, api_key_env: str | None = None, **kw: Any) -> ModelSpec:
        return _spec("openrouter", model, api_key_env, **kw)

    @staticmethod
    def nvidia_hosted(model: str, *, api_key_env: str | None = None, **kw: Any) -> ModelSpec:
        return _spec("nvidia_hosted", model, api_key_env, **kw)

    @staticmethod
    def ollama(model: str, *, base_url: str | None = None, **kw: Any) -> ModelSpec:
        return _spec("ollama", model, None, **({"base_url": base_url} if base_url else {}), **kw)

    @staticmethod
    def custom(model: str, *, base_url: str, api_key_env: str | None = None, **kw: Any) -> ModelSpec:
        """Any OpenAI-compatible endpoint (a gateway, vLLM, LiteLLM, ...)."""
        return _spec("openai_compatible", model, api_key_env, base_url=base_url, **kw)


@dataclass(frozen=True)
class ResolvedModel:
    provider: str
    model: str
    base_url: str
    api_key: Secret | None
    api_key_env: str | None  # the variable name, for runtimes that read the key themselves (never the value)
    temperature: float | None
    max_tokens: int | None
    agent_mode: Literal["tool_calling", "react"]


def resolve_model(
    spec: ModelSpec,
    *,
    environ: Mapping[str, str] | None = None,
    stores: Sequence[SecretStore] = (),
    need_key: bool = True,
) -> ResolvedModel:
    """Fill in defaults, pick the agent mode and (when `need_key`) resolve the credential. Raises CredentialError if a
    configured key is missing or malformed; with `need_key=False` the key is not read (compile and validate steps)."""
    env = os.environ if environ is None else environ
    base_url = spec.base_url or DEFAULT_BASE_URL.get(spec.provider)
    if base_url is None:  # unreachable: openai_compatible requires base_url in the spec
        raise ValueError(f"no base_url for provider {spec.provider}")
    ref = spec.credential_ref
    key = resolve_credential(ref, environ=env, stores=stores) if (need_key and ref) else None
    key_env = ref.removeprefix("env://") if ref and ref.startswith("env://") else None
    return ResolvedModel(
        provider=spec.provider,
        model=spec.model,
        base_url=base_url.rstrip("/"),
        api_key=key,
        api_key_env=key_env,
        temperature=spec.temperature,
        max_tokens=spec.max_tokens,
        agent_mode=resolve_agent_mode(spec),
    )
