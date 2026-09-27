"""Process-local production assembly, before importing gateway feature modules."""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from contextlib import asynccontextmanager

from app.runtime_config import RuntimeConfig, get_runtime_config, install_runtime_config
from app.runtime_capabilities import RuntimeCapabilities, RuntimeCapability
from app.runtime_contracts import JobService, AssetService, ChatService, ModelResidencyService


@dataclass(frozen=True, slots=True)
class GatewayRuntimeServices:
    """Process-owned repositories; requests still open their own transactions."""

    jobs: JobService
    assets: AssetService
    chat: ChatService
    model_residency: ModelResidencyService


def production_readiness(config: RuntimeConfig | None = None) -> dict:
    from app.persistence.runtime import ensure_postgresql_runtime_ready

    status = ensure_postgresql_runtime_ready(
        auto_initialize_fresh_install=False,
        apply_schema_changes=False,
    )
    config = config or get_runtime_config()
    required = set(config.required_workers)
    required.update(name for name in ("tts", "stt", "image") if (endpoint := getattr(config, name)) is not None and endpoint.required)
    unavailable = []
    if required:
        from app.gateway.workers import get_worker_health_payload

        workers = {worker.id: worker for worker in get_worker_health_payload().workers}
        unavailable = sorted(
            worker_id
            for worker_id in required
            if worker_id not in workers
            or not workers[worker_id].ok
            or workers[worker_id].mocked
        )
    return {
        "ready": status.ready and status.backend == "postgresql" and not unavailable,
        "backend": status.backend,
        "authority_state": status.authority_state,
        "migrations_pending": list(status.migrations_pending),
        "required_workers_unavailable": unavailable,
    }


def create_production_app(config: RuntimeConfig | None = None):
    config = config or get_runtime_config()
    install_runtime_config(config)
    capabilities = RuntimeCapabilities.from_config(config)
    from app.persistence.startup import bootstrap_status_payload

    status = bootstrap_status_payload()
    if not status["ready"] or status["backend"] != "postgresql":
        raise RuntimeError("Production gateway requires ready PostgreSQL authority")
    from app.live_voice_hardware_policy import install_live_voice_hardware_policy

    install_live_voice_hardware_policy()
    # Resolve adapters after bootstrap, including when a schema exporter or test
    # previously imported the provider-free gateway factory in this process.
    from app.assets import default_asset_store
    from app.chat import default_chat_store
    from app.jobs import default_job_store, default_model_residency_store
    from app.gateway.main import create_gateway_app
    from app.persistence.gateway_runtime import GatewayRuntimeOwner
    from app.chat.generation_jobs import recover_abandoned_chat_generation_jobs
    from app.chat.generation_jobs import _ChatGenerationDispatcher
    from app.gateway.background_runtime import GatewayBackgroundRuntime

    services = GatewayRuntimeServices(
        jobs=default_job_store(),
        assets=default_asset_store(),
        chat=default_chat_store(),
        model_residency=default_model_residency_store(),
    )
    owner = GatewayRuntimeOwner(services.jobs.database, services.jobs.context.workspace_id, config=config)
    services.jobs.chat_execution_owner = owner
    dispatcher = _ChatGenerationDispatcher()
    capabilities.require(RuntimeCapability.RUN_CHAT_DISPATCH)
    services.jobs.chat_dispatcher = dispatcher
    background = GatewayBackgroundRuntime(
        services.jobs.database, services.jobs.context.workspace_id, config=config,
    )
    if capabilities.allows(RuntimeCapability.RUN_RECOVERY):
        from app.persistence.background_authority import background_execution

        def recover():
            with background_execution(background):
                return recover_abandoned_chat_generation_jobs(services.chat, services.jobs)

        owner.recover = recover

    @asynccontextmanager
    async def lifecycle():
        async with owner.lifespan(), background.lifespan():
            try:
                yield
            finally:
                remaining = await asyncio.to_thread(dispatcher.close)
                if remaining:
                    logging.getLogger(__name__).warning(
                        "Chat dispatcher shutdown deadline exceeded: %s workers", remaining
                    )

    def readiness():
        payload = production_readiness(config)
        payload["execution_owner_ready"] = owner.ready()
        payload['background_role'] = background.role
        payload['background_ready'] = background.ready()
        payload["ready"] = payload["ready"] and payload["execution_owner_ready"] and payload['background_ready']
        return payload

    gateway = create_gateway_app(
        job_store_factory=lambda: services.jobs,
        asset_store_factory=lambda: services.assets,
        chat_store_factory=lambda: services.chat,
        model_residency_store_factory=lambda: services.model_residency,
        readiness_check=readiness,
        runtime_lifecycle=lifecycle,
        background_runtime=background,
        runtime_config=config,
    )
    gateway.state.persistence_startup = status
    gateway.state.runtime_services = services
    gateway.state.execution_owner = owner
    gateway.state.runtime_config = config
    gateway.state.runtime_capabilities = capabilities
    return gateway


class ProductionApplication:
    """Import-safe ASGI entrypoint; initializes inside the serving process."""

    def __init__(self, factory=None):
        self._application = None
        self._lock = threading.Lock()
        self._factory = factory

    def _load(self):
        with self._lock:
            if self._application is None:
                self._application = (self._factory or create_production_app)()
            return self._application

    async def __call__(self, scope, receive, send):
        application = self._application
        if application is None:
            try:
                application = await asyncio.to_thread(self._load)
            except Exception:
                from app.persistence.database import close_default_database

                await asyncio.to_thread(close_default_database)
                if scope["type"] == "lifespan":
                    await receive()
                    await send(
                        {
                            "type": "lifespan.startup.failed",
                            "message": "Omnix production initialization failed",
                        }
                    )
                    return
                raise
        try:
            await application(scope, receive, send)
        finally:
            if scope["type"] == "lifespan":
                from app.persistence.database import close_default_database

                await asyncio.to_thread(close_default_database)


app = ProductionApplication()
