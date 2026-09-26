"""Process-local production assembly, before importing gateway feature modules."""

from __future__ import annotations

import asyncio
import os
import threading
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GatewayRuntimeServices:
    """Process-owned repositories; requests still open their own transactions."""

    jobs: Any
    assets: Any
    chat: Any
    model_residency: Any


def production_readiness() -> dict:
    from app.persistence.runtime import ensure_postgresql_runtime_ready

    status = ensure_postgresql_runtime_ready(
        auto_initialize_fresh_install=False,
        apply_schema_changes=False,
    )
    required = {
        value.strip()
        for value in os.environ.get("OMNIX_GATEWAY_REQUIRED_WORKERS", "").split(",")
        if value.strip()
    }
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


def create_production_app():
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

    services = GatewayRuntimeServices(
        jobs=default_job_store(),
        assets=default_asset_store(),
        chat=default_chat_store(),
        model_residency=default_model_residency_store(),
    )
    gateway = create_gateway_app(
        job_store_factory=lambda: services.jobs,
        asset_store_factory=lambda: services.assets,
        chat_store_factory=lambda: services.chat,
        model_residency_store_factory=lambda: services.model_residency,
        readiness_check=production_readiness,
    )
    gateway.state.persistence_startup = status
    gateway.state.runtime_services = services
    return gateway


class ProductionApplication:
    """Import-safe ASGI entrypoint; initializes inside the serving process."""

    def __init__(self):
        self._application = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._application is None:
                self._application = create_production_app()
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
