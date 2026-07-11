"""Validation primitives shared across the deterministic validators.

Every authoritative interpretation MUST pass the deterministic validators
before it can be CERTIFIED. The primitive types (Violation, ValidatorResult,
Severity) live here so all four validator submodules share one shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    BLOCK = "block"   # blocks CERTIFIED status


@dataclass(frozen=True)
class Violation:
    """One deterministic check failure."""
    code: str
    severity: str        # see Severity
    message: str
    evidence_ids: tuple[str, ...] = ()
    field_path: str = ""
    checker: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "evidence_ids": list(self.evidence_ids),
            "field_path": self.field_path,
            "checker": self.checker,
        }


@dataclass(frozen=True)
class ValidatorResult:
    """Aggregate of one validation run."""
    violations: tuple[Violation, ...] = ()
    certified: bool = False
    abstained: bool = False
    checked: tuple[str, ...] = ()
    summary: Mapping[str, Any] = field(default_factory=dict)

    @property
    def blocks(self) -> tuple[Violation, ...]:
        return tuple(v for v in self.violations if v.severity == Severity.BLOCK.value)

    @property
    def errors(self) -> tuple[Violation, ...]:
        return tuple(v for v in self.violations if v.severity == Severity.ERROR.value)


__all__ = ["Severity", "Violation", "ValidatorResult"]