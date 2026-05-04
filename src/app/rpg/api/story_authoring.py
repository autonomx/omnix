from __future__ import annotations

from typing import Any, Dict

from app.rpg.session_store import get_session
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.rpg.story_authoring.approval import (
    approve_story_proposal,
    draft_story_proposal_for_approval,
    list_pending_story_proposals,
    reject_story_proposal,
)
from app.rpg.story_authoring.inspector import (
    approve_story_authoring_inspector_proposal,
    build_story_authoring_inspector_payload,
    draft_story_authoring_inspector_proposal,
    reject_story_authoring_inspector_proposal,
)
from app.rpg.story_packs.activation import (
    activate_story_pack,
    build_story_pack_activation_snapshot,
    deactivate_story_pack,
)
from app.shared import get_provider

router = APIRouter(prefix="/api/rpg/story_authoring", tags=["rpg-story-authoring"])


class StoryAuthoringDraftRequest(BaseModel):
    session_id: str
    authoring_goal: str
    turn_index: int = 0
    repair_once: bool = False
    llm_text_override: Any | None = None


class StoryAuthoringListRequest(BaseModel):
    session_id: str
    limit: int = Field(default=20, ge=0, le=50)


class StoryAuthoringApprovalRequest(BaseModel):
    session_id: str
    pending_id: str
    turn_index: int = 0
    reason: str = ""
    auto_activate: bool = False


class StoryPackActivationRequest(BaseModel):
    session_id: str
    pack_id: str
    turn_index: int = 0
    reason: str = ""


class StoryPackActivationListRequest(BaseModel):
    session_id: str
    limit: int = Field(default=20, ge=0, le=50)


class _AppContext:
    def get_provider(self):
        return get_provider()


def _simulation_state_for_session(session_id: str) -> Dict[str, Any]:
    session = get_session(session_id)
    if not isinstance(session, dict):
        raise KeyError(f"session_not_found:{session_id}")
    simulation_state = session.setdefault("simulation_state", {})
    return simulation_state


@router.post("/draft")
def draft_story_authoring_proposal(request: StoryAuthoringDraftRequest) -> Dict[str, Any]:
    simulation_state = _simulation_state_for_session(request.session_id)
    result = draft_story_proposal_for_approval(
        simulation_state,
        authoring_goal=request.authoring_goal,
        app_context=_AppContext(),
        turn_index=request.turn_index,
        llm_text_override=request.llm_text_override,
        repair_once=request.repair_once,
    )
    return result


@router.post("/pending")
def pending_story_authoring_proposals(request: StoryAuthoringListRequest) -> Dict[str, Any]:
    simulation_state = _simulation_state_for_session(request.session_id)
    return list_pending_story_proposals(simulation_state, limit=request.limit)


@router.post("/inspector")
def story_authoring_inspector(request: StoryAuthoringListRequest) -> Dict[str, Any]:
    simulation_state = _simulation_state_for_session(request.session_id)
    return build_story_authoring_inspector_payload(simulation_state, limit=request.limit)


@router.post("/inspector/draft")
def draft_story_authoring_inspector(request: StoryAuthoringDraftRequest) -> Dict[str, Any]:
    simulation_state = _simulation_state_for_session(request.session_id)
    return draft_story_authoring_inspector_proposal(
        simulation_state,
        authoring_goal=request.authoring_goal,
        app_context=_AppContext(),
        turn_index=request.turn_index,
        llm_text_override=request.llm_text_override,
        repair_once=request.repair_once,
    )


@router.post("/inspector/approve")
def approve_story_authoring_inspector(request: StoryAuthoringApprovalRequest) -> Dict[str, Any]:
    simulation_state = _simulation_state_for_session(request.session_id)
    return approve_story_authoring_inspector_proposal(
        simulation_state,
        pending_id=request.pending_id,
        turn_index=request.turn_index,
        reason=request.reason or "gm_approved",
        auto_activate=request.auto_activate,
    )


@router.post("/inspector/reject")
def reject_story_authoring_inspector(request: StoryAuthoringApprovalRequest) -> Dict[str, Any]:
    simulation_state = _simulation_state_for_session(request.session_id)
    return reject_story_authoring_inspector_proposal(
        simulation_state,
        pending_id=request.pending_id,
        turn_index=request.turn_index,
        reason=request.reason or "gm_rejected",
    )


@router.post("/approve")
def approve_story_authoring_proposal(request: StoryAuthoringApprovalRequest) -> Dict[str, Any]:
    simulation_state = _simulation_state_for_session(request.session_id)
    return approve_story_proposal(
        simulation_state,
        pending_id=request.pending_id,
        turn_index=request.turn_index,
        reason=request.reason or "gm_approved",
        auto_activate=request.auto_activate,
    )


@router.post("/reject")
def reject_story_authoring_proposal(request: StoryAuthoringApprovalRequest) -> Dict[str, Any]:
    simulation_state = _simulation_state_for_session(request.session_id)
    return reject_story_proposal(
        simulation_state,
        pending_id=request.pending_id,
        turn_index=request.turn_index,
        reason=request.reason or "gm_rejected",
    )


@router.post("/packs/activation")
def story_pack_activation_snapshot(request: StoryPackActivationListRequest) -> Dict[str, Any]:
    simulation_state = _simulation_state_for_session(request.session_id)
    return build_story_pack_activation_snapshot(simulation_state, limit=request.limit)


@router.post("/packs/activate")
def activate_imported_story_pack(request: StoryPackActivationRequest) -> Dict[str, Any]:
    simulation_state = _simulation_state_for_session(request.session_id)
    result = activate_story_pack(
        simulation_state,
        request.pack_id,
        turn_index=request.turn_index,
        reason=request.reason or "gm_activated",
    )
    return {
        **result,
        "activation": build_story_pack_activation_snapshot(simulation_state),
    }


@router.post("/packs/deactivate")
def deactivate_imported_story_pack(request: StoryPackActivationRequest) -> Dict[str, Any]:
    simulation_state = _simulation_state_for_session(request.session_id)
    result = deactivate_story_pack(
        simulation_state,
        request.pack_id,
        turn_index=request.turn_index,
        reason=request.reason or "gm_deactivated",
    )
    return {
        **result,
        "activation": build_story_pack_activation_snapshot(simulation_state),
    }