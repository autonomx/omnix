"""Data models for the Phase 7.2 Gameplay Control Layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class OptionConstraint:
    """Constraint that can hide or disable an option."""

    constraint_id: str
    condition: str  # e.g. "fact_exists", "thread_resolved", "danger_level"
    required_value: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "OptionConstraint":
        return cls(**data)


@dataclass
class ChoiceOption:
    """A single player-choice option produced by the OptionEngine.

    Each option carries explicit metadata about *why* it exists so that
    the UI/debugger can explain the control layer's reasoning.
    """

    option_id: str
    label: str
    intent_type: str
    summary: str
    target_id: Optional[str]
    tags: list[str] = field(default_factory=list)
    constraints: list[OptionConstraint] = field(default_factory=list)
    priority: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "option_id": self.option_id,
            "label": self.label,
            "intent_type": self.intent_type,
            "summary": self.summary,
            "target_id": self.target_id,
            "tags": list(self.tags),
            "constraints": [c.to_dict() for c in self.constraints],
            "priority": self.priority,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChoiceOption":
        return cls(
            option_id=data["option_id"],
            label=data["label"],
            intent_type=data["intent_type"],
            summary=data["summary"],
            target_id=data.get("target_id"),
            tags=list(data.get("tags", [])),
            constraints=[
                OptionConstraint.from_dict(c)
                for c in data.get("constraints", [])
            ],
            priority=data.get("priority", 0.5),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class ChoiceSet:
    """A complete set of choice options for the current tick.

    The choice_set_id is deterministic so that replays and UI diffs
    can reliably identify which control-state produced this set.
    """

    choice_set_id: str
    title: str
    prompt: str
    options: list[ChoiceOption] = field(default_factory=list)
    source_summary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "choice_set_id": self.choice_set_id,
            "title": self.title,
            "prompt": self.prompt,
            "options": [o.to_dict() for o in self.options],
            "source_summary": dict(self.source_summary),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChoiceSet":
        return cls(
            choice_set_id=data["choice_set_id"],
            title=data["title"],
            prompt=data["prompt"],
            options=[ChoiceOption.from_dict(o) for o in data.get("options", [])],
            source_summary=dict(data.get("source_summary", {})),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class PacingState:
    """Current pacing values that bias option priorities."""

    danger_level: str = "medium"  # low, medium, high
    reveal_pressure: str = "low"  # low, medium, high
    social_pressure: str = "low"  # low, medium, high
    action_pressure: str = "low"  # low, medium, high
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PacingState":
        return cls(**data)


@dataclass
class FramingState:
    """Current framing values that bias option priorities.

    The forced_* flags are consumed (cleared) by the controller each
    tick so that they only affect a single choice set production.
    """

    focus_target_type: Optional[str] = None
    focus_target_id: Optional[str] = None
    forced_option_framing_pending: bool = False
    forced_recap_pending: bool = False
    last_choice_set: Optional[ChoiceSet] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        result = asdict(self)
        # Don't serialize the full last_choice_set; store a summary instead.
        if self.last_choice_set is not None:
            result["last_choice_set_id"] = self.last_choice_set.choice_set_id
            del result["last_choice_set"]
        else:
            result["last_choice_set_id"] = None
            del result["last_choice_set"]
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "FramingState":
        return cls(
            focus_target_type=data.get("focus_target_type"),
            focus_target_id=data.get("focus_target_id"),
            forced_option_framing_pending=data.get("forced_option_framing_pending", False),
            forced_recap_pending=data.get("forced_recap_pending", False),
            metadata=dict(data.get("metadata", {})),
        )