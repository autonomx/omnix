"""Composition boundary for deterministic Companion Activity state reduction."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .authority import activity_field_policy
from .contracts import EvidenceProposition, FrozenContract
from .progress import ActivityProgressReducer, PROGRESS_PREDICATES
from .reducer import ActivityReducer
from .state import ActivityStateChange, CompanionActivityState


class ActivityRuntimeResult(FrozenContract):
    state: CompanionActivityState
    changes: tuple[ActivityStateChange, ...] = ()
    ignored_proposition_ids: tuple[str, ...] = ()
    processed_proposition_ids: tuple[str, ...] = Field(default=(), max_length=512)


class CompanionActivityRuntime:
    """Reduce evidence into one replayable, revisable current activity projection."""

    def __init__(
        self,
        *,
        field_reducer: ActivityReducer | None = None,
        progress_reducer: ActivityProgressReducer | None = None,
    ) -> None:
        self._field_reducer = field_reducer or ActivityReducer()
        self._progress_reducer = progress_reducer or ActivityProgressReducer()

    def reduce(
        self,
        state: CompanionActivityState,
        propositions: tuple[EvidenceProposition, ...],
        *,
        now: datetime,
    ) -> ActivityRuntimeResult:
        field_propositions = tuple(
            item for item in propositions if activity_field_policy(item.predicate) is not None
        )
        progress_propositions = tuple(
            item for item in propositions if item.predicate in PROGRESS_PREDICATES
        )
        recognized = {
            item.proposition_id for item in (*field_propositions, *progress_propositions)
        }
        unknown = [
            item.proposition_id
            for item in propositions
            if item.proposition_id not in recognized
        ]
        field_result = self._field_reducer.reduce(
            state,
            field_propositions,
            now=now,
        )
        next_state = self._progress_reducer.reduce(
            field_result.state,
            progress_propositions,
            state_changes=field_result.changes,
            now=now,
        )
        if next_state != state and next_state.revision != state.revision + 1:
            next_state = next_state.model_copy(update={"revision": state.revision + 1})
        return ActivityRuntimeResult(
            state=next_state,
            changes=field_result.changes,
            ignored_proposition_ids=tuple(
                dict.fromkeys((*field_result.ignored_proposition_ids, *unknown))
            ),
            processed_proposition_ids=tuple(
                item.proposition_id
                for item in propositions
                if item.proposition_id not in unknown
            ),
        )


__all__ = ["ActivityRuntimeResult", "CompanionActivityRuntime"]
