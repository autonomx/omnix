"""Thin browser-facing gateway foundation."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.assistant_tools import (
    AssistantToolRegistryPayload,
    assistant_tool_registry_payload,
)
from app.production import app as production_app
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
    interrupt_active_chat_generation_jobs,
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
from app.prompts import (
    PromptRenderError,
    PromptRenderRequest,
    PromptTemplateRenderer,
    RenderedPrompt,
)
from app.providers.cache_status import (
    ProviderModelRefreshRequest,
    create_provider_model_refresh_job_request,
)
from app.providers.facade import (
    ProviderFacade,
    ProviderFacadePayload,
    default_provider_facade,
)
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

from .story_asset_save import (
    SaveStoryAssetRequest,
    SavedStoryAssetResponse,
    save_story_asset,
)
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
    auth_url: str | None = None


def _configured_codex_path() -> str:
    profile = load_settings_profile(load_settings())
    return profile.provider_configs.chatgpt_codex.codex_path


class CompatibilityHandoffPayload(BaseModel):
    ok: bool = True
    format_version: str = GATEWAY_FORMAT_VERSION
    legacy_ui_status: Literal["retired"] = "retired"
    existing_fastapi_app: str = "app.gateway.main:app"
    domain_logic_policy: str = "delegate_to_existing_service_modules"
    migration_note: str = (
        "The classic browser UI and compatibility application server are retired. "
        "Current apps use the shared gateway; saved-data migration adapters remain supported."
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
                "current_owner": "app.gateway RPG routes",
                "gateway_phase": "current",
            },
            {
                "namespace": "/api/image-generation",
                "current_owner": "app.gateway image workspace and image service",
                "gateway_phase": "current",
            },
            {
                "namespace": "/api/jobs",
                "current_owner": "app.jobs feature execution and speech workers",
                "gateway_phase": "current",
            },
            {
                "namespace": "/api/assets/{asset_id}/file",
                "current_owner": "app.gateway.image_asset_routes",
                "gateway_phase": "current",
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
            "existing_fastapi_app": "app.gateway.main:app",
            "domain_logic_policy": "delegate_to_existing_service_modules",
        },
    )


def _sse_event(
    event_type: str, payload: dict[str, Any], event_id: int | None = None
) -> str:
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
    return next(
        (asset for asset in asset_store.list_assets().assets if asset.id == asset_id),
        None,
    )


def _chat_message_image_data_urls(metadata: object) -> list[str]:
    if not isinstance(metadata, dict):
        return []
    values: list[str] = []
    raw = metadata.get("image_data_urls")
    if isinstance(raw, list):
        values.extend(value for value in raw if isinstance(value, str) and value)
    legacy = metadata.get("image_data_url")
    if isinstance(legacy, str) and legacy:
        values.insert(0, legacy)
    return list(dict.fromkeys(values))


def _delete_legacy_voice_clone_files(asset: AssetRecord) -> dict[str, Any]:
    """Remove the local clone source and manifest entry so it cannot reappear."""
    import app.shared as shared
    from app.assets.canonical_voice_clones import canonical_voice_clone_root

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
        )
        if str(value or "").strip()
    }
    removed_ids: set[str] = set()
    manifest_changed = False
    try:
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest_path.is_file()
            else {}
        )
    except Exception:
        manifest = {}
    if isinstance(manifest, dict):
        for name, value in list(manifest.items()):
            row = value if isinstance(value, dict) else {}
            clone_id = str(row.get("voice_clone_id") or name).strip()
            if (
                str(name).casefold() in identifiers
                or clone_id.casefold() in identifiers
            ):
                manifest.pop(name, None)
                removed_ids.add(clone_id)
                manifest_changed = True
        if manifest_changed:
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )

    removed_ids.update(str(value) for value in identifiers if value)
    file_deleted = False
    for clone_id in removed_ids:
        for suffix in (
            ".wav",
            ".mp3",
            ".mp4",
            ".m4a",
            ".webm",
            ".ogg",
            ".flac",
            ".json",
        ):
            target = (clone_dir / f"{clone_id}{suffix}").resolve()
            if (
                target.parent != clone_dir
                or target == manifest_path
                or not target.is_file()
            ):
                continue
            target.unlink()
            file_deleted = True
    source = Path(str(asset.storage_path or "")).resolve()
    allowed_roots = (clone_dir, canonical_voice_clone_root().resolve())
    if (
        source.suffix.lower()
        in {".wav", ".mp3", ".mp4", ".m4a", ".webm", ".ogg", ".flac"}
        and any(source.is_relative_to(root) for root in allowed_roots)
        and source.parent.is_dir()
    ):
        # Read-through profiles have no shared or legacy manifest entry. Remove
        # the source and its sidecar, including case variants on disk.
        for target in source.parent.iterdir():
            if (
                target.is_file()
                and target.stem.casefold() == source.stem.casefold()
                and target.suffix.lower()
                in {
                    ".wav",
                    ".mp3",
                    ".mpeg",
                    ".mp4",
                    ".m4a",
                    ".webm",
                    ".ogg",
                    ".flac",
                    ".json",
                }
            ):
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
        events = await asyncio.to_thread(
            job_store.list_events,
            after_id=last_event_id,
            limit=EVENT_STREAM_BATCH_LIMIT,
        )
        if events:
            for event in events:
                last_event_id = max(last_event_id, event.id)
                yield _sse_event(
                    event.event_type, event.model_dump(mode="json"), event_id=event.id
                )
            seconds_until_heartbeat = 0.0
            continue
        if seconds_until_heartbeat <= 0:
            yield _sse_comment("heartbeat")
            seconds_until_heartbeat = EVENT_STREAM_HEARTBEAT_SECONDS
        await asyncio.sleep(EVENT_STREAM_POLL_SECONDS)
        seconds_until_heartbeat -= EVENT_STREAM_POLL_SECONDS


__all__ = [
    "AbstractAsyncContextManager",
    "Any",
    "AssetContentResponse",
    "AssetLegacyImportDryRun",
    "AssetListResponse",
    "AssetMigrationPreview",
    "AssetRecord",
    "AssetType",
    "AssistantToolRegistryPayload",
    "AsyncExitStack",
    "BaseModel",
    "Callable",
    "CancelJobRequest",
    "ChatGPTCodexProvider",
    "ChatSession",
    "ChatSessionListResponse",
    "ChatSessionStore",
    "CheckpointEnvelope",
    "ClaimJobRequest",
    "ClaimJobResponse",
    "CodexAuthStatus",
    "CompatibilityHandoffPayload",
    "CompleteJobRequest",
    "CreateChatSessionRequest",
    "CreateJobRequest",
    "DEFAULT_GATEWAY_HOST",
    "DEFAULT_GATEWAY_PORT",
    "DeleteChatSessionResponse",
    "DiagnosticsPayload",
    "EVENT_STREAM_BATCH_LIMIT",
    "EVENT_STREAM_HEARTBEAT_SECONDS",
    "EVENT_STREAM_POLL_SECONDS",
    "FailJobRequest",
    "FastAPI",
    "Field",
    "GATEWAY_FORMAT_VERSION",
    "GatewayHealth",
    "HTTPException",
    "Header",
    "InMemoryJobStore",
    "InMemoryModelResidencyStore",
    "JSONResponse",
    "JobListResponse",
    "JobRecord",
    "LegacyGenerateTitleRequest",
    "LegacyGenerateTitleResponse",
    "LegacySessionCreateResponse",
    "LegacySessionListResponse",
    "LegacySessionResponse",
    "LegacySessionUpdateRequest",
    "LegacySuccessResponse",
    "Literal",
    "ModelResidencyDiagnostics",
    "ModelResidencyRecord",
    "Path",
    "PersistenceInventory",
    "PromptRenderError",
    "PromptRenderRequest",
    "PromptTemplateRenderer",
    "ProviderFacade",
    "ProviderFacadePayload",
    "ProviderModelRefreshRequest",
    "Query",
    "RenderedPrompt",
    "ReplayPrimitiveList",
    "ReportListResponse",
    "ResourceClass",
    "RpgReplayPersistenceAdapter",
    "RuntimeStatusPayload",
    "SaveStoryAssetRequest",
    "SavedStoryAssetResponse",
    "SendChatMessageRequest",
    "SendChatMessageResponse",
    "SettingsPayload",
    "SettingsSaveResponse",
    "SharedAssetStore",
    "StateHashRequest",
    "StateHashResponse",
    "StreamingResponse",
    "TEXT_ASSET_MAX_BYTES",
    "TEXT_ASSET_MIME_TYPES",
    "WorkerHealthPayload",
    "WorkerPayloadPolicy",
    "_asset_by_id",
    "_chat_message_image_data_urls",
    "_compatibility_handoff",
    "_configured_codex_path",
    "_delete_legacy_voice_clone_files",
    "_install_required_rpg_turn_hooks",
    "_live_job_event_stream",
    "_parse_event_id",
    "_read_text_asset",
    "_runtime_status",
    "_sse_comment",
    "_sse_event",
    "_text_asset_supported",
    "adventure_simulation_state_payload",
    "annotations",
    "assistant_tool_registry_payload",
    "asynccontextmanager",
    "asyncio",
    "cancel_chat_generation_job",
    "chat_submission_lock",
    "compare_adventure_entity_payload",
    "compare_adventure_world_payload",
    "create_legacy_session",
    "create_provider_model_refresh_job_request",
    "default_asset_store",
    "default_chat_store",
    "default_job_store",
    "default_model_residency_store",
    "default_provider_facade",
    "default_rpg_replay_adapter",
    "delete_legacy_session",
    "existing_chat_generation_turn",
    "find_chat_generation_job",
    "generate_legacy_session_title",
    "get_diagnostics_payload",
    "get_legacy_session",
    "get_rpg_session_payload",
    "get_settings_payload",
    "get_worker_health_payload",
    "get_worker_payload_policy",
    "inspect_adventure_world_payload",
    "inspect_adventure_world_snapshot_payload",
    "inspect_npc_reasoning_payload",
    "inspect_tick_diff_payload",
    "inspect_timeline_payload",
    "inspect_timeline_tick_payload",
    "inspect_world_events_payload",
    "interrupt_active_chat_generation_jobs",
    "json",
    "list_adventure_templates_payload",
    "list_legacy_sessions",
    "list_report_artifacts",
    "list_rpg_sessions_payload",
    "load_settings",
    "load_settings_profile",
    "logger",
    "logging",
    "mark_chat_acceptance_failed",
    "os",
    "player_codex_payload",
    "player_encounter_payload",
    "player_journal_payload",
    "player_objectives_payload",
    "player_state_payload",
    "preview_adventure_payload",
    "production_app",
    "recover_abandoned_chat_generation_jobs",
    "register_assistant_context_routes",
    "save_settings_payload",
    "save_story_asset",
    "simulate_adventure_step_payload",
    "start_chat_generation_job",
    "summarize_job",
    "update_legacy_session",
    "validate_adventure_payload",
]
