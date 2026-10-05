"""Phase 8.5 — Migration Models.

Explicit migration artifact dataclasses and constants.
All models are serializable and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CURRENT_SAVE_FORMAT_VERSION: int = 2
CURRENT_PACK_FORMAT_VERSION: int = 2
SUPPORTED_MIGRATION_SCOPES: frozenset[str] = frozenset({"save", "pack"})


# ---------------------------------------------------------------------------
# MigrationStep — describes a single version hop
# ---------------------------------------------------------------------------

@dataclass
class MigrationStep:
    """Describes a single version migration hop."""

    from_version: int
    to_version: int
    scope: str
    name: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_version": self.from_version,
            "to_version": self.to_version,
            "scope": self.scope,
            "name": self.name,
            "description": self.description,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MigrationStep:
        return cls(
            from_version=data.get("from_version", 0),
            to_version=data.get("to_version", 0),
            scope=data.get("scope", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            metadata=dict(data.get("metadata", {})),
        )


# ---------------------------------------------------------------------------
# MigrationReport — inspectable record of what happened during migration
# ---------------------------------------------------------------------------

@dataclass
class MigrationReport:
    """Inspectable report of a migration run."""

    scope: str = ""
    original_version: int | None = None
    final_version: int | None = None
    applied_steps: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    changed_keys: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "original_version": self.original_version,
            "final_version": self.final_version,
            "applied_steps": list(self.applied_steps),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "changed_keys": list(self.changed_keys),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MigrationReport:
        return cls(
            scope=data.get("scope", ""),
            original_version=data.get("original_version"),
            final_version=data.get("final_version"),
            applied_steps=list(data.get("applied_steps", [])),
            warnings=list(data.get("warnings", [])),
            errors=list(data.get("errors", [])),
            changed_keys=list(data.get("changed_keys", [])),
            metadata=dict(data.get("metadata", {})),
        )


# ---------------------------------------------------------------------------
# CompatibilityReport — structured compatibility check result
# ---------------------------------------------------------------------------

@dataclass
class CompatibilityReport:
    """Structured result of a compatibility check."""

    scope: str = ""
    compatible: bool = True
    format_version: int | None = None
    engine_constraints: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "compatible": self.compatible,
            "format_version": self.format_version,
            "engine_constraints": dict(self.engine_constraints),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompatibilityReport:
        return cls(
            scope=data.get("scope", ""),
            compatible=data.get("compatible", True),
            format_version=data.get("format_version"),
            engine_constraints=dict(data.get("engine_constraints", {})),
            warnings=list(data.get("warnings", [])),
            errors=list(data.get("errors", [])),
            metadata=dict(data.get("metadata", {})),
        )


# ---------------------------------------------------------------------------
# MigratedPayload — result of a migration: payload + report
# ---------------------------------------------------------------------------

@dataclass
class MigratedPayload:
    """Result of a migration: the transformed payload and a report."""

    payload: dict[str, Any] = field(default_factory=dict)
    report: MigrationReport = field(default_factory=MigrationReport)

    def to_dict(self) -> dict[str, Any]:
        return {
            "payload": dict(self.payload),
            "report": self.report.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MigratedPayload:
        return cls(
            payload=dict(data.get("payload", {})),
            report=MigrationReport.from_dict(data.get("report", {})),
        )


# ---------------------------------------------------------------------------
# PackCompatibilityResult — dedicated pack compatibility result
# ---------------------------------------------------------------------------

@dataclass
class PackCompatibilityResult:
    """Dedicated result for pack compatibility checks."""

    pack_id: str | None = None
    compatible: bool = True
    normalized_pack: dict[str, Any] = field(default_factory=dict)
    report: MigrationReport = field(default_factory=MigrationReport)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "compatible": self.compatible,
            "normalized_pack": dict(self.normalized_pack),
            "report": self.report.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PackCompatibilityResult:
        return cls(
            pack_id=data.get("pack_id"),
            compatible=data.get("compatible", True),
            normalized_pack=dict(data.get("normalized_pack", {})),
            report=MigrationReport.from_dict(data.get("report", {})),
        )
