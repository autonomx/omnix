"""Thin browser-facing gateway foundation."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.assistant_tools import AssistantToolRegistryPayload, assistant_tool_registry_payload
from app.assistant_context import register_assistant_context_routes
from app.assets import (
    AssetLegacyImportDryRun,
    AssetListResponse,
    AssetMigrationPreview,
    AssetRecord,
    AssetType,
    SharedAssetStore,
    default_asset_store,
)
from app.chat import (
    ChatSession,
    ChatSessionListResponse,
    ChatSessionStore,
    CreateChatSessionRequest,
    DeleteChatSessionResponse,
    SendChatMessageRequest,
    SendChatMessageResponse,
    default_chat_store,
)
from app.chat.generation_jobs import (
    cancel_chat_generation_job,
    chat_submission_lock,
    existing_chat_generation_turn,
    find_chat_generation_job,
    mark_chat_acceptance_failed,
    recover_abandoned_chat_generation_jobs,
    start_chat_generation_job,
)
from app.jobs import (
    CancelJobRequest,
    ClaimJobRequest,
    ClaimJobResponse,
    CompleteJobRequest,
    CreateJobRequest,
    FailJobRequest,
    InMemoryJobStore,
    InMemoryModelResidencyStore,
    JobListResponse,
    JobRecord,
    ModelResidencyDiagnostics,
    ModelResidencyRecord,
    ResourceClass,
    default_job_store,
    default_model_residency_store,
)
from app.gateway.job_summaries import summarize_job
from app.platform import (
    DiagnosticsPayload,
    LegacyGenerateTitleRequest,
    LegacyGenerateTitleResponse,
    LegacySessionCreateResponse,
    LegacySessionListResponse,
    LegacySessionResponse,
    LegacySessionUpdateRequest,
    LegacySuccessResponse,
    ReportListResponse,
    SettingsPayload,
    SettingsSaveResponse,
    adventure_simulation_state_payload,
    compare_adventure_entity_payload,
    compare_adventure_world_payload,
    create_legacy_session,
    delete_legacy_session,
    generate_legacy_session_title,
    get_diagnostics_payload,
    get_legacy_session,
    get_rpg_session_payload,
    get_settings_payload,
    inspect_adventure_world_payload,
    inspect_adventure_world_snapshot_payload,
    inspect_npc_reasoning_payload,
    inspect_tick_diff_payload,
    inspect_timeline_payload,
    inspect_timeline_tick_payload,
    inspect_world_events_payload,
    list_adventure_templates_payload,
    list_legacy_sessions,
    list_report_artifacts,
    list_rpg_sessions_payload,
    player_codex_payload,
    player_encounter_payload,
    player_journal_payload,
    player_objectives_payload,
    player_state_payload,
    preview_adventure_payload,
    save_settings_payload,
    simulate_adventure_step_payload,
    update_legacy_session,
    validate_adventure_payload,
)
from app.platform.settings_profile_repository import load_settings_profile
from app.prompts import PromptRenderError, PromptRenderRequest, PromptTemplateRenderer, RenderedPrompt
from app.providers.cache_status import ProviderModelRefreshRequest, create_provider_model_refresh_job_request
from app.providers.facade import ProviderFacade, ProviderFacadePayload, default_provider_facade
from app.providers.chatgpt_codex_provider import ChatGPTCodexProvider
from app.shared import load_settings
from app.replay import (
    CheckpointEnvelope,
    PersistenceInventory,
    ReplayPrimitiveList,
    RpgReplayPersistenceAdapter,
    StateHashRequest,
    StateHashResponse,
    default_rpg_replay_adapter,
)

from .story_asset_save import SaveStoryAssetRequest, SavedStoryAssetResponse, save_story_asset
from . import _install_required_rpg_turn_hooks
from .workers import (
    GATEWAY_FORMAT_VERSION,
    WorkerHealthPayload,
    WorkerPayloadPolicy,
    get_worker_health_payload,
    get_worker_payload_policy,
)

DEFAULT_GATEWAY_HOST = "127.0.0.1"
DEFAULT_GATEWAY_PORT = 8000
EVENT_STREAM_BATCH_LIMIT = 100
EVENT_STREAM_POLL_SECONDS = 1.0
EVENT_STREAM_HEARTBEAT_SECONDS = 15.0
TEXT_ASSET_MAX_BYTES = 2_000_000
TEXT_ASSET_MIME_TYPES = {
    "application/json",
    "application/x-subrip",
    "text/html",
    "text/markdown",
    "text/plain",
    "text/vtt",
}
logger = logging.getLogger(__name__)


class GatewayHealth(BaseModel):
    ok: bool = True
    status: Literal["ready"] = "ready"
    service: Literal["omnix-gateway"] = "omnix-gateway"
    format_version: str = GATEWAY_FORMAT_VERSION


class RuntimeStatusPayload(BaseModel):
    ok: bool = True
    status: Literal["ready", "degraded"] = "ready"
    format_version: str = GATEWAY_FORMAT_VERSION
    gateway: GatewayHealth = Field(default_factory=GatewayHealth)
    workers: WorkerHealthPayload = Field(default_factory=WorkerHealthPayload)
    compatibility: dict[str, Any] = Field(default_factory=dict)


class CodexAuthStatus(BaseModel):
    installed: bool = False
    authenticated: bool = False
    auth_mode: str | None = None
    cli_version: str | None = None
    detail: str = ""
    started: bool = False
    pid: int | None = None


def _configured_codex_path() -> str:
    profile = load_settings_profile(load_settings())
    return profile.provider_configs.chatgpt_codex.codex_path


class CompatibilityHandoffPayload(BaseModel):
    ok: bool = True
    format_version: str = GATEWAY_FORMAT_VERSION
    legacy_ui_status: Literal["retired"] = "retired"
    existing_fastapi_app: str = "run_app:app"
    domain_logic_policy: str = "delegate_to_existing_service_modules"
    migration_note: str = (
        "The classic template/static browser UI is retired. Backend domain routes may remain "
        "as compatibility surfaces until feature-specific contracts are migrated."
    )
    handoff_targets: list[dict[str, str]] = Field(default_factory=list)


class AssetContentResponse(BaseModel):
    asset: AssetRecord
    content: str
    encoding: Literal["utf-8"] = "utf-8"
    size_bytes: int
    truncated: Literal[False] = False


def _compatibility_handoff() -> CompatibilityHandoffPayload:
    return CompatibilityHandoffPayload(
        handoff_targets=[
            {"namespace": "/api/rpg", "current_owner": "run_app:app and app.rpg.api routers", "gateway_phase": "future typed contract wrapper"},
            {"namespace": "/api/image", "current_owner": "app.image.api and image service", "gateway_phase": "future worker-backed image contract"},
            {"namespace": "/api/voice, /api/tts, /api/stt", "current_owner": "run_app:app, tts_server, parakeet_stt_server", "gateway_phase": "future worker health and job contract"},
            {"namespace": "/generated-images", "current_owner": "run_app:app static asset route", "gateway_phase": "future shared asset reference route"},
        ]
    )


def _runtime_status() -> RuntimeStatusPayload:
    workers = get_worker_health_payload()
    return RuntimeStatusPayload(
        ok=workers.ok,
        status="ready" if workers.ok else "degraded",
        gateway=GatewayHealth(),
        workers=workers,
        compatibility={"legacy_ui_status": "retired", "existing_fastapi_app": "run_app:app", "domain_logic_policy": "delegate_to_existing_service_modules"},
    )


def _sse_event(event_type: str, payload: dict[str, Any], event_id: int | None = None) -> str:
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event_type}")
    lines.append(f"data: {json.dumps(payload, sort_keys=True)}")
    return "\n".join(lines) + "\n\n"


def _sse_comment(comment: str) -> str:
    return f": {comment}\n\n"


def _parse_event_id(value: str | None, fallback: int = 0) -> int:
    if not value:
        return fallback
    try:
        return int(value)
    except ValueError:
        return fallback


def _text_asset_supported(asset: AssetRecord) -> bool:
    mime_type = asset.mime_type.lower().split(";", 1)[0]
    return mime_type.startswith("text/") or mime_type in TEXT_ASSET_MIME_TYPES


def _asset_by_id(asset_store: SharedAssetStore, asset_id: str) -> AssetRecord | None:
    get_asset = getattr(asset_store, "get_asset", None)
    if callable(get_asset):
        return get_asset(asset_id)
    return next((asset for asset in asset_store.list_assets().assets if asset.id == asset_id), None)


def _delete_legacy_voice_clone_files(asset: AssetRecord) -> dict[str, Any]:
    """Remove the local clone source and manifest entry so it cannot reappear."""
    import app.shared as shared

    clone_dir = Path(str(shared.VOICE_CLONES_DIR)).resolve()
    manifest_path = Path(str(shared.VOICE_CLONES_FILE)).resolve()
    metadata = dict(asset.metadata or {})
    identifiers = {
        str(value).strip().casefold()
        for value in (
            asset.id.removeprefix("voice-cloning:"),
            metadata.get("profile_name"),
            metadata.get("voice_id"),
            metadata.get("voice_clone_id"),
            metadata.get("speaker"),
        )
        if str(value or "").strip()
    }
    removed_ids: set[str] = set()
    manifest_changed = False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    except Exception:
        manifest = {}
    if isinstance(manifest, dict):
        for name, value in list(manifest.items()):
            row = value if isinstance(value, dict) else {}
            clone_id = str(row.get("voice_clone_id") or name).strip()
            if str(name).casefold() in identifiers or clone_id.casefold() in identifiers:
                manifest.pop(name, None)
                removed_ids.add(clone_id)
                manifest_changed = True
        if manifest_changed:
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    removed_ids.update(str(value) for value in identifiers if value)
    file_deleted = False
    for clone_id in removed_ids:
        for suffix in (".wav", ".mp3", ".mp4", ".m4a", ".webm", ".ogg", ".flac", ".json"):
            target = (clone_dir / f"{clone_id}{suffix}").resolve()
            if target.parent != clone_dir or target == manifest_path or not target.is_file():
                continue
            target.unlink()
            file_deleted = True
    return {"manifest_deleted": manifest_changed, "file_deleted": file_deleted}


def _read_text_asset(asset: AssetRecord) -> AssetContentResponse:
    if not _text_asset_supported(asset):
        raise HTTPException(status_code=415, detail="asset_content_not_text")
    path = Path(asset.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="asset_file_not_found")
    try:
        size_bytes = path.stat().st_size
    except OSError as exc:
        raise HTTPException(status_code=404, detail="asset_file_not_found") from exc
    if size_bytes > TEXT_ASSET_MAX_BYTES:
        raise HTTPException(status_code=413, detail="asset_content_too_large")
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=415, detail="asset_content_not_utf8") from exc
    except OSError as exc:
        raise HTTPException(status_code=404, detail="asset_file_not_found") from exc
    return AssetContentResponse(asset=asset, content=content, size_bytes=size_bytes)


async def _live_job_event_stream(job_store: InMemoryJobStore, after_id: int = 0):
    last_event_id = max(0, after_id)
    seconds_until_heartbeat = 0.0
    yield _sse_comment("omnix-events-open")
    while True:
        events = job_store.list_events(after_id=last_event_id, limit=EVENT_STREAM_BATCH_LIMIT)
        if events:
            for event in events:
                last_event_id = max(last_event_id, event.id)
                yield _sse_event(event.event_type, event.model_dump(mode="json"), event_id=event.id)
            seconds_until_heartbeat = 0.0
            continue
        if seconds_until_heartbeat <= 0:
            yield _sse_comment("heartbeat")
            seconds_until_heartbeat = EVENT_STREAM_HEARTBEAT_SECONDS
        await asyncio.sleep(EVENT_STREAM_POLL_SECONDS)
        seconds_until_heartbeat -= EVENT_STREAM_POLL_SECONDS


@asynccontextmanager
async def _gateway_lifespan(
    app: FastAPI,
    *,
    get_chat_store: Callable[[], ChatSessionStore],
    get_job_store: Callable[[], InMemoryJobStore],
):
    recovered = await asyncio.to_thread(
        recover_abandoned_chat_generation_jobs,
        get_chat_store(),
        get_job_store(),
    )
    if recovered:
        logger.warning("Recovered %s abandoned Chat generation job(s)", recovered)

    # The custom lifespan replaces Starlette's default lifespan, which is the
    # code path that normally runs router.on_startup/on_shutdown handlers.
    startup = getattr(app.router, "startup", None) or getattr(app.router, "_startup")
    await startup()
    try:
        yield
    finally:
        shutdown = getattr(app.router, "shutdown", None) or getattr(app.router, "_shutdown")
        await shutdown()


def create_gateway_app(
    job_store_factory: Callable[[], InMemoryJobStore] | None = None,
    provider_facade_factory: Callable[[], ProviderFacade] | None = None,
    asset_store_factory: Callable[[], SharedAssetStore] | None = None,
    chat_store_factory: Callable[[], ChatSessionStore] | None = None,
    replay_adapter_factory: Callable[[], RpgReplayPersistenceAdapter] | None = None,
    model_residency_store_factory: Callable[[], InMemoryModelResidencyStore] | None = None,
) -> FastAPI:
    _install_required_rpg_turn_hooks()
    get_job_store = job_store_factory or default_job_store
    get_provider_facade = provider_facade_factory or default_provider_facade
    get_asset_store = asset_store_factory or default_asset_store
    get_chat_store = chat_store_factory or default_chat_store
    get_replay_adapter = replay_adapter_factory or default_rpg_replay_adapter
    get_model_residency_store = model_residency_store_factory or default_model_residency_store

    def gateway_lifespan(_app: FastAPI):
        return _gateway_lifespan(
            _app,
            get_chat_store=get_chat_store,
            get_job_store=get_job_store,
        )

    gateway = FastAPI(
        title="Omnix Web Gateway",
        version="0.1.0",
        summary="Thin local-first gateway foundation for the Omnix web app redesign.",
        lifespan=gateway_lifespan,
    )
    _remove_hook_installed_assistant_context_routes(gateway)
    register_assistant_context_routes(
        gateway,
        chat_store_factory=get_chat_store,
        job_store_factory=get_job_store,
    )

    @gateway.get("/health", response_model=GatewayHealth, tags=["gateway"])
    async def health() -> GatewayHealth:
        return GatewayHealth()

    @gateway.get("/api/health", response_model=GatewayHealth, tags=["gateway"])
    async def api_health() -> GatewayHealth:
        return GatewayHealth()

    @gateway.get("/api/runtime/status", response_model=RuntimeStatusPayload, tags=["runtime"])
    async def runtime_status() -> RuntimeStatusPayload:
        return _runtime_status()

    @gateway.get("/api/workers/health", response_model=WorkerHealthPayload, tags=["workers"])
    async def worker_health() -> WorkerHealthPayload:
        return get_worker_health_payload()

    @gateway.get("/api/workers/payload-policy", response_model=WorkerPayloadPolicy, tags=["workers"])
    async def worker_payload_policy() -> WorkerPayloadPolicy:
        return get_worker_payload_policy()

    @gateway.get("/api/compatibility/legacy", response_model=CompatibilityHandoffPayload, tags=["compatibility"])
    async def compatibility_handoff() -> CompatibilityHandoffPayload:
        return _compatibility_handoff()

    @gateway.get("/api/assistant/tools", response_model=AssistantToolRegistryPayload, tags=["assistant-tools"])
    async def assistant_tools() -> AssistantToolRegistryPayload:
        return assistant_tool_registry_payload()

    @gateway.get("/api/chat/sessions", response_model=ChatSessionListResponse, tags=["chat"])
    async def chat_sessions() -> ChatSessionListResponse:
        return get_chat_store().list_sessions()

    @gateway.post("/api/chat/sessions", response_model=ChatSession, tags=["chat"])
    async def create_chat_session(request: CreateChatSessionRequest) -> ChatSession:
        return get_chat_store().create_session(request)

    @gateway.get("/api/chat/sessions/{session_id}", response_model=ChatSession, tags=["chat"])
    async def chat_session(session_id: str) -> ChatSession:
        session = get_chat_store().get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="chat session not found")
        return session

    @gateway.delete("/api/chat/sessions/{session_id}", response_model=DeleteChatSessionResponse, tags=["chat"])
    async def delete_chat_session(session_id: str) -> DeleteChatSessionResponse:
        if not get_chat_store().delete_session(session_id):
            raise HTTPException(status_code=404, detail="chat session not found")
        return DeleteChatSessionResponse(session_id=session_id)

    @gateway.post("/api/chat/sessions/{session_id}/messages", response_model=SendChatMessageResponse, tags=["chat"])
    async def send_chat_message(session_id: str, request: SendChatMessageRequest) -> SendChatMessageResponse:
        chat_store = get_chat_store()
        job_store = get_job_store()
        with chat_submission_lock(session_id, request.user_turn_id):
            existing_job = find_chat_generation_job(
                job_store,
                session_id=session_id,
                submission_id=request.user_turn_id,
            )
            if existing_job is not None:
                existing_turn = existing_chat_generation_turn(chat_store, existing_job)
                if existing_turn is not None:
                    session, user_message = existing_turn
                    return SendChatMessageResponse(
                        session=session,
                        user_message=user_message,
                        job=existing_job,
                    )
                raise HTTPException(
                    status_code=409,
                    detail="accepted chat submission is missing its user message",
                )
            appended = chat_store.begin_user_message(session_id, request)
            if appended is None:
                raise HTTPException(status_code=404, detail="chat session not found")
            session, user_message = appended
            try:
                job = job_store.create_job(
                    CreateJobRequest(
                        module="chatbot",
                        type="chat.generate",
                        resource_class=ResourceClass.GPU_LLM,
                        input_ref={"session_id": session.id, "message_id": user_message.id},
                        input_payload={
                            "session_id": session.id,
                            "message_id": user_message.id,
                            "submission_id": request.user_turn_id,
                            "provider_id": request.provider_id or session.provider_id,
                            "model_id": request.model_id or session.model_id,
                            "request": request.model_dump(mode="json"),
                        },
                        compat={"contract": "chat_session_v1", "inline_execution": True},
                    )
                )
            except Exception as exc:
                mark_chat_acceptance_failed(
                    chat_store,
                    session_id=session.id,
                    message_id=user_message.id,
                    error=exc,
                )
                raise HTTPException(
                    status_code=503,
                    detail="chat generation could not be queued",
                ) from exc
        job = start_chat_generation_job(
            chat_store=chat_store,
            job_store=job_store,
            job=job,
            request=request,
        )
        return SendChatMessageResponse(session=session, user_message=user_message, job=job)

    @gateway.post("/api/chat/sessions/{session_id}/messages/stream", tags=["chat"])
    async def stream_chat_message(session_id: str, request: SendChatMessageRequest) -> StreamingResponse:
        chat_store = get_chat_store()
        appended = await asyncio.to_thread(chat_store.begin_user_message, session_id, request)
        if appended is None:
            raise HTTPException(status_code=404, detail="chat session not found")
        session, user_message = appended

        def generate():
            yield f"data: {json.dumps({'type': 'user_message', 'message': user_message.model_dump(mode='json')}, sort_keys=True)}\n\n"
            content = ""
            metadata: dict[str, Any] = {"generation_status": "completed"}
            completed = None
            reply_persisted = False
            try:
                for event in chat_store.stream_provider_reply_chunks(
                    session,
                    user_message,
                    provider_id=request.provider_id or session.provider_id,
                    model_id=request.model_id or session.model_id,
                ):
                    if event.get("type") == "complete":
                        content = str(event.get("content") or "").strip()
                        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else metadata
                        # Persist at the provider completion boundary, before the
                        # completion event is yielded. Live voice playback can
                        # outlast LLM generation and a later barge-in may close
                        # the HTTP body before the session footer is requested.
                        completed = chat_store.complete_streamed_reply(
                            session.id,
                            user_message.id,
                            content,
                            metadata,
                        )
                        reply_persisted = True
                    yield f"data: {json.dumps(event, sort_keys=True)}\n\n"
                if not reply_persisted:
                    completed = chat_store.complete_streamed_reply(
                        session.id,
                        user_message.id,
                        content,
                        metadata,
                    )
                if completed is not None:
                    yield f"data: {json.dumps({'type': 'session', 'session': completed.model_dump(mode='json')}, sort_keys=True)}\n\n"
                yield f"data: {json.dumps({'type': 'done'}, sort_keys=True)}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc) or 'Chat stream failed.'}, sort_keys=True)}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    @gateway.get("/api/providers", response_model=ProviderFacadePayload, tags=["providers"])
    async def providers() -> ProviderFacadePayload:
        return get_provider_facade().payload()

    @gateway.get("/api/models", response_model=ProviderFacadePayload, tags=["providers"])
    async def models() -> ProviderFacadePayload:
        return get_provider_facade().payload()

    @gateway.get("/api/providers/chatgpt-codex/auth", response_model=CodexAuthStatus, tags=["providers"])
    async def chatgpt_codex_auth_status() -> CodexAuthStatus:
        return ChatGPTCodexProvider.auth_status(_configured_codex_path())

    @gateway.post("/api/providers/chatgpt-codex/login", response_model=CodexAuthStatus, tags=["providers"])
    async def chatgpt_codex_login() -> CodexAuthStatus:
        return ChatGPTCodexProvider.start_login(_configured_codex_path())

    @gateway.post("/api/providers/refresh", response_model=JobRecord, tags=["providers"])
    async def refresh_providers(request: ProviderModelRefreshRequest) -> JobRecord:
        return get_job_store().create_job(create_provider_model_refresh_job_request(request))

    @gateway.post("/api/models/refresh", response_model=JobRecord, tags=["providers"])
    async def refresh_models(request: ProviderModelRefreshRequest) -> JobRecord:
        return get_job_store().create_job(create_provider_model_refresh_job_request(request))

    @gateway.get("/api/settings", response_model=SettingsPayload, tags=["settings"])
    async def settings() -> SettingsPayload:
        return get_settings_payload()

    @gateway.post("/api/settings", response_model=SettingsSaveResponse, tags=["settings"])
    async def save_settings(request: dict[str, Any]) -> SettingsSaveResponse:
        return save_settings_payload(request)

    @gateway.get("/api/sessions", response_model=LegacySessionListResponse, tags=["legacy-sessions"])
    async def legacy_sessions() -> LegacySessionListResponse:
        return list_legacy_sessions()

    @gateway.post("/api/sessions", response_model=LegacySessionCreateResponse, tags=["legacy-sessions"])
    async def create_session() -> LegacySessionCreateResponse:
        return create_legacy_session()

    @gateway.post("/api/sessions/generate-title", response_model=LegacyGenerateTitleResponse, tags=["legacy-sessions"])
    async def generate_session_title(request: LegacyGenerateTitleRequest) -> LegacyGenerateTitleResponse:
        return generate_legacy_session_title(request)

    @gateway.get("/api/sessions/{session_id}", response_model=LegacySessionResponse, tags=["legacy-sessions"])
    async def legacy_session(session_id: str) -> LegacySessionResponse:
        session = get_legacy_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Not found")
        return session

    @gateway.put("/api/sessions/{session_id}", response_model=LegacySuccessResponse, tags=["legacy-sessions"])
    async def update_session(session_id: str, request: LegacySessionUpdateRequest) -> LegacySuccessResponse:
        result = update_legacy_session(session_id, request)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        return result

    @gateway.delete("/api/sessions/{session_id}", response_model=LegacySuccessResponse, tags=["legacy-sessions"])
    async def delete_session(session_id: str) -> LegacySuccessResponse:
        result = delete_legacy_session(session_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        return result

    @gateway.get("/api/rpg/adventure/templates", tags=["rpg-adventure-compat"])
    async def rpg_adventure_templates() -> dict[str, Any]:
        return list_adventure_templates_payload()

    @gateway.post("/api/rpg/adventure/validate", tags=["rpg-adventure-compat"])
    async def rpg_adventure_validate(request: dict[str, Any]) -> dict[str, Any]:
        return validate_adventure_payload(request)

    @gateway.post("/api/rpg/adventure/preview", tags=["rpg-adventure-compat"])
    async def rpg_adventure_preview(request: dict[str, Any]) -> dict[str, Any]:
        return preview_adventure_payload(request)

    @gateway.post("/api/rpg/adventure/inspect-world", tags=["rpg-adventure-compat"])
    async def rpg_adventure_inspect_world(request: dict[str, Any]) -> dict[str, Any]:
        return inspect_adventure_world_payload(request)

    @gateway.post("/api/rpg/adventure/inspect-world-snapshot", tags=["rpg-adventure-compat"])
    async def rpg_adventure_inspect_world_snapshot(request: dict[str, Any]) -> dict[str, Any]:
        return inspect_adventure_world_snapshot_payload(request)

    @gateway.post("/api/rpg/adventure/compare-world", tags=["rpg-adventure-compat"])
    async def rpg_adventure_compare_world(request: dict[str, Any]) -> dict[str, Any]:
        return compare_adventure_world_payload(request)

    @gateway.post("/api/rpg/adventure/compare-entity", tags=["rpg-adventure-compat"])
    async def rpg_adventure_compare_entity(request: dict[str, Any]) -> dict[str, Any]:
        return compare_adventure_entity_payload(request)

    @gateway.post("/api/rpg/adventure/simulate-step", tags=["rpg-adventure-compat"])
    async def rpg_adventure_simulate_step(request: dict[str, Any]) -> dict[str, Any]:
        return simulate_adventure_step_payload(request)

    @gateway.post("/api/rpg/adventure/simulation-state", tags=["rpg-adventure-compat"])
    async def rpg_adventure_simulation_state(request: dict[str, Any]) -> dict[str, Any]:
        return adventure_simulation_state_payload(request)

    @gateway.post("/api/rpg/session/list", tags=["rpg-session-compat"])
    async def rpg_session_list() -> dict[str, Any]:
        return list_rpg_sessions_payload()

    @gateway.post("/api/rpg/session/get", tags=["rpg-session-compat"])
    def rpg_session_get(request: dict[str, Any]) -> dict[str, Any]:
        return get_rpg_session_payload(request)

    @gateway.post("/api/rpg/inspect/timeline", tags=["rpg-inspection-compat"])
    async def rpg_inspect_timeline(request: dict[str, Any]) -> dict[str, Any]:
        return inspect_timeline_payload(request)

    @gateway.post("/api/rpg/inspect/timeline_tick", tags=["rpg-inspection-compat"])
    async def rpg_inspect_timeline_tick(request: dict[str, Any]) -> dict[str, Any]:
        return inspect_timeline_tick_payload(request)

    @gateway.post("/api/rpg/inspect/tick_diff", tags=["rpg-inspection-compat"])
    async def rpg_inspect_tick_diff(request: dict[str, Any]) -> dict[str, Any]:
        return inspect_tick_diff_payload(request)

    @gateway.post("/api/rpg/inspect/npc_reasoning", tags=["rpg-inspection-compat"])
    async def rpg_inspect_npc_reasoning(request: dict[str, Any]) -> dict[str, Any]:
        return inspect_npc_reasoning_payload(request)

    @gateway.post("/api/rpg/inspect/world_events", tags=["rpg-inspection-compat"])
    async def rpg_inspect_world_events(request: dict[str, Any]) -> dict[str, Any]:
        return inspect_world_events_payload(request)

    @gateway.post("/api/rpg/player/state", tags=["rpg-player-compat"])
    async def rpg_player_state(request: dict[str, Any]) -> dict[str, Any]:
        return player_state_payload(request)

    @gateway.post("/api/rpg/player/journal", tags=["rpg-player-compat"])
    async def rpg_player_journal(request: dict[str, Any]) -> dict[str, Any]:
        return player_journal_payload(request)

    @gateway.post("/api/rpg/player/codex", tags=["rpg-player-compat"])
    async def rpg_player_codex(request: dict[str, Any]) -> dict[str, Any]:
        return player_codex_payload(request)

    @gateway.post("/api/rpg/player/objectives", tags=["rpg-player-compat"])
    async def rpg_player_objectives(request: dict[str, Any]) -> dict[str, Any]:
        return player_objectives_payload(request)

    @gateway.post("/api/rpg/player/encounter", tags=["rpg-player-compat"])
    async def rpg_player_encounter(request: dict[str, Any]) -> dict[str, Any]:
        return player_encounter_payload(request)

    @gateway.get("/api/reports", response_model=ReportListResponse, tags=["reports"])
    async def reports() -> ReportListResponse:
        return list_report_artifacts()

    @gateway.get("/api/diagnostics", response_model=DiagnosticsPayload, tags=["diagnostics"])
    async def diagnostics() -> DiagnosticsPayload:
        return get_diagnostics_payload(model_residency_records=get_model_residency_store().list_records())

    @gateway.get("/api/model-residency", response_model=ModelResidencyDiagnostics, tags=["models"])
    async def model_residency() -> ModelResidencyDiagnostics:
        return get_model_residency_store().diagnostics()

    @gateway.post("/api/model-residency", response_model=ModelResidencyDiagnostics, tags=["models"])
    async def report_model_residency(record: ModelResidencyRecord) -> ModelResidencyDiagnostics:
        store = get_model_residency_store()
        store.upsert_record(record)
        return store.diagnostics()

    @gateway.delete("/api/model-residency/{model_id}", response_model=ModelResidencyDiagnostics, tags=["models"])
    async def delete_model_residency(model_id: str) -> ModelResidencyDiagnostics:
        store = get_model_residency_store()
        store.delete_record(model_id)
        return store.diagnostics()

    @gateway.get("/api/assets", response_model=AssetListResponse, tags=["assets"])
    async def assets() -> AssetListResponse:
        return get_asset_store().list_assets()

    @gateway.get("/api/assets/{asset_id}/content", response_model=AssetContentResponse, include_in_schema=False)
    async def asset_content(asset_id: str) -> AssetContentResponse:
        asset = _asset_by_id(get_asset_store(), asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="asset_not_found")
        return _read_text_asset(asset)

    @gateway.delete("/api/voice-cloning/assets/{asset_id}", include_in_schema=False)
    def delete_voice_clone_asset(asset_id: str) -> dict[str, Any]:
        store = get_asset_store()
        asset = _asset_by_id(store, asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="asset_not_found")
        if asset.type != AssetType.VOICE_PROFILE or asset.module != "voice-cloning":
            raise HTTPException(status_code=409, detail="asset_not_voice_clone")
        shared_result = store.delete_asset(asset_id)
        legacy_result = _delete_legacy_voice_clone_files(asset)
        deleted = bool(shared_result.get("deleted")) or bool(legacy_result.get("manifest_deleted"))
        if not deleted:
            raise HTTPException(status_code=404, detail="asset_not_deletable")
        return {
            "ok": True,
            "asset_id": asset_id,
            "deleted": True,
            "file_deleted": bool(shared_result.get("file_deleted")) or bool(legacy_result.get("file_deleted")),
        }

    @gateway.post("/api/assets/story", response_model=SavedStoryAssetResponse, include_in_schema=False)
    async def save_story_asset_endpoint(request: SaveStoryAssetRequest) -> SavedStoryAssetResponse:
        return save_story_asset(get_asset_store(), request)

    @gateway.post("/api/assets/migrations/image/dry-run", response_model=AssetMigrationPreview, tags=["assets"])
    async def image_asset_migration_dry_run() -> AssetMigrationPreview:
        return get_asset_store().import_image_manifest_dry_run()

    @gateway.post("/api/assets/migrations/image/import", response_model=AssetMigrationPreview, tags=["assets"])
    async def image_asset_migration_import() -> AssetMigrationPreview:
        return get_asset_store().import_image_manifest()

    @gateway.post(
        "/api/assets/migrations/legacy-non-image/dry-run",
        response_model=AssetLegacyImportDryRun,
        tags=["assets"],
    )
    async def legacy_non_image_asset_migration_dry_run() -> AssetLegacyImportDryRun:
        return get_asset_store().preview_legacy_non_image_import()

    @gateway.post("/api/prompts/render", response_model=RenderedPrompt, tags=["prompts"])
    async def render_prompt(request: PromptRenderRequest) -> RenderedPrompt:
        try:
            return PromptTemplateRenderer().render(request)
        except PromptRenderError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @gateway.get("/api/replay/primitives", response_model=ReplayPrimitiveList, tags=["replay"])
    async def replay_primitives() -> ReplayPrimitiveList:
        return get_replay_adapter().list_primitives()

    @gateway.post("/api/replay/state-hash", response_model=StateHashResponse, tags=["replay"])
    async def replay_state_hash(request: StateHashRequest) -> StateHashResponse:
        return get_replay_adapter().state_hash(request.state)

    @gateway.post("/api/replay/checkpoints", response_model=CheckpointEnvelope, tags=["replay"])
    async def replay_checkpoint(bundle: dict[str, Any]) -> CheckpointEnvelope:
        return get_replay_adapter().create_checkpoint(bundle)

    @gateway.get("/api/replay/persistence/inventory", response_model=PersistenceInventory, tags=["replay"])
    async def replay_persistence_inventory() -> PersistenceInventory:
        return get_replay_adapter().list_sessions()

    @gateway.post("/api/jobs", response_model=JobRecord, tags=["jobs"])
    def create_job(request: CreateJobRequest) -> JobRecord:
        return get_job_store().create_job(request)

    @gateway.get("/api/jobs", response_model=JobListResponse, tags=["jobs"])
    def list_jobs(limit: int = Query(default=100, ge=1, le=500), full: bool = False) -> JobListResponse:
        jobs = get_job_store().list_jobs(limit=limit)
        if full:
            return JobListResponse(jobs=jobs)
        return JobListResponse(jobs=[summarize_job(job) for job in jobs])

    @gateway.get("/events", include_in_schema=False)
    async def events(after_id: int = 0, last_event_id: str | None = Header(default=None, alias="Last-Event-ID")) -> StreamingResponse:
        return StreamingResponse(
            _live_job_event_stream(get_job_store(), after_id=_parse_event_id(last_event_id, fallback=after_id)),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    @gateway.get("/api/jobs/events", tags=["jobs"])
    async def job_events(after_id: int = 0, limit: int = 100) -> StreamingResponse:
        events = get_job_store().list_events(after_id=after_id, limit=limit)

        def generate():
            for event in events:
                yield _sse_event(event.event_type, event.model_dump(mode="json"), event_id=event.id)

        return StreamingResponse(generate(), media_type="text/event-stream")

    @gateway.get("/api/jobs/{job_id}", response_model=JobRecord, tags=["jobs"])
    async def get_job(job_id: str) -> JobRecord:
        job = get_job_store().get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job_not_found")
        return job

    @gateway.post("/api/jobs/claim", response_model=ClaimJobResponse, tags=["jobs"])
    async def claim_job(request: ClaimJobRequest) -> ClaimJobResponse:
        return get_job_store().claim_next(request)

    @gateway.post("/api/jobs/{job_id}/complete", response_model=JobRecord, tags=["jobs"])
    async def complete_job(job_id: str, request: CompleteJobRequest) -> JobRecord:
        job = get_job_store().complete_job(job_id, request)
        if job is None:
            raise HTTPException(status_code=404, detail="job_not_found")
        return job

    @gateway.post("/api/jobs/{job_id}/fail", response_model=JobRecord, tags=["jobs"])
    async def fail_job(job_id: str, request: FailJobRequest) -> JobRecord:
        job = get_job_store().fail_job(job_id, request)
        if job is None:
            raise HTTPException(status_code=404, detail="job_not_found")
        return job

    @gateway.post("/api/jobs/{job_id}/cancel", response_model=JobRecord, tags=["jobs"])
    async def cancel_job(job_id: str, request: CancelJobRequest) -> JobRecord:
        job_store = get_job_store()
        current = job_store.get_job(job_id)
        if current is not None and current.type == "chat.generate":
            job = cancel_chat_generation_job(
                get_chat_store(),
                job_store,
                job_id,
                request,
            )
        else:
            job = job_store.cancel_job(job_id, request)
        if job is None:
            raise HTTPException(status_code=404, detail="job_not_found")
        return job

    return gateway


def _remove_hook_installed_assistant_context_routes(gateway: FastAPI) -> None:
    assistant_context_route_names = {
        "assistant_context_chat_message_endpoint",
        "assistant_context_stream_chat_message_endpoint",
        "assistant_research_runtime_status_endpoint",
    }
    gateway.router.routes = [
        route
        for route in gateway.router.routes
        if getattr(route, "name", "") not in assistant_context_route_names
    ]


app = create_gateway_app()


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("OMNIX_GATEWAY_HOST", DEFAULT_GATEWAY_HOST)
    port = int(os.environ.get("OMNIX_GATEWAY_PORT", str(DEFAULT_GATEWAY_PORT)))
    uvicorn.run("app.gateway.main:app", host=host, port=port, reload=False)
