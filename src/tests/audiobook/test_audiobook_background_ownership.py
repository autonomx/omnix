import asyncio
import threading
from types import SimpleNamespace

import pytest

from app.apps.audiobook import routes
from app.runtime.background import (
    BackgroundOwnershipUnavailable,
    GatewayBackgroundRuntime,
    register_background_worker,
)
from app.runtime.config import GatewayRole, RuntimeConfig
from app.persistence.background_authority import background_execution
from app.runtime.tenant_context import current_tenant, pop_tenant, push_tenant, tenant_context


def _tenant(name):
    return tenant_context(user_id="user:ab", workspace_id=f"workspace:{name}",
                          membership_id=f"membership:{name}", roles=["owner"])


def test_service_is_shared_but_the_tenant_follows_each_request(monkeypatch):
    service = object()
    monkeypatch.setattr(routes, "_SERVICE", service)
    seen = []
    for name in ("a", "b", "a"):
        token = push_tenant(_tenant(name))
        try:
            seen.append(routes._service_and_context())
        finally:
            pop_tenant(token)
    assert [found is service for found, _ in seen] == [True, True, True]
    assert [context.workspace_id for _, context in seen] == ["workspace:a", "workspace:b", "workspace:a"]


def test_worker_step_runs_in_each_ready_workspace_under_its_own_tenant(monkeypatch):
    service = SimpleNamespace(database=object(), blobs=object())
    classes_asked = []

    def ready(database, classes):
        classes_asked.append(classes)
        return [_tenant("a"), _tenant("b")]

    monkeypatch.setattr(routes, "_ready_workspace_contexts", ready)
    calls = []

    def step(database, blobs, context, worker_id):
        calls.append((context.workspace_id, current_tenant().workspace_id))
        return context.workspace_id == "workspace:b"

    assert routes._AudiobookWorkers._step_any_workspace(service, step, "w", ("cpu",)) is True
    assert calls == [("workspace:a", "workspace:a"), ("workspace:b", "workspace:b")]
    assert classes_asked == [("cpu",)]

    monkeypatch.setattr(routes, "_ready_workspace_contexts", lambda database, classes: [])
    assert routes._AudiobookWorkers._step_any_workspace(service, step, "w", ("cpu",)) is False


def test_a_failing_workspace_does_not_hold_up_the_others(monkeypatch):
    service = SimpleNamespace(database=object(), blobs=object())
    monkeypatch.setattr(routes, "_ready_workspace_contexts", lambda database, classes: [_tenant("a"), _tenant("b")])

    def step(database, blobs, context, worker_id):
        if context.workspace_id == "workspace:a":
            raise RuntimeError("broken chapter")
        return True

    logged: list = []
    monkeypatch.setattr(routes, "_LOG", SimpleNamespace(warning=lambda *args, **kwargs: logged.append((args, kwargs))))
    assert routes._AudiobookWorkers._step_any_workspace(service, step, "w", ("cpu",)) is True
    # The failure the other workspace's work passed over is logged, not lost.
    assert [args[1] for args, _ in logged] == ["workspace:a"]
    assert "broken chapter" in str(logged[0][1]["exc_info"])

    def only_failures(database, blobs, context, worker_id):
        raise RuntimeError(f"broken in {context.workspace_id}")

    with pytest.raises(RuntimeError, match="workspace:a"):
        routes._AudiobookWorkers._step_any_workspace(service, only_failures, "w", ("cpu",))


def test_api_audiobook_lifecycle_never_initializes_workers(monkeypatch):
    owner = GatewayBackgroundRuntime(object(), "workspace", config=RuntimeConfig(gateway_role=GatewayRole.API))
    monkeypatch.setattr(routes, "_audiobook_service", lambda: pytest.fail("API started audiobook work"))
    register_background_worker(owner, routes.create_audiobook_background_worker())
    assert owner.diagnostics()["registered_workers"] == ["audiobook"]
    asyncio.run(owner.startup())
    assert not owner.diagnostics()["started_workers"]


def test_audiobook_threads_inherit_ownership_and_stop_after_revocation(monkeypatch):
    from app.apps.audiobook import worker, assembly_service, export_service, render_service
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
    monkeypatch.setattr(routes, "_audiobook_service", lambda: SimpleNamespace(database=object(), blobs=object()))
    monkeypatch.setattr(routes, "_ready_workspace_contexts", lambda database, classes: [_tenant("a")])
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
