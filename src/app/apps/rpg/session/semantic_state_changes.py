from __future__ import annotations

import logging

# RPG session runtime responsibility module.
from app.apps.rpg.session.state_normalization import (
    _safe_dict as _safe_dict,
    _safe_int as _safe_int,
    _safe_list as _safe_list,
    _safe_str as _safe_str,
)
from app.apps.rpg.session.world_consequence_runtime import (
    _accepted_state_change_event_ids as _accepted_state_change_event_ids,
    _allowed_semantic_actions as _allowed_semantic_actions,
    _applied_semantic_proposal_ids as _applied_semantic_proposal_ids,
    _ensure_semantic_pipeline_state as _ensure_semantic_pipeline_state,
    _find_actor_state as _find_actor_state,
    _normalize_actor_state_for_delta as _normalize_actor_state_for_delta,
    _normalize_semantic_state_change_proposal as _normalize_semantic_state_change_proposal,
    _safe_actor_states as _safe_actor_states,
    _stable_state_change_event_id as _stable_state_change_event_id,
    _write_actor_states as _write_actor_states,
    clear_recorded_semantic_llm_capture as clear_recorded_semantic_llm_capture,
    emit_scene_beat as emit_scene_beat,
    enqueue_semantic_state_change_proposal as enqueue_semantic_state_change_proposal,
    validate_semantic_state_change_proposal as validate_semantic_state_change_proposal,
)
from app.apps.rpg.session.companion_turn_runtime import (
    _MAX_ACCEPTED_STATE_CHANGE_EVENTS as _MAX_ACCEPTED_STATE_CHANGE_EVENTS,
    _MAX_APPLIED_PROPOSAL_IDS as _MAX_APPLIED_PROPOSAL_IDS,
    _SEMANTIC_LLM_PROPOSAL_COOLDOWN_TICKS as _SEMANTIC_LLM_PROPOSAL_COOLDOWN_TICKS,
)
import json as json
from typing import (
    Any as Any, Dict as Dict, List as List,
)

import re as re


logger = logging.getLogger(__name__)


def compile_semantic_state_change_to_canonical_delta(
    proposal: dict[str, Any],
    simulation_state: dict[str, Any],
    runtime_state: dict[str, Any],
) -> dict[str, Any]:
    proposal = _normalize_semantic_state_change_proposal(proposal)
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)

    actor_states = _safe_actor_states(simulation_state)
    actor = _find_actor_state(actor_states, proposal["actor_id"])
    if not actor:
        raise ValueError(f"compile_missing_actor:{_safe_str(proposal.get('actor_id'))}")
    actor_before = _normalize_actor_state_for_delta(actor)
    delta = dict(_safe_dict(proposal.get("delta")))

    semantic_action = _safe_str(proposal.get("semantic_action"))
    implied = dict(_allowed_semantic_actions().get(semantic_action, {}))
    for key, value in implied.items():
        if not _safe_str(delta.get(key)):
            delta[key] = value

    if proposal["target_location_id"] and not _safe_str(delta.get("location_id")):
        delta["location_id"] = proposal["target_location_id"]

    actor_after = dict(actor_before)
    for key in ("activity", "availability", "location_id", "mood", "intent", "engagement"):
        value = _safe_str(delta.get(key))
        if value:
            actor_after[key] = value
    if actor_after == actor_before:
        raise ValueError(f"empty_compiled_delta:{_safe_str(proposal.get('proposal_id'))}")

    beat_summary = _safe_str(proposal.get("beat_summary"))
    if not beat_summary:
        actor_name = _safe_str(actor_after.get("name")) or _safe_str(actor_before.get("name")) or "Someone"
        if semantic_action == "take_break":
            beat_summary = f"{actor_name} steps away for a short break."
        elif semantic_action == "wash_up":
            beat_summary = f"{actor_name} slips away to wash up."
        elif semantic_action == "rest":
            beat_summary = f"{actor_name} settles in to rest."
        elif semantic_action == "investigate":
            beat_summary = f"{actor_name} begins investigating the situation."
        elif semantic_action == "leave_scene":
            beat_summary = f"{actor_name} leaves the area."
        elif semantic_action == "return_to_scene":
            beat_summary = f"{actor_name} returns to the scene."
        elif semantic_action == "argue":
            beat_summary = f"{actor_name} becomes engaged in a heated exchange."
        elif _safe_str(actor_after.get("activity")) and _safe_str(actor_after.get("activity")) != _safe_str(actor_before.get("activity")):
            beat_summary = f"{actor_name} shifts into {_safe_str(actor_after.get('activity')).replace('_', ' ')}."
        else:
            beat_summary = _safe_str(proposal.get("summary"))

    current_tick = _safe_int(
        simulation_state.get("current_tick")
        or simulation_state.get("tick")
        or runtime_state.get("tick"),
        0,
    )

    canonical_event = {
        "event_id": "",
        "tick": current_tick,
        "proposal_id": _safe_str(proposal.get("proposal_id")),
        "actor_id": _safe_str(proposal.get("actor_id")),
        "semantic_action": semantic_action,
        "location_id": _safe_str(actor_after.get("location_id")),
        "summary": _safe_str(proposal.get("summary")) or beat_summary,
        "before": actor_before,
        "after": actor_after,
        "beat": {
            "summary": beat_summary,
            "priority": int(proposal.get("priority", 50) or 50),
            "recap_level": "notable",
            "tags": ["state_change", semantic_action or "semantic_action"],
        },
    }
    canonical_event["event_id"] = _stable_state_change_event_id(canonical_event)
    assert canonical_event["tick"] == _safe_int(simulation_state.get("tick"), 0)

    logger.debug(
        "DEBUG SEMANTIC EVENT CREATED = %s",
        {
            "event_id": canonical_event.get("event_id"),
            "tick": canonical_event.get("tick"),
            "proposal_id": canonical_event.get("proposal_id"),
            "actor_id": canonical_event.get("actor_id"),
            "summary": canonical_event.get("summary"),
            "location_id": canonical_event.get("location_id"),
        },
    )

    return canonical_event


def _apply_canonical_state_change_event(
    simulation_state: dict[str, Any],
    runtime_state: dict[str, Any],
    event: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)
    event = _safe_dict(event)

    actor_states = _safe_actor_states(simulation_state)
    actor_id = _safe_str(event.get("actor_id"))
    after = _safe_dict(event.get("after"))

    updated = []
    found = False
    for actor in actor_states:
        actor = _safe_dict(actor)
        if _safe_str(actor.get("id")) == actor_id:
            merged = dict(actor)
            for key in ("activity", "availability", "location_id", "mood", "intent", "engagement"):
                value = _safe_str(after.get(key))
                if value:
                    merged[key] = value
            updated.append(merged)
            found = True
        else:
            updated.append(actor)
    if not found:
        raise ValueError(f"state_change_target_actor_missing:{actor_id}")

    simulation_state = _write_actor_states(simulation_state, updated)
    return simulation_state, runtime_state


def _record_accepted_state_change_event(runtime_state: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)
    event = _safe_dict(event)
    accepted = _safe_list(runtime_state.get("accepted_state_change_events"))
    accepted.append(event)
    accepted.sort(
        key=lambda x: (
            int(_safe_dict(x).get("tick", 0) or 0),
            _safe_str(_safe_dict(x).get("event_id")),
        )
    )
    runtime_state["accepted_state_change_events"] = accepted[-_MAX_ACCEPTED_STATE_CHANGE_EVENTS:]
    return runtime_state


def _record_applied_semantic_proposal_id(runtime_state: dict[str, Any], proposal_id: str) -> dict[str, Any]:
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)
    proposal_id = _safe_str(proposal_id)
    if not proposal_id:
        return runtime_state
    items = [x for x in _safe_list(runtime_state.get("applied_semantic_proposal_ids")) if _safe_str(x)]
    items.append(proposal_id)
    deduped = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    runtime_state["applied_semantic_proposal_ids"] = deduped[-_MAX_APPLIED_PROPOSAL_IDS:]
    return runtime_state


def _emit_scene_beat_from_accepted_state_change(runtime_state: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)
    event = _safe_dict(event)
    beat = _safe_dict(event.get("beat"))
    after = _safe_dict(event.get("after"))
    return emit_scene_beat(
        runtime_state,
        tick=int(event.get("tick", 0) or 0),
        summary=_safe_str(beat.get("summary")) or _safe_str(event.get("summary")),
        kind="state_change_beat",
        priority=int(beat.get("priority", 50) or 50),
        scene_id="",
        interaction_id=_safe_str(event.get("proposal_id")),
        actors=[_safe_str(event.get("actor_id"))] if _safe_str(event.get("actor_id")) else [],
        location_id=_safe_str(after.get("location_id")),
        recap_level=_safe_str(beat.get("recap_level")) or "notable",
        tags=[_safe_str(x) for x in _safe_list(beat.get("tags")) if _safe_str(x)],
    )


def process_semantic_state_change_proposals(
    simulation_state: dict[str, Any],
    runtime_state: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:

    from app.apps.rpg.session.combat_intent import (
        _log_interaction_trace as _log_interaction_trace,
    )

    simulation_state = _safe_dict(simulation_state)
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)

    raw_proposals = [
        _normalize_semantic_state_change_proposal(x)
        for x in _safe_list(runtime_state.get("semantic_state_change_proposals"))
    ]
    proposals = []
    seen_proposal_ids = set()
    for proposal in raw_proposals:
        proposal_id = _safe_str(proposal.get("proposal_id"))
        if proposal_id and proposal_id in seen_proposal_ids:
            continue
        if proposal_id:
            seen_proposal_ids.add(proposal_id)
        proposals.append(proposal)

    # Current policy: proposals are processed once per tick and never retried.
    # Invalid proposals are recorded in rejected_state_change_events.
    remaining: list[Any] = []
    accepted_ids = _accepted_state_change_event_ids(runtime_state)
    applied_proposal_ids = _applied_semantic_proposal_ids(runtime_state)

    for proposal in proposals:
        proposal_id = _safe_str(proposal.get("proposal_id"))
        if proposal_id and proposal_id in applied_proposal_ids:
            continue

        validation = validate_semantic_state_change_proposal(proposal, simulation_state, runtime_state)
        if not validation.get("ok"):
            rejected = _safe_list(runtime_state.get("rejected_state_change_events"))
            rejected.append(
                {
                    "proposal_id": _safe_str(proposal.get("proposal_id")),
                    "actor_id": _safe_str(proposal.get("actor_id")),
                    "semantic_action": _safe_str(proposal.get("semantic_action")),
                    "errors": _safe_list(validation.get("errors")),
                    "tick": int(runtime_state.get("tick", 0) or 0),
                }
            )
            runtime_state["rejected_state_change_events"] = rejected[-_MAX_ACCEPTED_STATE_CHANGE_EVENTS:]
            continue

        try:
            event = compile_semantic_state_change_to_canonical_delta(
                proposal,
                simulation_state,
                runtime_state,
            )
        except ValueError as exc:
            rejected = _safe_list(runtime_state.get("rejected_state_change_events"))
            rejected.append(
                {
                    "proposal_id": _safe_str(proposal.get("proposal_id")),
                    "actor_id": _safe_str(proposal.get("actor_id")),
                    "semantic_action": _safe_str(proposal.get("semantic_action")),
                    "errors": [str(exc)],
                    "tick": int(runtime_state.get("tick", 0) or 0),
                }
            )
            runtime_state["rejected_state_change_events"] = rejected[-_MAX_ACCEPTED_STATE_CHANGE_EVENTS:]
            continue
        event_id = _safe_str(event.get("event_id"))
        if event_id and event_id in accepted_ids:
            continue

        simulation_state, runtime_state = _apply_canonical_state_change_event(
            simulation_state,
            runtime_state,
            event,
        )

        logger.debug(
            "DEBUG SEMANTIC EVENT APPEND accepted_state_change_events = %s",
            {
                "existing_count": len(_safe_list(runtime_state.get("accepted_state_change_events"))),
                "event_id": event.get("event_id"),
                "tick": event.get("tick"),
            },
        )

        runtime_state = _record_accepted_state_change_event(runtime_state, event)
        _log_interaction_trace(
            "semantic_accept",
            {
                "tick": _safe_int(event.get("tick"), 0),
                "actor_id": _safe_str(event.get("actor_id")),
                "semantic_action": _safe_str(event.get("semantic_action")),
                "summary": _safe_str(event.get("summary"))[:160],
                "interaction_count": len(_safe_list(simulation_state.get("active_interactions"))),
            },
            runtime_state,
        )
        if event_id:
            accepted_ids.add(event_id)
        runtime_state = _record_applied_semantic_proposal_id(runtime_state, proposal_id)
        applied_proposal_ids = _applied_semantic_proposal_ids(runtime_state)
        runtime_state = _emit_scene_beat_from_accepted_state_change(runtime_state, event)

    runtime_state["semantic_state_change_proposals"] = remaining
    return simulation_state, runtime_state


def llm_semantic_proposal_gateway(
    simulation_state: dict[str, Any],
    runtime_state: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Replay-safe gateway stub.

    Source of truth:
    - live mode: consume proposals already captured into runtime_state["recorded_semantic_llm_proposals"]
    - replay mode: consume the same recorded proposals

    This function MUST NOT call a live provider directly. Any future live LLM
    integration should happen upstream through a recorded nondeterministic
    boundary that persists prompt, raw output, and normalized proposals.
    """
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)
    recorded = _safe_list(runtime_state.get("recorded_semantic_llm_proposals"))
    out: list[dict[str, Any]] = []
    seen = set()
    for item in recorded[:3]:
        proposal = _normalize_semantic_state_change_proposal(_safe_dict(item))
        proposal_id = _safe_str(proposal.get("proposal_id"))
        if proposal_id and proposal_id in seen:
            continue
        if proposal_id:
            seen.add(proposal_id)
        if not proposal.get("actor_id"):
            continue
        out.append(proposal)
    return out


def _should_generate_llm_semantic_proposals(
    simulation_state: dict[str, Any],
    runtime_state: dict[str, Any],
) -> bool:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)
    # Keep activity generation alive at a low rate even if a small number of
    # queued proposals already exist.
    if len(_safe_list(runtime_state.get("semantic_state_change_proposals"))) > 2:
        return False
    if _safe_list(runtime_state.get("recorded_semantic_llm_proposals")):
        return True

    # Active interactions are explicitly allowed. NPCs should remain visibly
    # active during them, and the LLM proposal layer should be able to describe
    # that bounded behavior.
    actor_states = _safe_actor_states(simulation_state)
    if not actor_states:
        return False
    tick = _safe_int(runtime_state.get("tick", 0), 0)
    last_tick = _safe_int(runtime_state.get("last_semantic_llm_tick", -999999), -999999)
    return (tick - last_tick) >= _SEMANTIC_LLM_PROPOSAL_COOLDOWN_TICKS


def maybe_enqueue_llm_semantic_state_change_proposals(
    simulation_state: dict[str, Any],
    runtime_state: dict[str, Any],
) -> dict[str, Any]:

    simulation_state = _safe_dict(simulation_state)
    runtime_state = _ensure_semantic_pipeline_state(runtime_state)
    if not _should_generate_llm_semantic_proposals(simulation_state, runtime_state):
        return runtime_state
    proposals = llm_semantic_proposal_gateway(simulation_state, runtime_state)
    consumed_any = False
    for proposal in proposals:
        runtime_state = enqueue_semantic_state_change_proposal(runtime_state, proposal)
        consumed_any = True
    # Consume recorded proposals exactly once.
    if _safe_list(runtime_state.get("recorded_semantic_llm_proposals")):
        runtime_state = clear_recorded_semantic_llm_capture(runtime_state)
        consumed_any = True

    if consumed_any:
        runtime_state["last_semantic_llm_tick"] = _safe_int(runtime_state.get("tick", 0), 0)
    return runtime_state


__all__ = [
    "_MAX_ACCEPTED_STATE_CHANGE_EVENTS",
    "_MAX_APPLIED_PROPOSAL_IDS",
    "_SEMANTIC_LLM_PROPOSAL_COOLDOWN_TICKS",
    "_apply_canonical_state_change_event",
    "_emit_scene_beat_from_accepted_state_change",
    "_record_accepted_state_change_event",
    "_record_applied_semantic_proposal_id",
    "_should_generate_llm_semantic_proposals",
    "compile_semantic_state_change_to_canonical_delta",
    "llm_semantic_proposal_gateway",
    "maybe_enqueue_llm_semantic_state_change_proposals",
    "process_semantic_state_change_proposals",
]
