from __future__ import annotations

import asyncio
import threading
import time

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.gateway.blocking_route_offload import offload_blocking_gateway_routes


def _route(app: FastAPI, path: str) -> APIRoute:
    return next(
        route
        for route in app.routes
        if isinstance(route, APIRoute) and route.path == path
    )


def test_blocking_poll_route_runs_off_event_loop_thread() -> None:
    app = FastAPI()
    entered = threading.Event()
    release = threading.Event()
    worker_thread_ids: list[int] = []

    @app.get("/api/chat/sessions")
    async def chat_sessions() -> dict[str, bool]:
        worker_thread_ids.append(threading.get_ident())
        entered.set()
        release.wait(timeout=1.0)
        return {"ok": True}

    assert offload_blocking_gateway_routes(app) == ["/api/chat/sessions"]
    route = _route(app, "/api/chat/sessions")

    async def exercise() -> None:
        event_loop_thread_id = threading.get_ident()
        safety_release = threading.Timer(0.35, release.set)
        safety_release.start()
        started_at = time.perf_counter()
        try:
            task = asyncio.create_task(route.dependant.call())
            assert await asyncio.to_thread(entered.wait, 0.20)
            await asyncio.sleep(0.02)
            # Without the offload bridge, the event loop cannot reach this
            # assertion until the safety timer releases the blocking handler.
            assert time.perf_counter() - started_at < 0.20
            release.set()
            assert await task == {"ok": True}
            assert worker_thread_ids == [worker_thread_ids[0]]
            assert worker_thread_ids[0] != event_loop_thread_id
        finally:
            release.set()
            safety_release.cancel()

    asyncio.run(exercise())


def test_blocking_chat_generation_post_runs_off_event_loop_thread() -> None:
    app = FastAPI()
    entered = threading.Event()
    release = threading.Event()
    worker_thread_ids: list[int] = []

    @app.post("/api/chat/sessions/{session_id}/messages")
    async def send_chat_message(session_id: str) -> dict[str, str]:
        worker_thread_ids.append(threading.get_ident())
        entered.set()
        release.wait(timeout=1.0)
        return {"session_id": session_id}

    assert offload_blocking_gateway_routes(app) == [
        "/api/chat/sessions/{session_id}/messages"
    ]
    route = _route(app, "/api/chat/sessions/{session_id}/messages")

    async def exercise() -> None:
        event_loop_thread_id = threading.get_ident()
        safety_release = threading.Timer(0.35, release.set)
        safety_release.start()
        started_at = time.perf_counter()
        try:
            task = asyncio.create_task(route.dependant.call(session_id="chat-1"))
            assert await asyncio.to_thread(entered.wait, 0.20)
            await asyncio.sleep(0.02)
            assert time.perf_counter() - started_at < 0.20
            release.set()
            assert await task == {"session_id": "chat-1"}
            assert worker_thread_ids == [worker_thread_ids[0]]
            assert worker_thread_ids[0] != event_loop_thread_id
        finally:
            release.set()
            safety_release.cancel()

    asyncio.run(exercise())


def test_target_path_with_wrong_method_is_not_replaced() -> None:
    app = FastAPI()

    @app.get("/api/chat/sessions/{session_id}/messages")
    async def list_messages(session_id: str) -> dict[str, str]:
        return {"session_id": session_id}

    route = _route(app, "/api/chat/sessions/{session_id}/messages")
    original = route.dependant.call

    assert offload_blocking_gateway_routes(app) == []
    assert route.dependant.call is original


def test_non_target_route_is_not_replaced() -> None:
    app = FastAPI()

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    route = _route(app, "/health")
    original = route.dependant.call

    assert offload_blocking_gateway_routes(app) == []
    assert route.dependant.call is original


def test_offload_is_idempotent() -> None:
    app = FastAPI()

    @app.get("/api/settings")
    async def settings() -> dict[str, bool]:
        return {"ok": True}

    assert offload_blocking_gateway_routes(app) == ["/api/settings"]
    first = _route(app, "/api/settings").dependant.call
    assert offload_blocking_gateway_routes(app) == []
    assert _route(app, "/api/settings").dependant.call is first
