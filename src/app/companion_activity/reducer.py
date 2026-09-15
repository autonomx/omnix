"""Deterministic reducer from evidence propositions to revisable activity state."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from .authority import (
    ActivityAuthoritySource,
    ActivityFieldPolicy,
    activity_field_policy,
    authority_source_for,
)
from .contracts import EvidenceProposition
from .state import (
    ActivityField,
    ActivityReductionResult,
    ActivityStateChange,
    CompanionActivityState,
)


class ActivityReducer:
    """Apply predicate-specific authority without letting producers mutate state directly."""

    def reduce(
        self,
        state: CompanionActivityState,
        propositions: tuple[EvidenceProposition, ...],
        *,
        now: datetime,
    ) -> ActivityReductionResult:
        fields = dict(state.fields)
        changes: list[ActivityStateChange] = []
        ignored: list[str] = []
        repeated = Counter(
            (item.predicate, _value_key(item.value))
            for item in propositions
            if item.source_kind == "external"
        )
        grouped: dict[str, list[tuple[EvidenceProposition, ActivityAuthoritySource]]] = {}
        for proposition in propositions:
            policy = activity_field_policy(proposition.predicate)
            if policy is None or not self._valid_now(proposition, now):
                ignored.append(proposition.proposition_id)
                continue
            source = authority_source_for(
                proposition,
                repeated_perception=(
                    proposition.source_kind == "external"
                    and repeated[(proposition.predicate, _value_key(proposition.value))] > 1
                ),
            )
            if not policy.source_allowed(source):
                ignored.append(proposition.proposition_id)
                continue
            grouped.setdefault(proposition.predicate, []).append((proposition, source))

        for field_name, candidates in grouped.items():
            policy = activity_field_policy(field_name)
            assert policy is not None
            selected, source = self._select_candidate(policy, candidates)
            current = fields.get(field_name)
            if current is not None and not self._may_replace(policy, current, selected, source):
                ignored.extend(
                    item.proposition_id
                    for item, _candidate_source in candidates
                    if item.proposition_id != selected.proposition_id
                )
                ignored.append(selected.proposition_id)
                continue

            proposition_ids = tuple(
                sorted(
                    item.proposition_id
                    for item, item_source in candidates
                    if item_source == source and _value_key(item.value) == _value_key(selected.value)
                )
            )
            if current is not None and _value_key(current.value) == _value_key(selected.value):
                fields[field_name] = ActivityField(
                    value=selected.value,
                    authority_source=source,
                    confidence=max(current.confidence, selected.confidence),
                    proposition_ids=tuple(sorted(set(current.proposition_ids) | set(proposition_ids))),
                    stable_since=current.stable_since,
                    updated_at=now,
                    revision=current.revision,
                    last_transition_reason=current.last_transition_reason,
                )
                continue

            reason = self._transition_reason(policy, current, source)
            fields[field_name] = ActivityField(
                value=selected.value,
                authority_source=source,
                confidence=selected.confidence,
                proposition_ids=proposition_ids,
                stable_since=now,
                updated_at=now,
                revision=(current.revision + 1) if current else 1,
                last_transition_reason=reason,
            )
            changes.append(
                ActivityStateChange(
                    field_name=field_name,
                    previous_value=current.value if current else None,
                    new_value=selected.value,
                    authority_source=source,
                    proposition_ids=proposition_ids,
                    reason=reason,
                    changed_at=now,
                )
            )

        if not changes and fields == state.fields:
            return ActivityReductionResult(
                state=state,
                ignored_proposition_ids=tuple(dict.fromkeys(ignored)),
            )
        generation = next(
            (item.generation for item in reversed(propositions) if item.generation),
            state.generation,
        )
        next_state = state.model_copy(
            update={
                "fields": fields,
                "revision": state.revision + (1 if changes else 0),
                "generation": generation,
                "last_meaningful_change_at": now if changes else state.last_meaningful_change_at,
            }
        )
        return ActivityReductionResult(
            state=next_state,
            changes=tuple(changes),
            ignored_proposition_ids=tuple(dict.fromkeys(ignored)),
        )

    @staticmethod
    def _valid_now(proposition: EvidenceProposition, now: datetime) -> bool:
        if proposition.valid_from and now < proposition.valid_from:
            return False
        return not proposition.valid_until or now <= proposition.valid_until

    @staticmethod
    def _select_candidate(
        policy: ActivityFieldPolicy,
        candidates: list[tuple[EvidenceProposition, ActivityAuthoritySource]],
    ) -> tuple[EvidenceProposition, ActivityAuthoritySource]:
        def key(item: tuple[EvidenceProposition, ActivityAuthoritySource]) -> tuple[Any, ...]:
            proposition, source = item
            value_component: float = 0.0
            if policy.conflict_policy == "highest_count":
                value_component = _numeric_value(proposition.value)
            return (
                -policy.authority_rank(source),
                value_component,
                proposition.confidence,
                proposition.observed_at.timestamp(),
                proposition.proposition_id,
            )

        return max(candidates, key=key)

    @staticmethod
    def _may_replace(
        policy: ActivityFieldPolicy,
        current: ActivityField,
        proposition: EvidenceProposition,
        source: ActivityAuthoritySource,
    ) -> bool:
        if _value_key(current.value) == _value_key(proposition.value):
            return True
        new_rank = policy.authority_rank(source)
        current_rank = policy.authority_rank(current.authority_source)
        if new_rank < current_rank:
            return True
        if new_rank > current_rank:
            return False
        if policy.conflict_policy == "highest_count":
            return _numeric_value(proposition.value) >= _numeric_value(current.value)
        if policy.conflict_policy == "newest_within_authority":
            return True
        return proposition.confidence >= current.confidence

    @staticmethod
    def _transition_reason(
        policy: ActivityFieldPolicy,
        current: ActivityField | None,
        source: ActivityAuthoritySource,
    ) -> str:
        if current is None:
            return f"field_initialized:{source}"
        if policy.authority_rank(source) < policy.authority_rank(current.authority_source):
            return f"higher_field_authority:{source}"
        return f"same_authority_revision:{source}"


def _value_key(value: Any) -> str:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return repr(value)
    return repr(value)


def _numeric_value(value: Any) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return float("-inf")


__all__ = ["ActivityReducer"]
