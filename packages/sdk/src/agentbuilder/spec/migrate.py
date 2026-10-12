"""Spec version migrations. `spec_version` is separate from the package version (PLAN 16.5).

Old specs load through `MIGRATIONS[n]` (n -> n+1). A spec from a NEWER version than this SDK knows is refused."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from agentbuilder.spec.errors import SpecVersionError
from agentbuilder.spec.models import SPEC_VERSION

MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}  # nothing to migrate yet: version 1 is the first


def upgrade(data: Mapping[str, Any], target: int = SPEC_VERSION) -> dict[str, Any]:
    out = dict(data)
    version = out.get("spec_version", 1)
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise SpecVersionError(f"spec_version must be a positive integer, got {version!r}")
    if version > target:
        raise SpecVersionError(
            f"spec_version {version} is newer than this SDK supports ({target}); upgrade agentbuilder"
        )
    while version < target:
        step = MIGRATIONS.get(version)
        if step is None:
            raise SpecVersionError(f"no migration from spec_version {version} to {version + 1}")
        out = step(out)
        version += 1
        out["spec_version"] = version
    return out
