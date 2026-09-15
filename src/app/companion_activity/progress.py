"""Progress, blocker and open-loop lifecycle projection for companion activity."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .authority import ActivityAuthoritySource, authority_source_for
from .contracts import EvidenceProposition
from .state import (
    ActivityMeaningfulEvent,
    ActivityOpenLoop,
    ActivityProgressMarker,
    ActivityStateChange,
    ActivityStrategyChange,
    CompanionActivityState,
    OpenLoopStatus,
)

PROGRESS_PREDICATES = frozenset(
    {
        "progress_marker",
        "meaningful_event",
        "blocker",
        "blocker_cleared",
        "open_loop",
        "open_loop_status",
    }
)

_OPEN_LOOP_AUTHORITY_ORDER: tuple[ActivityAuthoritySource, ...] = (
    "user_explicit",
    "deterministic_telemetry",
    "trusted_process_integration",
    "repeated_perception",
    "single_perception",
    "language_inference",
    "imported_unverified",
    "runtime_state",
)


class ActivityProgressReducer:
    def reduce(
        self,
        state: CompanionActivityState,
        propositions: tuple[EvidenceProposition, ...],
        *,
        state_changes: tuple[ActivityStateChange, ...] = (),
        now: datetime,
    ) -> CompanionActivityState:
        markers = list(state.progress_markers)
        events = list(state.recent_meaningful_events)
        strategy_changes = list(state.strategy_changes)
        blockers = list(state.blockers)
        loops = {item.loop_id: item for item in state.open_loops}
        mutated = False

        for change in state_changes:
            if change.field_name != "strategy":
                continue
            strategy_changes.append(
                ActivityStrategyChange(
                    change_id=f"strategy:{change.changed_at.isoformat()}:{change.revision if hasattr(change, 'revision') else len(strategy_changes) + 1}",
                    previous_strategy=change.previous_value,
                    new_strategy=change.new_value,
                    proposition_ids=change.proposition_ids,
                    changed_at=change.changed_at,
                )
            )
            strategy_changes = strategy_changes[-24:]
            mutated = True

        for proposition in propositions:
            if proposition.predicate not in PROGRESS_PREDICATES:
                continue
            if proposition.confidence < 0.55:
                continue
            source = authority_source_for(proposition)
            if proposition.predicate == "progress_marker":
                marker_id, description = _id_and_description(
                    proposition,
                    id_key="marker_id",
                    default_prefix="progress",
                )
                if any(item.marker_id == marker_id for item in markers):
                    continue
                markers.append(
                    ActivityProgressMarker(
                        marker_id=marker_id,
                        description=description,
                        proposition_ids=(proposition.proposition_id,),
                        confidence=proposition.confidence,
                        recorded_at=proposition.observed_at,
                    )
                )
                markers = markers[-64:]
                mutated = True
                continue

            if proposition.predicate == "meaningful_event":
                event_id, description = _id_and_description(
                    proposition,
                    id_key="event_id",
                    default_prefix="event",
                )
                if any(item.event_id == event_id for item in events):
                    continue
                kind = _mapping_value(proposition.value, "kind", "activity")
                events.append(
                    ActivityMeaningfulEvent(
                        event_id=event_id,
                        kind=kind,
                        description=description,
                        proposition_ids=(proposition.proposition_id,),
                        confidence=proposition.confidence,
                        occurred_at=proposition.observed_at,
                    )
                )
                events = events[-32:]
                mutated = True
                continue

            if proposition.predicate == "blocker":
                blocker = _description(proposition.value)
                if blocker and blocker not in blockers:
                    blockers.append(blocker)
                    blockers = blockers[-32:]
                    mutated = True
                continue

            if proposition.predicate == "blocker_cleared":
                blocker = _description(proposition.value)
                if blocker in blockers:
                    blockers.remove(blocker)
                    mutated = True
                continue

            if proposition.predicate == "open_loop":
                proposed = _open_loop_from_proposition(
                    state.activity_id,
                    proposition,
                    source=source,
                )
                current = loops.get(proposed.loop_id)
                if current is None or _open_loop_may_replace(current, proposed):
                    loops[proposed.loop_id] = proposed
                    mutated = True
                continue

            if proposition.predicate == "open_loop_status":
                loop_id = _mapping_value(proposition.value, "loop_id", "")
                status = _mapping_value(proposition.value, "status", "")
                if loop_id not in loops or status not in {
                    "open",
                    "resolved",
                    "abandoned",
                    "superseded",
                }:
                    continue
                current = loops[loop_id]
                if not _status_change_allowed(current.authority_source, source):
                    continue
                next_status: OpenLoopStatus = status  # type: ignore[assignment]
                loops[loop_id] = current.model_copy(
                    update={
                        "status": next_status,
                        "last_referenced_at": now,
                        "resolution_evidence": tuple(
                            sorted(
                                set(current.resolution_evidence)
                                | {proposition.proposition_id}
                            )
                        ),
                    }
                )
                mutated = mutated or next_status != current.status

        if not mutated:
            return state
        return state.model_copy(
            update={
                "revision": state.revision + 1,
                "progress_markers": tuple(markers),
                "recent_meaningful_events": tuple(events),
                "strategy_changes": tuple(strategy_changes),
                "blockers": tuple(blockers),
                "open_loops": tuple(
                    sorted(loops.values(), key=lambda item: (item.opened_at, item.loop_id))
                ),
                "last_meaningful_change_at": now,
            }
        )


def _open_loop_from_proposition(
    activity_id: str,
    proposition: EvidenceProposition,
    *,
    source: ActivityAuthoritySource,
) -> ActivityOpenLoop:
    value = proposition.value
    loop_id = _mapping_value(value, "loop_id", f"loop:{proposition.proposition_id}")
    kind = _mapping_value(value, "kind", "commitment")
    description = _description(value)
    importance = _mapping_float(value, "importance", 0.5)
    blocking = _mapping_bool(value, "blocking", False)
    return ActivityOpenLoop(
        loop_id=loop_id,
        activity_id=activity_id,
        kind=kind,
        description=description,
        created_from=(proposition.proposition_id,),
        authority_source=source,
        confidence=proposition.confidence,
        importance=importance,
        blocking=blocking,
        opened_at=proposition.observed_at,
        last_referenced_at=proposition.observed_at,
    )


def _open_loop_may_replace(current: ActivityOpenLoop, proposed: ActivityOpenLoop) -> bool:
    current_rank = _authority_rank(current.authority_source)
    proposed_rank = _authority_rank(proposed.authority_source)
    if proposed_rank < current_rank:
        return True
    if proposed_rank > current_rank:
        return False
    return proposed.confidence >= current.confidence


def _status_change_allowed(
    current: ActivityAuthoritySource,
    proposed: ActivityAuthoritySource,
) -> bool:
    return _authority_rank(proposed) <= _authority_rank(current)


def _authority_rank(source: ActivityAuthoritySource) -> int:
    try:
        return _OPEN_LOOP_AUTHORITY_ORDER.index(source)
    except ValueError:
        return len(_OPEN_LOOP_AUTHORITY_ORDER) + 100


def _id_and_description(
    proposition: EvidenceProposition,
    *,
    id_key: str,
    default_prefix: str,
) -> tuple[str, str]:
    identifier = _mapping_value(
        proposition.value,
        id_key,
        f"{default_prefix}:{proposition.proposition_id}",
    )
    return identifier, _description(proposition.value)


def _description(value: Any) -> str:
    if isinstance(value, dict):
        candidate = value.get("description") or value.get("text") or value.get("value") or ""
        return " ".join(str(candidate).split())[:1200]
    return " ".join(str(value).split())[:1200]


def _mapping_value(value: Any, key: str, default: str) -> str:
    if not isinstance(value, dict):
        return default
    candidate = str(value.get(key) or "").strip()
    return candidate[:240] or default


def _mapping_float(value: Any, key: str, default: float) -> float:
    if not isinstance(value, dict):
        return default
    try:
        candidate = float(value.get(key, default))
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, candidate))


def _mapping_bool(value: Any, key: str, default: bool) -> bool:
    if not isinstance(value, dict):
        return default
    candidate = value.get(key, default)
    return candidate if isinstance(candidate, bool) else default


__all__ = ["ActivityProgressReducer", "PROGRESS_PREDICATES"]
