"""Phase 8.1 — Dialogue Models.

Explicit structured dialogue artifacts for NPC interaction planning.
These are NOT truth owners — they describe the structured plan and
presentation of dialogue turns, derived from authoritative state.

All models are serializable and deterministic.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class DialogueTurnContext:
    """Full structured input to dialogue planning.

    Gathered from coherence, social state, arc control, and NPC agency
    by the DialogueContextBuilder.  Never mutates upstream state.
    """

    speaker_id: str
    listener_id: str | None = None
    scene_location: str | None = None
    scene_summary: dict[str, Any] = field(default_factory=dict)
    speaker_state: dict[str, Any] = field(default_factory=dict)
    listener_state: dict[str, Any] = field(default_factory=dict)
    relationship_state: dict[str, Any] = field(default_factory=dict)
    social_context: dict[str, Any] = field(default_factory=dict)
    coherence_context: dict[str, Any] = field(default_factory=dict)
    arc_context: dict[str, Any] = field(default_factory=dict)
    interaction_history: list[dict[str, Any]] = field(default_factory=list)
    current_intent_type: str = ""
    current_action_outcome: str | None = None
    current_tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DialogueTurnContext":
        return cls(
            speaker_id=data.get("speaker_id", ""),
            listener_id=data.get("listener_id"),
            scene_location=data.get("scene_location"),
            scene_summary=dict(data.get("scene_summary", {})),
            speaker_state=dict(data.get("speaker_state", {})),
            listener_state=dict(data.get("listener_state", {})),
            relationship_state=dict(data.get("relationship_state", {})),
            social_context=dict(data.get("social_context", {})),
            coherence_context=dict(data.get("coherence_context", {})),
            arc_context=dict(data.get("arc_context", {})),
            interaction_history=list(data.get("interaction_history", [])),
            current_intent_type=data.get("current_intent_type", ""),
            current_action_outcome=data.get("current_action_outcome"),
            current_tags=list(data.get("current_tags", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class DialogueActDecision:
    """Captures 'what kind of response is this'.

    Produced by the response planner's classification step.
    """

    primary_act: str = "acknowledge"
    secondary_acts: list[str] = field(default_factory=list)
    intent_alignment: str = "neutral"
    tone: str = "neutral"
    stance: str = "neutral"
    reveal_level: str = "none"
    urgency: str = "normal"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DialogueActDecision":
        return cls(
            primary_act=data.get("primary_act", "acknowledge"),
            secondary_acts=list(data.get("secondary_acts", [])),
            intent_alignment=data.get("intent_alignment", "neutral"),
            tone=data.get("tone", "neutral"),
            stance=data.get("stance", "neutral"),
            reveal_level=data.get("reveal_level", "none"),
            urgency=data.get("urgency", "normal"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class DialogueResponsePlan:
    """Central dialogue plan object.

    Built from the act decision and full turn context.  Contains the
    authoritative reasoning (act, framing, state_drivers, trace) and
    text slots for surface rendering.
    """

    response_id: str = ""
    speaker_id: str = ""
    listener_id: str | None = None
    primary_act: str = "acknowledge"
    secondary_acts: list[str] = field(default_factory=list)
    framing: dict[str, Any] = field(default_factory=dict)
    state_drivers: dict[str, Any] = field(default_factory=dict)
    allowed_topics: list[str] = field(default_factory=list)
    blocked_topics: list[str] = field(default_factory=list)
    hint_targets: list[str] = field(default_factory=list)
    text_slots: dict[str, str] = field(default_factory=dict)
    trace: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DialogueResponsePlan":
        return cls(
            response_id=data.get("response_id", ""),
            speaker_id=data.get("speaker_id", ""),
            listener_id=data.get("listener_id"),
            primary_act=data.get("primary_act", "acknowledge"),
            secondary_acts=list(data.get("secondary_acts", [])),
            framing=dict(data.get("framing", {})),
            state_drivers=dict(data.get("state_drivers", {})),
            allowed_topics=list(data.get("allowed_topics", [])),
            blocked_topics=list(data.get("blocked_topics", [])),
            hint_targets=list(data.get("hint_targets", [])),
            text_slots=dict(data.get("text_slots", {})),
            trace=dict(data.get("trace", {})),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class DialoguePresentation:
    """UI-safe final payload for the player.

    Stripped of internal reasoning — only shows act, tone, stance,
    and the rendered line.
    """

    speaker_id: str = ""
    listener_id: str | None = None
    act: str = "acknowledge"
    tone: str = "neutral"
    stance: str = "neutral"
    summary: str = ""
    line: str = ""
    choices_hint: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DialoguePresentation":
        return cls(
            speaker_id=data.get("speaker_id", ""),
            listener_id=data.get("listener_id"),
            act=data.get("act", "acknowledge"),
            tone=data.get("tone", "neutral"),
            stance=data.get("stance", "neutral"),
            summary=data.get("summary", ""),
            line=data.get("line", ""),
            choices_hint=list(data.get("choices_hint", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class DialogueLogEntry:
    """Entry for memory/journal integration.

    Only produced for structurally meaningful interactions.
    """

    entry_id: str = ""
    tick: int | None = None
    speaker_id: str = ""
    listener_id: str | None = None
    act: str = "acknowledge"
    outcome: str = ""
    summary: str = ""
    line: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DialogueLogEntry":
        return cls(
            entry_id=data.get("entry_id", ""),
            tick=data.get("tick"),
            speaker_id=data.get("speaker_id", ""),
            listener_id=data.get("listener_id"),
            act=data.get("act", "acknowledge"),
            outcome=data.get("outcome", ""),
            summary=data.get("summary", ""),
            line=data.get("line", ""),
            metadata=dict(data.get("metadata", {})),
        )
