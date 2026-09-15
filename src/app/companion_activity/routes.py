"""Server-authoritative initiative lease endpoints shared by all companion channels."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.chat import ChatSessionStore, default_chat_store

from .initiative import (
    CompanionInitiativeAuthorityStore,
    InitiativeAcquireRequest,
    InitiativeChannel,
    InitiativeDecision,
    InitiativeInterruptibility,
    InitiativeUrgency,
    default_companion_initiative_authority,
)

_INITIATIVE_GENERATION = "session"


class CompanionInitiativeAcquireApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=200)
    owner: str = Field(min_length=1, max_length=120)
    intent_id: str = Field(min_length=1, max_length=240)
    channel: InitiativeChannel
    urgency: InitiativeUrgency = "normal"
    interruptibility: InitiativeInterruptibility = "idle_only"
    ttl_seconds: float = Field(default=15.0, gt=0.0, le=120.0)
    minimum_spacing_seconds: float = Field(default=25.0, ge=0.0, le=600.0)


class CompanionInitiativeFinishApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=200)
    lease_id: str = Field(min_length=1, max_length=240)
    delivered: bool = False


class CompanionInitiativeFinishApiResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    finished: bool


def register_companion_activity_routes(
    app: FastAPI,
    *,
    authority_factory: Callable[[], CompanionInitiativeAuthorityStore] = (
        default_companion_initiative_authority
    ),
    chat_store_factory: Callable[[], ChatSessionStore] = default_chat_store,
) -> None:
    @app.post(
        "/api/companion-initiative/acquire",
        response_model=InitiativeDecision,
        tags=["companion-activity"],
        include_in_schema=False,
    )
    def acquire_companion_initiative(
        request: CompanionInitiativeAcquireApiRequest,
    ) -> InitiativeDecision:
        _require_session(request.session_id, chat_store_factory())
        authority = authority_factory()
        authority.register_generation(request.session_id, _INITIATIVE_GENERATION)
        return authority.acquire(
            InitiativeAcquireRequest(
                session_id=request.session_id,
                generation=_INITIATIVE_GENERATION,
                owner=request.owner,
                intent_id=request.intent_id,
                channel=request.channel,
                urgency=request.urgency,
                interruptibility=request.interruptibility,
                requested_at=_utcnow(),
                ttl_seconds=request.ttl_seconds,
                minimum_spacing_seconds=request.minimum_spacing_seconds,
            )
        )

    @app.post(
        "/api/companion-initiative/finish",
        response_model=CompanionInitiativeFinishApiResponse,
        tags=["companion-activity"],
        include_in_schema=False,
    )
    def finish_companion_initiative(
        request: CompanionInitiativeFinishApiRequest,
    ) -> CompanionInitiativeFinishApiResponse:
        _require_session(request.session_id, chat_store_factory())
        finished = authority_factory().finish(
            session_id=request.session_id,
            lease_id=request.lease_id,
            finished_at=_utcnow(),
            delivered=request.delivered,
        )
        return CompanionInitiativeFinishApiResponse(finished=finished)


def _require_session(session_id: str, store: ChatSessionStore) -> None:
    if store.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="chat_session_not_found")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "CompanionInitiativeAcquireApiRequest",
    "CompanionInitiativeFinishApiRequest",
    "CompanionInitiativeFinishApiResponse",
    "register_companion_activity_routes",
]
