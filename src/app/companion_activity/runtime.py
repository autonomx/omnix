"""Composition boundary for deterministic Companion Activity state reduction."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .authority import activity_field_policy
from .contracts import EvidenceProposition, FrozenContract
from .progress import PROGRESS_PREDICATES, ActivityProgressReducer
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
        eligible, generation_ignored, incoming_generation = _generation_filter(
            state,
            propositions,
        )
        field_propositions = tuple(
            item for item in eligible if activity_field_policy(item.predicate) is not None
        )
        progress_propositions = tuple(
            item for item in eligible if item.predicate in PROGRESS_PREDICATES
        )
        recognized = {
            item.proposition_id for item in (*field_propositions, *progress_propositions)
        }
        unknown = [
            item.proposition_id
            for item in eligible
            if item.proposition_id not in recognized
        ]

        field_result = self._field_reducer.reduce(
            state,
            field_propositions,
            now=now,
        )
        progress_result = self._progress_reducer.reduce(
            field_result.state,
            progress_propositions,
            state_changes=field_result.changes,
            now=now,
        )
        next_state = progress_result.state
        if incoming_generation is not None and next_state.generation is None:
            next_state = next_state.model_copy(update={"generation": incoming_generation})
        if next_state != state and next_state.revision != state.revision + 1:
            next_state = next_state.model_copy(update={"revision": state.revision + 1})

        field_ignored = set(field_result.ignored_proposition_ids)
        field_processed = tuple(
            item.proposition_id
            for item in field_propositions
            if item.proposition_id not in field_ignored
        )
        ignored = tuple(
            dict.fromkeys(
                (
                    *generation_ignored,
                    *field_result.ignored_proposition_ids,
                    *progress_result.ignored_proposition_ids,
                    *unknown,
                )
            )
        )
        processed = tuple(
            dict.fromkeys(
                (*field_processed, *progress_result.processed_proposition_ids)
            )
        )
        return ActivityRuntimeResult(
            state=next_state,
            changes=field_result.changes,
            ignored_proposition_ids=ignored,
            processed_proposition_ids=processed,
        )


def _generation_filter(
    state: CompanionActivityState,
    propositions: tuple[EvidenceProposition, ...],
) -> tuple[tuple[EvidenceProposition, ...], tuple[str, ...], str | None]:
    """Reject stale/mixed tagged generations before any reducer can mutate state."""

    if state.generation is not None:
        eligible = tuple(
            item
            for item in propositions
            if item.generation is None or item.generation == state.generation
        )
        ignored = tuple(
            item.proposition_id
            for item in propositions
            if item.generation is not None and item.generation != state.generation
        )
        return eligible, ignored, state.generation

    generations = tuple(
        dict.fromkeys(item.generation for item in propositions if item.generation is not None)
    )
    if len(generations) <= 1:
        return propositions, (), generations[0] if generations else None

    eligible = tuple(item for item in propositions if item.generation is None)
    ignored = tuple(
        item.proposition_id for item in propositions if item.generation is not None
    )
    return eligible, ignored, None


__all__ = ["ActivityRuntimeResult", "CompanionActivityRuntime"]
