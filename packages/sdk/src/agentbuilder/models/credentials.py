"""Resolve credential references (`env://NAME`, `secret://path`) into secrets, safely.

Lessons from this project's own mistakes are enforced here:
- a key pasted with spaces or line breaks inside is refused with a clear message (it once arrived garbled);
- a `Secret` never prints its value (repr and str are masked), and `redact()` scrubs it from any text before logging.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from typing import Protocol


class CredentialError(ValueError):
    """A credential reference cannot be resolved to a usable value."""


class Secret:
    """Holds a secret value. Printing, logging and repr show only a mask; call `reveal()` where the value is needed."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Secret(****)"

    __str__ = __repr__

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Secret) and other._value == self._value

    def __hash__(self) -> int:
        return hash(self._value)

    def __bool__(self) -> bool:
        return bool(self._value)


class SecretStore(Protocol):
    """Anything that can look a `secret://<name>` up (a file, a keychain, OpenBao...). Return None if not found."""

    def get(self, name: str) -> str | None: ...


_REF = re.compile(r"^(env|secret)://(.+)$")


def _clean(value: str, what: str) -> Secret:
    value = value.strip()  # a trailing newline from a pasted line is harmless
    if not value:
        raise CredentialError(f"{what} is empty")
    if re.search(r"\s", value):
        raise CredentialError(
            f"{what} contains spaces or line breaks inside the value; it was probably pasted wrapped. "
            "Re-copy it as one unbroken line."
        )
    return Secret(value)


def secret_env_name(path: str) -> str:
    """`secret://llm/primary` is looked up as the environment variable AGENTBUILDER_SECRET_LLM_PRIMARY."""
    return "AGENTBUILDER_SECRET_" + re.sub(r"[^A-Za-z0-9]+", "_", path).strip("_").upper()


def resolve_credential(
    ref: str | None, *, environ: Mapping[str, str] | None = None, stores: Sequence[SecretStore] = ()
) -> Secret | None:
    """Return the secret a reference points to; None when no credential is configured (for example local Ollama)."""
    if ref is None:
        return None
    env = os.environ if environ is None else environ
    m = _REF.match(ref)
    if not m:
        raise CredentialError("credentials are by reference only: use env://VAR or secret://name, never the key itself")
    scheme, name = m.groups()
    if scheme == "env":
        value = env.get(name)
        if value is None:
            raise CredentialError(f"environment variable {name} is not set (referenced as {ref})")
        return _clean(value, f"environment variable {name}")
    for store in stores:
        found = store.get(name)
        if found is not None:
            return _clean(found, f"secret {ref}")
    fallback = secret_env_name(name)
    if fallback in env:
        return _clean(env[fallback], f"environment variable {fallback}")
    raise CredentialError(f"secret {ref} not found in the configured stores or as ${fallback}")


def redact(text: str, secrets: Sequence[Secret | str | None]) -> str:
    """Replace every secret value in `text` with ****. Use before writing any log line that might contain one."""
    for s in secrets:
        value = s.reveal() if isinstance(s, Secret) else s
        if value and len(value) >= 6:
            text = text.replace(value, "****")
    return text
