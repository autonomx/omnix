from __future__ import annotations

import asyncio
import signal
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.runtime.drain import (
    DrainController,
    DrainMiddleware,
    create_draining_server,
    process_drain,
    start_drain_then,
)


@pytest.fixture(autouse=True)
def reset_process_drain():
    process_drain().reset_for_tests()
    yield
    process_drain().reset_for_tests()


def _app(controller: DrainController) -> FastAPI:
    app = FastAPI()
    release = threading.Event()
    app.state.release = release
    app.state.entered = threading.Event()

    @app.get("/slow")
    def slow() -> dict[str, bool]:
        app.state.entered.set()
        assert release.wait(5)
        return {"ok": True}

    @app.get("/ready")
    def ready() -> dict[str, bool]:
        return {"ready": True}

    @app.websocket("/ws")
    async def socket(websocket) -> None:
        await websocket.accept()
        await websocket.close()

    app.add_middleware(DrainMiddleware, controller=controller)
    return app


def test_draining_refuses_new_requests_but_finishes_in_flight_ones() -> None:
    controller = DrainController()
    app = _app(controller)
    client = TestClient(app)
    results: list[int] = []
    worker = threading.Thread(target=lambda: results.append(client.get("/slow").status_code))
    worker.start()
    assert app.state.entered.wait(5)
    assert controller.inflight == 1

    assert controller.begin() is True
    assert controller.begin() is False
    refused = client.get("/slow")
    assert refused.status_code == 503
    assert refused.json() == {"detail": "draining"}
    assert refused.headers["retry-after"] == "1"
    assert refused.headers["connection"] == "close"
    # Probes still answer so the ingress observes readiness.
    assert client.get("/ready").status_code == 200

    assert controller.wait_idle(0.05) is False
    app.state.release.set()
    worker.join(5)
    assert results == [200]
    assert controller.wait_idle(1) is True


def test_draining_closes_new_websockets_with_service_restart() -> None:
    controller = DrainController()
    client = TestClient(_app(controller))
    controller.begin()
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect("/ws"):
            pass
    assert closed.value.code == 1012


def test_drain_stops_the_server_once_idle_or_after_the_window() -> None:
    controller = DrainController()
    stopped = threading.Event()
    thread = start_drain_then(stopped.set, controller, timeout=5)
    assert thread is not None
    assert stopped.wait(1)  # nothing in flight: stop immediately
    assert start_drain_then(stopped.set, controller, timeout=5) is None

    busy = DrainController()
    busy.enter()
    late = threading.Event()
    started = time.monotonic()
    start_drain_then(late.set, busy, timeout=0.2)
    assert late.wait(2)
    assert time.monotonic() - started >= 0.15


def test_minimum_drain_window_keeps_an_idle_process_not_ready() -> None:
    controller = DrainController()
    stopped = threading.Event()
    started = time.monotonic()
    start_drain_then(stopped.set, controller, timeout=5, minimum=0.3)
    assert not stopped.wait(0.1)
    assert stopped.wait(2)
    # Tolerance for coarse (~15 ms) Windows timer resolution.
    assert time.monotonic() - started >= 0.25


def test_first_exit_signal_drains_and_second_falls_through(monkeypatch) -> None:
    import uvicorn

    monkeypatch.setenv("OMNIX_DRAIN_SECONDS", "5")
    server = create_draining_server(uvicorn.Config(FastAPI()))
    process_drain().enter()
    server.handle_exit(signal.SIGTERM, None)
    assert process_drain().draining is True
    assert server.should_exit is False
    process_drain().exit()
    deadline = time.monotonic() + 2
    while not server.should_exit and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.should_exit is True
    # Once exiting, signals fall through to uvicorn: Ctrl+C again forces it.
    server.handle_exit(signal.SIGINT, None)
    assert server.force_exit is True


def test_gateway_readiness_reports_draining_with_build_revision(monkeypatch) -> None:
    from app.config.runtime import RuntimeConfig
    from app.gateway.main import create_gateway_app

    config = RuntimeConfig.from_environment({"OMNIX_SOFTWARE_REVISION": "rev-n1"})
    app = create_gateway_app(runtime_config=config)
    client = TestClient(app, base_url="http://127.0.0.1")
    process_drain().begin()
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"ready": False, "reason": "draining", "build_revision": "rev-n1"}
    refused = client.get("/api/jobs")
    assert refused.status_code == 503
    assert refused.json() == {"detail": "draining"}


def test_drain_middleware_counts_concurrent_async_requests() -> None:
    controller = DrainController()
    app = FastAPI()

    @app.get("/wait")
    async def wait() -> dict[str, int]:
        await asyncio.sleep(0.05)
        return {"inflight": controller.inflight}

    app.add_middleware(DrainMiddleware, controller=controller)
    assert TestClient(app).get("/wait").json() == {"inflight": 1}
    assert controller.inflight == 0
