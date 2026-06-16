"""Thin browser-facing gateway foundation.

This app is intentionally small. It exposes the stable health/runtime/OpenAPI
surface that later redesign phases can build on while the current larger app
and legacy browser paths remain available during migration.
"""
from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.assets import (
    AssetLegacyImportDryRun,
    AssetListResponse,
    AssetMigrationPreview,
    AssetRecord,
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
    ModelResidencyDiagnostics,
    ModelResidencyRecord,
    ResourceClass,
    SQLiteModelResidencyStore,
    SQLiteJobStore,
    default_job_store,
    default_model_residency_store,
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
from app.providers.cache_status import (
    ProviderModelRefreshRequest,
    create_provider_model_refresh_job_request,
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

from .story_asset_save import SaveStoryAssetRequest, SavedStoryAssetResponse, save_story_asset
from .workers import (
    GATEWAY_FORMAT_VERSION,
    WorkerHealthPayload,
    WorkerPayloadPolicy,
    get_worker_health_payload,
    get_worker_payload_policy,
)

DEFAULT_GATEWAY_HOST = "127.0.0.1"
DEFAULT_GATEWAY_PORT = 5050
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


class AssetContentResponse(BaseModel):
    asset: AssetRecord
    content: str
    encoding: Literal["utf-8"] = "utf-8"
    size_bytes: int
    truncated: Literal[False] = False


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
    return next((asset for asset in asset_store.list_assets().assets if asset.id == asset_id), None)


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


async def _live_job_event_stream(job_store: SQLiteJobStore, after_id: int = 0):
    """Yield a live SSE stream for shared job events.

    The finite `/api/jobs/events` route remains a compatibility/history endpoint.
    The browser-facing shared event client uses `/events`, which stays open,
    emits event ids for EventSource resume, and sends heartbeat comments so
    proxies and diagnostics can tell the stream is still alive.
    """
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
        seconds_until_heartbeat -= EVENT_STREAM_POLL_SECONDS)
