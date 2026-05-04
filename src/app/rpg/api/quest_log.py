from __future__ import annotations

from typing import Any, Dict

from app.rpg.session_store import get_session
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.rpg.quest_log.runtime import (
    build_objective_tracker_payload,
    build_quest_log_payload,
    pin_objective,
    unpin_objective,
)

router = APIRouter(prefix="/api/rpg/quest_log", tags=["rpg-quest-log"])


class QuestLogPayloadRequest(BaseModel):
    session_id: str
    limit: int = Field(default=50, ge=0, le=50)


class ObjectiveTrackerRequest(BaseModel):
    session_id: str
    limit: int = Field(default=8, ge=0, le=8)


class ObjectivePinRequest(BaseModel):
    session_id: str
    objective_id: str
    turn_index: int = 0
    reason: str = ""


def _simulation_state_for_session(session_id: str) -> Dict[str, Any]:
    session = get_session(session_id)
    if not isinstance(session, dict):
        raise KeyError(f"session_not_found:{session_id}")
    return session.setdefault("simulation_state", {})


@router.post("/payload")
def quest_log_payload(request: QuestLogPayloadRequest) -> Dict[str, Any]:
    simulation_state = _simulation_state_for_session(request.session_id)
    return build_quest_log_payload(simulation_state, limit=request.limit)


@router.post("/tracker")
def objective_tracker_payload(request: ObjectiveTrackerRequest) -> Dict[str, Any]:
    simulation_state = _simulation_state_for_session(request.session_id)
    return build_objective_tracker_payload(simulation_state, limit=request.limit)


@router.post("/pin")
def pin_quest_log_objective(request: ObjectivePinRequest) -> Dict[str, Any]:
    simulation_state = _simulation_state_for_session(request.session_id)
    result = pin_objective(
        simulation_state,
        request.objective_id,
        turn_index=request.turn_index,
        reason=request.reason or "player_pinned",
    )
    return {
        **result,
        "quest_log": build_quest_log_payload(simulation_state),
        "tracker": build_objective_tracker_payload(simulation_state),
    }


@router.post("/unpin")
def unpin_quest_log_objective(request: ObjectivePinRequest) -> Dict[str, Any]:
    simulation_state = _simulation_state_for_session(request.session_id)
    result = unpin_objective(
        simulation_state,
        request.objective_id,
        turn_index=request.turn_index,
        reason=request.reason or "player_unpinned",
    )
    return {
        **result,
        "quest_log": build_quest_log_payload(simulation_state),
        "tracker": build_objective_tracker_payload(simulation_state),
    }