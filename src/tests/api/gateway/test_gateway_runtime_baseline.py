"""Production bootstrap, readiness and event-loop regression coverage."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import threading
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient


def test_production_import_does_not_import_gateway_or_contact_database():
    import os
    from pathlib import Path
    import subprocess
    import sys

    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[3]))
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import main, launch, sys; assert main.app is launch.app; "
            "assert 'app.gateway.main' not in sys.modules; "
            "assert 'app.persistence.startup' not in sys.modules",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_production_assembly_bootstraps_before_gateway_composition(monkeypatch):
    from app import production
    from app.persistence import startup
    from app.gateway import main
    from app import live_voice_hardware_policy
    from app import assets, chat, jobs

    calls = []
    stores = [SimpleNamespace() for _ in range(4)]
    monkeypatch.setattr(jobs, "default_job_store", lambda: stores[0])
    monkeypatch.setattr(assets, "default_asset_store", lambda: stores[1])
    monkeypatch.setattr(chat, "default_chat_store", lambda: stores[2])
    monkeypatch.setattr(jobs, "default_model_residency_store", lambda: stores[3])
    monkeypatch.setattr(
        startup,
        "bootstrap_status_payload",
        lambda: calls.append("bootstrap") or {"ready": True, "backend": "postgresql"},
    )
    monkeypatch.setattr(
        live_voice_hardware_policy,
        "install_live_voice_hardware_policy",
        lambda: calls.append("policy"),
    )

    def compose(**kwargs):
        calls.append("compose")
        assert callable(kwargs["job_store_factory"])
        assert (
            kwargs["job_store_factory"]() is kwargs["job_store_factory"]() is stores[0]
        )
        assert (
            kwargs["asset_store_factory"]()
            is kwargs["asset_store_factory"]()
            is stores[1]
        )
        assert kwargs["readiness_check"] is production.production_readiness
        return SimpleNamespace(state=SimpleNamespace())

    monkeypatch.setattr(main, "create_gateway_app", compose)
    gateway = production.create_production_app()
    assert calls == ["bootstrap", "policy", "compose"]
    assert gateway.state.persistence_startup["backend"] == "postgresql"


def test_production_rejects_legacy_backend(monkeypatch):
    from app.production import create_production_app
    from app.persistence import startup

    monkeypatch.setattr(
        startup,
        "bootstrap_status_payload",
        lambda: {"ready": True, "backend": "legacy"},
    )
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        create_production_app()


def test_reload_launcher_defers_bootstrap_to_serving_process(monkeypatch):
    from pathlib import Path
    import runpy
    import sys
    import uvicorn
    from app.persistence import startup

    def forbidden():
        raise AssertionError("reload parent must not bootstrap persistence")

    monkeypatch.setattr(startup, "bootstrap_status_payload", forbidden)
    calls = []
    monkeypatch.setattr(
        uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    monkeypatch.setattr(sys, "argv", ["run_omnix_gateway.py", "--reload"])
    launcher = runpy.run_path(
        str(Path(__file__).resolve().parents[4] / "scripts/run_omnix_gateway.py")
    )
    assert launcher["main"]() == 0
    assert calls[0][0] == ("app.production:app",)
    assert calls[0][1]["reload"] is True


def test_production_application_composes_once_for_concurrent_requests(monkeypatch):
    from app import production

    calls = []

    async def application(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    def compose():
        calls.append(threading.get_ident())
        return application

    monkeypatch.setattr(production, "create_production_app", compose)

    async def run():
        gateway = production.ProductionApplication()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=gateway), base_url="http://test"
        ) as client:
            responses = await asyncio.gather(
                client.get("/health"), client.get("/health")
            )
            assert all(response.status_code == 200 for response in responses)
            assert calls[0] != threading.get_ident()

    asyncio.run(run())
    assert len(calls) == 1


def test_gateway_lifespan_marks_ready_after_hooks_and_clears_on_shutdown(monkeypatch):
    from app.gateway import main

    calls = []

    def recover(chat_store, job_store):
        calls.append(threading.get_ident())
        return 0

    monkeypatch.setattr(main, "recover_abandoned_chat_generation_jobs", recover)
    gateway = main.create_gateway_app(
        chat_store_factory=object,
        job_store_factory=object,
        readiness_check=lambda: {"ready": True},
    )
    # Isolate lifecycle orchestration from real trading and provider workers.
    gateway.router.on_startup.clear()
    gateway.router.on_shutdown.clear()

    async def run():
        async with gateway.router.lifespan_context(gateway):
            assert gateway.state.runtime_started is True
            assert calls[0] != threading.get_ident()
        assert gateway.state.runtime_started is False

    asyncio.run(run())


def test_bootstrap_failure_is_reported_as_failed_lifespan(monkeypatch):
    from app import production
    from app.persistence import database

    def fail():
        raise RuntimeError("secret database credentials")

    monkeypatch.setattr(production, "create_production_app", fail)
    closed = []
    monkeypatch.setattr(database, "close_default_database", lambda: closed.append(True))

    async def run():
        sent = []

        async def receive():
            return {"type": "lifespan.startup"}

        async def send(message):
            sent.append(message)

        await production.ProductionApplication()({"type": "lifespan"}, receive, send)
        return sent

    messages = asyncio.run(run())
    assert messages == [
        {
            "type": "lifespan.startup.failed",
            "message": "Omnix production initialization failed",
        }
    ]
    assert closed == [True]


def test_readiness_is_separate_from_liveness_and_redacts_errors():
    from app.gateway.main import create_gateway_app

    def probe():
        raise RuntimeError("postgresql://user:secret@private-host/db")

    gateway = create_gateway_app(readiness_check=probe)
    client = TestClient(gateway)
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 503
    gateway.state.runtime_started = True
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"ready": False, "reason": "persistence_unavailable"}


def test_ready_probe_reports_status_without_changing_health():
    from app.gateway.main import create_gateway_app

    payload = {"ready": True, "backend": "postgresql"}
    gateway = create_gateway_app(readiness_check=lambda: payload)
    gateway.state.runtime_started = True
    client = TestClient(gateway)
    assert client.get("/ready").json() == payload
    assert client.get("/ready").status_code == 200
    payload["ready"] = False
    assert client.get("/ready").status_code == 503
    assert client.get("/health").status_code == 200


def test_job_read_does_not_block_health():
    from app.gateway.main import create_gateway_app

    entered, release = threading.Event(), threading.Event()

    class Store:
        def get_job(self, job_id):
            entered.set()
            assert release.wait(5)
            return None

    gateway = create_gateway_app(job_store_factory=Store)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=gateway), base_url="http://test"
        ) as client:
            job = asyncio.create_task(client.get("/api/jobs/missing"))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                health = await asyncio.wait_for(client.get("/health"), timeout=1)
                assert health.status_code == 200
                assert not release.is_set()
            finally:
                release.set()
                assert (await job).status_code == 404

    asyncio.run(run())


def test_sse_store_poll_runs_outside_event_loop_thread():
    from app.gateway.main import _live_job_event_stream

    threads = []

    class Store:
        def list_events(self, **kwargs):
            threads.append(threading.get_ident())
            return []

    async def run():
        stream = _live_job_event_stream(Store())
        await anext(stream)
        try:
            assert "heartbeat" in await anext(stream)
            assert threads[0] != threading.get_ident()
        finally:
            await stream.aclose()

    asyncio.run(run())


def test_readiness_does_not_migrate_or_initialize_authority(monkeypatch):
    from app.persistence import runtime

    def forbidden(*args, **kwargs):
        raise AssertionError("readiness must not mutate schema or authority")

    monkeypatch.setattr(
        runtime, "persistence_mode", lambda: runtime.PersistenceMode.POSTGRESQL
    )
    monkeypatch.setattr(runtime, "apply_migrations", forbidden)
    monkeypatch.setattr(runtime, "initialize_fresh_install_authority", forbidden)

    def status(db, **kwargs):
        assert kwargs["initialize_table"] is False
        return {"ok": True, "pending": []}

    monkeypatch.setattr(runtime, "migration_status", status)
    monkeypatch.setattr(runtime, "assert_schema_compatible", lambda status: None)
    monkeypatch.setattr(
        runtime,
        "require_authority_operation",
        lambda *args: SimpleNamespace(
            mode="postgresql", authority_state="postgresql_stabilized"
        ),
    )

    class Database:
        def health(self):
            return {"ok": True}

        @contextmanager
        def connection(self):
            yield self

        transaction = connection

        def execute(self, sql):
            return self

        def fetchone(self):
            return ("postgresql", "1", False, {})

    status = runtime.ensure_postgresql_runtime_ready(
        Database(), auto_initialize_fresh_install=False, apply_schema_changes=False
    )
    assert status.ready


def test_required_worker_failure_and_missing_worker_gate_readiness(monkeypatch):
    from app import production
    from app.persistence import runtime
    from app.gateway import workers

    monkeypatch.setattr(
        runtime,
        "ensure_postgresql_runtime_ready",
        lambda **kwargs: SimpleNamespace(
            ready=True,
            backend="postgresql",
            authority_state="postgresql_stabilized",
            migrations_pending=(),
        ),
    )
    monkeypatch.setenv("OMNIX_GATEWAY_REQUIRED_WORKERS", "tts,stt")
    monkeypatch.setattr(
        workers,
        "get_worker_health_payload",
        lambda: SimpleNamespace(
            workers=[SimpleNamespace(id="tts", ok=True, mocked=True)]
        ),
    )
    assert production.production_readiness()["required_workers_unavailable"] == [
        "stt",
        "tts",
    ]
    monkeypatch.delenv("OMNIX_GATEWAY_REQUIRED_WORKERS")
    assert production.production_readiness()["ready"] is True


def test_worker_health_probes_run_concurrently_and_keep_discovery_order(monkeypatch):
    from app.gateway import workers

    barrier = threading.Barrier(3)
    specs = [
        workers.WorkerSpec(
            id=name, url="http://test", capabilities=(), source_env="TEST"
        )
        for name in ["tts", "stt", "image"]
    ]
    monkeypatch.setattr(workers, "discover_worker_specs", lambda env: specs)

    def probe(spec):
        barrier.wait(timeout=3)
        return workers.WorkerHealth(id=spec.id, ok=True, status="ready")

    monkeypatch.setattr(workers, "probe_worker_health", probe)
    payload = workers.get_worker_health_payload({})
    assert [worker.id for worker in payload.workers] == ["tts", "stt", "image"]
    assert payload.ok
