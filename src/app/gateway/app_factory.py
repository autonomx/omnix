"""Gateway application composition root."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.assets import SharedAssetStore, default_asset_store
from app.chat import ChatSessionStore, default_chat_store
from app.chat.generation_jobs import recover_abandoned_chat_generation_jobs
from app.jobs import (
    InMemoryModelResidencyStore,
    default_model_residency_store,
)
from app.providers.facade import ProviderFacade, default_provider_facade
from app.replay import RpgReplayPersistenceAdapter, default_rpg_replay_adapter

_LOCAL_BROWSER_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
)


def _install_local_browser_cors(gateway: FastAPI) -> None:
    """Attach local development CORS policy to this gateway instance."""
    gateway.add_middleware(
        CORSMiddleware,
        allow_origins=list(_LOCAL_BROWSER_ORIGINS),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        max_age=86_400,
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
    scheduler_runtime=None,
    runtime_config=None,
    runtime_services=None,
    auth_service=None,
) -> FastAPI:
    from app.runtime.config import get_runtime_config
    from app.runtime.capabilities import RuntimeCapabilities

    runtime_config = runtime_config or get_runtime_config()
    from app.chat.delivery_sync import persist_live_voice_delivery
    from app.live_voice.diagnostics import configure_delivery_checkpoint_recorder

    configure_delivery_checkpoint_recorder(persist_live_voice_delivery)
    if job_store_factory is None:
        from app.runtime_composition import production_job_store

        get_job_store = production_job_store
    else:
        get_job_store = job_store_factory
    from app.jobs.store import install_default_job_store_factory

    install_default_job_store_factory(get_job_store)
    get_provider_facade = provider_facade_factory or default_provider_facade
    get_asset_store = asset_store_factory or default_asset_store
    get_chat_store = chat_store_factory or default_chat_store
    get_replay_adapter = replay_adapter_factory or default_rpg_replay_adapter
    model_residency_store_is_injected = model_residency_store_factory is not None
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
    _install_local_browser_cors(gateway)
    from app.rpg.api.feature_routes import add_rpg_debug_middleware

    add_rpg_debug_middleware(gateway)
    gateway.state.runtime_started = False
    gateway.state.background_runtime = background_runtime
    gateway.state.scheduler_runtime = scheduler_runtime
    gateway.state.runtime_config = runtime_config
    if runtime_services is None:
        from types import SimpleNamespace

        from app.runtime.contracts import KernelServices, LazyServiceProxy

        runtime_services = SimpleNamespace(
            jobs=LazyServiceProxy(get_job_store),
            assets=LazyServiceProxy(get_asset_store),
            chat=LazyServiceProxy(get_chat_store),
            model_residency=LazyServiceProxy(get_model_residency_store),
            database=None,
            tenant=None,
            settings=None,
        )
        runtime_services = cast(KernelServices, runtime_services)
    gateway.state.runtime_services = runtime_services
    gateway.state.runtime_capabilities = RuntimeCapabilities.from_config(runtime_config)
    from .background_runtime import GatewayBackgroundRegistryAdapter
    from .scheduler_runtime import GatewaySchedulerRegistryAdapter

    gateway.state.background_registry = GatewayBackgroundRegistryAdapter(gateway)
    gateway.state.scheduler_registry = GatewaySchedulerRegistryAdapter(gateway)
    gateway.state.feature_lifecycles = []
    from app.platform.runtime_diagnostics import RequestMetrics, RuntimeRequestMiddleware

    gateway.state.runtime_metrics = RequestMetrics()
    from app.observability.tts_stream_diagnostics import runtime_stream_snapshot

    gateway.state.tts_stream_snapshot = runtime_stream_snapshot
    gateway.add_middleware(RuntimeRequestMiddleware, metrics=gateway.state.runtime_metrics)
    from .feature_registry import compose_features
    from app.runtime.net import allowed_origins
    from app.security.request_guard import RequestGuardMiddleware
    from fastapi.middleware.cors import CORSMiddleware

    from app.security.auth import AuthService, AuthenticationMiddleware, resolve_auth_settings

    # Deny by default once OMNIX_AUTH_MODE is explicit (WP-4.1). Without an
    # injected service, every composition resolves the same configuration.
    # Added before CORS so preflights and CORS headers wrap auth rejections.
    gateway.state.auth_service = auth_service or AuthService(resolve_auth_settings())
    gateway.add_middleware(
        AuthenticationMiddleware,
        authenticator_factory=lambda: gateway.state.auth_service,
    )
    gateway.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_credentials=False,
        allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        max_age=86_400,
    )
    gateway.add_middleware(RequestGuardMiddleware)
    compose_features(gateway)

    from app.security.auth import create_auth_router

    gateway.include_router(create_auth_router(lambda: gateway.state.auth_service))

    from .kernel_routes import create_kernel_router

    gateway.include_router(
        create_kernel_router(
            gateway.state,
            readiness_check=readiness_check,
            get_job_store=get_job_store,
            get_provider_facade=get_provider_facade,
            get_asset_store=get_asset_store,
            get_chat_store=get_chat_store,
            get_replay_adapter=get_replay_adapter,
            get_model_residency_store=get_model_residency_store,
            allow_offline_model_residency_store=model_residency_store_is_injected,
        )
    )

    return gateway
