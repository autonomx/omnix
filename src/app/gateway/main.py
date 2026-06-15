"""Thin browser-facing gateway foundation.

This app is intentionally small. It exposes the stable health/runtime/OpenAPI
surface that later redesign phases can build on while the current larger app
and legacy browser paths remain available during migration.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.assets import (
    AssetListResponse,
    AssetMigrationPreview,
    SharedAssetStore,
    default_asset_store,
)
from app.chat import (
    ChatSession,
    ChatSessionListResponse,
    ChatSessionStore,
    CreateChatSessionRequest,
    SendChatMessageRequest,
    SendChatMessageResponse,
    default_chat_store,
)
from app.jobs import (
    CancelJobRequest,
    ClaimJobRequest,
    ClaimJobResponse,
    CompleteJobRequest,
    CreateJobRequest,
    FailJobRequest,
    JobListResponse,
    JobRecord,
    ResourceClass,
    SQLiteJobStore,
    default_job_store,
)
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
from app.prompts import (
    PromptRenderError,
    PromptRenderRequest,
    PromptTemplateRenderer,
    RenderedPrompt,
)
from app.providers.facade import (
    ProviderFacade,
    ProviderFacadePayload,
    default_provider_facade,
)
from app.replay import (
    CheckpointEnvelope,
    PersistenceInventory,
    ReplayPrimitiveList,
    RpgReplayPersistenceAdapter,
    StateHashRequest,
    StateHashResponse,
    default_rpg_replay_adapter,
)

from .workers import (
    GATEWAY_FORMAT_VERSION,
    WorkerHealthPayload,
    WorkerPayloadPolicy,
    get_worker_health_payload,
    get_worker_payload_policy,
)

DEFAULT_GATEWAY_HOST = "127.0.0.1"
DEFAULT_GATEWAY_PORT = 5050


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


class CompatibilityHandoffPayload(BaseModel):
    ok: bool = True
    format_version: str = GATEWAY_FORMAT_VERSION
    legacy_ui_status: Literal["retired"] = "retired"
    existing_fastapi_app: str = "run_app:app"
    domain_logic_policy: str = "delegate_to_existing_service_modules"
    migration_note: str = (
        "The classic template/static browser UI is retired. Backend domain "
        "routes may remain as compatibility surfaces until feature-specific "
        "contracts are migrated."
    )
    handoff_targets: list[dict[str, str]] = Field(default_factory=list)


def _compatibility_handoff() -> CompatibilityHandoffPayload:
    return CompatibilityHandoffPayload(
        handoff_targets=[
            {
                "namespace": "/api/rpg",
                "current_owner": "run_app:app and app.rpg.api routers",
                "gateway_phase": "future typed contract wrapper",
            },
            {
                "namespace": "/api/image",
                "current_owner": "app.image.api and image service",
                "gateway_phase": "future worker-backed image contract",
            },
            {
                "namespace": "/api/voice, /api/tts, /api/stt",
                "current_owner": "run_app:app, tts_server, parakeet_stt_server",
                "gateway_phase": "future worker health and job contract",
            },
            {
                "namespace": "/generated-images",
                "current_owner": "run_app:app static asset route",
                "gateway_phase": "future shared asset reference route",
            },
        ]
    )


def _runtime_status() -> RuntimeStatusPayload:
    workers = get_worker_health_payload()
    return RuntimeStatusPayload(
        ok=workers.ok,
        status="ready" if workers.ok else "degraded",
        gateway=GatewayHealth(),
        workers=workers,
        compatibility={
            "legacy_ui_status": "retired",
            "existing_fastapi_app": "run_app:app",
            "domain_logic_policy": "delegate_to_existing_service_modules",
        },
    )


def _sse_event(event_type: str, payload: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload, sort_keys=True)}\n\n"


def create_gateway_app(
    job_store_factory: Callable[[], SQLiteJobStore] | None = None,
    provider_facade_factory: Callable[[], ProviderFacade] | None = None,
    asset_store_factory: Callable[[], SharedAssetStore] | None = None,
    chat_store_factory: Callable[[], ChatSessionStore] | None = None,
    replay_adapter_factory: Callable[[], RpgReplayPersistenceAdapter] | None = None,
) -> FastAPI:
    """Create the thin gateway app without importing model-heavy services."""
    get_job_store = job_store_factory or default_job_store
    get_provider_facade = provider_facade_factory or default_provider_facade
    get_asset_store = asset_store_factory or default_asset_store
    get_chat_store = chat_store_factory or default_chat_store
    get_replay_adapter = replay_adapter_factory or default_rpg_replay_adapter
    gateway = FastAPI(
        title="Omnix Web Gateway",
        version="0.1.0",
        summary="Thin local-first gateway foundation for the Omnix web app redesign.",
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

    @gateway.get(
        "/api/compatibility/legacy",
        response_model=CompatibilityHandoffPayload,
        tags=["compatibility"],
    )
    async def compatibility_handoff() -> CompatibilityHandoffPayload:
        return _compatibility_handoff()

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

    @gateway.post(
        "/api/chat/sessions/{session_id}/messages",
        response_model=SendChatMessageResponse,
        tags=["chat"],
    )
    async def send_chat_message(session_id: str, request: SendChatMessageRequest) -> SendChatMessageResponse:
        appended = get_chat_store().append_user_message(session_id, request)
        if appended is None:
            raise HTTPException(status_code=404, detail="chat session not found")

        session, user_message = appended
        job = get_job_store().create_job(
            CreateJobRequest(
                module="chatbot",
                type="chat.generate",
                resource_class=ResourceClass.GPU_LLM,
                input_payload={
                    "session_id": session.id,
                    "message_id": user_message.id,
                    "provider_id": request.provider_id or session.provider_id,
                    "model_id": request.model_id or session.model_id,
                },
                compat={"contract": "chat_session_v1"},
            )
        )
        return SendChatMessageResponse(session=session, user_message=user_message, job=job)

    @gateway.get("/api/providers", response_model=ProviderFacadePayload, tags=["providers"])
    async def providers() -> ProviderFacadePayload:
        return get_provider_facade().payload()

    @gateway.get("/api/models", response_model=ProviderFacadePayload, tags=["providers"])
    async def models() -> ProviderFacadePayload:
        return get_provider_facade().payload()

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

    @gateway.post(
        "/api/sessions/generate-title",
        response_model=LegacyGenerateTitleResponse,
        tags=["legacy-sessions"],
    )
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
    async def rpg_session_get(request: dict[str, Any]) -> dict[str, Any]:
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
        return get_diagnostics_payload()

    @gateway.get("/api/assets", response_model=AssetListResponse, tags=["assets"])
    async def assets() -> AssetListResponse:
        return get_asset_store().list_assets()

    @gateway.post(
        "/api/assets/migrations/image/dry-run",
        response_model=AssetMigrationPreview,
        tags=["assets"],
    )
    async def image_asset_migration_dry_run() -> AssetMigrationPreview:
        return get_asset_store().import_image_manifest_dry_run()

    @gateway.post(
        "/api/assets/migrations/image/import",
        response_model=AssetMigrationPreview,
        tags=["assets"],
    )
    async def image_asset_migration_import() -> AssetMigrationPreview:
        return get_asset_store().import_image_manifest()

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
    async def create_job(request: CreateJobRequest) -> JobRecord:
        return get_job_store().create_job(request)

    @gateway.get("/api/jobs", response_model=JobListResponse, tags=["jobs"])
    async def list_jobs() -> JobListResponse:
        return JobListResponse(jobs=get_job_store().list_jobs())

    @gateway.get("/api/jobs/events", tags=["jobs"])
    async def job_events(after_id: int = 0, limit: int = 100) -> StreamingResponse:
        events = get_job_store().list_events(after_id=after_id, limit=limit)

        def generate():
            for event in events:
                yield _sse_event(event.event_type, event.model_dump(mode="json"))

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
        job = get_job_store().cancel_job(job_id, request)
        if job is None:
            raise HTTPException(status_code=404, detail="job_not_found")
        return job

    return gateway


app = create_gateway_app()


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("OMNIX_GATEWAY_HOST", DEFAULT_GATEWAY_HOST)
    port = int(os.environ.get("OMNIX_GATEWAY_PORT", str(DEFAULT_GATEWAY_PORT)))
    uvicorn.run("app.gateway.main:app", host=host, port=port, reload=False)
