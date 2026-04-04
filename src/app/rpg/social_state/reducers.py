"""Phase 7.6 — Social State Reducers.

Deterministic reducers from existing event types into persistent social state.
Effects are conservative — small deltas per event.
"""

from __future__ import annotations

from typing import Any


def _get_event_type(event: Any) -> str:
    """Extract event type from an event dict or object."""
    if isinstance(event, dict):
        return event.get("type", "")
    return getattr(event, "type", "")


def _get_payload(event: Any) -> dict:
    """Extract payload from an event dict or object."""
    if isinstance(event, dict):
        return dict(event.get("payload", {}))
    return dict(getattr(event, "payload", {}))


def _get_event_id(event: Any) -> str | None:
    """Extract event id if available."""
    if isinstance(event, dict):
        return event.get("event_id") or event.get("id")
    return getattr(event, "event_id", None) or getattr(event, "id", None)


def reduce_npc_response_agreed(core: Any, event: Any) -> None:
    """NPC agreed — increase trust/respect, improve reputation."""
    payload = _get_payload(event)
    event_id = _get_event_id(event)
    npc_id = payload.get("npc_id", "unknown")
    target_id = payload.get("target_id") or payload.get("player_id") or "player"

    core.relationship_tracker.adjust(
        core.state, npc_id, target_id,
        trust=0.1, respect=0.05,
        event_id=event_id,
    )
    core.reputation_graph.adjust_score(
        core.state, target_id, npc_id,
        delta=0.1, event_id=event_id,
    )


def reduce_npc_response_refused(core: Any, event: Any) -> None:
    """NPC refused — decrease trust slightly, increase hostility slightly."""
    payload = _get_payload(event)
    event_id = _get_event_id(event)
    npc_id = payload.get("npc_id", "unknown")
    target_id = payload.get("target_id") or payload.get("player_id") or "player"

    core.relationship_tracker.adjust(
        core.state, npc_id, target_id,
        trust=-0.05, hostility=0.05,
        event_id=event_id,
    )


def reduce_npc_response_delayed(core: Any, event: Any) -> None:
    """NPC delayed — minor metadata trace, no significant social change."""
    payload = _get_payload(event)
    event_id = _get_event_id(event)
    npc_id = payload.get("npc_id", "unknown")
    target_id = payload.get("target_id") or payload.get("player_id") or "player"

    core.relationship_tracker.adjust(
        core.state, npc_id, target_id,
        event_id=event_id,
        metadata={"delayed": True},
    )


def reduce_npc_response_threatened(core: Any, event: Any) -> None:
    """NPC threatened — increase fear and hostility, worsen reputation."""
    payload = _get_payload(event)
    event_id = _get_event_id(event)
    npc_id = payload.get("npc_id", "unknown")
    target_id = payload.get("target_id") or payload.get("player_id") or "player"

    core.relationship_tracker.adjust(
        core.state, npc_id, target_id,
        fear=0.15, hostility=0.15,
        event_id=event_id,
    )
    core.reputation_graph.adjust_score(
        core.state, target_id, npc_id,
        delta=-0.15, event_id=event_id,
    )


def reduce_npc_response_redirected(core: Any, event: Any) -> None:
    """NPC redirected — minor trust change only."""
    payload = _get_payload(event)
    event_id = _get_event_id(event)
    npc_id = payload.get("npc_id", "unknown")
    target_id = payload.get("target_id") or payload.get("player_id") or "player"

    core.relationship_tracker.adjust(
        core.state, npc_id, target_id,
        trust=-0.02,
        event_id=event_id,
    )


def reduce_npc_secondary_supported(core: Any, event: Any) -> None:
    """Secondary NPC supported — improve alliance strength."""
    payload = _get_payload(event)
    event_id = _get_event_id(event)
    npc_id = payload.get("npc_id", "unknown")
    primary_npc_id = payload.get("primary_npc_id") or payload.get("target_id") or "player"

    core.alliance_tracker.adjust_strength(
        core.state, npc_id, primary_npc_id,
        delta=0.1, event_id=event_id,
    )


def reduce_npc_secondary_opposed(core: Any, event: Any) -> None:
    """Secondary NPC opposed — worsen alliance strength."""
    payload = _get_payload(event)
    event_id = _get_event_id(event)
    npc_id = payload.get("npc_id", "unknown")
    primary_npc_id = payload.get("primary_npc_id") or payload.get("target_id") or "player"

    core.alliance_tracker.adjust_strength(
        core.state, npc_id, primary_npc_id,
        delta=-0.1, event_id=event_id,
    )
    core.relationship_tracker.adjust(
        core.state, npc_id, primary_npc_id,
        hostility=0.05,
        event_id=event_id,
    )


def reduce_rumor_seeded(core: Any, event: Any) -> None:
    """Rumor seeded — create rumor record in RumorLog."""
    payload = _get_payload(event)
    event_id = _get_event_id(event)

    rumor_id = payload.get("rumor_id", f"rumor:{event_id or 'unknown'}")
    core.rumor_log.seed_rumor(
        core.state,
        rumor_id=rumor_id,
        source_npc_id=payload.get("source_npc_id"),
        subject_id=payload.get("subject_id"),
        rumor_type=payload.get("rumor_type", "general"),
        summary=payload.get("summary", ""),
        location=payload.get("location"),
        event_id=event_id,
        metadata=payload.get("metadata"),
    )


def reduce_action_blocked(core: Any, event: Any) -> None:
    """Action blocked — no social change, metadata trace only."""
    pass


# Dispatch table mapping event types to reducers
_REDUCER_MAP: dict[str, Any] = {
    "npc_response_agreed": reduce_npc_response_agreed,
    "npc_response_refused": reduce_npc_response_refused,
    "npc_response_delayed": reduce_npc_response_delayed,
    "npc_response_threatened": reduce_npc_response_threatened,
    "npc_response_redirected": reduce_npc_response_redirected,
    "npc_secondary_supported": reduce_npc_secondary_supported,
    "npc_secondary_opposed": reduce_npc_secondary_opposed,
    "rumor_seeded": reduce_rumor_seeded,
    "action_blocked": reduce_action_blocked,
}


def reduce_event(core: Any, event: Any) -> None:
    """Route an event to the appropriate social state reducer."""
    event_type = _get_event_type(event)
    reducer = _REDUCER_MAP.get(event_type)
    if reducer is not None:
        reducer(core, event)
