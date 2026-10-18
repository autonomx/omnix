"""Production bootstrap, readiness and event-loop regression coverage."""

from __future__ import annotations

from app.runtime.tenant_context import current_tenant

import asyncio
from contextlib import asynccontextmanager, contextmanager
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
            "assert 'app.composition.gateway.main' not in sys.modules; "
            "assert 'app.persistence.startup' not in sys.modules",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_package_create_app_uses_production_composition(monkeypatch):
    import app
    from app.composition import production

    expected = object()
    monkeypatch.setattr(production, "create_production_app", lambda: expected)
    assert app.create_app() is expected



def test_production_assembly_bootstraps_before_gateway_composition(monkeypatch):
    from app.composition import production
    from app.persistence import startup, database as database_module, identity_service
    from app.composition.gateway import main
    from app.composition import runtime_composition
    from app.platform.live_voice import hardware_policy as live_voice_hardware_policy
    from app import assets, jobs
    from app.security import tenant_context
    from app.settings import access as settings_access
    from app.runtime.config import RuntimeConfig, GatewayRole, get_runtime_config

    config = RuntimeConfig(gateway_role=GatewayRole.API)
    calls = []
    stores = [SimpleNamespace() for _ in range(4)]
    fake_database = object()
    stores[0].database = fake_database
    stores[0].context = SimpleNamespace(
        workspace_id="test-workspace", user_id="test-user"
    )
    def production_job_store_factory(
        *, database, context, chat_execution_owner, chat_dispatcher
    ):
        assert database is fake_database
        # Request-serving stores follow each request's tenant (WP-4.2); the
        # runtime owner stays on the process tenant.
        assert context is None
        assert chat_execution_owner.workspace_id == current_tenant().workspace_id
        assert chat_execution_owner.database is fake_database
        assert chat_dispatcher is not None
        return stores[0]

    monkeypatch.setattr(runtime_composition, "production_job_store", production_job_store_factory)
    monkeypatch.setattr(assets, "default_asset_store", lambda: stores[1])

    def production_chat_store_factory(*, job_service, live_agent_planner):
        assert job_service is stores[0]
        assert live_agent_planner is not None
        return stores[2]

    monkeypatch.setattr(runtime_composition, "production_chat_store", production_chat_store_factory)
    monkeypatch.setattr(jobs, "default_model_residency_store", lambda: stores[3])
    monkeypatch.setattr(runtime_composition, "production_model_residency_store", lambda: stores[3])
    monkeypatch.setattr(database_module, "default_database", lambda: fake_database)
    monkeypatch.setattr(
        identity_service,
        "ensure_local_identity",
        lambda _database: stores[0].context,
    )
    monkeypatch.setattr(
        tenant_context,
        "install_process_tenant",
        lambda context: calls.append(("tenant", context.workspace_id)),
    )
    monkeypatch.setattr(
        settings_access,
        "install_settings_service",
        lambda _service: calls.append("settings"),
    )
    def bootstrap():
        calls.append("bootstrap")
        tenant = identity_service.ensure_local_identity(fake_database)
        tenant_context.install_process_tenant(tenant)
        return {"ready": True, "backend": "postgresql"}

    monkeypatch.setattr(startup, "bootstrap_status_payload", bootstrap)
    monkeypatch.setattr(
        live_voice_hardware_policy,
        "apply_live_voice_process_defaults",
        lambda: calls.append("policy"),
    )

    def compose(**kwargs):
        calls.append("compose")
        assert callable(kwargs["job_store_factory"])
        assert kwargs["job_store_factory"]() is stores[0]
        assert kwargs["asset_store_factory"]() is stores[1]
        assert callable(kwargs["readiness_check"])
        assert callable(kwargs["runtime_lifecycle"])
        assert kwargs["background_runtime"].database is stores[0].database
        assert kwargs["background_runtime"].config is config
        assert kwargs["runtime_config"] is config
        assert kwargs["runtime_services"].database is fake_database
        assert get_runtime_config() is config
        return SimpleNamespace(
            state=SimpleNamespace(
                background_runtime=kwargs["background_runtime"],
                job_handler_registry=object(),
            )
        )

    from app.persistence import device_permits

    permit_databases = []
    monkeypatch.setattr(
        device_permits,
        "configure_default_device_permit_service",
        lambda database, **_kwargs: permit_databases.append(database),
    )
    monkeypatch.setattr(main, "create_gateway_app", compose)
    gateway = production.create_production_app(config)
    assert permit_databases == [fake_database]
    assert calls[:4] == [
        "bootstrap",
        ("tenant", "test-workspace"),
        "settings",
        "policy",
    ]
    assert "compose" in calls
    assert not hasattr(gateway.state, "durable_feature_job_worker")
    assert gateway.state.persistence_startup["backend"] == "postgresql"
    assert gateway.state.runtime_config is config


def test_production_rejects_legacy_backend(monkeypatch):
    from app.composition.production import create_production_app
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
    import secrets
    import sys
    import uvicorn
    from app.persistence import startup

    def forbidden():
        raise AssertionError("reload parent must not bootstrap persistence")

    monkeypatch.setattr(startup, "bootstrap_status_payload", forbidden)
    calls = []
    # Runtime launch inherits an explicit ephemeral token; never access the
    # operator's protected credential store from this bootstrap unit test.
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", secrets.token_urlsafe(32))
    run_token_key = secrets.token_urlsafe(32)
    monkeypatch.setenv("OMNIX_RUN_TOKEN_KEY", run_token_key)
    monkeypatch.setattr(
        uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    monkeypatch.setattr(sys, "argv", ["run_omnix_gateway.py", "--reload", "--api-replicas", "0"])
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[4] / "scripts"))
    launcher = runpy.run_path(
        str(Path(__file__).resolve().parents[4] / "scripts/run_omnix_gateway.py")
    )
    import logging

    from app.observability import logging as omnix_logging

    root = logging.getLogger()
    before = list(root.handlers)
    try:
        assert launcher["main"]() == 0
        # The container entrypoint installs the structured log handler.
        assert any(getattr(h, omnix_logging._HANDLER_MARKER, False) for h in root.handlers)
    finally:
        for handler in list(root.handlers):
            if handler not in before:
                root.removeHandler(handler)
    assert calls[0][0] == ("app.composition.production:app",)
    assert calls[0][1]["reload"] is True
    import os

    assert os.environ["OMNIX_RUN_TOKEN_KEY"] == run_token_key


def test_production_application_composes_once_for_concurrent_requests(monkeypatch):
    from app.composition import production

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
            transport=httpx.ASGITransport(app=gateway), base_url="http://127.0.0.1",
            headers={"X-Omnix-Client": "test"},
        ) as client:
            responses = await asyncio.gather(
                client.get("/health"), client.get("/health")
            )
            assert all(response.status_code == 200 for response in responses)
            assert calls[0] != threading.get_ident()

    asyncio.run(run())
    assert len(calls) == 1


def test_gateway_lifespan_marks_ready_after_hooks_and_clears_on_shutdown(monkeypatch):
    from app.composition.gateway import main
    from app.composition.gateway import app_factory

    calls = []
    lifecycle = []

    @asynccontextmanager
    async def owner_lifespan():
        lifecycle.append('register')
        try:
            yield
        finally:
            assert gateway.state.runtime_started is False
            lifecycle.append('stop')

    def recover(chat_store, job_store):
        assert lifecycle == ['register']
        lifecycle.append('recover')
        calls.append(threading.get_ident())
        return 0

    monkeypatch.setattr(app_factory, "recover_abandoned_chat_generation_jobs", recover)
    gateway = main.create_gateway_app(
        chat_store_factory=object,
        job_store_factory=object,
        readiness_check=lambda: {"ready": True},
        runtime_lifecycle=owner_lifespan,
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
    assert lifecycle == ['register', 'recover', 'stop']


def test_bootstrap_failure_is_reported_as_failed_lifespan(monkeypatch):
    from app.composition import production
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
    from app.composition.gateway.main import create_gateway_app

    def probe():
        raise RuntimeError("postgresql://user:secret@private-host/db")

    gateway = create_gateway_app(readiness_check=probe)
    client = TestClient(gateway, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 503
    gateway.state.runtime_started = True
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"ready": False, "reason": "persistence_unavailable"}


def test_ready_probe_reports_status_without_changing_health():
    from app.composition.gateway.main import create_gateway_app

    payload = {"ready": True, "backend": "postgresql"}
    gateway = create_gateway_app(readiness_check=lambda: payload)
    gateway.state.runtime_started = True
    client = TestClient(gateway, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})
    assert client.get("/ready").json() == payload
    assert client.get("/ready").status_code == 200
    payload["ready"] = False
    assert client.get("/ready").status_code == 503
    assert client.get("/health").status_code == 200


def test_job_read_does_not_block_health():
    from app.composition.gateway.main import create_gateway_app

    entered, release = threading.Event(), threading.Event()

    class Store:
        def get_job(self, job_id):
            entered.set()
            assert release.wait(5)
            return None

    gateway = create_gateway_app(job_store_factory=Store)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=gateway), base_url="http://127.0.0.1",
            headers={"X-Omnix-Client": "test"},
        ) as client:
            # FastAPI builds its route state on the first request; warm it so
            # the timing below measures the blocking job read, not cold start.
            assert (await client.get("/health")).status_code == 200
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
    from app.composition.gateway.kernel_routes.live_event_stream import resilient_live_job_event_stream

    threads = []

    class Store:
        def list_events(self, **kwargs):
            threads.append(threading.get_ident())
            return []

    async def run():
        stream = resilient_live_job_event_stream(Store())
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
    from app.composition import production
    from app.persistence import runtime
    from app.runtime import worker_health as workers

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
    from app.runtime import worker_health as workers

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


def test_request_paths_do_not_apply_migrations_or_bootstrap_identity(
    monkeypatch, tmp_path
):
    from app.persistence import identity_service, migrations

    def forbidden(*_args, **_kwargs):
        raise AssertionError("request paths must not migrate or bootstrap identity")

    monkeypatch.setattr(migrations, "apply_migrations", forbidden)
    monkeypatch.setattr(identity_service, "ensure_local_identity", forbidden)
    monkeypatch.setattr("app.persistence.apply_migrations", forbidden)

    from app.apps.rpg.edge.api.feature_routes import rpg_world_library_routes
    from app.apps.rpg.session import service as rpg_session_service

    monkeypatch.setattr(
        rpg_world_library_routes,
        "read_world_library",
        lambda **_kwargs: {
            "ok": True,
            "worlds": [],
            "scenarios": [],
            "campaigns": [],
            "generation_runs": [],
        },
    )
    monkeypatch.setattr(rpg_session_service, "load_session", lambda _session_id: None)

    from app.platform.characters import feature as character_feature
    from app.platform.characters.models import CharacterListResponse

    original_register_character_routes = character_feature.register_character_routes

    def register_test_character_routes(router):
        original_register_character_routes(
            router,
            service_factory=lambda: SimpleNamespace(
                list=lambda **_kwargs: CharacterListResponse(characters=[])
            ),
        )

    monkeypatch.setattr(
        character_feature, "register_character_routes", register_test_character_routes
    )

    from app.composition.gateway.main import create_gateway_app
    from fastapi.testclient import TestClient

    client = TestClient(
        create_gateway_app(),
        base_url="http://127.0.0.1:5173",
        headers={"X-Omnix-Client": "test"},
    )

    turn = client.post(
        "/api/rpg/sessions/missing-session/turn",
        json={"command": "look around"},
    )
    world_library = client.get("/api/rpg/world-library")
    prompt = client.post(
        "/api/prompts/render",
        json={
            "template": {
                "id": "chat.reply",
                "version": "v1",
                "module": "chat",
                "text": "Reply to {message}.",
            },
            "variables": {"message": "hello"},
        },
    )
    characters = client.get("/api/characters")

    assert turn.status_code == 404
    assert world_library.status_code == 200
    assert prompt.status_code == 200
    assert prompt.json()["rendered_text"] == "Reply to hello."
    assert characters.status_code == 200
    assert characters.json()["characters"] == []


def test_disabled_features_are_not_imported():
    """Composing without RPG and trading imports neither module (WP-7.7).

    Only their kernel-only declarations may load, with the package that holds
    them: the settings profile reads every module's section, enabled or not (PA-2.1).
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    src = Path(__file__).resolve().parents[3]
    script = (
        "import sys\n"
        "from app.config.runtime import RuntimeConfig\n"
        "from app.composition.gateway.main import create_gateway_app\n"
        "create_gateway_app(runtime_config=RuntimeConfig(disabled_features=('rpg', 'trading', 'hermes')))\n"
        "declarations = {'app.apps.rpg', 'app.apps.rpg.declarations', 'app.apps.trading', 'app.apps.trading.declarations'}\n"
        # The kernel replay routes load RPG's replay adapter whatever is enabled (as app.replay did before PA-5.3).
        "replay = ('app.apps.rpg.edge', 'app.apps.rpg.edge.replay', 'app.apps.rpg.edge.replay.models', 'app.apps.rpg.edge.replay.rpg_adapter')\n"
        "loaded = sorted(m for m in sys.modules if m.startswith(('app.apps.rpg', 'app.apps.trading'))\n"
        "                and m not in declarations and m not in replay)\n"
        "print(len(loaded), loaded[:5])\n"
    )
    environment = {**os.environ, "PYTHONPATH": str(src), "OMNIX_ALLOWED_HOSTS": "localhost"}
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=src, env=environment, capture_output=True, text=True, timeout=180
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip().splitlines()[-1] == "0 []"
