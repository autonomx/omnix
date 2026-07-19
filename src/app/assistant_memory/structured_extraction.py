"""Structured post-turn memory proposals with deterministic validation."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import MemoryCategory, MemoryKind, MemoryScope
from .typed_memory import validate_typed_payload

ClaimType = Literal["explicit_command", "user_asserted", "repeated_observation", "assistant_inference"]

_SECRET_TERMS = {
    "password",
    "secret",
    "api key",
    "access token",
    "refresh token",
    "private key",
    "credential",
}
_EXTERNAL_MARKERS = {
    "http://",
    "https://",
    "context retrieved for this turn",
    "ignore previous",
    "system prompt",
    "developer message",
}
_WEEKDAY_MAP = {
    "monday": "MO",
    "tuesday": "TU",
    "wednesday": "WE",
    "thursday": "TH",
    "friday": "FR",
    "saturday": "SA",
    "sunday": "SU",
}


class StructuredMemoryProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: MemoryKind
    claim_type: ClaimType
    scope: MemoryScope = "global"
    category: MemoryCategory
    content: str = Field(min_length=1, max_length=4096)
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_message_ids: list[str] = Field(default_factory=list, max_length=64)
    contradiction_key: str | None = Field(default=None, max_length=200)


def _normalize_text(content: str) -> str:
    return " ".join(content.strip().split())


def _parse_time(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip().lower().replace(" ", "")
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(am|pm)?", value)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3)
    if minute > 59 or hour > (12 if meridiem else 23) or hour == 0 and meridiem:
        return None
    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}"


def _days(text: str) -> list[str]:
    lowered = text.casefold()
    if "weekday" in lowered:
        return ["MO", "TU", "WE", "TH", "FR"]
    result = [code for name, code in _WEEKDAY_MAP.items() if name in lowered]
    return result


def _proposal(
    *,
    kind: MemoryKind,
    category: MemoryCategory,
    content: str,
    payload: dict[str, Any] | None,
    confidence: float,
    message_id: str,
    contradiction_key: str | None = None,
    claim_type: ClaimType = "user_asserted",
) -> StructuredMemoryProposal:
    validated = validate_typed_payload(kind, payload)
    return StructuredMemoryProposal(
        kind=kind,
        claim_type=claim_type,
        category=category,
        content=content,
        payload=validated,
        confidence=confidence,
        evidence_message_ids=[message_id] if message_id else [],
        contradiction_key=contradiction_key,
    )


def extract_structured_memory_proposals(
    content: str,
    *,
    source_message_id: str,
) -> tuple[list[StructuredMemoryProposal], list[str]]:
    """Extract conservative durable proposals from one user-authored turn."""

    text = _normalize_text(content)
    lowered = text.casefold()
    if not text:
        return [], ["empty_message"]
    if any(marker in lowered for marker in _EXTERNAL_MARKERS):
        return [], ["external_or_instructional_content"]
    if any(term in lowered for term in _SECRET_TERMS):
        return [], ["sensitive_content"]

    proposals: list[StructuredMemoryProposal] = []

    explicit = re.match(r"^(?:remember that|please remember that)\s+(.+)$", text, re.I)
    if explicit:
        value = explicit.group(1).strip()
        proposals.append(
            _proposal(
                kind="semantic_fact",
                category="fact",
                content=value,
                payload={},
                confidence=1.0,
                message_id=source_message_id,
                claim_type="explicit_command",
            )
        )
        return proposals, []

    preference = re.match(r"^(?:i\s+(?:really\s+)?prefer|i\s+like)\s+(.+)$", text, re.I)
    if preference:
        proposals.append(
            _proposal(
                kind="preference",
                category="preference",
                content=f"The user prefers {preference.group(1).strip()}",
                payload={},
                confidence=0.95,
                message_id=source_message_id,
            )
        )

    instruction = re.match(r"^(?:always|please\s+always)\s+(.+)$", text, re.I)
    if instruction:
        proposals.append(
            _proposal(
                kind="instruction",
                category="instruction",
                content=instruction.group(1).strip(),
                payload={},
                confidence=0.95,
                message_id=source_message_id,
            )
        )

    routine = re.match(
        r"^i\s+(?:normally|usually|typically|generally)\s+(.+?)(?:\s+(?:at|around|by)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?))?(?:\s+(.*))?$",
        text,
        re.I,
    )
    if routine:
        activity = routine.group(1).strip().rstrip(".")
        time_value = _parse_time(routine.group(2))
        suffix = routine.group(3) or ""
        payload: dict[str, Any] = {
            "activity": activity.casefold().replace(" ", "_"),
            "days": _days(text),
            "evidence_count": 1,
        }
        if time_value:
            payload["start_time"] = time_value
        proposals.append(
            _proposal(
                kind="routine",
                category="fact",
                content=f"The user usually {activity}",
                payload=payload,
                confidence=0.9,
                message_id=source_message_id,
                contradiction_key=f"routine:{payload['activity']}",
            )
        )

    changed_routine = re.match(r"^i\s+(?:now|no longer)\s+(.+)$", text, re.I)
    if changed_routine:
        activity = changed_routine.group(1).strip().rstrip(".")
        payload = {
            "activity": "current_routine",
            "days": _days(text),
            "evidence_count": 1,
        }
        proposals.append(
            _proposal(
                kind="routine",
                category="fact",
                content=f"The user now {activity}",
                payload=payload,
                confidence=0.85,
                message_id=source_message_id,
                contradiction_key="routine:current_routine",
            )
        )

    goal = re.match(r"^i(?:'m| am)\s+(?:trying|planning|hoping)\s+to\s+(.+)$", text, re.I)
    if goal:
        target = goal.group(1).strip().rstrip(".")
        proposals.append(
            _proposal(
                kind="goal",
                category="project",
                content=f"The user is trying to {target}",
                payload={"state": "active", "priority": 50},
                confidence=0.9,
                message_id=source_message_id,
                contradiction_key=f"goal:{target.casefold()[:120]}",
            )
        )

    open_loop = re.match(r"^i\s+(?:need|have)\s+to\s+(.+)$", text, re.I)
    if open_loop:
        action = open_loop.group(1).strip().rstrip(".")
        proposals.append(
            _proposal(
                kind="open_loop",
                category="project",
                content=f"The user needs to {action}",
                payload={"state": "open"},
                confidence=0.85,
                message_id=source_message_id,
                contradiction_key=f"open-loop:{action.casefold()[:110]}",
            )
        )

    relationship = re.match(r"^(.{1,80}?)\s+is\s+my\s+(.{2,120})$", text, re.I)
    if relationship:
        proposals.append(
            _proposal(
                kind="relationship_state",
                category="relationship",
                content=f"{relationship.group(1).strip()} is the user's {relationship.group(2).strip()}",
                payload={},
                confidence=0.9,
                message_id=source_message_id,
                contradiction_key=f"relationship:{relationship.group(1).casefold().strip()}",
            )
        )

    temporal = re.match(r"^my\s+(.{2,80}?)\s+is\s+(.{2,240})$", text, re.I)
    if temporal:
        proposals.append(
            _proposal(
                kind="semantic_fact",
                category="fact",
                content=f"The user's {temporal.group(1).strip()} is {temporal.group(2).strip()}",
                payload={},
                confidence=0.9,
                message_id=source_message_id,
                contradiction_key=f"fact:{temporal.group(1).casefold().strip()}",
            )
        )

    if not proposals:
        return [], ["no_durable_candidate"]

    unique: dict[tuple[str, str], StructuredMemoryProposal] = {}
    for item in proposals:
        unique[(item.kind, item.content.casefold())] = item
    return list(unique.values()), []


__all__ = [
    "ClaimType",
    "StructuredMemoryProposal",
    "extract_structured_memory_proposals",
]
