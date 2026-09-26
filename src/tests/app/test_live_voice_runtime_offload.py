from __future__ import annotations

import asyncio
import threading
import time

from fastapi import FastAPI

from app.gateway.live_voice_runtime_offload import (
    CachedTtsProviderResolver,
    DeliveryPersistenceWorker,
)


def test_delivery_persistence_runs_without_blocking_caller() -> None:
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    worker_thread_ids: list[int] = []

    def persist(_details: dict[str, object]) -> None:
        worker_thread_ids.append(threading.get_ident())
        started.set()
        release.wait(1.0)
        finished.set()

    worker = DeliveryPersistenceWorker(persist, max_queue_size=8, log=lambda *_args, **_kwargs: None)
    caller_thread_id = threading.get_ident()
    started_at = time.perf_counter()
    worker.enqueue({"assistant_turn_id": "assistant-turn:test"})
    caller_elapsed = time.perf_counter() - started_at

    assert caller_elapsed < 0.025
    assert started.wait(1.0)
    assert len(worker_thread_ids) == 1
    assert worker_thread_ids[0] != caller_thread_id

    release.set()
    assert finished.wait(1.0)
    worker.stop(timeout=1.0)


def test_cached_provider_returns_immediately_while_refresh_runs() -> None:
    provider = object()
    refresh_finished = threading.Event()
    calls = 0

    def resolve() -> object:
        nonlocal calls
        calls += 1
        time.sleep(0.050)
        if calls >= 2:
            refresh_finished.set()
        return provider

    resolver = CachedTtsProviderResolver(
        resolve,
        active_streams=lambda: {},
        refresh_seconds=0.010,
        log=lambda *_args, **_kwargs: None,
    )
    assert resolver.refresh() is provider
    time.sleep(0.015)

    started_at = time.perf_counter()
    assert resolver.get() is provider
    caller_elapsed = time.perf_counter() - started_at

    assert caller_elapsed < 0.025
    assert refresh_finished.wait(1.0)
    assert calls == 2


def test_first_provider_request_waits_for_background_warmup() -> None:
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    provider = object()
    result: list[object] = []

    def resolve() -> object:
        started.set()
        release.wait(2.0)
        return provider

    resolver = CachedTtsProviderResolver(resolve, log=lambda *_args, **_kwargs: None)
    assert resolver.refresh_in_background()
    assert started.wait(1.0)

    def get_provider() -> None:
        result.append(resolver.get())
        finished.set()

    request = threading.Thread(target=get_provider)
    request.start()
    try:
        assert not finished.wait(0.05)
    finally:
        release.set()
        request.join(timeout=1.0)
    assert finished.is_set()
    assert result == [provider]


def test_cached_provider_defers_refresh_during_active_tts() -> None:
    provider = object()
    calls = 0

    def resolve() -> object:
        nonlocal calls
        calls += 1
        return provider

    resolver = CachedTtsProviderResolver(
        resolve,
        active_streams=lambda: {"stream-1": {"age_ms": 10.0}},
        refresh_seconds=0.001,
        log=lambda *_args, **_kwargs: None,
    )
    assert resolver.refresh() is provider
    time.sleep(0.005)

    assert resolver.get() is provider
    time.sleep(0.025)
    assert calls == 1


def test_provider_monitor_refreshes_after_stream_becomes_idle() -> None:
    provider = object()
    active = True
    refresh_finished = threading.Event()
    calls = 0

    def resolve() -> object:
        nonlocal calls
        calls += 1
        if calls >= 2:
            refresh_finished.set()
        return provider

    def active_streams() -> dict[str, object]:
        return {"stream-1": {}} if active else {}

    resolver = CachedTtsProviderResolver(
        resolve,
        active_streams=active_streams,
        refresh_seconds=0.010,
        log=lambda *_args, **_kwargs: None,
    )
    assert resolver.refresh() is provider
    resolver.start()
    time.sleep(0.030)
    assert calls == 1

    active = False
    assert refresh_finished.wait(1.0)
    resolver.stop(timeout=1.0)
    assert calls >= 2


def test_gateway_startup_does_not_wait_for_tts_provider(monkeypatch) -> None:
    app = FastAPI(title="Omnix Web Gateway")
    resolver = app.state.live_voice_tts_provider_resolver
    started = threading.Event()
    release = threading.Event()
    provider = object()

    def slow_resolve() -> object:
        started.set()
        release.wait(2.0)
        return provider

    monkeypatch.setattr(resolver, "_resolve", slow_resolve)
    startup = next(
        handler for handler in app.router.on_startup
        if handler.__module__ == "app.gateway.live_voice_runtime_offload"
    )

    try:
        started_at = time.perf_counter()
        asyncio.run(startup())
        assert time.perf_counter() - started_at < 0.5
        assert started.wait(1.0)
        assert resolver._provider is None
    finally:
        release.set()
        resolver.stop(timeout=1.0)
