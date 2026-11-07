"""Compiler C: CompiledAgent -> OpenShell sandbox policy and provider profile.

The policy is generated from what each tool's manifest DECLARES: its network hosts and file paths become exactly
what the sandbox allows, nothing more (everything else is denied by default).

The provider profile describes how the model's API key reaches the model: OpenShell keeps the key outside the
sandbox and injects it only for the model host and only for the listed binaries (spikes/s3-openshell, part 4).

Binary paths are those INSIDE the sandbox image, so they are parameters (defaults match our `agentbuilder/s3-agent`
image). Allowed-binary rules follow process ancestry: a child process inherits its parent's access, so keep shell
tools out of agents that hold provider access.

Limits: network rules are per SANDBOX, not per tool server. OpenShell matches on the binary, and every tool server and
the agent itself run the same Python, so any of them can reach every listed host. For real separation between tool
servers, give each its own sandbox or its own binary. Tool hosts are always port 443 because manifests allow bare host
names only.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit

import yaml

from agentbuilder.compile.compiled import CompiledAgent
from agentbuilder.compile.compiler import CompileError

DEFAULT_BINARIES = ("/usr/bin/python3.12", "/opt/venv/bin/python")
DEFAULT_READ_ONLY = ("/usr", "/lib", "/etc", "/opt/venv")
_WRITING = {"write", "external_comms", "destructive", "financial"}
_LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def to_openshell_policy(
    c: CompiledAgent,
    *,
    binaries: Sequence[str] = DEFAULT_BINARIES,
    read_only: Sequence[str] = DEFAULT_READ_ONLY,
    run_as: str = "1000",
) -> dict[str, Any]:
    paths: dict[str, bool] = {}  # path -> must be writable
    for t in c.tools:
        for p in t.fs_paths:
            paths[p] = paths.get(p, False) or t.side_effects in _WRITING
    read_write = sorted({"/tmp", *(p for p, w in paths.items() if w)})
    readable = sorted({*read_only, *(p for p, w in paths.items() if not w)} - set(read_write))

    network: dict[str, Any] = {}
    for server in c.servers:
        tools = c.tools_for(server.name)
        hosts = sorted({h for t in tools for h in t.egress_hosts})
        if not hosts:
            continue
        mode = "read-write" if any(t.risk_tier >= 1 or t.side_effects in _WRITING for t in tools) else "read-only"
        network[f"tools_{_key(server.name)}"] = {
            "name": f"tools-{_key(server.name).replace('_', '-')}",
            "endpoints": [
                {"host": h, "port": 443, "protocol": "rest", "enforcement": "enforce", "access": mode} for h in hosts
            ],
            "binaries": [{"path": b} for b in binaries],
        }

    policy: dict[str, Any] = {
        "version": 1,
        "filesystem_policy": {"include_workdir": False, "read_only": readable, "read_write": read_write},
        "landlock": {"compatibility": "best_effort"},
        "process": {"run_as_user": run_as, "run_as_group": run_as},
    }
    if network:
        policy["network_policies"] = network
    return policy


def to_openshell_provider_profile(
    c: CompiledAgent, *, binaries: Sequence[str] = DEFAULT_BINARIES
) -> dict[str, Any] | None:
    """The model endpoint as an OpenShell provider profile, or None when the model needs no key (nothing to inject)."""
    if not c.model.api_key_env:
        return None
    url = urlsplit(c.model.base_url)
    host = url.hostname or ""
    if host in _LOOPBACK:
        raise CompileError(
            f"the model endpoint {c.model.base_url} is on this machine's loopback; a sandbox cannot reach it there "
            "(use host.openshell.internal instead of localhost)"
        )
    port = url.port or (443 if url.scheme == "https" else 80)
    extra = f"_{port}" if url.port else ""  # profiles are global by id: two ports on one host must not share one
    return {
        "id": f"agentbuilder-{_key(f'{c.model.provider}_{host}{extra}').replace('_', '-')}",
        "display_name": f"Agent Builder: {c.model.provider}",
        "description": f"Model API for agent '{c.name}'",
        "category": "inference",
        "inference_capable": True,
        "credentials": [
            {
                "name": "api_key",
                "description": f"API key for {host}",
                "env_vars": [c.model.api_key_env],
                "required": True,
                "auth_style": "bearer",
                "header_name": "authorization",
            }
        ],
        "discovery": {"credentials": ["api_key"]},
        "endpoints": [
            {
                "host": host,
                "port": port,
                "protocol": "rest",
                "access": "read-write",
                "enforcement": "enforce",
            }
        ],
        "binaries": list(binaries),
    }


def to_openshell_yaml(mapping: dict[str, Any], what: str) -> str:
    header = f"# Generated by agentbuilder ({what}). Do not edit; edit the spec.\n"
    return header + yaml.safe_dump(mapping, sort_keys=False, allow_unicode=True, default_flow_style=False)
