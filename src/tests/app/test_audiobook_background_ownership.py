import asyncio
import threading
from types import SimpleNamespace

import pytest

from app.audiobook import routes
from app.runtime.background import (
    BackgroundOwnershipUnavailable,
    GatewayBackgroundRuntime,
    register_background_worker,
)
from app.runtime.config import GatewayRole, RuntimeConfig
from app.persistence.background_authority import background_execution


def test_api_audiobook_lifecycle_never_initializes_workers(monkeypatch):
    owner = GatewayBackgroundRuntime(object(), "workspace", config=RuntimeConfig(gateway_role=GatewayRole.API))
    monkeypatch.setattr(routes, "_service_and_context", lambda: pytest.fail("API started audiobook work"))
    register_background_worker(owner, routes.create_audiobook_background_worker())
    assert owner.diagnostics()["registered_workers"] == ["audiobook"]
    asyncio.run(owner.startup())
    assert not owner.diagnostics()["started_workers"]


def test_audiobook_threads_inherit_ownership_and_stop_after_revocation(monkeypatch):
    from app.audiobook import worker, assembly_service, export_service, render_service
    from app.persistence.background_authority import require_background_owner

    owner = GatewayBackgroundRuntime(
        object(), "workspace", role="job-worker", execution_scope=background_execution
    )
    live = threading.Event()
    live.set()
    release = threading.Event()
    entered = [threading.Event() for _ in range(3)]
    fenced = [threading.Event() for _ in range(3)]
    calls = []

    def require_live():
        if not live.is_set():
            raise BackgroundOwnershipUnavailable("revoked")

    def poll(index):
        def run(*args, **kwargs):
            require_background_owner()
            calls.append(index)
            entered[index].set()
            assert release.wait(3)
            with pytest.raises(BackgroundOwnershipUnavailable):
                require_background_owner()
            fenced[index].set()
            return True
        return run

    monkeypatch.setattr(owner, "require_live", require_live)
    monkeypatch.setattr(
        routes,
        "_service_and_context",
        lambda: (SimpleNamespace(database=object(), blobs=object()), object()),
    )
    monkeypatch.setattr(worker, "run_ingest_once", poll(0))
    monkeypatch.setattr(render_service, "run_render_once", poll(1))
    monkeypatch.setattr(render_service, "run_preview_once", poll(2))
    monkeypatch.setattr(worker, "run_analyze_once", lambda *a, **k: pytest.fail("unexpected analysis"))
    monkeypatch.setattr(assembly_service, "run_assemble_once", lambda *a, **k: pytest.fail("unexpected assembly"))
    monkeypatch.setattr(export_service, "run_export_once", lambda *a, **k: pytest.fail("unexpected export"))
    register_background_worker(owner, routes.create_audiobook_background_worker())

    async def run():
        await owner.startup()
        try:
            assert all(event.wait(3) for event in entered)
            threads = [thread for thread in threading.enumerate() if thread.name in {
                "audiobook-ingest", "audiobook-render", "audiobook-preview",
            }]
            assert len(threads) == 3
            live.clear()
            release.set()
            for thread in threads:
                await asyncio.to_thread(thread.join, 3)
            assert all(not thread.is_alive() for thread in threads)
            assert all(event.is_set() for event in fenced)
            assert sorted(calls) == [0, 1, 2]
        finally:
            release.set()
            await owner.shutdown()

    asyncio.run(run())
