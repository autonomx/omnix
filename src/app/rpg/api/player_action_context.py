from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.rpg.player_action_context.runtime import build_player_action_context
from app.rpg.session.service import load_session

router = APIRouter(prefix="/api/rpg/player_action_context", tags=["rpg-player-action-context"])


class PlayerActionContextRequest(BaseModel):
    session_id: str
    turn_index: int = 0
    limit: int = Field(default=12, ge=0, le=12)


def _simulation_state_for_session(session_id: str) -> Dict[str, Any]:
    session = load_session(session_id)
    if not isinstance(session, dict):
        raise KeyError(f"session_not_found:{session_id}")
    return session.setdefault("simulation_state", {})


@router.post("/payload")
def player_action_context_payload(request: PlayerActionContextRequest) -> Dict[str, Any]:
    simulation_state = _simulation_state_for_session(request.session_id)
    return build_player_action_context(
        simulation_state,
        turn_index=request.turn_index,
        limit=request.limit,
    )
