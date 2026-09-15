"""Revisable current-state projection for continuous companion activity."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from .authority import ActivityAuthoritySource
from .contracts import FrozenContract


class ActivityField(FrozenContract):
    value: Any
    authority_source: ActivityAuthoritySource
    confidence: float = Field(ge=0.0, le=1.0)
    proposition_ids: tuple[str, ...] = ()
    stable_since: datetime
    updated_at: datetime
    revision: int = Field(default=1, ge=1)
    last_transition_reason: str = Field(min_length=1, max_length=240)


class ActivityTransitionCandidate(FrozenContract):
    field_name: str = Field(min_length=1, max_length=160)
    value: Any
    authority_source: ActivityAuthoritySource
    confidence: float = Field(ge=0.0, le=1.0)
    proposition_ids: tuple[str, ...] = ()
    first_seen_at: datetime
    last_seen_at: datetime
    confirmation_count: int = Field(default=1, ge=1)


class ActivityStateChange(FrozenContract):
    field_name: str
    previous_value: Any | None = None
    new_value: Any
    authority_source: ActivityAuthoritySource
    proposition_ids: tuple[str, ...] = ()
    reason: str
    changed_at: datetime


class CompanionActivityState(FrozenContract):
    """Derived, revisable state. Evidence remains authoritative outside this object."""

    activity_id: str = Field(min_length=1, max_length=200)
    session_id: str = Field(min_length=1, max_length=200)
    character_id: str | None = Field(default=None, max_length=200)
    revision: int = Field(default=0, ge=0)
    generation: str | None = Field(default=None, max_length=160)
    fields: dict[str, ActivityField] = Field(default_factory=dict)
    pending_transitions: tuple[ActivityTransitionCandidate, ...] = ()
    started_at: datetime
    last_meaningful_change_at: datetime

    def field(self, name: str) -> ActivityField | None:
        return self.fields.get(name)


class ActivityReductionResult(FrozenContract):
    state: CompanionActivityState
    changes: tuple[ActivityStateChange, ...] = ()
    ignored_proposition_ids: tuple[str, ...] = ()


def empty_activity_state(
    *,
    activity_id: str,
    session_id: str,
    started_at: datetime,
    character_id: str | None = None,
    generation: str | None = None,
) -> CompanionActivityState:
    return CompanionActivityState(
        activity_id=activity_id,
        session_id=session_id,
        character_id=character_id,
        generation=generation,
        started_at=started_at,
        last_meaningful_change_at=started_at,
    )


__all__ = [
    "ActivityField",
    "ActivityReductionResult",
    "ActivityStateChange",
    "ActivityTransitionCandidate",
    "CompanionActivityState",
    "empty_activity_state",
]
