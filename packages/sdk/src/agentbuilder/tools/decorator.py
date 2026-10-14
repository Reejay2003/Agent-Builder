"""`@tool`: turn a typed Python function into a tool with a manifest, an input schema and an MCP-servable callable.

@tool(namespace="demo", risk=0)
def add_numbers(a: float, b: float) -> float:
    \"\"\"Add two numbers.\"\"\"
    return a + b

add_numbers.manifest.risk_tier      # 0
add_numbers.input_schema            # JSON Schema generated from the type hints
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypeVar, overload

from pydantic import BaseModel, ConfigDict, ValidationError, create_model

from agentbuilder.tools.manifest import MIN_TIER, RateLimits, SideEffect, ToolManifest

F = TypeVar("F", bound=Callable[..., Any])
_DEFAULT_EFFECT: dict[int, SideEffect] = {0: "none", 1: "write", 2: "external_comms", 3: "destructive"}


class ToolDefinitionError(TypeError):
    """The decorated function cannot be turned into a safe, well-described tool."""


class ToolArgumentError(ValueError):
    """Arguments given to a tool do not match its input schema."""


def _input_model(fn: Callable[..., Any], name: str) -> type[BaseModel]:
    fields: dict[str, Any] = {}
    for p in inspect.signature(fn).parameters.values():
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            raise ToolDefinitionError(f"tool '{name}': *args/**kwargs are not allowed; declare every parameter")
        if p.annotation is inspect.Parameter.empty:
            raise ToolDefinitionError(f"tool '{name}': parameter '{p.name}' needs a type annotation")
        fields[p.name] = (p.annotation, ... if p.default is inspect.Parameter.empty else p.default)
    return create_model(f"{name}_args", __config__=ConfigDict(extra="forbid"), **fields)


class Tool:
    """A decorated function plus everything derived from it. Calling it runs the function unchanged."""

    def __init__(self, fn: Callable[..., Any], manifest: ToolManifest, args_model: type[BaseModel]) -> None:
        self.fn = fn
        self.manifest = manifest
        self._args_model = args_model
        self.__doc__ = fn.__doc__
        self.__name__ = fn.__name__

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def mcp_name(self) -> str:
        return self.manifest.mcp_name

    @property
    def input_schema(self) -> dict[str, Any]:
        return self.manifest.input_schema

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.fn(*args, **kwargs)

    def call(self, arguments: Mapping[str, Any]) -> Any:
        """Validate `arguments` against the input schema, then run. Raises ToolArgumentError on a mismatch."""
        try:
            validated = self._args_model(**dict(arguments))
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or '<args>'}: {e['msg']}" for e in exc.errors())
            raise ToolArgumentError(f"{self.id}: {problems}") from exc
        return self.fn(**{k: getattr(validated, k) for k in type(validated).model_fields})

    def __repr__(self) -> str:
        return f"Tool({self.id!r}, risk={self.manifest.risk_tier})"


@overload
def tool(fn: F, /) -> Tool: ...
@overload
def tool(
    *,
    id: str | None = ...,
    namespace: str = ...,
    name: str | None = ...,
    description: str | None = ...,
    risk: int = ...,
    side_effects: SideEffect | None = ...,
    scopes: Sequence[str] = ...,
    creds_required: Sequence[str] = ...,
    egress_hosts: Sequence[str] = ...,
    fs_paths: Sequence[str] = ...,
    rate_limit_per_minute: int | None = ...,
    mock_response: Any = ...,
) -> Callable[[F], Tool]: ...
def tool(
    fn: Callable[..., Any] | None = None,
    /,
    *,
    id: str | None = None,
    namespace: str = "custom",
    name: str | None = None,
    description: str | None = None,
    risk: int = 0,
    side_effects: SideEffect | None = None,
    scopes: Sequence[str] = (),
    creds_required: Sequence[str] = (),
    egress_hosts: Sequence[str] = (),
    fs_paths: Sequence[str] = (),
    rate_limit_per_minute: int | None = None,
    mock_response: Any = None,
) -> Tool | Callable[[Callable[..., Any]], Tool]:
    """Declare a tool. Safe by default: risk tier 0, no side effects, no network, no file access.

    The risk tier must be at least the minimum for the declared side effects (an email-sending tool cannot be tier 0).
    """

    def build(func: Callable[..., Any]) -> Tool:
        mcp_name = name or func.__name__
        text = description or (inspect.getdoc(func) or "").strip().splitlines()[0:1]
        plain = text if isinstance(text, str) else (text[0] if text else "")
        if not plain.strip():
            raise ToolDefinitionError(
                f"tool '{mcp_name}': add a plain-language description (docstring or description=); "
                "users read it in the wizard"
            )
        if risk not in (0, 1, 2, 3):
            raise ToolDefinitionError(f"tool '{mcp_name}': risk must be 0, 1, 2 or 3, got {risk!r}")
        effect = side_effects or _DEFAULT_EFFECT[risk]
        if risk < MIN_TIER[effect]:
            raise ToolDefinitionError(
                f"tool '{mcp_name}': side_effects '{effect}' needs risk >= {MIN_TIER[effect]}, got {risk}"
            )
        try:
            json.dumps(mock_response)
        except TypeError as exc:
            raise ToolDefinitionError(f"tool '{mcp_name}': mock_response must be JSON-serialisable") from exc
        model = _input_model(func, mcp_name)
        schema = model.model_json_schema()
        schema.pop("title", None)
        manifest = ToolManifest(
            id=id or f"{namespace}.{mcp_name}",
            mcp_name=mcp_name,
            description_plain=plain.strip(),
            input_schema=schema,
            scopes=list(scopes),
            side_effects=effect,
            risk_tier=risk,
            creds_required=list(creds_required),
            egress_hosts=list(egress_hosts),
            fs_paths=list(fs_paths),
            rate_limits=RateLimits(per_minute=rate_limit_per_minute),
            mock_response=mock_response,
        )
        return Tool(func, manifest, model)

    return build(fn) if fn is not None else build
