"""Structured models for player options, pacing state, and framing state."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class OptionConstraint:
    constraint_id: str
    constraint_type: str
    value: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "OptionConstraint":
        return cls(**data)


@dataclass
class ChoiceOption:
    option_id: str
    label: str
    intent_type: str
    summary: str
    target_id: str | None = None
    tags: list[str] = field(default_factory=list)
    constraints: list[OptionConstraint] = field(default_factory=list)
    priority: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ChoiceOption":
        raw_constraints = data.pop("constraints", [])
        constraints = [OptionConstraint.from_dict(c) for c in raw_constraints]
        return cls(**data, constraints=constraints)


@dataclass
class ChoiceSet:
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
            "source_summary": self.source_summary,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChoiceSet":
        raw_options = data.pop("options", [])
        options = [ChoiceOption.from_dict(o) for o in raw_options]
        return cls(**data, options=options)


@dataclass
class PacingState:
    scene_index: int = 0
    danger_level: str = "medium"
    mystery_pressure: str = "medium"
    social_pressure: str = "medium"
    combat_pressure: str = "low"
    reveal_pressure: str = "medium"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PacingState":
        return cls(**data)


@dataclass
class FramingState:
    last_choice_set: dict[str, Any] | None = None
    last_recap_tick: int | None = None
    forced_recap_pending: bool = False
    forced_option_framing_pending: bool = False
    focus_target_type: str | None = None
    focus_target_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FramingState":
        return cls(**data)
