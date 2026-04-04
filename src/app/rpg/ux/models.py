"""Phase 8.0 — UX-Layer Payload Models.

Explicit dataclasses for player-facing UX payloads.
These are presentation-layer models only — they do not own or mutate
any game truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlayerChoiceCard:
    """A single player-facing choice option."""

    choice_id: str
    label: str
    summary: str
    intent_type: str
    target_id: str | None = None
    tags: list[str] = field(default_factory=list)
    priority: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "choice_id": self.choice_id,
            "label": self.label,
            "summary": self.summary,
            "intent_type": self.intent_type,
            "target_id": self.target_id,
            "tags": list(self.tags),
            "priority": self.priority,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlayerChoiceCard":
        return cls(
            choice_id=data.get("choice_id", ""),
            label=data.get("label", ""),
            summary=data.get("summary", ""),
            intent_type=data.get("intent_type", ""),
            target_id=data.get("target_id"),
            tags=list(data.get("tags", [])),
            priority=float(data.get("priority", 0.0)),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class PanelDescriptor:
    """Describes a single UI panel available to the player."""

    panel_id: str
    title: str
    panel_type: str
    count: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "panel_id": self.panel_id,
            "title": self.title,
            "panel_type": self.panel_type,
            "count": self.count,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PanelDescriptor":
        return cls(
            panel_id=data.get("panel_id", ""),
            title=data.get("title", ""),
            panel_type=data.get("panel_type", ""),
            count=data.get("count"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class SceneUXPayload:
    """Unified player-facing scene payload."""

    payload_id: str
    scene: dict[str, Any]
    choices: list[PlayerChoiceCard] = field(default_factory=list)
    panels: list[PanelDescriptor] = field(default_factory=list)
    highlights: dict[str, Any] = field(default_factory=dict)
    interaction: dict[str, Any] = field(default_factory=dict)
    encounter: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    trace: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "payload_id": self.payload_id,
            "scene": dict(self.scene),
            "choices": [c.to_dict() for c in self.choices],
            "panels": [p.to_dict() for p in self.panels],
            "highlights": dict(self.highlights),
            "interaction": dict(self.interaction),
            "encounter": dict(self.encounter),
            "metadata": dict(self.metadata),
            "trace": dict(self.trace),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SceneUXPayload":
        return cls(
            payload_id=data.get("payload_id", ""),
            scene=dict(data.get("scene", {})),
            choices=[
                PlayerChoiceCard.from_dict(c)
                for c in data.get("choices", [])
            ],
            panels=[
                PanelDescriptor.from_dict(p)
                for p in data.get("panels", [])
            ],
            highlights=dict(data.get("highlights", {})),
            interaction=dict(data.get("interaction", {})),
            encounter=dict(data.get("encounter", {})),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class ActionResultPayload:
    """Result payload returned after a player selects a choice."""

    result_id: str
    action_result: dict[str, Any]
    updated_scene: dict[str, Any] = field(default_factory=dict)
    updated_choices: list[PlayerChoiceCard] = field(default_factory=list)
    updated_panels: list[PanelDescriptor] = field(default_factory=list)
    interaction: dict[str, Any] = field(default_factory=dict)
    encounter: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "result_id": self.result_id,
            "action_result": dict(self.action_result),
            "updated_scene": dict(self.updated_scene),
            "updated_choices": [c.to_dict() for c in self.updated_choices],
            "updated_panels": [p.to_dict() for p in self.updated_panels],
            "interaction": dict(self.interaction),
            "encounter": dict(self.encounter),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ActionResultPayload":
        return cls(
            result_id=data.get("result_id", ""),
            action_result=dict(data.get("action_result", {})),
            updated_scene=dict(data.get("updated_scene", {})),
            updated_choices=[
                PlayerChoiceCard.from_dict(c)
                for c in data.get("updated_choices", [])
            ],
            updated_panels=[
                PanelDescriptor.from_dict(p)
                for p in data.get("updated_panels", [])
            ],
            interaction=dict(data.get("interaction", {})),
            encounter=dict(data.get("encounter", {})),
            metadata=dict(data.get("metadata", {})),
        )
