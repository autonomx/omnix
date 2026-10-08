"""Phase 7.9 — Adventure Pack Models.

Explicit pack dataclasses with full roundtrip serialization.
Packs are content/config modules, not runtime truth owners.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PackMetadata:
    """Metadata describing an adventure pack."""

    pack_id: str
    title: str
    version: str
    author: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    requires_engine_version: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    pack_format_version: int = 0
    engine_compatibility: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "pack_id": self.pack_id,
            "title": self.title,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "tags": list(self.tags),
            "requires_engine_version": self.requires_engine_version,
            "metadata": dict(self.metadata),
            "pack_format_version": self.pack_format_version,
            "engine_compatibility": dict(self.engine_compatibility),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PackMetadata":
        return cls(
            pack_id=data.get("pack_id", ""),
            title=data.get("title", ""),
            version=data.get("version", ""),
            author=data.get("author", ""),
            description=data.get("description", ""),
            tags=list(data.get("tags", [])),
            requires_engine_version=data.get("requires_engine_version", ""),
            metadata=dict(data.get("metadata", {})),
            pack_format_version=int(data.get("pack_format_version", 0)),
            engine_compatibility=dict(data.get("engine_compatibility", {})),
        )


@dataclass
class PackManifest:
    """Manifest describing pack dependencies, conflicts, and namespaces."""

    manifest_id: str
    pack_id: str
    content_version: str
    dependencies: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    namespaces: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "manifest_id": self.manifest_id,
            "pack_id": self.pack_id,
            "content_version": self.content_version,
            "dependencies": list(self.dependencies),
            "conflicts": list(self.conflicts),
            "namespaces": list(self.namespaces),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PackManifest":
        return cls(
            manifest_id=data.get("manifest_id", ""),
            pack_id=data.get("pack_id", ""),
            content_version=data.get("content_version", ""),
            dependencies=list(data.get("dependencies", [])),
            conflicts=list(data.get("conflicts", [])),
            namespaces=list(data.get("namespaces", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class PackContent:
    """Structured content provided by an adventure pack."""

    creator_facts: list[dict] = field(default_factory=list)
    setup_templates: list[dict] = field(default_factory=list)
    factions: list[dict] = field(default_factory=list)
    locations: list[dict] = field(default_factory=list)
    npcs: list[dict] = field(default_factory=list)
    threads: list[dict] = field(default_factory=list)
    arcs: list[dict] = field(default_factory=list)
    social_seeds: list[dict] = field(default_factory=list)
    reveal_seeds: list[dict] = field(default_factory=list)
    pacing_presets: list[dict] = field(default_factory=list)
    gm_presets: list[dict] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "creator_facts": [dict(x) for x in self.creator_facts],
            "setup_templates": [dict(x) for x in self.setup_templates],
            "factions": [dict(x) for x in self.factions],
            "locations": [dict(x) for x in self.locations],
            "npcs": [dict(x) for x in self.npcs],
            "threads": [dict(x) for x in self.threads],
            "arcs": [dict(x) for x in self.arcs],
            "social_seeds": [dict(x) for x in self.social_seeds],
            "reveal_seeds": [dict(x) for x in self.reveal_seeds],
            "pacing_presets": [dict(x) for x in self.pacing_presets],
            "gm_presets": [dict(x) for x in self.gm_presets],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PackContent":
        return cls(
            creator_facts=list(data.get("creator_facts", [])),
            setup_templates=list(data.get("setup_templates", [])),
            factions=list(data.get("factions", [])),
            locations=list(data.get("locations", [])),
            npcs=list(data.get("npcs", [])),
            threads=list(data.get("threads", [])),
            arcs=list(data.get("arcs", [])),
            social_seeds=list(data.get("social_seeds", [])),
            reveal_seeds=list(data.get("reveal_seeds", [])),
            pacing_presets=list(data.get("pacing_presets", [])),
            gm_presets=list(data.get("gm_presets", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class AdventurePack:
    """A complete adventure pack with metadata, manifest, and content."""

    metadata: PackMetadata
    manifest: PackManifest
    content: PackContent

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata.to_dict(),
            "manifest": self.manifest.to_dict(),
            "content": self.content.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AdventurePack":
        return cls(
            metadata=PackMetadata.from_dict(data.get("metadata", {})),
            manifest=PackManifest.from_dict(data.get("manifest", {})),
            content=PackContent.from_dict(data.get("content", {})),
        )


@dataclass
class PackValidationIssue:
    """A single validation issue found in a pack."""

    path: str
    code: str
    message: str
    severity: str = "error"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PackValidationIssue":
        return cls(
            path=data.get("path", ""),
            code=data.get("code", ""),
            message=data.get("message", ""),
            severity=data.get("severity", "error"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class PackValidationResult:
    """Aggregated validation result for a pack."""

    issues: list[PackValidationIssue] = field(default_factory=list)

    def is_blocking(self) -> bool:
        """Return True if any issue has severity 'error'."""
        return any(issue.severity == "error" for issue in self.issues)

    def to_dict(self) -> dict:
        return {
            "issues": [issue.to_dict() for issue in self.issues],
            "is_blocking": self.is_blocking(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PackValidationResult":
        return cls(
            issues=[
                PackValidationIssue.from_dict(i)
                for i in data.get("issues", [])
            ]
        )
