from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

from hn_signal.config import log

T = TypeVar("T")


@dataclass
class StageResult(Generic[T]):
    """Result from a pipeline stage, carrying value plus health signals."""

    value: T
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True if no errors occurred."""
        return not self.errors

    @property
    def degraded(self) -> bool:
        """True if warnings were generated (but no errors)."""
        return bool(self.warnings)

    def warn(self, msg: str) -> None:
        """Add a warning and log it."""
        self.warnings.append(msg)
        log.warning(msg)

    def error(self, msg: str) -> None:
        """Add an error and log it."""
        self.errors.append(msg)
        log.error(msg)
