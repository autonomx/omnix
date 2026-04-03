"""Phase 7.3 — Execution models.

Explicit structured models for action resolution. These are resolution
artifacts, NOT state owners. They describe what happened when a player
option was resolved, and what events should be emitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ActionConsequence:
    """A single consequence produced by resolving an action."""

    consequence_id: str
    consequence_type: str
    summary: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "consequence_id": self.consequence_id,
            "consequence_type": self.consequence_type,
            "summary": self.summary,
            "event_type": self.event_type,
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ActionConsequence":
        return cls(
            consequence_id=data["consequence_id"],
            consequence_type=data["consequence_type"],
            summary=data["summary"],
            event_type=data["event_type"],
            payload=dict(data.get("payload", {})),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class SceneTransition:
    """Describes an explicit scene/location transition."""

    transition_id: str
    transition_type: str
    from_location: Optional[str] = None
    to_location: Optional[str] = None
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "transition_id": self.transition_id,
            "transition_type": self.transition_type,
            "from_location": self.from_location,
            "to_location": self.to_location,
            "summary": self.summary,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SceneTransition":
        return cls(
            transition_id=data["transition_id"],
            transition_type=data["transition_type"],
            from_location=data.get("from_location"),
            to_location=data.get("to_location"),
            summary=data.get("summary", ""),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class ResolvedAction:
    """The full resolved result of a player selecting a choice option."""

    action_id: str
    option_id: str
    intent_type: str
    target_id: Optional[str] = None
    summary: str = ""
    consequences: list[ActionConsequence] = field(default_factory=list)
    transition: Optional[SceneTransition] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "option_id": self.option_id,
            "intent_type": self.intent_type,
            "target_id": self.target_id,
            "summary": self.summary,
            "consequences": [c.to_dict() for c in self.consequences],
            "transition": self.transition.to_dict() if self.transition else None,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ResolvedAction":
        consequences = [
            ActionConsequence.from_dict(c) for c in data.get("consequences", [])
        ]
        transition_data = data.get("transition")
        transition = SceneTransition.from_dict(transition_data) if transition_data else None
        return cls(
            action_id=data["action_id"],
            option_id=data["option_id"],
            intent_type=data["intent_type"],
            target_id=data.get("target_id"),
            summary=data.get("summary", ""),
            consequences=consequences,
            transition=transition,
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class ActionResolutionResult:
    """Top-level result of resolving a choice option into events."""

    resolved_action: ResolvedAction = field(default_factory=lambda: ResolvedAction(
        action_id="", option_id="", intent_type=""
    ))
    events: list[dict] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "resolved_action": self.resolved_action.to_dict(),
            "events": list(self.events),
            "trace": dict(self.trace),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ActionResolutionResult":
        return cls(
            resolved_action=ResolvedAction.from_dict(data.get("resolved_action", {
                "action_id": "", "option_id": "", "intent_type": ""
            })),
            events=list(data.get("events", [])),
            trace=dict(data.get("trace", {})),
        )
