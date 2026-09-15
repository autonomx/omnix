"""FastAPI management routes for durable Character profiles and session mode."""
from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.assistant_memory import default_memory_service, resolve_chat_scope
from app.chat.live_call_greeting import stream_live_call_greeting_chunks
from app.chat.live_conversation_proactive import (
    ProactiveDeliveryRequest,
    ProactiveDeliveryResponse,
    commit_proactive_delivery,
    stream_proactive_turn_chunks,
)
from app.chat.models import ChatSession
from app.companion_activity.initiative import (
    CompanionInitiativeAuthorityStore,
    InitiativeAcquireRequest,
    default_companion_initiative_authority,
)

from .hermes_adapter import (
    CharacterHermesSyncStatus,
    export_character_memory_to_hermes,
    import_character_hermes_memory,
)
from .live_call import CharacterLiveCallRuntime, resolve_live_call_runtime
from .live_conversation_profile import (
    LiveConversationProfile,
    LiveConversationProfileEnvelope,
    LiveConversationProfileStore,
    LiveConversationProfileUpdate,
    default_live_conversation_profile_store,
)
from .management import (
    CharacterDataActionRequest,
    CharacterDataActionResponse,
    CharacterDataExport,
    CharacterManagementService,
)
from .models import (
    ArchiveCharacterResponse,
    CharacterListResponse,
    CharacterProfile,
    CharacterVersionListResponse,
    CreateCharacterRequest,
    UpdateCharacterRequest,
)
from .repository import CharacterConflictError, CharacterNotFoundError
from .service import CharacterService, CharacterVoiceAssetError, default_character_service
from .session_models import SetSessionInteractionRequest
from .voice_consent import (
    UpdateVoiceProfileGovernanceRequest,
    VoiceConsentError,
    VoiceProfileGovernance,
    default_voice_governance_service,
)

_INITIATIVE_GENERATION = "session"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _proactive_initiative_policy(reason: str) -> tuple[str, str, str, str, float]:
    normalized = reason.strip().lower()
    if normalized.startswith("desktop_critical:"):
        return "desktop", "text", "critical", "interrupt", 0.0
    if normalized.startswith("desktop_companion:"):
        return "desktop", "text", "normal", "idle_only", 4.0
    if normalized == "ambient_visual_presence":
        return "ambient", "voice", "normal", "idle_only", 25.0
    return "social", "voice", "normal", "idle_only", 25.0


def _proactive_turn_id(event: dict[str, Any]) -> str | None:
    direct = event.get("turn_id")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    metadata = event.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get("turn_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _proactive_event_is_skip(event: dict[str, Any]) -> bool:
    metadata = event.get("metadata")
    if isinstance(metadata, dict) and metadata.get("generation_status") == "skipped":
        return True
    if event.get("type") != "complete":
        return False
    content = event.get("content")
    if not isinstance(content, str):
        return False
    return content.strip().upper().rstrip(".! ") == "SKIP"


def _delivery_already_committed(session: ChatSession, turn_id: str) -> bool:
    return any(
        message.role == "assistant" and message.metadata.get("turn_id") == turn_id
        for message in session.messages
    )


def register_character_routes(
    app: FastAPI,
    *,
    service_factory: Callable[[], CharacterService] = default_character_service,
    chat_store_factory: Callable[[], Any] | None = None,
    live_conversation_profile_store_factory: Callable[[], LiveConversationProfileStore] = default_live_conversation_profile_store,
    initiative_authority_factory: Callable[[], CompanionInitiativeAuthorityStore] = default_companion_initiative_authority,
) -> None:
    """Register typed routes while keeping the flagged feature out of public OpenAPI."""

    @app.get("/api/characters", response_model=CharacterListResponse, tags=["characters"], include_in_schema=False)
    async def list_characters(include_archived: bool = Query(default=False)) -> CharacterListResponse:
        return service_factory().list(include_archived=include_archived)

    @app.post("/api/characters", response_model=CharacterProfile, status_code=201, tags=["characters"], include_in_schema=False)
    async def create_character(request: CreateCharacterRequest) -> CharacterProfile:
        try:
            return service_factory().create(request)
        except CharacterConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except CharacterVoiceAssetError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/characters/{character_id}", response_model=CharacterProfile, tags=["characters"], include_in_schema=False)
    async def get_character(character_id: str, include_archived: bool = Query(default=False)) -> CharacterProfile:
        try:
            return service_factory().get(character_id, include_archived=include_archived)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc

    @app.patch("/api/characters/{character_id}", response_model=CharacterProfile, tags=["characters"], include_in_schema=False)
    async def update_character(character_id: str, request: UpdateCharacterRequest) -> CharacterProfile:
        try:
            return service_factory().update(character_id, request)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc
        except CharacterConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except CharacterVoiceAssetError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.delete("/api/characters/{character_id}", response_model=ArchiveCharacterResponse, tags=["characters"], include_in_schema=False)
    async def archive_character(character_id: str) -> ArchiveCharacterResponse:
        try:
            return service_factory().archive(character_id)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc

    @app.get("/api/characters/{character_id}/versions", response_model=CharacterVersionListResponse, tags=["characters"], include_in_schema=False)
    async def list_character_versions(character_id: str) -> CharacterVersionListResponse:
        try:
            return service_factory().versions(character_id)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc

    def character_hermes_context(character_id: str):
        service_factory().get(character_id)
        return resolve_chat_scope(
            f"character-hermes:{character_id}",
            owner_type="character",
            owner_id=character_id,
        )

    @app.post(
        "/api/characters/{character_id}/hermes/import",
        response_model=CharacterHermesSyncStatus,
        tags=["characters"],
        include_in_schema=False,
    )
    async def import_character_hermes(character_id: str) -> CharacterHermesSyncStatus:
        try:
            return import_character_hermes_memory(
                default_memory_service(),
                character_hermes_context(character_id),
                character_id,
            )
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post(
        "/api/characters/{character_id}/hermes/export",
        response_model=CharacterHermesSyncStatus,
        tags=["characters"],
        include_in_schema=False,
    )
    async def export_character_hermes(character_id: str) -> CharacterHermesSyncStatus:
        try:
            return export_character_memory_to_hermes(
                default_memory_service(),
                character_hermes_context(character_id),
                character_id,
            )
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get(
        "/api/voice-profiles/{asset_id}/governance",
        response_model=VoiceProfileGovernance,
        tags=["characters"],
        include_in_schema=False,
    )
    async def get_voice_profile_governance(asset_id: str) -> VoiceProfileGovernance:
        try:
            return default_voice_governance_service().get(asset_id)
        except VoiceConsentError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.patch(
        "/api/voice-profiles/{asset_id}/governance",
        response_model=VoiceProfileGovernance,
        tags=["characters"],
        include_in_schema=False,
    )
    async def update_voice_profile_governance(
        asset_id: str,
        request: UpdateVoiceProfileGovernanceRequest,
    ) -> VoiceProfileGovernance:
        try:
            return default_voice_governance_service().update(asset_id, request)
        except VoiceConsentError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get(
        "/api/live-chat/profile/defaults",
        response_model=LiveConversationProfile,
        tags=["live-chat"],
        include_in_schema=False,
    )
    async def get_live_conversation_defaults() -> LiveConversationProfile:
        return live_conversation_profile_store_factory().get_defaults()

    @app.patch(
        "/api/live-chat/profile/defaults",
        response_model=LiveConversationProfile,
        tags=["live-chat"],
        include_in_schema=False,
    )
    async def update_live_conversation_defaults(request: LiveConversationProfileUpdate) -> LiveConversationProfile:
        return live_conversation_profile_store_factory().update_defaults(request)

    if chat_store_factory is None:
        return

    def management_service() -> CharacterManagementService:
        return CharacterManagementService(service_factory(), chat_store_factory())

    def require_session(session_id: str) -> ChatSession:
        session = chat_store_factory().get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="chat session not found")
        return session

    @app.get(
        "/api/characters/{character_id}/data",
        response_model=CharacterDataExport,
        tags=["characters"],
        include_in_schema=False,
    )
    async def export_character_data(character_id: str) -> CharacterDataExport:
        try:
            return management_service().export(character_id)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc

    @app.post(
        "/api/characters/{character_id}/data/actions",
        response_model=CharacterDataActionResponse,
        tags=["characters"],
        include_in_schema=False,
    )
    async def apply_character_data_actions(
        character_id: str,
        request: CharacterDataActionRequest,
    ) -> CharacterDataActionResponse:
        try:
            return management_service().apply(character_id, request)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc
        except (CharacterConflictError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/chat/sessions/{session_id}/interaction", response_model=ChatSession, tags=["characters"], include_in_schema=False)
    async def get_session_interaction(session_id: str) -> ChatSession:
        return require_session(session_id)

    @app.post("/api/chat/sessions/{session_id}/interaction", response_model=ChatSession, tags=["characters"], include_in_schema=False)
    async def set_session_interaction(session_id: str, request: SetSessionInteractionRequest) -> ChatSession:
        try:
            session = chat_store_factory().set_session_interaction(session_id, request)
        except (CharacterNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if session is None:
            raise HTTPException(status_code=404, detail="chat session not found")
        return session

    @app.get(
        "/api/chat/sessions/{session_id}/live-conversation/profile",
        response_model=LiveConversationProfileEnvelope,
        tags=["live-chat"],
        include_in_schema=False,
    )
    async def get_live_conversation_profile(session_id: str) -> LiveConversationProfileEnvelope:
        require_session(session_id)
        return live_conversation_profile_store_factory().get(session_id)

    @app.patch(
        "/api/chat/sessions/{session_id}/live-conversation/profile",
        response_model=LiveConversationProfileEnvelope,
        tags=["live-chat"],
        include_in_schema=False,
    )
    async def update_live_conversation_profile(
        session_id: str,
        request: LiveConversationProfileUpdate,
    ) -> LiveConversationProfileEnvelope:
        require_session(session_id)
        return live_conversation_profile_store_factory().update(session_id, request)

    @app.delete(
        "/api/chat/sessions/{session_id}/live-conversation/profile",
        response_model=LiveConversationProfileEnvelope,
        tags=["live-chat"],
        include_in_schema=False,
    )
    async def clear_live_conversation_profile(session_id: str) -> LiveConversationProfileEnvelope:
        require_session(session_id)
        return live_conversation_profile_store_factory().clear(session_id)

    @app.get(
        "/api/chat/sessions/{session_id}/live-call/runtime",
        response_model=CharacterLiveCallRuntime,
        tags=["characters"],
        include_in_schema=False,
    )
    async def get_live_call_runtime(session_id: str) -> CharacterLiveCallRuntime:
        session = require_session(session_id)
        try:
            return resolve_live_call_runtime(session, character_service_factory=service_factory)
        except (CharacterNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post(
        "/api/chat/sessions/{session_id}/live-call/greeting/stream",
        tags=["characters"],
        include_in_schema=False,
    )
    async def stream_live_call_greeting(
        session_id: str,
        purpose: str = Query(default="greeting"),
        initiative_reason: str = Query(default="quiet_follow_up", max_length=120),
        state_summary: str | None = Query(default=None, max_length=500),
    ) -> StreamingResponse:
        store = chat_store_factory()
        session = require_session(session_id)
        authority: CompanionInitiativeAuthorityStore | None = None
        lease = None
        if purpose == "proactive_reengagement":
            authority = initiative_authority_factory()
            authority.register_generation(session_id, _INITIATIVE_GENERATION)
            owner, channel, urgency, interruptibility, spacing = _proactive_initiative_policy(
                initiative_reason
            )
            decision = authority.acquire(
                InitiativeAcquireRequest(
                    session_id=session_id,
                    generation=_INITIATIVE_GENERATION,
                    owner=owner,
                    intent_id=f"proactive:pending:{uuid.uuid4().hex}",
                    channel=channel,
                    urgency=urgency,
                    interruptibility=interruptibility,
                    requested_at=_utcnow(),
                    ttl_seconds=90.0,
                    minimum_spacing_seconds=spacing,
                )
            )
            if not decision.accepted or decision.lease is None:
                raise HTTPException(status_code=409, detail=decision.reason)
            lease = decision.lease

        def generate():
            bound_lease = None
            released = False
            handed_off = False

            def release_without_delivery() -> None:
                nonlocal released
                if released or authority is None or lease is None:
                    return
                authority.finish(
                    session_id=session_id,
                    lease_id=lease.lease_id,
                    finished_at=_utcnow(),
                    delivered=False,
                )
                released = True

            try:
                events = (
                    stream_proactive_turn_chunks(
                        store,
                        session,
                        initiative_reason=initiative_reason,
                        state_summary=state_summary,
                    )
                    if purpose == "proactive_reengagement"
                    else stream_live_call_greeting_chunks(store, session)
                )
                for event in events:
                    if authority is not None and lease is not None:
                        turn_id = _proactive_turn_id(event)
                        if turn_id and bound_lease is None:
                            bound_lease = authority.bind_intent(
                                session_id=session_id,
                                lease_id=lease.lease_id,
                                intent_id=turn_id,
                                bound_at=_utcnow(),
                            )
                            if bound_lease is None:
                                yield "data: " + json.dumps(
                                    {
                                        "type": "error",
                                        "message": "Companion initiative authority expired or was preempted.",
                                    },
                                    sort_keys=True,
                                ) + "\n\n"
                                return
                        if bound_lease is not None and not authority.authorizes(
                            bound_lease,
                            now=_utcnow(),
                        ):
                            yield "data: " + json.dumps(
                                {
                                    "type": "error",
                                    "message": "Companion initiative authority expired or was preempted.",
                                },
                                sort_keys=True,
                            ) + "\n\n"
                            return
                    yield f"data: {json.dumps(event, sort_keys=True)}\n\n"
                    if authority is not None and _proactive_event_is_skip(event):
                        release_without_delivery()

                if authority is not None and lease is not None and not released:
                    if bound_lease is None:
                        release_without_delivery()
                    elif not authority.authorizes(bound_lease, now=_utcnow()):
                        yield "data: " + json.dumps(
                            {
                                "type": "error",
                                "message": "Companion initiative authority expired or was preempted.",
                            },
                            sort_keys=True,
                        ) + "\n\n"
                        return
                    else:
                        handed_off = True
                yield f"data: {json.dumps({'type': 'done'}, sort_keys=True)}\n\n"
            except GeneratorExit:
                if not handed_off:
                    release_without_delivery()
                raise
            except Exception as exc:
                if not handed_off:
                    release_without_delivery()
                label = (
                    "Proactive live-conversation turn"
                    if purpose == "proactive_reengagement"
                    else "Live-call greeting"
                )
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc) or f'{label} failed.'}, sort_keys=True)}\n\n"
            finally:
                if authority is not None and not handed_off and not released:
                    release_without_delivery()

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.post(
        "/api/chat/sessions/{session_id}/live-conversation/proactive/delivery",
        response_model=ProactiveDeliveryResponse,
        tags=["live-chat"],
        include_in_schema=False,
    )
    async def commit_live_conversation_proactive_delivery(
        session_id: str,
        request: ProactiveDeliveryRequest,
    ) -> ProactiveDeliveryResponse:
        session = require_session(session_id)
        store = chat_store_factory()
        already_committed = (
            not request.purpose.startswith("desktop_")
            and _delivery_already_committed(session, request.turn_id)
        )
        if not already_committed:
            authority = initiative_authority_factory()
            finished = authority.finish_intent(
                session_id=session_id,
                intent_id=request.turn_id,
                finished_at=_utcnow(),
                delivered=True,
            )
            if not finished:
                raise HTTPException(status_code=409, detail="initiative_lease_inactive")
        result = commit_proactive_delivery(store, session_id, request)
        if result is None:
            raise HTTPException(status_code=404, detail="chat session not found")
        return result


__all__ = ["register_character_routes"]
