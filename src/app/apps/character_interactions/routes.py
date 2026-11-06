"""Composition-owned routes joining Character, Chat, and memory services."""
from __future__ import annotations
import json
import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.platform.companion_activity.contracts import (
    CompanionInitiativeAuthorityStore, InitiativeAcquireRequest,
    default_companion_initiative_authority,
)
from app.conversation.contracts import ChatSession
from app.conversation.memory_contracts import (
    MemoryCandidate,
    MemoryCategory,
    MemoryConflictError,
    MemoryRecord,
    SYSTEM_MEMORY_OWNER_ID,
)
from app.platform.chat.contracts import stream_live_call_greeting_chunks
from app.platform.chat.contracts import (
    ProactiveDeliveryRequest,
    ProactiveDeliveryResponse,
    commit_proactive_delivery,
    stream_proactive_turn_chunks,
)
from app.platform.characters.contracts import CharacterLiveCallRuntime, resolve_live_call_runtime
from app.platform.characters.contracts import (
    LiveConversationProfileEnvelope, LiveConversationProfileStore,
    LiveConversationProfileUpdate, default_live_conversation_profile_store,
)
from app.platform.characters.contracts import (
    CharacterDataActionRequest, CharacterDataActionResponse, CharacterDataExport,
    CharacterManagementService,
)
from app.platform.characters.contracts import CharacterConflictError, CharacterNotFoundError
from app.platform.characters.contracts import SetSessionInteractionRequest
from app.platform.characters.contracts import CharacterService, default_character_service
from app.runtime.pagination import MAX_PAGE_SIZE

logger = logging.getLogger(__name__)

_INITIATIVE_GENERATION = "session"


class UnderstoodEarlier(BaseModel):
    """A view the note turned away from, and when it changed."""

    statement: str
    until: datetime | None = None


class UnderstoodNote(BaseModel):
    key: str
    aspect: str
    statement: str
    corrected: bool = False
    updated_at: datetime | None = None
    earlier: list[UnderstoodEarlier] = Field(default_factory=list)


class UnderstoodTrigger(BaseModel):
    """What brings on a feeling in the person, what it concerns, and how often it was seen."""

    key: str
    emotion: str
    pattern: str
    about: list[str] = Field(default_factory=list)
    seen: int = 1
    since: datetime | None = None


class UnderstoodConnection(BaseModel):
    key: str
    subject: str
    relation: str
    object: str


class UnderstoodRelationship(BaseModel):
    statement: str
    closeness: float | None = None
    trust: float | None = None
    ease: float | None = None
    corrected: bool = False
    updated_at: datetime | None = None


class UnderstoodMood(BaseModel):
    key: str
    emotion: str
    at: datetime | None = None


class UnderstoodEpisode(BaseModel):
    key: str
    title: str
    summary: str
    at: datetime | None = None


class UnderstoodLesson(BaseModel):
    """A pattern the person's reactions to replies showed, and how often it was seen."""

    key: str
    aspect: str
    lesson: str
    advice: str | None = None  # what the character does about it from now on
    seen: int = 1
    since: datetime | None = None


class UnderstoodPromise(BaseModel):
    """Something the owner told the person it would do, and whether that has happened."""

    key: str
    what: str
    kept: bool = False
    since: datetime | None = None


class UnderstoodJoke(BaseModel):
    key: str
    joke: str
    seen: int = 1
    since: datetime | None = None


class OwnerSide(BaseModel):
    """The owner's own side: how it has come to stand toward the person, what it promised, what they joke about."""

    stance: str | None = None
    stance_updated_at: datetime | None = None
    promises: list[UnderstoodPromise] = Field(default_factory=list)
    jokes: list[UnderstoodJoke] = Field(default_factory=list)


class OwnerUnderstanding(BaseModel):
    """What the owner has come to understand about the person from their conversations."""

    person: list[UnderstoodNote] = Field(default_factory=list)
    lessons: list[UnderstoodLesson] = Field(default_factory=list)
    triggers: list[UnderstoodTrigger] = Field(default_factory=list)
    own_side: OwnerSide = Field(default_factory=OwnerSide)
    connections: list[UnderstoodConnection] = Field(default_factory=list)
    relationship: UnderstoodRelationship | None = None
    moods: list[UnderstoodMood] = Field(default_factory=list)
    episodes: list[UnderstoodEpisode] = Field(default_factory=list)


class OwnerMemoryView(BaseModel):
    """What a character or the System Assistant remembers, and what is waiting to be accepted."""

    owner_id: str
    records: list[MemoryRecord]
    suggestions: list[MemoryCandidate]
    understanding: OwnerUnderstanding = Field(default_factory=OwnerUnderstanding)


class CorrectUnderstandingRequest(BaseModel):
    text: str = Field(min_length=1, max_length=400)


class UnderstandingChanged(BaseModel):
    changed: bool = True


class CreateOwnerMemoryRequest(BaseModel):
    category: MemoryCategory = "fact"
    content: str = Field(min_length=1, max_length=4096)


class UpdateOwnerMemoryRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4096)
    expected_revision: int = Field(ge=1)


def all_pages(list_page: Callable[..., list[Any]], **filters: Any) -> list[Any]:
    items: list[Any] = []
    while True:
        page = list_page(limit=MAX_PAGE_SIZE, offset=len(items), **filters)
        items.extend(page)
        if len(page) < MAX_PAGE_SIZE:
            return items


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

def register_character_integration_routes(
    router: APIRouter,
    *,
    chat_store_factory: Callable[[], Any],
    service_factory: Callable[[], CharacterService] = default_character_service,
    live_conversation_profile_store_factory: Callable[[], LiveConversationProfileStore] = default_live_conversation_profile_store,
    initiative_authority_factory: Callable[[], CompanionInitiativeAuthorityStore] = default_companion_initiative_authority,
    memory_service_factory: Callable[[], Any] | None = None,
    memory_repository_factory: Callable[[], Any] | None = None,
) -> None:
    from app.platform.assistant_memory.contracts import (
        CharacterHermesSyncStatus, export_character_memory_to_hermes,
        import_character_hermes_memory,
    )
    from app.platform.assistant_memory.contracts import MemoryPolicyError, default_memory_service, resolve_chat_scope
    from app.platform.characters.contracts import character_hermes_sync_enabled
    get_memory_service = memory_service_factory or default_memory_service
    if memory_repository_factory is None:

        def memory_repository_factory():
            from app.platform.assistant_memory.contracts import owner_memory_repository

            return owner_memory_repository()

    def character_hermes_context(character_id: str):
        service_factory().get(character_id)
        return resolve_chat_scope(
            f"character-hermes:{character_id}",
            owner_type="character",
            owner_id=character_id,
        )

    @router.post(
        "/api/characters/{character_id}/hermes/import",
        response_model=CharacterHermesSyncStatus,
        tags=["characters"],
    )
    def import_character_hermes(character_id: str) -> CharacterHermesSyncStatus:
        try:
            return import_character_hermes_memory(
                get_memory_service(),
                character_hermes_context(character_id),
                character_id,
                enabled=character_hermes_sync_enabled(),
            )
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/characters/{character_id}/hermes/export",
        response_model=CharacterHermesSyncStatus,
        tags=["characters"],
    )
    def export_character_hermes(character_id: str) -> CharacterHermesSyncStatus:
        try:
            return export_character_memory_to_hermes(
                get_memory_service(),
                character_hermes_context(character_id),
                character_id,
                enabled=character_hermes_sync_enabled(),
            )
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def management_service() -> CharacterManagementService:
        return CharacterManagementService(
            service_factory(),
            chat_store_factory(),
            memory_repository=memory_repository_factory(),
        )

    def require_session(session_id: str) -> ChatSession:
        session = chat_store_factory().get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="chat session not found")
        return session

    def owner_memory_context(owner_id: str, scope: str | None = None, scope_id: str | None = None):
        """A memory owner's context with no chat behind it: what a person sees and edits in the owner's Memory tab."""
        is_system = owner_id == SYSTEM_MEMORY_OWNER_ID
        if not is_system:
            try:
                service_factory().get(owner_id, include_archived=True)
            except CharacterNotFoundError as exc:
                raise HTTPException(status_code=404, detail="memory owner not found") from exc
        context = resolve_chat_scope(
            f"owner-memory:{owner_id}",
            owner_type="system" if is_system else "character",
            owner_id=owner_id,
        )
        # A record is only visible from the scope it was saved in, whichever chat that was.
        field = {"global": "profile_id", "workspace": "workspace_id", "project": "project_id", "session": "session_id"}
        return context.model_copy(update={field[scope]: scope_id}) if scope and scope_id else context

    def owner_understanding(context: Any) -> OwnerUnderstanding:
        from app.platform.assistant_memory.contracts import read_owner_understanding

        result = OwnerUnderstanding()
        understood = read_owner_understanding(context.owner_type, context.owner_id, context.profile_id)
        earlier: dict[str, list[UnderstoodEarlier]] = {}
        for item in understood:
            if item.kind == "earlier":
                earlier.setdefault(item.key, []).append(UnderstoodEarlier(statement=item.text, until=item.at))
        for item in understood:
            if item.kind == "person":
                result.person.append(UnderstoodNote(
                    key=item.key, aspect=item.label or item.key, statement=item.text,
                    corrected=item.corrected, updated_at=item.at, earlier=earlier.get(item.key, []),
                ))
            elif item.kind == "connection":
                subject, relation, object_ = (item.label or "").split("\x1f")
                result.connections.append(UnderstoodConnection(
                    key=item.key, subject=subject, relation=relation, object=object_,
                ))
            elif item.kind == "relationship":
                result.relationship = UnderstoodRelationship(
                    statement=item.text, corrected=item.corrected, updated_at=item.at, **dict(item.metrics),
                )
            elif item.kind == "mood":
                result.moods.append(UnderstoodMood(key=item.key, emotion=item.text, at=item.at))
            elif item.kind == "episode":
                result.episodes.append(UnderstoodEpisode(
                    key=item.key, title=item.label or "", summary=item.text, at=item.at,
                ))
            elif item.kind == "lesson":
                result.lessons.append(UnderstoodLesson(
                    key=item.key, aspect=item.label or "", lesson=item.text, advice=item.advice, seen=item.seen,
                    since=item.at,
                ))
            elif item.kind == "stance":
                result.own_side.stance, result.own_side.stance_updated_at = item.text, item.at
            elif item.kind == "promise":
                result.own_side.promises.append(UnderstoodPromise(
                    key=item.key, what=item.text, kept=item.label == "kept", since=item.at,
                ))
            elif item.kind == "joke":
                result.own_side.jokes.append(UnderstoodJoke(key=item.key, joke=item.text, seen=item.seen, since=item.at))
            elif item.kind == "trigger":
                result.triggers.append(UnderstoodTrigger(
                    key=item.key, emotion=item.label or "", pattern=item.text, about=list(item.about),
                    seen=item.seen, since=item.at,
                ))
        result.lessons.sort(key=lambda lesson: -lesson.seen)
        result.triggers.sort(key=lambda trigger: -trigger.seen)
        result.own_side.promises.sort(key=lambda promise: promise.kept)  # open ones first
        result.own_side.jokes.sort(key=lambda joke: -joke.seen)
        return result

    def owned_record(owner_id: str, memory_id: str):
        record = get_memory_service().owner_repository.get_record(memory_id)
        if record is None or record.owner_id != owner_id:
            raise HTTPException(status_code=404, detail="memory not found")
        return record, owner_memory_context(owner_id, record.scope, record.scope_id)

    def owned_suggestion(owner_id: str, candidate_id: str):
        candidate = get_memory_service().owner_repository.get_candidate(candidate_id)
        if candidate is None or candidate.owner_id != owner_id:
            raise HTTPException(status_code=404, detail="memory suggestion not found")
        return candidate, owner_memory_context(owner_id, candidate.proposed_scope, candidate.proposed_scope_id)

    @router.get("/api/memory-owners/{owner_id}", response_model=OwnerMemoryView, tags=["characters"])
    def read_owner_memory(owner_id: str) -> OwnerMemoryView:
        context = owner_memory_context(owner_id)
        repository = memory_repository_factory()
        filters = {"owner_type": context.owner_type, "owner_id": owner_id}
        records = all_pages(repository.list_records, status="active", **filters)
        suggestions = all_pages(repository.list_candidates, status="pending", **filters)
        return OwnerMemoryView(
            owner_id=owner_id,
            records=sorted(records, key=lambda item: item.updated_at, reverse=True),
            suggestions=sorted(suggestions, key=lambda item: item.created_at, reverse=True),
            understanding=owner_understanding(context),
        )

    @router.delete(
        "/api/memory-owners/{owner_id}/understanding/{kind}/{key}",
        response_model=UnderstandingChanged,
        tags=["characters"],
    )
    def forget_owner_understanding(owner_id: str, kind: str, key: str) -> UnderstandingChanged:
        """Forget one thing understood about the person, so that its words leave the log too."""
        from app.platform.assistant_memory.contracts import forget_owner_understanding as forget

        context = owner_memory_context(owner_id)
        rewritten = forget(context.owner_type, context.owner_id, context.profile_id, kind, key)
        if not rewritten:
            raise HTTPException(status_code=404, detail="nothing like that is remembered")
        return UnderstandingChanged()

    @router.patch(
        "/api/memory-owners/{owner_id}/understanding/{kind}/{key}",
        response_model=UnderstandingChanged,
        tags=["characters"],
    )
    def correct_owner_understanding(
        owner_id: str, kind: str, key: str, request: CorrectUnderstandingRequest,
    ) -> UnderstandingChanged:
        """The person's own wording replaces a note on them or how the relationship stands."""
        from app.platform.assistant_memory.contracts import correct_owner_understanding as correct

        context = owner_memory_context(owner_id)
        if not correct(context.owner_type, context.owner_id, context.profile_id, kind, key, request.text.strip()):
            raise HTTPException(status_code=404, detail="that cannot be reworded")
        return UnderstandingChanged()

    @router.post("/api/memory-owners/{owner_id}/records", response_model=MemoryRecord, status_code=201, tags=["characters"])
    def add_owner_memory(owner_id: str, request: CreateOwnerMemoryRequest) -> MemoryRecord:
        context = owner_memory_context(owner_id)
        try:
            return get_memory_service().create_explicit_memory(
                context, scope="global", category=request.category, content=request.content, provenance_id=None,
            )
        except MemoryPolicyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.patch("/api/memory-owners/{owner_id}/records/{memory_id}", response_model=MemoryRecord, tags=["characters"])
    def edit_owner_memory(owner_id: str, memory_id: str, request: UpdateOwnerMemoryRequest) -> MemoryRecord:
        _record, context = owned_record(owner_id, memory_id)
        try:
            return get_memory_service().edit_memory(
                context, memory_id, content=request.content, expected_revision=request.expected_revision,
            )
        except MemoryConflictError as exc:
            raise HTTPException(status_code=409, detail="memory changed since it was read") from exc
        except MemoryPolicyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.delete("/api/memory-owners/{owner_id}/records/{memory_id}", status_code=204, tags=["characters"])
    def forget_owner_memory(owner_id: str, memory_id: str, expected_revision: int = Query(ge=1)) -> None:
        _record, context = owned_record(owner_id, memory_id)
        try:
            get_memory_service().forget_memory(context, memory_id, expected_revision=expected_revision)
        except MemoryConflictError as exc:
            raise HTTPException(status_code=409, detail="memory changed since it was read") from exc

    @router.post(
        "/api/memory-owners/{owner_id}/suggestions/{candidate_id}/approve",
        response_model=MemoryRecord,
        tags=["characters"],
    )
    def approve_owner_memory_suggestion(owner_id: str, candidate_id: str) -> MemoryRecord:
        _candidate, context = owned_suggestion(owner_id, candidate_id)
        try:
            return get_memory_service().approve_candidate(context, candidate_id)
        except MemoryPolicyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/api/memory-owners/{owner_id}/suggestions/{candidate_id}/reject", status_code=204, tags=["characters"])
    def reject_owner_memory_suggestion(owner_id: str, candidate_id: str) -> None:
        owned_suggestion(owner_id, candidate_id)
        get_memory_service().reject_candidate(candidate_id)

    @router.get(
        "/api/characters/{character_id}/data",
        response_model=CharacterDataExport,
        tags=["characters"],
    )
    def export_character_data(character_id: str) -> CharacterDataExport:
        try:
            return management_service().export(character_id)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc

    @router.post(
        "/api/characters/{character_id}/data/actions",
        response_model=CharacterDataActionResponse,
        tags=["characters"],
    )
    def apply_character_data_actions(
        character_id: str,
        request: CharacterDataActionRequest,
    ) -> CharacterDataActionResponse:
        try:
            return management_service().apply(character_id, request)
        except CharacterNotFoundError as exc:
            raise HTTPException(status_code=404, detail="character not found") from exc
        except (CharacterConflictError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/api/chat/sessions/{session_id}/interaction", response_model=ChatSession, tags=["characters"])
    def get_session_interaction(session_id: str) -> ChatSession:
        return require_session(session_id)

    @router.post("/api/chat/sessions/{session_id}/interaction", response_model=ChatSession, tags=["characters"])
    def set_session_interaction(session_id: str, request: SetSessionInteractionRequest) -> ChatSession:
        try:
            session = chat_store_factory().set_session_interaction(session_id, request)
        except (CharacterNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if session is None:
            raise HTTPException(status_code=404, detail="chat session not found")
        return session

    @router.get(
        "/api/chat/sessions/{session_id}/live-conversation/profile",
        response_model=LiveConversationProfileEnvelope,
        tags=["live-chat"],
    )
    def get_live_conversation_profile(session_id: str) -> LiveConversationProfileEnvelope:
        require_session(session_id)
        return live_conversation_profile_store_factory().get(session_id)

    @router.patch(
        "/api/chat/sessions/{session_id}/live-conversation/profile",
        response_model=LiveConversationProfileEnvelope,
        tags=["live-chat"],
    )
    def update_live_conversation_profile(
        session_id: str,
        request: LiveConversationProfileUpdate,
    ) -> LiveConversationProfileEnvelope:
        require_session(session_id)
        return live_conversation_profile_store_factory().update(session_id, request)

    @router.delete(
        "/api/chat/sessions/{session_id}/live-conversation/profile",
        response_model=LiveConversationProfileEnvelope,
        tags=["live-chat"],
    )
    def clear_live_conversation_profile(session_id: str) -> LiveConversationProfileEnvelope:
        require_session(session_id)
        return live_conversation_profile_store_factory().clear(session_id)

    @router.get(
        "/api/chat/sessions/{session_id}/live-call/runtime",
        response_model=CharacterLiveCallRuntime,
        tags=["characters"],
    )
    def get_live_call_runtime(session_id: str) -> CharacterLiveCallRuntime:
        session = require_session(session_id)
        try:
            return resolve_live_call_runtime(session, character_service_factory=service_factory)
        except (CharacterNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/chat/sessions/{session_id}/live-call/greeting/stream",
        tags=["characters"],
        response_model=None,
        responses={
            200: {
                "description": "Live-call greeting generation events as Server-Sent Events.",
                "content": {"text/event-stream": {"schema": {"type": "string"}}},
            }
        },
    )
    def stream_live_call_greeting(
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
            except Exception as exc:  # noqa: BLE001 - provider failures become SSE errors
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

    @router.post(
        "/api/chat/sessions/{session_id}/live-conversation/proactive/delivery",
        response_model=ProactiveDeliveryResponse,
        tags=["live-chat"],
    )
    def commit_live_conversation_proactive_delivery(
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
__all__ = ["register_character_integration_routes"]
