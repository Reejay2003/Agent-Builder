"""Spec errors. `SpecError.problems` holds one readable line per problem (`field.path: message`)."""

from __future__ import annotations


class SpecError(ValueError):
    def __init__(self, message: str, problems: list[str] | None = None) -> None:
        super().__init__(message)
        self.problems: list[str] = problems or [message]


class SpecVersionError(SpecError):
    """The spec declares a version this SDK cannot load or migrate."""
