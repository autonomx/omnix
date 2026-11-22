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
    CompanionInitiativeAuthorityStore, InitiativeAcquireRequest, SceneTalkAttemptRequest,
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
    GREETING_WAIT_SECONDS,
    PROACTIVE_TURN_WAIT_SECONDS,
    ProactiveDeliveryRequest,
    ProactiveDeliveryResponse,
    SCENE_SPEAKER_HEADER,
    SceneTalkMaterial,
    camera_share_look,
    claim_proposal_report,
    commit_proactive_delivery,
    direct_scene_reaction,
    direct_scene_talk,
    is_open_loop_reason,
    is_scene_reason,
    is_scene_reaction_reason,
    is_scene_turn_id,
    open_loop_material,
    reported_task_id,
    load_scene,
    scene_reaction_opening,
    scene_talk_kind,
    scene_talk_opening,
    seconds_since_last_message,
    stream_proactive_turn_chunks,
    task_report_material,
)
from app.runtime.tenant_context import LOCAL_USER_ID, current_tenant
from app.platform.characters.contracts import CharacterLiveCallRuntime, LiveCallSceneGuest, resolve_live_call_runtime
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


class SceneTurnReleaseRequest(BaseModel):
    turn_id: str = Field(min_length=1, max_length=512)


class SceneTurnReleaseResponse(BaseModel):
    released: bool


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
    if reported_task_id(reason=reason.strip()) is not None:
        # The person asked for this work: its report outranks social initiative and waits only briefly.
        return "task", "voice", "high", "idle_only", 4.0
    if normalized.startswith("desktop_companion:"):
        return "desktop", "text", "normal", "idle_only", 4.0
    if normalized == "ambient_visual_presence":
        return "ambient", "voice", "normal", "idle_only", 25.0
    if is_scene_reason(normalized):
        # A reaction or a line follows a reply at once or not at all, and an opener waits out the level's silence
        # (companion 6.4): code's checks and the talk cap are the limits, not spacing.
        return "scene", "voice", "normal", "idle_only", 0.0
    return "social", "voice", "normal", "idle_only", 25.0

_AUTHORITY_LOST_EVENT = "data: " + json.dumps(
    {"type": "error", "message": "Companion initiative authority expired or was preempted."}, sort_keys=True,
) + "\n\n"


def _finish_unused_lease(authority: Any, lease: Any, session_id: str) -> None:
    """Give back a lease taken for a turn that will not stream, so the next initiative need not wait out its TTL."""
    if authority is not None and lease is not None:
        authority.finish(session_id=session_id, lease_id=lease.lease_id, finished_at=_utcnow(), delivered=False)


def _checked_initiative_materials(
    session: ChatSession,
    initiative_reason: str,
    purpose: str,
    job_store_factory: Callable[[], Any] | None,
) -> tuple[Any, Any]:
    """What the server checked for a reason that names a task or an open loop; 409 when not due. Scene turns are
    checked under their lease (``_SceneAsk``)."""
    task_report = open_loop = None
    if reported_task_id(reason=initiative_reason) is not None:
        # A report names a task; the server checks it is this chat's, settled and not yet reported.
        if purpose != "proactive_reengagement" or job_store_factory is None:
            raise HTTPException(status_code=409, detail="task_report_unavailable")
        task_report = task_report_material(session, job_store_factory(), initiative_reason)
        if task_report is None:
            raise HTTPException(status_code=409, detail="task_report_not_due")
    if is_open_loop_reason(initiative_reason):
        # An open loop names the speaker's own memory; the server checks it is still open and not yet raised.
        if purpose != "proactive_reengagement":
            raise HTTPException(status_code=409, detail="open_loop_unavailable")
        open_loop = open_loop_material(session, initiative_reason)
        if open_loop is None:
            raise HTTPException(status_code=409, detail="open_loop_not_due")
    return task_report, open_loop


def _scene_attempt_kind(reason: str) -> str | None:
    """The attempt a scene reason asks for: ``reaction`` (5.4), ``line`` or ``start`` (6); else None."""
    if is_scene_reaction_reason(reason):
        return "reaction"
    kind = scene_talk_kind(reason)
    return None if kind is None else "line" if kind == "line" else "start"


def _account_id() -> str:
    """Whose talk cap an attempt counts against: the signed-in account, or the single local one."""
    try:
        return current_tenant().user_id
    except RuntimeError:
        return LOCAL_USER_ID


class _SceneAsk:
    """A scene turn the client asked for (companion 5.4, 6): the setting's checks, the opening it would follow,
    and its attempt's outcome, recorded once on the authority."""

    _DETAIL = {"reaction": "scene_reaction", "line": "scene_line", "start": "scene_talk"}

    def __init__(self, kind: str, profile: Any, *, switched_off: bool) -> None:
        self.kind = kind
        self.profile = profile
        self.switched_off = switched_off
        self.detail = self._DETAIL[kind]

    def refuse(self, reason: str) -> HTTPException:
        return HTTPException(status_code=409, detail=f"{self.detail}_{reason}")

    def check_setting(self) -> None:
        """The setting and the per-call switch: with talk on, a reply is followed by a capped line, never the
        uncapped reaction; the switch's flag can only narrow (6.1, 6.2)."""
        talk_on = bool(self.profile.scene_talk_enabled) and not self.switched_off
        if self.kind == "reaction":
            if talk_on:
                raise HTTPException(status_code=409, detail="scene_talk_on")
            return
        if not talk_on:
            raise HTTPException(status_code=409, detail="scene_talk_off")
        if self.kind == "start" and (self.profile.initiative_mode == "off"
                                     or int(self.profile.max_initiatives_per_hour) <= 0):
            raise HTTPException(status_code=409, detail="scene_talk_starts_off")

    def opening(self, session: Any, now: datetime) -> tuple[Any, Any] | None:
        """The scene and the opening this turn would follow now, or None when it is not due."""
        if self.kind == "reaction":
            return scene_reaction_opening(session)
        if self.kind == "line":
            return scene_talk_opening(session, "line", max_lines=int(self.profile.scene_talk_max_lines))
        quiet = seconds_since_last_message(session.messages, now)
        if quiet is None or quiet < self.profile.scene_talk_silence_seconds():
            return None
        return scene_talk_opening(session, "talk", max_lines=int(self.profile.scene_talk_max_lines))

    def attempt(self, opening: Any) -> SceneTalkAttemptRequest:
        """The attempt the lease records. A line answering the person (a thread they started) is not counted
        against the hourly cap (group calls, 2026-11-19): the thread's line limit and a SKIP bound it."""
        answering_person = self.kind == "line" and getattr(opening, "start_kind", "") == "person"
        return SceneTalkAttemptRequest(user_id=_account_id(), anchor_message_id=opening.anchor_id, kind=self.kind,
                                       attempts_per_hour=self.profile.scene_talk_attempt_cap(),
                                       counted=not answering_person)

    def direct(self, session: Any, scene: Any, opening: Any) -> Any:
        """Who speaks: the model proposes, code checks the name (None: nobody)."""
        if self.kind == "reaction":
            return direct_scene_reaction(session, scene, opening)
        return direct_scene_talk(session, scene, opening, "line" if self.kind == "line" else "talk")

    def material(self, opening: Any) -> SceneTalkMaterial | None:
        if self.kind == "reaction":
            return None
        return SceneTalkMaterial(kind="line" if self.kind == "line" else "talk", opening=opening)

    def record(self, authority: Any, lease: Any, outcome: str, *, streamed_text: str | None = None) -> None:
        """Set the attempt's outcome once; a start that says nothing backs off further starts (6.2)."""
        if authority is None or lease is None:
            return
        backoff = (2.0 * self.profile.scene_talk_silence_seconds()
                   if self.kind == "start" and outcome in {"declined", "skipped"} else 0.0)
        try:
            authority.record_scene_attempt(attempt_id=lease.lease_id, outcome=outcome, finished_at=_utcnow(),
                                           streamed_text=streamed_text, start_backoff_seconds=backoff)
        except Exception:  # noqa: BLE001 - the lease's TTL and the commit's checks still hold
            logger.warning("scene talk attempt outcome was not recorded", exc_info=True)


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
    job_store_factory: Callable[[], Any] | None = None,
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
            runtime = resolve_live_call_runtime(session, character_service_factory=service_factory)
        except (CharacterNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _with_scene_guests(session, runtime)

    def _with_scene_guests(session: ChatSession, runtime: CharacterLiveCallRuntime) -> CharacterLiveCallRuntime:
        """Each guest's voice and face, resolved from that guest's own view of the session (companion 5.5)."""
        from app.conversation.scene import speaking_as

        try:
            scene = load_scene(session)
        except Exception:  # noqa: BLE001 - the call still starts, with its host alone
            logger.warning("scene unavailable for the live-call runtime of chat %s", session.id, exc_info=True)
            return runtime
        if scene is None:
            return runtime
        guests: list[LiveCallSceneGuest] = []
        for guest in scene.guests:
            try:
                guest_runtime = resolve_live_call_runtime(
                    speaking_as(session, scene.with_speaker(guest.character_id)),
                    character_service_factory=service_factory,
                )
            except (CharacterNotFoundError, ValueError):
                continue
            guests.append(LiveCallSceneGuest(
                character_id=guest.character_id,
                display_name=guest_runtime.display_name,
                voice_asset_id=guest_runtime.voice_asset_id,
                voice_speaker_id=guest_runtime.voice_speaker_id,
                avatar_pack=guest_runtime.avatar_pack,
                speech_style=guest_runtime.speech_style,
            ))
        return runtime.model_copy(update={"scene_guests": guests})

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
        scene_talk_switched_off: bool = Query(default=False),
        camera_shared: bool = Query(default=False),
    ) -> StreamingResponse:
        store = chat_store_factory()
        session = require_session(session_id)
        authority: CompanionInitiativeAuthorityStore | None = None
        lease = None
        task_report, open_loop = _checked_initiative_materials(session, initiative_reason, purpose, job_store_factory)
        scene_kind = _scene_attempt_kind(initiative_reason)
        scene_ask: _SceneAsk | None = None
        preliminary = None
        if scene_kind is not None:
            # Another call member may react to a reply (5.4), add a line to a thread or open talk (6).
            scene_ask = _SceneAsk(scene_kind, live_conversation_profile_store_factory().get(session_id).effective,
                                  switched_off=scene_talk_switched_off)
            if purpose != "proactive_reengagement":
                raise scene_ask.refuse("unavailable")
            scene_ask.check_setting()
            # A first look, for the anchor the attempt names; the turn is decided again under the lease.
            preliminary = scene_ask.opening(session, _utcnow())
            if preliminary is None:
                raise scene_ask.refuse("not_due")
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
                    scene_talk=(None if scene_ask is None or preliminary is None
                                else scene_ask.attempt(preliminary[1])),
                )
            )
            if not decision.accepted or decision.lease is None:
                raise HTTPException(status_code=409, detail=decision.reason)
            lease = decision.lease
        reaction = None
        speaker_session = session
        headers: dict[str, str] | None = None
        scene_refusal: HTTPException | None = None
        claimed = True
        try:
            # The person's next turn may confirm a proposal only after its question began (live_agent_store).
            claimed = (task_report is None or not task_report.proposal_message_id
                       or claim_proposal_report(store, session, task_report))
            if scene_ask is not None and preliminary is not None:
                # Under the lease, from the session as it is now (6.3): the opening must still follow the anchor
                # the attempt names, then the model proposes who speaks and code checks the name.
                session = require_session(session_id)
                current = scene_ask.opening(session, _utcnow())
                if current is None or current[1].anchor_id != preliminary[1].anchor_id:
                    scene_ask.record(authority, lease, "failed")
                    scene_refusal = scene_ask.refuse("not_due")
                else:
                    reaction = scene_ask.direct(session, *current)
                    if reaction is None:
                        scene_ask.record(authority, lease, "declined")
                        scene_refusal = scene_ask.refuse("declined")
                    else:
                        preliminary = current
        except Exception:
            if scene_ask is not None:
                scene_ask.record(authority, lease, "failed")
            _finish_unused_lease(authority, lease, session_id)
            raise
        if not claimed:
            _finish_unused_lease(authority, lease, session_id)
            raise HTTPException(status_code=409, detail="task_report_not_due")
        if scene_refusal is not None:
            _finish_unused_lease(authority, lease, session_id)
            raise scene_refusal
        scene_talk = None
        if reaction is not None and scene_ask is not None and preliminary is not None:
            initiative_reason = reaction.reason
            speaker_session = reaction.view
            headers = {SCENE_SPEAKER_HEADER: reaction.speaker_id}
            scene_talk = scene_ask.material(reaction.opening)

        def generate():
            bound_lease = None
            released = False
            handed_off = False

            def release_without_delivery() -> None:
                nonlocal released
                if released or authority is None or lease is None:
                    return
                if scene_ask is not None:
                    # A scene turn that ends here undelivered failed, unless its outcome is already set.
                    scene_ask.record(authority, lease, "failed")
                authority.finish(
                    session_id=session_id,
                    lease_id=lease.lease_id,
                    finished_at=_utcnow(),
                    delivered=False,
                )
                released = True
            try:
                # The camera the person shares (camera share): the web glanced just before asking for this turn.
                camera = (
                    None if not camera_shared or task_report is not None or open_loop is not None
                    or reaction is not None
                    else camera_share_look(session_id, wait_seconds=PROACTIVE_TURN_WAIT_SECONDS)
                    if purpose == "proactive_reengagement"
                    else camera_share_look(session_id, wait_seconds=GREETING_WAIT_SECONDS)
                )
                events = (
                    stream_proactive_turn_chunks(
                        store,
                        speaker_session,
                        initiative_reason=initiative_reason,
                        state_summary=state_summary,
                        task_report=task_report,
                        open_loop=open_loop,
                        scene_reaction=(reaction.opening if reaction is not None and scene_talk is None else None),
                        scene_talk=scene_talk,
                        camera=camera,
                    )
                    if purpose == "proactive_reengagement"
                    else stream_live_call_greeting_chunks(store, session, camera=camera)
                )
                for event in events:
                    if scene_ask is not None and event.get("type") == "complete":
                        # Recorded before the client can see it: the commit saves this text, never the client's.
                        if _proactive_event_is_skip(event):
                            scene_ask.record(authority, lease, "skipped")
                        else:
                            scene_ask.record(authority, lease, "streamed",
                                             streamed_text=str(event.get("content") or ""))
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
                                yield _AUTHORITY_LOST_EVENT
                                return
                        if bound_lease is not None and not authority.authorizes(
                            bound_lease,
                            now=_utcnow(),
                        ):
                            yield _AUTHORITY_LOST_EVENT
                            return
                    yield f"data: {json.dumps(event, sort_keys=True)}\n\n"
                    if authority is not None and _proactive_event_is_skip(event):
                        release_without_delivery()
                if authority is not None and lease is not None and not released:
                    if bound_lease is None:
                        release_without_delivery()
                    elif not authority.authorizes(bound_lease, now=_utcnow()):
                        yield _AUTHORITY_LOST_EVENT
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
        return StreamingResponse(generate(), media_type="text/event-stream", headers=headers)

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
        scene_anchor_id: str | None = None
        if not already_committed:
            authority = initiative_authority_factory()
            if is_scene_turn_id(request.turn_id):
                # A scene turn saves what the server recorded as streamed under its lease, never the client's
                # words, and remembers the message it followed for the late check (companion 6.3).
                attempt = authority.active_scene_attempt(session_id, now=_utcnow(), intent_id=request.turn_id)
                if attempt is None or attempt.outcome != "streamed" or not attempt.streamed_text:
                    raise HTTPException(status_code=409, detail="initiative_lease_inactive")
                request = request.model_copy(update={"content": attempt.streamed_text})
                scene_anchor_id = attempt.anchor_message_id
            finished = authority.finish_intent(
                session_id=session_id,
                intent_id=request.turn_id,
                finished_at=_utcnow(),
                delivered=True,
            )
            if not finished:
                raise HTTPException(status_code=409, detail="initiative_lease_inactive")
        result = commit_proactive_delivery(store, session_id, request, scene_anchor_id=scene_anchor_id)
        if result is None:
            raise HTTPException(status_code=404, detail="chat session not found")
        return result

    @router.post(
        "/api/chat/sessions/{session_id}/live-conversation/proactive/release",
        response_model=SceneTurnReleaseResponse,
        tags=["live-chat"],
    )
    def release_live_conversation_scene_turn(
        session_id: str,
        request: SceneTurnReleaseRequest,
    ) -> SceneTurnReleaseResponse:
        """A scene turn the call dropped before it played gives its lease back now, not at its TTL (companion 6.3)."""
        require_session(session_id)
        if not is_scene_turn_id(request.turn_id):
            raise HTTPException(status_code=422, detail="not_a_scene_turn")
        released = initiative_authority_factory().finish_intent(
            session_id=session_id,
            intent_id=request.turn_id,
            finished_at=_utcnow(),
            delivered=False,
        )
        return SceneTurnReleaseResponse(released=released)

__all__ = ["register_character_integration_routes"]
