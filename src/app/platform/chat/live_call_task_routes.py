"""The call's view of the tasks it started, its cancel, and the initiative it should take (companion roadmap 1.2, 1.3)."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.platform.chat.live_call_tasks import (
    CallTask, CallTaskList, InitiativeCandidate, call_proposal_message, cancel_call_task, initiative_candidate,
    list_call_tasks, proposal_button_allowed,
)
from app.platform.chat.live_call_camera import CAMERA_IMAGE_MAX_CHARS
from app.platform.chat.live_call_recap import LiveCallRecapRequest, LiveCallRecapStart, begin_call_recap
from app.platform.chat.models import _normalize_chat_image_data_url
from .live_call_open_loops import open_loop_candidate

LIVE_CALL_TASKS_PATH = "/api/chat/sessions/{session_id}/live-call/tasks"
LIVE_CALL_INITIATIVE_CANDIDATE_PATH = "/api/chat/sessions/{session_id}/live-call/initiative-candidate"
LIVE_CALL_RECAP_PATH = "/api/chat/sessions/{session_id}/live-call/recap"
LIVE_CALL_CAMERA_PATH ="/api/chat/sessions/{session_id}/live-call/camera"
CAMERA_GLANCE_PATH = "/api/chat/sessions/{session_id}/camera/glance"
SCREEN_GLANCE_PATH = "/api/chat/sessions/{session_id}/screen/glance"


class CameraAvailability(BaseModel):
    """Whether the call may offer Show (companion 4.1): vision configured, and local or remote with consent."""

    available: bool
    remote: bool
    reason: Literal["ready", "vision_not_configured", "remote_vision_not_allowed", "vision_unavailable"]


class CameraGlanceRequest(BaseModel):
    """One frame from the person's shared camera (camera share). Only its description is kept."""

    model_config = ConfigDict(extra="forbid")

    image: str = Field(max_length=CAMERA_IMAGE_MAX_CHARS)

    @field_validator("image")
    @classmethod
    def validate_image(cls, value: str) -> str:
        image = _normalize_chat_image_data_url(value)
        if image is None:
            raise ValueError("image must be a JPEG, PNG or WebP data URL")
        return image


class CameraGlanceResult(BaseModel):
    """Whether the frame is being described; it is described in the background and joins the next turn."""

    status: Literal["started", "in_progress", "vision_not_configured", "remote_vision_not_allowed",
                    "vision_unavailable"]


class CallProposalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["confirm", "cancel"]


class CallProposalDecision(BaseModel):
    task_id: str
    status: Literal["executed", "failed", "rejected"]
    # What the decision did, built by code: the call shows it.
    text: str


def decide_call_proposal(store: Any, session: Any, task_id: str, decision: str) -> CallProposalDecision:
    """The call's Confirm/Cancel buttons: the same decision as a spoken one, for a proposal of this chat whose
    question began within the window, run at most once by the claim."""
    from app.capabilities.executor import live_agent_tools
    from app.platform.chat.live_agent_store import decide_governed_proposal, execution_text, rejection_text

    message = call_proposal_message(session, task_id)
    if message is None:
        raise HTTPException(status_code=404, detail="proposal_not_found")
    if message.metadata.get("governed_tool_execution_status") != "pending":
        raise HTTPException(status_code=409, detail="proposal_decided")
    if not proposal_button_allowed(message):
        raise HTTPException(status_code=409, detail="proposal_expired")
    try:
        request = live_agent_tools().parse_request(message.metadata.get("pending_governed_tool_request") or {})
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="proposal_unreadable") from exc
    choice = "approve" if decision == "confirm" else "reject"
    decided = decide_governed_proposal(store, session.id, message, request, choice=choice,
                                       user_request=f"{decision} (call button)")
    if decided is None:
        raise HTTPException(status_code=409, detail="proposal_decided")
    if choice == "reject":
        return CallProposalDecision(task_id=task_id, status="rejected", text=rejection_text(request))
    failed = decided.execution_result.error is not None
    return CallProposalDecision(task_id=task_id, status="failed" if failed else "executed",
                                text=execution_text(decided))


def register_live_call_task_routes(router: APIRouter, *, chat_store_factory: Callable[[], Any],
                                   job_store_factory: Callable[[], Any]) -> None:
    """List a call's recent tasks and cancel one; a task is found only through its own chat."""

    def _session(session_id: str) -> Any:
        session = chat_store_factory().get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session_not_found")
        return session

    @router.get(LIVE_CALL_TASKS_PATH, response_model=CallTaskList)
    async def get_live_call_tasks(session_id: str) -> CallTaskList:
        def read() -> CallTaskList:
            return list_call_tasks(_session(session_id), job_store_factory())

        return await asyncio.to_thread(read)

    @router.post(LIVE_CALL_TASKS_PATH + "/{task_id}/cancel", response_model=CallTask)
    async def cancel_live_call_task(session_id: str, task_id: str) -> CallTask:
        def cancel() -> CallTask | None:
            return cancel_call_task(_session(session_id), job_store_factory(), task_id)

        task = await asyncio.to_thread(cancel)
        if task is None:
            raise HTTPException(status_code=404, detail="task_not_found")
        return task

    @router.post(LIVE_CALL_RECAP_PATH, response_model=LiveCallRecapStart)
    async def start_live_call_recap(session_id: str, request: LiveCallRecapRequest) -> LiveCallRecapStart:
        """After a call stops: its recap is written in the background, once per call (D3)."""

        def start() -> LiveCallRecapStart:
            store = chat_store_factory()
            return begin_call_recap(job_store_factory(), _session(session_id), request.call_started_at,
                                    chat_store=store)

        return await asyncio.to_thread(start)

    @router.post(LIVE_CALL_TASKS_PATH + "/{task_id}/decision", response_model=CallProposalDecision)
    async def decide_live_call_proposal(session_id: str, task_id: str,
                                        request: CallProposalDecisionRequest) -> CallProposalDecision:
        def decide() -> CallProposalDecision:
            store = chat_store_factory()
            return decide_call_proposal(store, _session(session_id), task_id, request.decision)

        return await asyncio.to_thread(decide)

    @router.get(LIVE_CALL_INITIATIVE_CANDIDATE_PATH, response_model=InitiativeCandidate)
    async def get_live_call_initiative_candidate(session_id: str, social: bool = False) -> InitiativeCandidate:
        """At most one reason; the call runs it through the initiative authority, which checks it again.

        A task's report comes first. With ``social`` (the call's policy may speak socially), an open loop from the
        speaker's own memory follows (companion 3.2).
        """
        def read() -> InitiativeCandidate:
            session = _session(session_id)
            candidate = initiative_candidate(session, job_store_factory())
            if candidate.reason is None and social:
                return InitiativeCandidate(reason=open_loop_candidate(session))
            return candidate

        return await asyncio.to_thread(read)

    @router.get(LIVE_CALL_CAMERA_PATH, response_model=CameraAvailability)
    async def get_live_call_camera(session_id: str) -> CameraAvailability:
        """Whether this call may offer the camera. Nothing is sent to a model."""
        from app.platform.chat.live_call_camera import camera_vision

        def read() -> CameraAvailability:
            _session(session_id)
            status = camera_vision()
            return CameraAvailability(available=status.available, remote=status.remote, reason=status.reason)

        return await asyncio.to_thread(read)

    @router.post(CAMERA_GLANCE_PATH, response_model=CameraGlanceResult)
    async def post_camera_glance(session_id: str, request: CameraGlanceRequest) -> CameraGlanceResult:
        """A frame from the person's shared camera, described in the background for their next turn."""
        from app.platform.chat.camera_glance import begin_glance

        def start() -> CameraGlanceResult:
            _session(session_id)
            return CameraGlanceResult(status=begin_glance(session_id, request.image))

        return await asyncio.to_thread(start)

    @router.post(SCREEN_GLANCE_PATH, response_model=CameraGlanceResult)
    async def post_screen_glance(session_id: str, request: CameraGlanceRequest) -> CameraGlanceResult:
        """A frame from the screen the person shares in a call (D2), described in the background for their next turn."""
        from app.platform.chat.screen_glance import begin_screen_glance

        def start() -> CameraGlanceResult:
            _session(session_id)
            return CameraGlanceResult(status=begin_screen_glance(session_id, request.image))

        return await asyncio.to_thread(start)


__all__ = [
    "CAMERA_GLANCE_PATH",
    "SCREEN_GLANCE_PATH",
    "CameraGlanceRequest",
    "CameraGlanceResult",
    "LIVE_CALL_CAMERA_PATH",
    "LIVE_CALL_INITIATIVE_CANDIDATE_PATH",
    "LIVE_CALL_TASKS_PATH",
    "CallProposalDecision",
    "CameraAvailability",
    "CallProposalDecisionRequest",
    "decide_call_proposal",
    "register_live_call_task_routes",
]
