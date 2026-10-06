"""Phase 7.8 — Arc Control Data Models.

Explicit arc/steering dataclasses for narrative arcs, reveal directives,
pacing plans, and scene bias state.

These are steering-layer objects — they bias selection, pacing, framing,
and reveal timing.  They do NOT override coherence truth directly and
must never become an authority source for canonical state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class NarrativeArc:
    """An explicit narrative arc with status and priority."""

    arc_id: str
    title: str
    status: str = "active"
    priority: str = "normal"
    arc_type: str = "general"
    related_thread_ids: list[str] = field(default_factory=list)
    focus_entity_ids: list[str] = field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "NarrativeArc":
        return cls(
            arc_id=data.get("arc_id", ""),
            title=data.get("title", ""),
            status=data.get("status", "active"),
            priority=data.get("priority", "normal"),
            arc_type=data.get("arc_type", "general"),
            related_thread_ids=list(data.get("related_thread_ids", [])),
            focus_entity_ids=list(data.get("focus_entity_ids", [])),
            summary=data.get("summary", ""),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class RevealDirectiveState:
    """A scheduled or held reveal directive."""

    reveal_id: str
    target_id: str
    target_type: str
    status: str = "scheduled"
    timing: str = "soon"
    hold_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RevealDirectiveState":
        return cls(
            reveal_id=data.get("reveal_id", ""),
            target_id=data.get("target_id", ""),
            target_type=data.get("target_type", ""),
            status=data.get("status", "scheduled"),
            timing=data.get("timing", "soon"),
            hold_reason=data.get("hold_reason", ""),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class PacingPlanState:
    """Multi-scene pacing intent."""

    plan_id: str
    label: str
    danger_bias: str = "medium"
    mystery_bias: str = "medium"
    social_bias: str = "medium"
    combat_bias: str = "low"
    target_scene_count: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PacingPlanState":
        return cls(
            plan_id=data.get("plan_id", ""),
            label=data.get("label", ""),
            danger_bias=data.get("danger_bias", "medium"),
            mystery_bias=data.get("mystery_bias", "medium"),
            social_bias=data.get("social_bias", "medium"),
            combat_bias=data.get("combat_bias", "low"),
            target_scene_count=data.get("target_scene_count", 3),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class SceneBiasState:
    """Scene/type biasing and live steering flags."""

    bias_id: str
    scene_type_bias: str = "balanced"
    focus_arc_id: str | None = None
    focus_thread_id: str | None = None
    focus_npc_id: str | None = None
    force_option_framing: bool = False
    force_recap: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SceneBiasState":
        return cls(
            bias_id=data.get("bias_id", ""),
            scene_type_bias=data.get("scene_type_bias", "balanced"),
            focus_arc_id=data.get("focus_arc_id"),
            focus_thread_id=data.get("focus_thread_id"),
            focus_npc_id=data.get("focus_npc_id"),
            force_option_framing=data.get("force_option_framing", False),
            force_recap=data.get("force_recap", False),
            metadata=dict(data.get("metadata", {})),
        )
