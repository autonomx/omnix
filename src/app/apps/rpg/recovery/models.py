"""Phase 6.5 — Recovery Models.

Dataclasses and enums for the UX recovery layer.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class RecoveryReason(str, Enum):
    """Reasons that triggered recovery."""

    PARSER_FAILURE = "parser_failure"
    DIRECTOR_FAILURE = "director_failure"
    RENDERER_FAILURE = "renderer_failure"
    CONTRADICTION = "contradiction"
    AMBIGUITY = "ambiguity"


class AmbiguityDecision(str, Enum):
    """Decisions the ambiguity policy can return."""

    AUTO_RESOLVE = "auto_resolve"
    NARRATE_UNCERTAINTY = "narrate_uncertainty"
    REQUEST_CLARIFICATION = "request_clarification"


@dataclass
class RecoveryRecord:
    """A single recovery event record."""

    recovery_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    reason: str = ""
    tick: int | None = None
    scene_anchor_id: str | None = None
    summary: str = ""
    selected_policy: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RecoveryRecord":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RecoveryResult:
    """Result of a recovery operation."""

    reason: str = ""
    policy: str = ""
    scene: dict[str, Any] = field(default_factory=dict)
    record: RecoveryRecord | None = None
    used_anchor: bool = False
    used_coherence_summary: bool = False

    def to_dict(self) -> dict:
        return {
            "reason": self.reason,
            "policy": self.policy,
            "scene": self.scene,
            "record": self.record.to_dict() if self.record else None,
            "used_anchor": self.used_anchor,
            "used_coherence_summary": self.used_coherence_summary,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RecoveryResult":
        record_data = data.get("record")
        return cls(
            reason=data.get("reason", ""),
            policy=data.get("policy", ""),
            scene=data.get("scene", {}),
            record=RecoveryRecord.from_dict(record_data) if record_data else None,
            used_anchor=data.get("used_anchor", False),
            used_coherence_summary=data.get("used_coherence_summary", False),
        )


@dataclass
class RecoveryState:
    """Persistent state for the recovery subsystem."""

    last_good_scene_anchor: dict | None = None
    recent_recoveries: list[RecoveryRecord] = field(default_factory=list)
    recovery_count_by_scene: dict[str, int] = field(default_factory=dict)
    last_recovery_reason: str | None = None
    last_recovery_tick: int | None = None

    def to_dict(self) -> dict:
        return {
            "last_good_scene_anchor": self.last_good_scene_anchor,
            "recent_recoveries": [r.to_dict() for r in self.recent_recoveries],
            "recovery_count_by_scene": dict(self.recovery_count_by_scene),
            "last_recovery_reason": self.last_recovery_reason,
            "last_recovery_tick": self.last_recovery_tick,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RecoveryState":
        return cls(
            last_good_scene_anchor=data.get("last_good_scene_anchor"),
            recent_recoveries=[
                RecoveryRecord.from_dict(r)
                for r in data.get("recent_recoveries", [])
            ],
            recovery_count_by_scene=dict(data.get("recovery_count_by_scene", {})),
            last_recovery_reason=data.get("last_recovery_reason"),
            last_recovery_tick=data.get("last_recovery_tick"),
        )
