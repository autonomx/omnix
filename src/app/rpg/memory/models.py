"""Phase 7.7 — Memory / Read-Model Data Models.

Explicit structured memory/read-model dataclasses for journal entries,
recap snapshots, codex entries, and campaign memory snapshots.

These are derived read-model objects — they do NOT store canonical truth
and must never be used to mutate coherence or social state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class JournalEntry:
    """A chronological journal entry derived from game state and events."""

    entry_id: str
    tick: int | None
    entry_type: str
    title: str
    summary: str
    entity_ids: list[str] = field(default_factory=list)
    thread_ids: list[str] = field(default_factory=list)
    location: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "JournalEntry":
        return cls(
            entry_id=data["entry_id"],
            tick=data.get("tick"),
            entry_type=data.get("entry_type", "action"),
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            entity_ids=list(data.get("entity_ids", [])),
            thread_ids=list(data.get("thread_ids", [])),
            location=data.get("location"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class RecapSnapshot:
    """A short-form recap snapshot grounded in current game state."""

    snapshot_id: str
    tick: int | None
    title: str
    summary: str
    scene_summary: dict[str, Any] = field(default_factory=dict)
    active_threads: list[dict] = field(default_factory=list)
    recent_consequences: list[dict] = field(default_factory=list)
    social_highlights: list[dict] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RecapSnapshot":
        return cls(
            snapshot_id=data["snapshot_id"],
            tick=data.get("tick"),
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            scene_summary=dict(data.get("scene_summary", {})),
            active_threads=list(data.get("active_threads", [])),
            recent_consequences=list(data.get("recent_consequences", [])),
            social_highlights=list(data.get("social_highlights", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class CodexEntry:
    """A structured codex reference entry for NPCs, factions, locations, lore, etc."""

    entry_id: str
    entry_type: str
    title: str
    summary: str
    canonical: bool = True
    tags: list[str] = field(default_factory=list)
    related_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CodexEntry":
        return cls(
            entry_id=data["entry_id"],
            entry_type=data.get("entry_type", "lore"),
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            canonical=bool(data.get("canonical", True)),
            tags=list(data.get("tags", [])),
            related_ids=list(data.get("related_ids", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class CampaignMemorySnapshot:
    """A longer-lived campaign memory snapshot for creators and future UI."""

    snapshot_id: str
    tick: int | None
    title: str
    current_scene: dict[str, Any] = field(default_factory=dict)
    active_threads: list[dict] = field(default_factory=list)
    resolved_threads: list[dict] = field(default_factory=list)
    major_consequences: list[dict] = field(default_factory=list)
    social_summary: dict[str, Any] = field(default_factory=dict)
    canon_summary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CampaignMemorySnapshot":
        return cls(
            snapshot_id=data["snapshot_id"],
            tick=data.get("tick"),
            title=data.get("title", ""),
            current_scene=dict(data.get("current_scene", {})),
            active_threads=list(data.get("active_threads", [])),
            resolved_threads=list(data.get("resolved_threads", [])),
            major_consequences=list(data.get("major_consequences", [])),
            social_summary=dict(data.get("social_summary", {})),
            canon_summary=dict(data.get("canon_summary", {})),
            metadata=dict(data.get("metadata", {})),
        )
