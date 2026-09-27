"""Application composition for the Omnix gateway."""

from __future__ import annotations

from app.config.env import env_str, environment

from typing import Any

from .core_services import (
    AbstractAsyncContextManager as AbstractAsyncContextManager,
    Any as Any,
    AssetContentResponse as AssetContentResponse,
    AssetLegacyImportDryRun as AssetLegacyImportDryRun,
    AssetListResponse as AssetListResponse,
    AssetMigrationPreview as AssetMigrationPreview,
    AssetRecord as AssetRecord,
    AssetType as AssetType,
    AssistantToolRegistryPayload as AssistantToolRegistryPayload,
    AsyncExitStack as AsyncExitStack,
    BaseModel as BaseModel,
    Callable as Callable,
    CancelJobRequest as CancelJobRequest,
    ChatGPTCodexProvider as ChatGPTCodexProvider,
    ChatSession as ChatSession,
    ChatSessionListResponse as ChatSessionListResponse,
    ChatSessionStore as ChatSessionStore,
    CheckpointEnvelope as CheckpointEnvelope,
    ClaimJobRequest as ClaimJobRequest,
    ClaimJobResponse as ClaimJobResponse,
    CodexAuthStatus as CodexAuthStatus,
    CompatibilityHandoffPayload as CompatibilityHandoffPayload,
    CompleteJobRequest as CompleteJobRequest,
    CreateChatSessionRequest as CreateChatSessionRequest,
    CreateJobRequest as CreateJobRequest,
    DEFAULT_GATEWAY_HOST as DEFAULT_GATEWAY_HOST,
    DEFAULT_GATEWAY_PORT as DEFAULT_GATEWAY_PORT,
    DeleteChatSessionResponse as DeleteChatSessionResponse,
    DiagnosticsPayload as DiagnosticsPayload,
    EVENT_STREAM_BATCH_LIMIT as EVENT_STREAM_BATCH_LIMIT,
    EVENT_STREAM_HEARTBEAT_SECONDS as EVENT_STREAM_HEARTBEAT_SECONDS,
    EVENT_STREAM_POLL_SECONDS as EVENT_STREAM_POLL_SECONDS,
    FailJobRequest as FailJobRequest,
    FastAPI as FastAPI,
    Field as Field,
    GATEWAY_FORMAT_VERSION as GATEWAY_FORMAT_VERSION,
    GatewayHealth as GatewayHealth,
    HTTPException as HTTPException,
    Header as Header,
    Any as Any,
    InMemoryModelResidencyStore as InMemoryModelResidencyStore,
    JSONResponse as JSONResponse,
    JobListResponse as JobListResponse,
    JobRecord as JobRecord,
    LegacyGenerateTitleRequest as LegacyGenerateTitleRequest,
    LegacyGenerateTitleResponse as LegacyGenerateTitleResponse,
    LegacySessionCreateResponse as LegacySessionCreateResponse,
    LegacySessionListResponse as LegacySessionListResponse,
    LegacySessionResponse as LegacySessionResponse,
    LegacySessionUpdateRequest as LegacySessionUpdateRequest,
    LegacySuccessResponse as LegacySuccessResponse,
    Literal as Literal,
    ModelResidencyDiagnostics as ModelResidencyDiagnostics,
    ModelResidencyRecord as ModelResidencyRecord,
    Path as Path,
    PersistenceInventory as PersistenceInventory,
    PromptRenderError as PromptRenderError,
    PromptRenderRequest as PromptRenderRequest,
    PromptTemplateRenderer as PromptTemplateRenderer,
    ProviderFacade as ProviderFacade,
    ProviderFacadePayload as ProviderFacadePayload,
    ProviderModelRefreshRequest as ProviderModelRefreshRequest,
    Query as Query,
    RenderedPrompt as RenderedPrompt,
    ReplayPrimitiveList as ReplayPrimitiveList,
    ReportListResponse as ReportListResponse,
    ResourceClass as ResourceClass,
    RpgReplayPersistenceAdapter as RpgReplayPersistenceAdapter,
    RuntimeStatusPayload as RuntimeStatusPayload,
    SaveStoryAssetRequest as SaveStoryAssetRequest,
    SavedStoryAssetResponse as SavedStoryAssetResponse,
    SendChatMessageRequest as SendChatMessageRequest,
    SendChatMessageResponse as SendChatMessageResponse,
    SettingsPayload as SettingsPayload,
    SettingsSaveResponse as SettingsSaveResponse,
    SharedAssetStore as SharedAssetStore,
    StateHashRequest as StateHashRequest,
    StateHashResponse as StateHashResponse,
    StreamingResponse as StreamingResponse,
    TEXT_ASSET_MAX_BYTES as TEXT_ASSET_MAX_BYTES,
    TEXT_ASSET_MIME_TYPES as TEXT_ASSET_MIME_TYPES,
    WorkerHealthPayload as WorkerHealthPayload,
    WorkerPayloadPolicy as WorkerPayloadPolicy,
    _asset_by_id as _asset_by_id,
    _chat_message_image_data_urls as _chat_message_image_data_urls,
    _compatibility_handoff as _compatibility_handoff,
    _configured_codex_path as _configured_codex_path,
    _delete_legacy_voice_clone_files as _delete_legacy_voice_clone_files,
    _install_required_rpg_turn_hooks as _install_required_rpg_turn_hooks,
    _live_job_event_stream as _live_job_event_stream,
    _parse_event_id as _parse_event_id,
    _read_text_asset as _read_text_asset,
    _runtime_status as _runtime_status,
    _sse_comment as _sse_comment,
    _sse_event as _sse_event,
    _text_asset_supported as _text_asset_supported,
    adventure_simulation_state_payload as adventure_simulation_state_payload,
    annotations as annotations,
    assistant_tool_registry_payload as assistant_tool_registry_payload,
    asynccontextmanager as asynccontextmanager,
    asyncio as asyncio,
    cancel_chat_generation_job as cancel_chat_generation_job,
    chat_submission_lock as chat_submission_lock,
    compare_adventure_entity_payload as compare_adventure_entity_payload,
    compare_adventure_world_payload as compare_adventure_world_payload,
    create_legacy_session as create_legacy_session,
    create_provider_model_refresh_job_request as create_provider_model_refresh_job_request,
    default_asset_store as default_asset_store,
    default_chat_store as default_chat_store,
    default_job_store as default_job_store,
    default_model_residency_store as default_model_residency_store,
    default_provider_facade as default_provider_facade,
    default_rpg_replay_adapter as default_rpg_replay_adapter,
    delete_legacy_session as delete_legacy_session,
    existing_chat_generation_turn as existing_chat_generation_turn,
    find_chat_generation_job as find_chat_generation_job,
    generate_legacy_session_title as generate_legacy_session_title,
    get_diagnostics_payload as get_diagnostics_payload,
    get_legacy_session as get_legacy_session,
    get_rpg_session_payload as get_rpg_session_payload,
    get_settings_payload as get_settings_payload,
    get_worker_health_payload as get_worker_health_payload,
    get_worker_payload_policy as get_worker_payload_policy,
    inspect_adventure_world_payload as inspect_adventure_world_payload,
    inspect_adventure_world_snapshot_payload as inspect_adventure_world_snapshot_payload,
    inspect_npc_reasoning_payload as inspect_npc_reasoning_payload,
    inspect_tick_diff_payload as inspect_tick_diff_payload,
    inspect_timeline_payload as inspect_timeline_payload,
    inspect_timeline_tick_payload as inspect_timeline_tick_payload,
    inspect_world_events_payload as inspect_world_events_payload,
    interrupt_active_chat_generation_jobs as interrupt_active_chat_generation_jobs,
    json as json,
    list_adventure_templates_payload as list_adventure_templates_payload,
    list_legacy_sessions as list_legacy_sessions,
    list_report_artifacts as list_report_artifacts,
    list_rpg_sessions_payload as list_rpg_sessions_payload,
    load_settings as load_settings,
    load_settings_profile as load_settings_profile,
    logger as logger,
    logging as logging,
    mark_chat_acceptance_failed as mark_chat_acceptance_failed,
    os as os,
    player_codex_payload as player_codex_payload,
    player_encounter_payload as player_encounter_payload,
    player_journal_payload as player_journal_payload,
    player_objectives_payload as player_objectives_payload,
    player_state_payload as player_state_payload,
    preview_adventure_payload as preview_adventure_payload,
    production_app as production_app,
    recover_abandoned_chat_generation_jobs as recover_abandoned_chat_generation_jobs,
    register_assistant_context_routes as register_assistant_context_routes,
    save_settings_payload as save_settings_payload,
    save_story_asset as save_story_asset,
    simulate_adventure_step_payload as simulate_adventure_step_payload,
    start_chat_generation_job as start_chat_generation_job,
    summarize_job as summarize_job,
    update_legacy_session as update_legacy_session,
    validate_adventure_payload as validate_adventure_payload,
)


def _gateway_lifespan(app, *, get_chat_store, get_job_store):
    from .lifecycle import gateway_lifespan

    return gateway_lifespan(
        app,
        get_chat_store=get_chat_store,
        get_job_store=get_job_store,
        recover_jobs=recover_abandoned_chat_generation_jobs,
    )


def create_gateway_app(
    job_store_factory: Callable[[], Any] | None = None,
    provider_facade_factory: Callable[[], ProviderFacade] | None = None,
    asset_store_factory: Callable[[], SharedAssetStore] | None = None,
    chat_store_factory: Callable[[], ChatSessionStore] | None = None,
    replay_adapter_factory: Callable[[], RpgReplayPersistenceAdapter] | None = None,
    model_residency_store_factory: Callable[[], InMemoryModelResidencyStore]
    | None = None,
    readiness_check: Callable[[], dict[str, Any]] | None = None,
    runtime_lifecycle: Callable[[], AbstractAsyncContextManager] | None = None,
    background_runtime=None,
    runtime_config=None,
    runtime_services=None,
) -> FastAPI:
    from app.runtime.config import get_runtime_config
    from app.runtime.capabilities import RuntimeCapabilities
    runtime_config = runtime_config or get_runtime_config()
    _install_required_rpg_turn_hooks()
    get_job_store = job_store_factory or default_job_store
    get_provider_facade = provider_facade_factory or default_provider_facade
    get_asset_store = asset_store_factory or default_asset_store
    get_chat_store = chat_store_factory or default_chat_store
    get_replay_adapter = replay_adapter_factory or default_rpg_replay_adapter
    get_model_residency_store = (
        model_residency_store_factory or default_model_residency_store
    )

    @asynccontextmanager
    async def gateway_lifespan(_app: FastAPI):
        async with AsyncExitStack() as stack:
            if runtime_lifecycle is not None:
                await stack.enter_async_context(runtime_lifecycle())
            await stack.enter_async_context(
                _gateway_lifespan(
                    _app,
                    get_chat_store=get_chat_store,
                    get_job_store=get_job_store,
                )
            )
            yield

    gateway = FastAPI(
        title="Omnix Web Gateway",
        version="0.1.0",
        summary="Thin local-first gateway foundation for the Omnix web app redesign.",
        lifespan=gateway_lifespan,
    )
    gateway.state.runtime_started = False
    gateway.state.background_runtime = background_runtime
    gateway.state.runtime_config = runtime_config
    gateway.state.runtime_services = runtime_services
    gateway.state.runtime_capabilities = RuntimeCapabilities.from_config(runtime_config)
    from .background_runtime import GatewayBackgroundRegistryAdapter
    gateway.state.background_registry = GatewayBackgroundRegistryAdapter(gateway)
    gateway.state.feature_lifecycles = []
    from app.platform.runtime_diagnostics import RequestMetrics, RuntimeRequestMiddleware
    gateway.state.runtime_metrics = RequestMetrics()
    gateway.add_middleware(RuntimeRequestMiddleware, metrics=gateway.state.runtime_metrics)
    from .feature_registry import register_gateway_features
    from app.runtime.net import allowed_origins
    from app.security.request_guard import RequestGuardMiddleware
    from fastapi.middleware.cors import CORSMiddleware

    gateway.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_credentials=False,
        allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        max_age=86_400,
    )
    gateway.add_middleware(RequestGuardMiddleware)
    register_gateway_features(gateway)
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

    @gateway.get("/ready", include_in_schema=False)
    def readiness() -> JSONResponse:
        if not gateway.state.runtime_started or readiness_check is None:
            return JSONResponse(
                {"ready": False, "reason": "runtime_not_started"}, status_code=503
            )
        try:
            payload = readiness_check()
        except Exception:
            # Database errors can include connection credentials and SQL details.
            return JSONResponse(
                {"ready": False, "reason": "persistence_unavailable"}, status_code=503
            )
        return JSONResponse(
            payload, status_code=200 if payload.get("ready") is True else 503
        )

    @gateway.get(
        "/api/runtime/status", response_model=RuntimeStatusPayload, tags=["runtime"]
    )
    def runtime_status() -> RuntimeStatusPayload:
        return _runtime_status()

    @gateway.get(
        "/api/workers/health", response_model=WorkerHealthPayload, tags=["workers"]
    )
    def worker_health() -> WorkerHealthPayload:
        return get_worker_health_payload()

    @gateway.get(
        "/api/workers/payload-policy",
        response_model=WorkerPayloadPolicy,
        tags=["workers"],
    )
    async def worker_payload_policy() -> WorkerPayloadPolicy:
        return get_worker_payload_policy()

    @gateway.get(
        "/api/compatibility/legacy",
        response_model=CompatibilityHandoffPayload,
        tags=["compatibility"],
    )
    async def compatibility_handoff() -> CompatibilityHandoffPayload:
        return _compatibility_handoff()

    @gateway.get(
        "/api/assistant/tools",
        response_model=AssistantToolRegistryPayload,
        tags=["assistant-tools"],
    )
    async def assistant_tools() -> AssistantToolRegistryPayload:
        return assistant_tool_registry_payload()

    from .core_chat_routes import register_core_chat_routes

    register_core_chat_routes(
        gateway, get_chat_store=get_chat_store, get_job_store=get_job_store
    )

    @gateway.get(
        "/api/providers", response_model=ProviderFacadePayload, tags=["providers"]
    )
    async def providers() -> ProviderFacadePayload:
        return await asyncio.to_thread(lambda: get_provider_facade().payload())

    @gateway.get(
        "/api/models", response_model=ProviderFacadePayload, tags=["providers"]
    )
    async def models() -> ProviderFacadePayload:
        return await asyncio.to_thread(lambda: get_provider_facade().payload())

    @gateway.get(
        "/api/providers/chatgpt-codex/auth",
        response_model=CodexAuthStatus,
        tags=["providers"],
    )
    async def chatgpt_codex_auth_status() -> CodexAuthStatus:
        return ChatGPTCodexProvider.auth_status(_configured_codex_path())

    @gateway.post(
        "/api/providers/chatgpt-codex/login",
        response_model=CodexAuthStatus,
        tags=["providers"],
    )
    async def chatgpt_codex_login() -> CodexAuthStatus:
        return ChatGPTCodexProvider.start_login(_configured_codex_path())

    @gateway.post(
        "/api/providers/refresh", response_model=JobRecord, tags=["providers"]
    )
    async def refresh_providers(request: ProviderModelRefreshRequest) -> JobRecord:
        return get_job_store().create_job(
            create_provider_model_refresh_job_request(request)
        )

    @gateway.post("/api/models/refresh", response_model=JobRecord, tags=["providers"])
    async def refresh_models(request: ProviderModelRefreshRequest) -> JobRecord:
        return get_job_store().create_job(
            create_provider_model_refresh_job_request(request)
        )

    @gateway.get("/api/settings", response_model=SettingsPayload, tags=["settings"])
    async def settings() -> SettingsPayload:
        return get_settings_payload()

    @gateway.post(
        "/api/settings", response_model=SettingsSaveResponse, tags=["settings"]
    )
    async def save_settings(request: dict[str, Any]) -> SettingsSaveResponse:
        return save_settings_payload(request)

    @gateway.get(
        "/api/sessions",
        response_model=LegacySessionListResponse,
        tags=["legacy-sessions"],
    )
    async def legacy_sessions() -> LegacySessionListResponse:
        return list_legacy_sessions()

    @gateway.post(
        "/api/sessions",
        response_model=LegacySessionCreateResponse,
        tags=["legacy-sessions"],
    )
    async def create_session() -> LegacySessionCreateResponse:
        return create_legacy_session()

    @gateway.post(
        "/api/sessions/generate-title",
        response_model=LegacyGenerateTitleResponse,
        tags=["legacy-sessions"],
    )
    async def generate_session_title(
        request: LegacyGenerateTitleRequest,
    ) -> LegacyGenerateTitleResponse:
        return generate_legacy_session_title(request)

    @gateway.get(
        "/api/sessions/{session_id}",
        response_model=LegacySessionResponse,
        tags=["legacy-sessions"],
    )
    async def legacy_session(session_id: str) -> LegacySessionResponse:
        session = get_legacy_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Not found")
        return session

    @gateway.put(
        "/api/sessions/{session_id}",
        response_model=LegacySuccessResponse,
        tags=["legacy-sessions"],
    )
    async def update_session(
        session_id: str, request: LegacySessionUpdateRequest
    ) -> LegacySuccessResponse:
        result = update_legacy_session(session_id, request)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        return result

    @gateway.delete(
        "/api/sessions/{session_id}",
        response_model=LegacySuccessResponse,
        tags=["legacy-sessions"],
    )
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

    @gateway.post(
        "/api/rpg/adventure/inspect-world-snapshot", tags=["rpg-adventure-compat"]
    )
    async def rpg_adventure_inspect_world_snapshot(
        request: dict[str, Any],
    ) -> dict[str, Any]:
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

    @gateway.get(
        "/api/diagnostics", response_model=DiagnosticsPayload, tags=["diagnostics"]
    )
    def diagnostics() -> DiagnosticsPayload:
        from app.platform.diagnostics import get_runtime_diagnostics_payload
        return get_runtime_diagnostics_payload(
            gateway, model_residency_store_factory=get_model_residency_store,
        )

    @gateway.get(
        "/api/model-residency",
        response_model=ModelResidencyDiagnostics,
        tags=["models"],
    )
    async def model_residency() -> ModelResidencyDiagnostics:
        return get_model_residency_store().diagnostics()

    @gateway.post(
        "/api/model-residency",
        response_model=ModelResidencyDiagnostics,
        tags=["models"],
    )
    async def report_model_residency(
        record: ModelResidencyRecord,
    ) -> ModelResidencyDiagnostics:
        store = get_model_residency_store()
        store.upsert_record(record)
        return store.diagnostics()

    @gateway.delete(
        "/api/model-residency/{model_id}",
        response_model=ModelResidencyDiagnostics,
        tags=["models"],
    )
    async def delete_model_residency(model_id: str) -> ModelResidencyDiagnostics:
        store = get_model_residency_store()
        store.delete_record(model_id)
        return store.diagnostics()

    from .core_assets_routes import register_core_assets_routes

    register_core_assets_routes(gateway, get_asset_store=get_asset_store)

    @gateway.delete("/api/voice-cloning/assets/{asset_id}", include_in_schema=False)
    def delete_voice_clone_asset(asset_id: str) -> dict[str, Any]:
        store = get_asset_store()
        asset = _asset_by_id(store, asset_id)
        if asset is None and asset_id.startswith("voice-cloning:"):
            from app.assets.canonical_voice_clones import (
                discover_canonical_voice_clone_assets,
            )

            asset = next(
                (
                    candidate
                    for candidate in discover_canonical_voice_clone_assets()
                    if candidate.id == asset_id
                ),
                None,
            )
        if asset is None:
            raise HTTPException(status_code=404, detail="asset_not_found")
        if asset.type != AssetType.VOICE_PROFILE or asset.module != "voice-cloning":
            raise HTTPException(status_code=409, detail="asset_not_voice_clone")
        shared_result = store.delete_asset(asset_id)
        legacy_result = _delete_legacy_voice_clone_files(asset)
        deleted = (
            bool(shared_result.get("deleted"))
            or bool(legacy_result.get("manifest_deleted"))
            or bool(legacy_result.get("file_deleted"))
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="asset_not_deletable")
        return {
            "ok": True,
            "asset_id": asset_id,
            "deleted": True,
            "file_deleted": bool(shared_result.get("file_deleted"))
            or bool(legacy_result.get("file_deleted")),
        }

    @gateway.post(
        "/api/prompts/render", response_model=RenderedPrompt, tags=["prompts"]
    )
    async def render_prompt(request: PromptRenderRequest) -> RenderedPrompt:
        try:
            return PromptTemplateRenderer().render(request)
        except PromptRenderError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @gateway.get(
        "/api/replay/primitives", response_model=ReplayPrimitiveList, tags=["replay"]
    )
    async def replay_primitives() -> ReplayPrimitiveList:
        return get_replay_adapter().list_primitives()

    @gateway.post(
        "/api/replay/state-hash", response_model=StateHashResponse, tags=["replay"]
    )
    async def replay_state_hash(request: StateHashRequest) -> StateHashResponse:
        return get_replay_adapter().state_hash(request.state)

    @gateway.post(
        "/api/replay/checkpoints", response_model=CheckpointEnvelope, tags=["replay"]
    )
    async def replay_checkpoint(bundle: dict[str, Any]) -> CheckpointEnvelope:
        return get_replay_adapter().create_checkpoint(bundle)

    @gateway.get(
        "/api/replay/persistence/inventory",
        response_model=PersistenceInventory,
        tags=["replay"],
    )
    async def replay_persistence_inventory() -> PersistenceInventory:
        return get_replay_adapter().list_sessions()

    from .core_jobs_routes import register_core_jobs_routes

    register_core_jobs_routes(
        gateway, get_chat_store=get_chat_store, get_job_store=get_job_store
    )

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


app = production_app


if __name__ == "__main__":
    import uvicorn

    from app.runtime.net import bind_host

    host = bind_host()
    port = int(environment().get("OMNIX_GATEWAY_PORT", str(DEFAULT_GATEWAY_PORT)))
    uvicorn.run("app.gateway.main:app", host=host, port=port, reload=False)
